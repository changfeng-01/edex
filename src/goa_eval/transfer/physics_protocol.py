from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol


EFFECT_STATUSES = frozenset({"supported", "not_applicable", "missing", "proxy"})


@dataclass(frozen=True)
class LocalElectricalState:
    scenario_key: str
    values_si: Mapping[str, float | None]
    feature_status: Mapping[str, str]
    model_status: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BarrierResult:
    value: float
    status: str
    violations: tuple[str, ...] = ()
    scenario_key: str = "nominal"
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["violations"] = list(self.violations)
        return payload


@dataclass(frozen=True)
class PhysicalEffect:
    status: str
    value: float | None = None
    uncertainty: float | None = None

    def __post_init__(self) -> None:
        if self.status not in EFFECT_STATUSES:
            raise ValueError(f"unsupported physical effect status: {self.status}")
        if self.status in {"missing", "not_applicable"} and self.value is not None:
            raise ValueError(f"{self.status} effects must not carry a numeric value")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhysicalEffectPacket:
    source_agent: str
    source_profile: str
    model_version: str
    scenario_key: str
    effects: Mapping[str, PhysicalEffect]
    raw_si: Mapping[str, float | None] = field(default_factory=dict)
    applicability: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "circuitpilot.physical-effect.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_agent": self.source_agent,
            "source_profile": self.source_profile,
            "model_version": self.model_version,
            "scenario_key": self.scenario_key,
            "effects": {name: effect.as_dict() for name, effect in self.effects.items()},
            "raw_si": dict(self.raw_si),
            "applicability": dict(self.applicability),
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PhysicalEffectPacket":
        effects = {
            str(name): effect
            if isinstance(effect, PhysicalEffect)
            else PhysicalEffect(
                status=str(effect.get("status", "missing")),
                value=effect.get("value"),
                uncertainty=effect.get("uncertainty"),
            )
            for name, effect in dict(value.get("effects", {})).items()
        }
        return cls(
            source_agent=str(value.get("source_agent", "unknown")),
            source_profile=str(value.get("source_profile", "unknown")),
            model_version=str(value.get("model_version", "unknown")),
            scenario_key=str(value.get("scenario_key", "nominal")),
            effects=effects,
            raw_si=dict(value.get("raw_si", {})),
            applicability=dict(value.get("applicability", {})),
            evidence=dict(value.get("evidence", {})),
            schema_version=str(value.get("schema_version", "circuitpilot.physical-effect.v1")),
        )


@dataclass(frozen=True)
class SensitivityArtifact:
    profile: str
    physics_version: str
    task_head_version: str
    scenario_jacobians: Mapping[str, Mapping[str, Mapping[str, float]]]
    normalized_uncertainty: Mapping[str, float] = field(default_factory=dict)
    evidence_status: str = "analytic_model_proxy"
    baseline_id: str = ""
    corner_set: tuple[str, ...] = ()
    schema_version: str = "circuitpilot.sensitivity.v1"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["corner_set"] = list(self.corner_set)
        return payload

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SensitivityArtifact":
        return cls(
            profile=str(value.get("profile", "unknown")),
            physics_version=str(value.get("physics_version", "unknown")),
            task_head_version=str(value.get("task_head_version", "unknown")),
            scenario_jacobians=dict(value.get("scenario_jacobians", {})),
            normalized_uncertainty=dict(value.get("normalized_uncertainty", {})),
            evidence_status=str(value.get("evidence_status", "analytic_model_proxy")),
            baseline_id=str(value.get("baseline_id", "")),
            corner_set=tuple(value.get("corner_set", ())),
            schema_version=str(value.get("schema_version", "circuitpilot.sensitivity.v1")),
        )


class DomainPhysicsAdapter(Protocol):
    def extract_local_state(
        self, row: Mapping[str, Any], scenario: Mapping[str, Any], profile: Mapping[str, Any]
    ) -> LocalElectricalState: ...

    def evaluate_barrier(self, state: LocalElectricalState, task_head: Any) -> BarrierResult: ...

    def to_canonical_effects(
        self, state: LocalElectricalState, baseline: LocalElectricalState
    ) -> PhysicalEffectPacket: ...

    def estimate_sensitivity(
        self, calibration: Any, operating_point: Mapping[str, Any]
    ) -> SensitivityArtifact: ...

    def project_effect(
        self,
        packet: PhysicalEffectPacket,
        sensitivity: SensitivityArtifact,
        parameter_profile: Any,
    ) -> Any: ...
