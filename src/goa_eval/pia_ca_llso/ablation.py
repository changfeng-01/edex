"""Ablation configuration builder for Phase 3 validation experiments."""
from __future__ import annotations

from copy import deepcopy


def build_ablation_config(base_config: dict, ablation: str) -> tuple[dict, str]:
    config = deepcopy(base_config)
    strategy = "classifier_level_hybrid"

    if ablation == "full":
        return config, strategy
    if ablation == "no_classifier":
        _set_enabled(config, "classifier_level_hybrid", False)
        return config, "adaptive_pia_capm"
    if ablation == "no_adaptive_capm":
        _set_enabled(config, "adaptive_capm", False)
        return config, strategy
    if ablation == "no_constraint_repair":
        _set_enabled(config, "repair_candidates", False)
        return config, strategy
    if ablation == "no_llso_offspring":
        _set_enabled(config, "llso_offspring", False)
        config.setdefault("evolution_loop", {})["offspring_per_generation"] = 0
        return config, strategy
    if ablation == "no_evaluation_scheduler":
        _set_enabled(config, "evaluation_scheduler", False)
        return config, strategy
    if ablation == "no_influence_graph":
        config.setdefault("active_influence_on_demand", {})["influence_graph_enabled"] = False
        return config, strategy
    if ablation == "no_on_demand_constraint":
        config.setdefault("active_influence_on_demand", {})["on_demand_constraint_enabled"] = False
        return config, strategy
    if ablation == "no_transfer_trust":
        config.setdefault("active_influence_on_demand", {})["transfer_trust_enabled"] = False
        return config, strategy
    if ablation == "capm_only":
        _set_enabled(config, "classifier_level_hybrid", False)
        _set_enabled(config, "adaptive_capm", False)
        _set_enabled(config, "repair_candidates", False)
        _set_enabled(config, "evaluation_scheduler", False)
        return config, "pia_capm_distance"
    if ablation == "no_capm_barrier":
        config.setdefault("capm_distance", {})["barrier_enabled"] = False
        return config, strategy
    if ablation == "no_capm_geodesic":
        config.setdefault("capm_distance", {})["geodesic_enabled"] = False
        return config, strategy
    if ablation == "no_capm_coupling":
        config.setdefault("capm_distance", {})["coupling_enabled"] = False
        return config, strategy
    if ablation == "no_missing_penalty":
        config.setdefault("capm_distance", {})["missing_penalty_enabled"] = False
        return config, strategy
    raise ValueError(f"Unknown PIA validation ablation: {ablation}")


def _set_enabled(config: dict, key: str, enabled: bool) -> None:
    config.setdefault(key, {})["enabled"] = enabled
