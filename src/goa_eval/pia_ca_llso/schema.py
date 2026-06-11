from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ParameterSpec:
    name: str
    lower: float | int | str | None = None
    upper: float | int | str | None = None
    scale: str = "linear"
    unit: str = ""
    description: str = ""
    group: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParameterSpec":
        return cls(**data)


@dataclass
class ProblemSpec:
    problem_name: str
    parameter_specs: list[ParameterSpec] = field(default_factory=list)
    objective_names: list[str] = field(default_factory=list)
    constraint_specs: dict[str, Any] = field(default_factory=dict)
    physics_feature_config: dict[str, Any] = field(default_factory=dict)
    score_config: dict[str, Any] = field(default_factory=dict)
    target_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["parameter_specs"] = [spec.to_dict() for spec in self.parameter_specs]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemSpec":
        payload = dict(data)
        payload["parameter_specs"] = [
            item if isinstance(item, ParameterSpec) else ParameterSpec.from_dict(item)
            for item in payload.get("parameter_specs", [])
        ]
        return cls(**payload)


@dataclass
class SimulationRecord:
    sample_id: str
    params: dict[str, float]
    metrics: dict[str, float]
    status: str
    hard_pass: bool
    constraint_violation: float = 0.0
    score: float | None = None
    level_label: str | None = None
    source: str = "imported"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulationRecord":
        return cls(**data)


@dataclass
class Candidate:
    candidate_id: str
    params: dict[str, float]
    source: str = "imported"
    predicted_level: str | None = None
    p_l1: float | None = None
    p_hard_pass: float | None = None
    predicted_score: float | None = None
    uncertainty: float | None = None
    raw_distance_to_l1: float | None = None
    physics_distance_to_l1: float | None = None
    latent_distance_to_l1: float | None = None
    attention_l1_mass: float | None = None
    acquisition_score: float | None = None
    selected_rank: int | None = None
    candidate_role: str | None = None
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        return cls(**data)


@dataclass
class SelectionResult:
    selected_candidates: Any
    all_candidates: Any
    model_report: dict[str, Any] = field(default_factory=dict)
    feature_report: dict[str, Any] = field(default_factory=dict)
    explanation_report: dict[str, Any] = field(default_factory=dict)
