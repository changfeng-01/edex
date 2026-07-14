from __future__ import annotations

from goa_eval.pia_ca_llso.ablation import build_ablation_config


def _base_config() -> dict:
    return {
        "adaptive_capm": {"enabled": True},
        "classifier_level_hybrid": {"enabled": True},
        "repair_candidates": {"enabled": True},
        "llso_offspring": {"enabled": True},
        "evaluation_scheduler": {"enabled": True},
        "evolution_loop": {"offspring_per_generation": 8},
    }


def test_ablation_no_classifier_uses_adaptive_capm_strategy() -> None:
    config, strategy = build_ablation_config(_base_config(), "no_classifier")

    assert strategy == "adaptive_pia_capm"
    assert config["classifier_level_hybrid"]["enabled"] is False


def test_ablation_no_constraint_repair_disables_repair_candidates() -> None:
    config, strategy = build_ablation_config(_base_config(), "no_constraint_repair")

    assert strategy == "classifier_level_hybrid"
    assert config["repair_candidates"]["enabled"] is False


def test_ablation_no_llso_offspring_uses_seed_candidates_only() -> None:
    config, strategy = build_ablation_config(_base_config(), "no_llso_offspring")

    assert strategy == "classifier_level_hybrid"
    assert config["llso_offspring"]["enabled"] is False
    assert config["evolution_loop"]["offspring_per_generation"] == 0


def test_ablation_no_scheduler_disables_evaluation_scheduler() -> None:
    config, strategy = build_ablation_config(_base_config(), "no_evaluation_scheduler")

    assert strategy == "classifier_level_hybrid"
    assert config["evaluation_scheduler"]["enabled"] is False


def test_active_influence_on_demand_component_ablations_disable_components() -> None:
    influence_config, _ = build_ablation_config(_base_config(), "no_influence_graph")
    constraint_config, _ = build_ablation_config(_base_config(), "no_on_demand_constraint")
    transfer_config, _ = build_ablation_config(_base_config(), "no_transfer_trust")

    assert influence_config["active_influence_on_demand"]["influence_graph_enabled"] is False
    assert constraint_config["active_influence_on_demand"]["on_demand_constraint_enabled"] is False
    assert transfer_config["active_influence_on_demand"]["transfer_trust_enabled"] is False


def test_ablation_capm_only_uses_pia_capm_distance_and_disables_adaptive_parts() -> None:
    config, strategy = build_ablation_config(_base_config(), "capm_only")

    assert strategy == "pia_capm_distance"
    assert config["classifier_level_hybrid"]["enabled"] is False
    assert config["adaptive_capm"]["enabled"] is False
    assert config["repair_candidates"]["enabled"] is False
    assert config["evaluation_scheduler"]["enabled"] is False


def test_capm_v2_component_ablations_set_distance_flags() -> None:
    normalization, _ = build_ablation_config(_base_config(), "no_capm_normalization")
    softmin, _ = build_ablation_config(_base_config(), "no_capm_softmin")
    electrical, _ = build_ablation_config(_base_config(), "no_capm_electrical_features")

    assert normalization["capm_distance"]["normalization_enabled"] is False
    assert softmin["capm_distance"]["l1_aggregation"] == "nearest"
    assert electrical["physics_features"]["electrical_features_enabled"] is False
