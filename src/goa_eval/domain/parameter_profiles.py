from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


PARAMETER_KINDS = frozenset({"design", "environment", "model", "parasitic", "variation", "derived"})
MAPPING_FIDELITY_ORDER = {"exact": 0, "validated": 1, "proxy": 2, "unknown": 3}
PARAMETER_GROUP_CONSTRAINTS = frozenset({"keep_ratio", "must_change_together", "tradeoff_coupled"})


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    column: str
    role: str
    property: str
    kind: str = "design"
    unit: str = ""
    optimizable: bool = False
    lower_bound: float | None = None
    upper_bound: float | None = None
    quantization: float | None = None
    group: str = ""
    mapping_fidelity: str = "unknown"

    @property
    def canonical_key(self) -> str:
        return f"{self.role}.{self.property}"

    @classmethod
    def from_mapping(cls, name: str, value: Mapping[str, Any]) -> "ParameterSpec":
        bounds = value.get("bounds")
        lower = upper = None
        if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
            lower, upper = float(bounds[0]), float(bounds[1])
            if lower > upper:
                raise ValueError(f"parameter {name} has reversed bounds")
        kind = str(value.get("kind", "design")).strip().lower()
        if kind not in PARAMETER_KINDS:
            raise ValueError(f"parameter {name} has unsupported kind: {kind}")
        fidelity = str(value.get("mapping_fidelity", "unknown")).strip().lower()
        if fidelity not in MAPPING_FIDELITY_ORDER:
            raise ValueError(f"parameter {name} has unsupported mapping_fidelity: {fidelity}")
        quantization = value.get("quantization")
        quantization_value = float(quantization) if quantization is not None else None
        if quantization_value is not None and quantization_value <= 0.0:
            raise ValueError(f"parameter {name} quantization must be positive")
        return cls(
            name=str(name),
            column=str(value.get("column", name)),
            role=str(value.get("role", "unknown")),
            property=str(value.get("property", name)),
            kind=kind,
            unit=str(value.get("unit", "")),
            optimizable=bool(value.get("optimizable", kind == "design")),
            lower_bound=lower,
            upper_bound=upper,
            quantization=quantization_value,
            group=str(value.get("group", "")),
            mapping_fidelity=fidelity,
        )


@dataclass(frozen=True)
class ParameterGroupSpec:
    name: str
    constraint: str

    @classmethod
    def from_mapping(cls, name: str, value: Mapping[str, Any]) -> "ParameterGroupSpec":
        constraint = str(value.get("constraint", "")).strip().lower()
        if constraint not in PARAMETER_GROUP_CONSTRAINTS:
            raise ValueError(f"parameter group {name} has unsupported constraint: {constraint}")
        return cls(name=str(name), constraint=constraint)


@dataclass(frozen=True)
class CircuitParameterProfile:
    name: str
    task_type: str
    parameters: tuple[ParameterSpec, ...]
    parameter_groups: tuple[ParameterGroupSpec, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CircuitParameterProfile":
        raw_parameters = value.get("parameters", {})
        if not isinstance(raw_parameters, Mapping):
            raise ValueError("parameter profile parameters must be a mapping")
        parameters = tuple(
            ParameterSpec.from_mapping(str(name), config)
            for name, config in raw_parameters.items()
            if isinstance(config, Mapping)
        )
        columns = [parameter.column for parameter in parameters]
        if len(columns) != len(set(columns)):
            raise ValueError("parameter profile contains duplicate local columns")
        raw_groups = value.get("parameter_groups", {})
        if not isinstance(raw_groups, Mapping):
            raise ValueError("parameter profile parameter_groups must be a mapping")
        parameter_groups = tuple(
            ParameterGroupSpec.from_mapping(str(name), config)
            for name, config in raw_groups.items()
            if isinstance(config, Mapping)
        )
        declared_groups = {group.name for group in parameter_groups}
        missing_groups = sorted(
            {parameter.group for parameter in parameters if parameter.group} - declared_groups
        )
        if missing_groups and raw_groups:
            raise ValueError(
                "parameter profile references undeclared parameter groups: "
                + ", ".join(missing_groups)
            )
        return cls(
            name=str(value.get("name", "unknown")),
            task_type=str(value.get("task_type", "unknown")),
            parameters=parameters,
            parameter_groups=parameter_groups,
        )

    @classmethod
    def from_circuit_profile(cls, profile: Mapping[str, Any]) -> "CircuitParameterProfile":
        """Read circuit-local parameter bindings from a circuit profile."""

        raw = profile.get("parameter_profile", {})
        if not isinstance(raw, Mapping):
            raise ValueError("circuit profile parameter_profile must be a mapping")
        adapted = dict(raw)
        adapted.setdefault("name", profile.get("name", "unknown"))
        adapted.setdefault("task_type", profile.get("type", "unknown"))
        return cls.from_mapping(adapted)

    @property
    def optimizable_parameters(self) -> tuple[ParameterSpec, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.optimizable and parameter.kind == "design")

    @property
    def parameters_by_kind(self) -> dict[str, tuple[ParameterSpec, ...]]:
        return {
            kind: tuple(parameter for parameter in self.parameters if parameter.kind == kind)
            for kind in sorted(PARAMETER_KINDS)
            if any(parameter.kind == kind for parameter in self.parameters)
        }

    @property
    def group_constraints(self) -> dict[str, str]:
        return {group.name: group.constraint for group in self.parameter_groups}


@dataclass(frozen=True)
class ParameterProfileAudit:
    status: str
    declared_count: int
    present_count: int
    optimizable_count: int
    present_optimizable_count: int
    declared_coverage: float
    optimizable_coverage: float
    missing_columns: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "declared_count": self.declared_count,
            "present_count": self.present_count,
            "optimizable_count": self.optimizable_count,
            "present_optimizable_count": self.present_optimizable_count,
            "declared_coverage": self.declared_coverage,
            "optimizable_coverage": self.optimizable_coverage,
            "missing_columns": list(self.missing_columns),
        }


