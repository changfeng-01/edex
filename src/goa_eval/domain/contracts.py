from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CircuitDomain:
    topology_family: str = "unknown"
    technology_family: str = "unknown"
    supply_v: float | None = None
    clock_period_s: float | None = None
    load_capacitance_f: float | None = None
    role_signature: tuple[str, ...] = ()
    process_family: str = "unknown"

    @classmethod
    def from_mapping(cls, value: object) -> "CircuitDomain":
        if not isinstance(value, dict):
            return cls()
        roles = value.get("role_signature", ())
        return cls(
            topology_family=str(value.get("topology_family", "unknown")),
            technology_family=str(value.get("technology_family", "unknown")),
            supply_v=_optional_float(value.get("supply_v")),
            clock_period_s=_optional_float(value.get("clock_period_s")),
            load_capacitance_f=_optional_float(value.get("load_capacitance_f")),
            role_signature=tuple(str(role) for role in roles) if isinstance(roles, (list, tuple)) else (),
            process_family=str(value.get("process_family", "unknown")),
        )


@dataclass(frozen=True)
class CanonicalAction:
    role: str
    parameter: str
    operation: str
    magnitude: float


@dataclass(frozen=True)
class DecodedAction:
    column: str
    value: float
    unclipped_value: float
    clipped: bool
    status: str


@dataclass(frozen=True)
class DomainDistance:
    total: float
    topology: float
    technology: float
    operating_scale: float
    role_mismatch: float
    missing_fraction: float


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
