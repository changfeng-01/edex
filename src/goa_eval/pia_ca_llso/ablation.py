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
    if ablation == "capm_only":
        _set_enabled(config, "classifier_level_hybrid", False)
        _set_enabled(config, "adaptive_capm", False)
        _set_enabled(config, "repair_candidates", False)
        _set_enabled(config, "evaluation_scheduler", False)
        return config, "pia_capm_distance"
    raise ValueError(f"Unknown PIA validation ablation: {ablation}")


def _set_enabled(config: dict, key: str, enabled: bool) -> None:
    config.setdefault(key, {})["enabled"] = enabled