@dataclass(frozen=True)
class ParameterUpdate:
    column: str
    value: float
    unclipped_value: float
    clipped: bool
    canonical_key: str


@dataclass(frozen=True)
class DecodedActionSet:
    canonical_key: str
    updates: tuple[ParameterUpdate, ...]
    status: str
    mapping_fidelity: str


def audit_parameter_profile(row: Mapping[str, Any], profile: CircuitParameterProfile) -> ParameterProfileAudit:
    present = [parameter for parameter in profile.parameters if _finite(row.get(parameter.column))]
    optimizable = profile.optimizable_parameters
    present_optimizable = [parameter for parameter in optimizable if _finite(row.get(parameter.column))]
    missing = tuple(parameter.column for parameter in profile.parameters if parameter not in present)
    missing_specs = [parameter for parameter in profile.parameters if parameter not in present]
    if not missing_specs:
        status = "complete"
    elif all(parameter.kind in {"model", "parasitic"} for parameter in missing_specs):
        status = "incomplete_model_inputs"
    elif any(parameter.optimizable for parameter in missing_specs):
        status = "incomplete_design_parameters"
    else:
        status = "incomplete_parameter_inputs"
    return ParameterProfileAudit(
        status=status,
        declared_count=len(profile.parameters),
        present_count=len(present),
        optimizable_count=len(optimizable),
        present_optimizable_count=len(present_optimizable),
        declared_coverage=len(present) / max(len(profile.parameters), 1),
        optimizable_coverage=len(present_optimizable) / max(len(optimizable), 1),
        missing_columns=missing,
    )


def decode_action_set(
    action: Any,
    profile: CircuitParameterProfile,
    row: Mapping[str, Any],
) -> DecodedActionSet:
    canonical_key = f"{action.role}.{action.parameter}"
    matched = [parameter for parameter in profile.parameters if parameter.canonical_key == canonical_key]
    if not matched:
        return DecodedActionSet(canonical_key, (), "unsupported", "unknown")
    optimizable = [parameter for parameter in matched if parameter.optimizable and parameter.kind == "design"]
    if not optimizable:
        return DecodedActionSet(canonical_key, (), "not_optimizable", _worst_fidelity(matched))
    if any(not _finite(row.get(parameter.column)) for parameter in optimizable):
        return DecodedActionSet(canonical_key, (), "missing_local_parameters", _worst_fidelity(optimizable))
    updates: list[ParameterUpdate] = []
    for parameter in optimizable:
        current = float(row[parameter.column])
        if action.operation == "log_scale":
            proposed = current * math.exp(float(action.magnitude))
        elif action.operation == "add":
            proposed = current + float(action.magnitude)
        elif action.operation == "set":
            proposed = float(action.magnitude)
        else:
            return DecodedActionSet(canonical_key, (), "unsupported_operation", _worst_fidelity(optimizable))
        value = project_parameter_value(parameter, proposed)
        updates.append(
            ParameterUpdate(
                column=parameter.column,
                value=value,
                unclipped_value=proposed,
                clipped=not math.isclose(value, proposed, rel_tol=1.0e-12, abs_tol=1.0e-12),
                canonical_key=canonical_key,
            )
        )
    return DecodedActionSet(
        canonical_key=canonical_key,
        updates=tuple(updates),
        status="one_to_many" if len(updates) > 1 else "exact",
        mapping_fidelity=_worst_fidelity(optimizable),
    )


def project_parameter_value(parameter: ParameterSpec, proposed: float) -> float:
    value = float(proposed)
    if parameter.lower_bound is not None:
        value = max(value, parameter.lower_bound)
    if parameter.upper_bound is not None:
        value = min(value, parameter.upper_bound)
    if parameter.quantization is not None:
        origin = parameter.lower_bound or 0.0
        value = origin + round((value - origin) / parameter.quantization) * parameter.quantization
        if parameter.lower_bound is not None:
            value = max(value, parameter.lower_bound)
        if parameter.upper_bound is not None:
            value = min(value, parameter.upper_bound)
    return float(value)


def _worst_fidelity(parameters: list[ParameterSpec]) -> str:
    return max(parameters, key=lambda parameter: MAPPING_FIDELITY_ORDER[parameter.mapping_fidelity]).mapping_fidelity


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
