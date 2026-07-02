"""Validation protocol schema for PIA-CA-LLSO Phase 3 experiments."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Mapping

import yaml

from goa_eval.pia_ca_llso.method_registry import FORMAL_ABLATIONS, FORMAL_METHODS


MINIMUM_METHODS = {
    "random",
    "ca_llso_raw_distance",
    "pia_physics_distance",
    "pia_capm_distance",
    "adaptive_pia_capm",
    "classifier_level_hybrid",
    "active_uncertainty_diversity",
    "active_influence_on_demand",
    "literature_ensemble_hybrid",
    "sklearn_surrogate_baseline",
    "pia_evolve_full",
}
MINIMUM_ABLATIONS = {
    "full",
    "no_classifier",
    "no_adaptive_capm",
    "no_constraint_repair",
    "no_llso_offspring",
    "no_evaluation_scheduler",
    "no_influence_graph",
    "no_on_demand_constraint",
    "no_transfer_trust",
    "capm_only",
}
REQUIRED_METHODS = set(FORMAL_METHODS)
REQUIRED_ABLATIONS = set(FORMAL_ABLATIONS)
BOUNDARY = {
    "data_source": "real_simulation_csv",
    "engineering_validity": "simulation_only",
    "must_resimulate": True,
}


@dataclass(frozen=True)
class ValidationRunSpec:
    scenario_id: str
    method: str
    ablation: str
    seed: int
    budget: int
    target_score: float


def load_validation_protocol(path: str | Path) -> dict[str, Any]:
    protocol_path = Path(path)
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8")) or {}
    validate_protocol(protocol)
    return protocol


def validate_protocol(protocol: Mapping[str, Any]) -> None:
    required_keys = [
        "primary_outcome",
        "target_score",
        "budgets",
        "seeds",
        "methods",
        "ablations",
        "scenarios",
        "boundary",
    ]
    missing = [key for key in required_keys if key not in protocol]
    if missing:
        raise ValueError(f"validation protocol missing required fields: {', '.join(missing)}")
    if protocol["primary_outcome"] != "simulations_to_target":
        raise ValueError("primary_outcome must be simulations_to_target")
    if protocol.get("validation_profile") == "formal":
        _require_values("methods", protocol["methods"], REQUIRED_METHODS)
        _require_values("ablations", protocol["ablations"], REQUIRED_ABLATIONS)
    else:
        _require_values("methods", protocol["methods"], MINIMUM_METHODS)
        _require_values("ablations", protocol["ablations"], MINIMUM_ABLATIONS)
    _require_formal_defaults(protocol)
    for field, expected in BOUNDARY.items():
        actual = protocol["boundary"].get(field)
        if actual != expected:
            raise ValueError(f"boundary.{field} must be {expected}")
    if not protocol["scenarios"]:
        raise ValueError("validation protocol requires at least one scenario")


def expand_validation_grid(protocol: Mapping[str, Any]) -> list[ValidationRunSpec]:
    validate_protocol(protocol)
    specs: list[ValidationRunSpec] = []
    scenarios = protocol["scenarios"]
    for scenario, method, ablation, seed, budget in product(
        scenarios,
        protocol["methods"],
        protocol["ablations"],
        protocol["seeds"],
        protocol["budgets"],
    ):
        scenario_id = scenario["scenario_id"] if isinstance(scenario, Mapping) else str(scenario)
        specs.append(
            ValidationRunSpec(
                scenario_id=str(scenario_id),
                method=str(method),
                ablation=str(ablation),
                seed=int(seed),
                budget=int(budget),
                target_score=float(protocol["target_score"]),
            )
        )
    return specs


def _require_values(name: str, values: Any, required: set[str]) -> None:
    present = {str(value) for value in values or []}
    missing = sorted(required - present)
    if missing:
        raise ValueError(f"{name} missing required values: {', '.join(missing)}")


def _require_formal_defaults(protocol: Mapping[str, Any]) -> None:
    if protocol.get("validation_profile") != "formal":
        return
    expected_budgets = [10, 20, 50, 100, 200]
    budgets = [int(value) for value in protocol.get("budgets", [])]
    if budgets != expected_budgets:
        raise ValueError(f"formal validation budgets must be {expected_budgets}")
    if len(protocol.get("seeds", [])) < 20:
        raise ValueError("formal validation requires at least 20 seeds")
