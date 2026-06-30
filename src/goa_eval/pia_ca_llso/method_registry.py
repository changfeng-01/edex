"""Formal validation method registry for PIA-CA-LLSO."""
from __future__ import annotations

from typing import Any


FORMAL_METHODS = (
    "random",
    "ca_llso_raw_distance",
    "pia_physics_distance",
    "pia_capm_distance",
    "adaptive_pia_capm",
    "sklearn_surrogate_baseline",
    "literature_ensemble_hybrid",
    "paper_ca_llso",
    "paper_adaptive_constraint_eval",
    "paper_distributed_multi_constraint",
    "classifier_level_hybrid",
    "pia_evolve_full",
)

FORMAL_ABLATIONS = (
    "full",
    "no_classifier",
    "no_adaptive_capm",
    "no_constraint_repair",
    "no_llso_offspring",
    "no_evaluation_scheduler",
    "capm_only",
    "no_capm_barrier",
    "no_capm_geodesic",
    "no_capm_coupling",
    "no_missing_penalty",
)

PAIRWISE_BASELINES = (
    "random",
    "ca_llso_raw_distance",
    "paper_ca_llso",
    "sklearn_surrogate_baseline",
)

METHOD_REGISTRY: dict[str, dict[str, Any]] = {
    "random": {"category": "weak_baseline", "uses_pia_ablation": False},
    "ca_llso_raw_distance": {"category": "same_family_baseline", "uses_pia_ablation": False},
    "pia_physics_distance": {"category": "physics_baseline", "uses_pia_ablation": False},
    "pia_capm_distance": {"category": "pia_distance_baseline", "uses_pia_ablation": True},
    "adaptive_pia_capm": {"category": "pia_intermediate", "uses_pia_ablation": True},
    "sklearn_surrogate_baseline": {"category": "surrogate_baseline", "uses_pia_ablation": False},
    "literature_ensemble_hybrid": {"category": "literature_baseline", "uses_pia_ablation": False},
    "paper_ca_llso": {"category": "paper_inspired_baseline", "uses_pia_ablation": False},
    "paper_adaptive_constraint_eval": {"category": "paper_inspired_baseline", "uses_pia_ablation": False},
    "paper_distributed_multi_constraint": {"category": "paper_inspired_baseline", "uses_pia_ablation": False},
    "classifier_level_hybrid": {"category": "pia_main_single_step", "uses_pia_ablation": True},
    "pia_evolve_full": {"category": "pia_closed_loop", "uses_pia_ablation": True},
}


def method_registry_records() -> list[dict[str, Any]]:
    records = []
    for name in FORMAL_METHODS:
        meta = METHOD_REGISTRY[name]
        records.append(
            {
                "method": name,
                "category": meta["category"],
                "uses_pia_ablation": bool(meta["uses_pia_ablation"]),
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        )
    return records


def method_uses_pia_ablation(method: str) -> bool:
    return bool(METHOD_REGISTRY.get(method, {}).get("uses_pia_ablation", False))
