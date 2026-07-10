from __future__ import annotations

import json

import pandas as pd

from goa_eval.pia_ca_llso.selector import _history_pass_rate, select_candidates


def test_history_pass_rate_parses_false_string() -> None:
    history = pd.DataFrame({"hard_constraint_passed": ["false", "no", "0"]})

    assert _history_pass_rate(history) == 0.0


def test_selector_returns_top_k_with_candidate_roles() -> None:
    history = pd.DataFrame(
        [{"sample_id": "h1", "pullup_w_l": 80.0, "level_label": "L1", "overall_score": 92, "hard_constraint_passed": True}]
    )
    candidates = pd.DataFrame(
        [
            {"candidate_id": f"c{i}", "pullup_w_l": 80.0 + i, "p_l1": 0.9 - i * 0.1, "p_hard_pass": 0.8, "predicted_score": 80 - i}
            for i in range(6)
        ]
    )

    result = select_candidates(candidates, history, strategy="pia_physics_distance", top_k=4)

    assert len(result.selected_candidates) == 4
    assert set(result.selected_candidates["candidate_role"]).issuperset({"exploitation_best", "l1_center"})


def test_capm_selector_ranks_without_model_prediction_columns() -> None:
    history = pd.DataFrame(
        [
            {
                "sample_id": "h1",
                "level_label": "L1",
                "cboot_cload_ratio": 1.2,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 0.4,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 2.5,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            }
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "risky",
                "cboot_cload_ratio": 1.2,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 3.5,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 0.05,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            },
            {
                "candidate_id": "safe",
                "cboot_cload_ratio": 1.15,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 0.45,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 2.4,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            },
        ]
    )

    result = select_candidates(candidates, history, strategy="pia_capm_distance", top_k=2)

    assert result.selected_candidates.iloc[0]["candidate_id"] == "safe"
    assert result.model_report["strategy"] == "pia_capm_distance"
    assert result.explanation_report["claim_boundary"] == "next-run simulation suggestions"
    assert "capm_distance_to_l1" in result.all_candidates.columns
    assert "p_l1" not in result.all_candidates.columns


def test_capm_selector_uses_configured_constraint_thresholds() -> None:
    history = pd.DataFrame(
        [
            {
                "sample_id": "h1",
                "level_label": "L1",
                "cboot_cload_ratio": 1.2,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 0.4,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 2.5,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            }
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "relaxed_by_config",
                "cboot_cload_ratio": 1.2,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 3.5,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 0.05,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            }
        ]
    )

    result = select_candidates(
        candidates,
        history,
        strategy="pia_capm_distance",
        top_k=1,
        config={"capm_distance": {"max_ron_pullup_cload_proxy": 4.0, "min_vgh_vth_margin": 0.01}},
    )

    assert result.all_candidates.iloc[0]["capm_hard_risk_passed"] is True


def test_capm_diversity_uses_capm_distance() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1",
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "c1",
            "cboot_cload_ratio": 1.1, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.5, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.3, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "candidate_id": "c2",
            "cboot_cload_ratio": 1.15, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
    ])

    result = select_candidates(candidates, history, strategy="pia_capm_distance", top_k=2)
    assert "diversity_score" in result.all_candidates.columns
    for score in result.all_candidates["diversity_score"]:
        assert 0.0 <= float(score) <= 1.0


def test_physics_distance_diversity_backward_compatible() -> None:
    history = pd.DataFrame([
        {"sample_id": "h1", "pullup_w_l": 80.0, "level_label": "L1", "overall_score": 92, "hard_constraint_passed": True}
    ])
    candidates = pd.DataFrame([
        {"candidate_id": f"c{i}", "pullup_w_l": 80.0 + i, "p_l1": 0.9 - i * 0.1, "p_hard_pass": 0.8, "predicted_score": 80 - i}
        for i in range(4)
    ])

    result = select_candidates(candidates, history, strategy="pia_physics_distance", top_k=4)
    assert "diversity_score" in result.all_candidates.columns


def test_adaptive_capm_strategy_is_registered_and_preserves_baseline() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 92, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h2", "level_label": "L4", "overall_score": 20, "hard_constraint_passed": False,
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 3.0, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "safe",
            "cboot_cload_ratio": 1.15, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "candidate_id": "risky",
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 3.0, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
    ])

    baseline = select_candidates(candidates, history, strategy="pia_capm_distance", top_k=2)
    adaptive = select_candidates(candidates, history, strategy="adaptive_pia_capm", top_k=2)

    assert baseline.model_report["strategy"] == "pia_capm_distance"
    assert adaptive.model_report["strategy"] == "adaptive_pia_capm"
    assert adaptive.selected_candidates.iloc[0]["candidate_id"] == "safe"
    assert adaptive.selected_candidates["diagnostic_status"].eq("adaptive_capm_from_history").all()
    assert "adaptive_capm_weights_json" in adaptive.all_candidates.columns
    assert "adaptive_acquisition_weights_json" in adaptive.all_candidates.columns


def test_adaptive_capm_learns_feature_weights_from_history() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h2", "level_label": "L1", "overall_score": 90, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.1, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.2, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h3", "level_label": "L4", "overall_score": 25, "hard_constraint_passed": False,
            "cboot_cload_ratio": 1.1, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 3.2, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.1, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h4", "level_label": "L4", "overall_score": 30, "hard_constraint_passed": False,
            "cboot_cload_ratio": 1.0, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 3.5, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.0, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "c1",
            "cboot_cload_ratio": 1.1, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.6, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.0, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])

    result = select_candidates(candidates, history, strategy="adaptive_pia_capm", top_k=1)
    weights = json.loads(result.all_candidates.loc[0, "adaptive_capm_weights_json"])

    assert weights["ron_pullup_cload_proxy"] > weights["vgl_off_margin"]
    assert json.loads(result.all_candidates.loc[0, "adaptive_acquisition_weights_json"])["distance"] > 0


def test_classifier_level_hybrid_uses_level_classifier_predictions() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h2", "level_label": "L4", "overall_score": 20, "hard_constraint_passed": False,
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 3.5, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 2.0, "clk_slew_proxy": 1.5,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "predicted_l4",
            "p_l1": 0.05, "p_hard_pass": 0.10, "predicted_score": 20.0, "predicted_level": "L4",
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 3.5, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 2.0, "clk_slew_proxy": 1.5,
        },
        {
            "candidate_id": "predicted_l1",
            "p_l1": 0.95, "p_hard_pass": 0.90, "predicted_score": 90.0, "predicted_level": "L1",
            "cboot_cload_ratio": 1.15, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
    ])

    result = select_candidates(candidates, history, strategy="classifier_level_hybrid", top_k=2)

    assert result.selected_candidates.iloc[0]["candidate_id"] == "predicted_l1"
    assert result.selected_candidates["diagnostic_status"].eq("classifier_level_hybrid").all()
    assert "classifier_hybrid_score" in result.all_candidates.columns
    assert "classifier_components_json" in result.all_candidates.columns
    assert json.loads(result.all_candidates.iloc[0]["classifier_components_json"])["p_l1"] >= 0.0


def test_classifier_level_hybrid_falls_back_when_training_data_is_insufficient() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 90, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "fallback",
            "cboot_cload_ratio": 1.1, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.5, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.3, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])

    result = select_candidates(candidates, history, strategy="classifier_level_hybrid", top_k=1)

    assert result.selected_candidates.loc[0, "model_status"] == "insufficient_data"
    assert result.selected_candidates.loc[0, "predicted_level"] == "L2"
    assert result.selected_candidates.loc[0, "diagnostic_status"] == "classifier_level_hybrid"


def test_sklearn_surrogate_baseline_ranks_without_result_leakage() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h2", "level_label": "L2", "overall_score": 82, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.0, "pullup_pulldown_ratio": 1.2,
            "ron_pullup_cload_proxy": 0.8, "ron_pulldown_cload_proxy": 0.7,
            "vgh_vth_margin": 2.0, "vgl_off_margin": 1.7, "clk_slew_proxy": 0.8,
        },
        {
            "sample_id": "h3", "level_label": "L4", "overall_score": 25, "hard_constraint_passed": False,
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 2.0,
            "ron_pullup_cload_proxy": 3.5, "ron_pulldown_cload_proxy": 3.2,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 0.2, "clk_slew_proxy": 1.8,
        },
        {
            "sample_id": "h4", "level_label": "L3", "overall_score": 55, "hard_constraint_passed": False,
            "cboot_cload_ratio": 0.6, "pullup_pulldown_ratio": 1.8,
            "ron_pullup_cload_proxy": 2.0, "ron_pulldown_cload_proxy": 1.8,
            "vgh_vth_margin": 1.0, "vgl_off_margin": 0.7, "clk_slew_proxy": 1.2,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "safe",
            "overall_score": 1.0,
            "hard_constraint_passed": False,
            "cboot_cload_ratio": 1.18, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.45,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.55,
        },
        {
            "candidate_id": "leaky_high_score",
            "overall_score": 999.0,
            "hard_constraint_passed": True,
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 2.0,
            "ron_pullup_cload_proxy": 3.5, "ron_pulldown_cload_proxy": 3.2,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 0.2, "clk_slew_proxy": 1.8,
        },
    ])

    result = select_candidates(candidates, history, strategy="sklearn_surrogate_baseline", top_k=2)

    assert result.model_report["surrogate_model_status"] in {"ok", "insufficient_data"}
    assert result.selected_candidates.iloc[0]["candidate_id"] == "safe"
    assert result.selected_candidates["diagnostic_status"].eq("sklearn_surrogate_baseline").all()
    assert "acquisition_score" in result.all_candidates.columns
    assert "candidate_role" in result.selected_candidates.columns
    assert "overall_score" not in result.all_candidates.columns
    assert "hard_constraint_passed" not in result.all_candidates.columns


def test_literature_ensemble_hybrid_exposes_paper_component_scores() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h2", "level_label": "L2", "overall_score": 78, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.1, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.7, "ron_pulldown_cload_proxy": 0.5,
            "vgh_vth_margin": 2.1, "vgl_off_margin": 1.8, "clk_slew_proxy": 0.7,
        },
        {
            "sample_id": "h3", "level_label": "L4", "overall_score": 25, "hard_constraint_passed": False,
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 2.5,
            "ron_pullup_cload_proxy": 3.4, "ron_pulldown_cload_proxy": 3.2,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 0.1, "clk_slew_proxy": 1.8,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "paper_safe",
            "p_l1": 0.92, "p_hard_pass": 0.88, "predicted_score": 93.0, "predicted_level": "L1",
            "uncertainty": 0.12, "model_status": "ok",
            "cboot_cload_ratio": 1.18, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.45,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.55,
        },
        {
            "candidate_id": "paper_boundary",
            "p_l1": 0.55, "p_hard_pass": 0.58, "predicted_score": 82.0, "predicted_level": "L2",
            "uncertainty": 0.45, "model_status": "ok",
            "cboot_cload_ratio": 1.0, "pullup_pulldown_ratio": 1.2,
            "ron_pullup_cload_proxy": 0.9, "ron_pulldown_cload_proxy": 0.8,
            "vgh_vth_margin": 1.8, "vgl_off_margin": 1.6, "clk_slew_proxy": 0.8,
        },
    ])

    result = select_candidates(candidates, history, strategy="literature_ensemble_hybrid", top_k=2)

    assert result.selected_candidates.iloc[0]["candidate_id"] == "paper_safe"
    assert result.explanation_report["data_source"] == "real_simulation_csv"
    assert result.explanation_report["engineering_validity"] == "simulation_only"
    assert result.explanation_report["must_resimulate"] is True
    for column in [
        "deaoe_on_demand_priority",
        "hrcea_rectification_score",
        "aiea_influence_score",
        "cesaea_relaxed_vote_score",
        "eccoea_asaa_weighted_score",
        "literature_ensemble_score",
    ]:
        assert column in result.all_candidates.columns
    components = json.loads(result.all_candidates.iloc[0]["literature_components_json"])
    assert set(components["weights"]) == {"deaoe", "hrcea", "aiea", "cesaea", "eccoea_asaa"}
    assert result.model_report["paper_lineage"][0].startswith("DEAOE")


def test_active_uncertainty_diversity_prefers_uncertain_candidate_when_base_scores_are_close() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "sample_id": "h2", "level_label": "L4", "overall_score": 20, "hard_constraint_passed": False,
            "cboot_cload_ratio": 0.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 3.5, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 0.05, "vgl_off_margin": 2.0, "clk_slew_proxy": 1.5,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "slightly_safe",
            "p_l1": 0.82, "p_hard_pass": 0.82, "predicted_score": 84.0, "predicted_level": "L1",
            "uncertainty": 0.05, "model_status": "ok",
            "cboot_cload_ratio": 1.16, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
        {
            "candidate_id": "uncertain_boundary",
            "p_l1": 0.80, "p_hard_pass": 0.80, "predicted_score": 82.0, "predicted_level": "L1",
            "uncertainty": 0.95, "model_status": "ok",
            "level_entropy_uncertainty": 0.9, "hard_pass_entropy_uncertainty": 0.9,
            "predicted_score_tree_std": 8.0, "score_tree_std_uncertainty": 1.0,
            "cboot_cload_ratio": 1.15, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.46, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.35, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        },
    ])

    result = select_candidates(candidates, history, strategy="active_uncertainty_diversity", top_k=1)

    assert result.selected_candidates.iloc[0]["candidate_id"] == "uncertain_boundary"
    assert result.selected_candidates.iloc[0]["diagnostic_status"] == "active_uncertainty_diversity"
    for column in [
        "active_acquisition_score",
        "active_uncertainty_score",
        "batch_diversity_score",
        "active_components_json",
        "selection_step",
    ]:
        assert column in result.all_candidates.columns
    components = json.loads(result.selected_candidates.iloc[0]["active_components_json"])
    assert components["uncertainty"] > 0.9


def test_active_uncertainty_diversity_uses_greedy_batch_diversity() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.0, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    common = {
        "p_l1": 0.85, "p_hard_pass": 0.85, "predicted_score": 85.0,
        "predicted_level": "L1", "uncertainty": 0.4, "model_status": "ok",
        "pullup_pulldown_ratio": 1.0, "ron_pulldown_cload_proxy": 0.4,
        "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
    }
    candidates = pd.DataFrame([
        {"candidate_id": "near_a", **common, "cboot_cload_ratio": 1.05, "ron_pullup_cload_proxy": 0.45},
        {"candidate_id": "near_b", **common, "cboot_cload_ratio": 1.06, "ron_pullup_cload_proxy": 0.46},
        {"candidate_id": "far", **common, "cboot_cload_ratio": 1.8, "ron_pullup_cload_proxy": 0.9},
    ])

    result = select_candidates(candidates, history, strategy="active_uncertainty_diversity", top_k=2)

    assert "far" in set(result.selected_candidates["candidate_id"])
    assert result.selected_candidates["selection_step"].tolist() == [1, 2]
    far = result.selected_candidates[result.selected_candidates["candidate_id"] == "far"].iloc[0]
    assert float(far["batch_diversity_score"]) > 0.0


def test_active_uncertainty_diversity_falls_back_when_classifier_is_disabled() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "fallback",
            "cboot_cload_ratio": 1.15, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])

    result = select_candidates(
        candidates,
        history,
        strategy="active_uncertainty_diversity",
        top_k=1,
        config={"classifier_level_hybrid": {"enabled": False}},
    )

    assert result.selected_candidates.iloc[0]["candidate_id"] == "fallback"
    assert result.selected_candidates.iloc[0]["model_status"] == "classifier_disabled"
    assert result.selected_candidates.iloc[0]["active_uncertainty_score"] == 0.5


def test_active_influence_on_demand_prefers_influential_candidate_when_base_scores_are_close() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.0, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    common = {
        "p_l1": 0.82, "p_hard_pass": 0.82, "predicted_score": 84.0,
        "predicted_level": "L1", "model_status": "ok",
        "pullup_pulldown_ratio": 1.0, "ron_pulldown_cload_proxy": 0.4,
        "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
    }
    candidates = pd.DataFrame([
        {"candidate_id": "hub", **common, "uncertainty": 0.20, "cboot_cload_ratio": 1.05, "ron_pullup_cload_proxy": 0.45},
        {"candidate_id": "near_uncertain_a", **common, "p_l1": 0.30, "p_hard_pass": 0.35, "predicted_score": 20.0, "uncertainty": 0.55, "cboot_cload_ratio": 1.06, "ron_pullup_cload_proxy": 0.46},
        {"candidate_id": "near_uncertain_b", **common, "p_l1": 0.30, "p_hard_pass": 0.35, "predicted_score": 20.0, "uncertainty": 0.55, "cboot_cload_ratio": 1.07, "ron_pullup_cload_proxy": 0.47},
        {"candidate_id": "isolated", **common, "uncertainty": 0.20, "cboot_cload_ratio": 1.75, "ron_pullup_cload_proxy": 0.85},
    ])

    result = select_candidates(candidates, history, strategy="active_influence_on_demand", top_k=1)

    selected = result.selected_candidates.iloc[0]
    assert selected["candidate_id"] == "hub"
    assert selected["diagnostic_status"] == "active_influence_on_demand"
    for column in [
        "active_influence_on_demand_score",
        "influence_gain_score",
        "constraint_urgency_score",
        "transfer_trust_score",
        "on_demand_eval_priority",
        "aiod_components_json",
    ]:
        assert column in result.all_candidates.columns
    components = json.loads(selected["aiod_components_json"])
    assert components["influence_gain"] > 0.5
    assert result.model_report["active_lineage"][0].startswith("active_uncertainty_diversity")


def test_active_influence_on_demand_prioritizes_constraint_urgency_when_base_scores_are_close() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.0, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    common = {
        "predicted_level": "L1",
        "uncertainty": 0.55, "model_status": "ok",
        "cboot_cload_ratio": 1.05, "pullup_pulldown_ratio": 1.0,
        "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
        "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
    }
    candidates = pd.DataFrame([
        {"candidate_id": "safe_clear", **common, "p_l1": 0.82, "predicted_score": 80.0, "p_hard_pass": 0.70},
        {"candidate_id": "constraint_boundary", **common, "p_l1": 0.98, "predicted_score": 98.0, "p_hard_pass": 0.55},
    ])

    result = select_candidates(candidates, history, strategy="active_influence_on_demand", top_k=1)

    selected = result.selected_candidates.iloc[0]
    assert selected["candidate_id"] == "constraint_boundary"
    safe = result.all_candidates[result.all_candidates["candidate_id"] == "safe_clear"].iloc[0]
    assert float(selected["constraint_urgency_score"]) > float(safe["constraint_urgency_score"])
    assert bool(selected["must_resimulate"]) is True
    assert selected["data_source"] == "real_simulation_csv"
    assert selected["engineering_validity"] == "simulation_only"


def test_active_influence_on_demand_uses_greedy_batch_diversity() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.0, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    common = {
        "p_l1": 0.85, "p_hard_pass": 0.85, "predicted_score": 85.0,
        "predicted_level": "L1", "uncertainty": 0.4, "model_status": "ok",
        "pullup_pulldown_ratio": 1.0, "ron_pulldown_cload_proxy": 0.4,
        "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
    }
    candidates = pd.DataFrame([
        {"candidate_id": "near_a", **common, "cboot_cload_ratio": 1.05, "ron_pullup_cload_proxy": 0.45},
        {"candidate_id": "near_b", **common, "cboot_cload_ratio": 1.06, "ron_pullup_cload_proxy": 0.46},
        {"candidate_id": "far", **common, "cboot_cload_ratio": 1.8, "ron_pullup_cload_proxy": 0.9},
    ])

    result = select_candidates(candidates, history, strategy="active_influence_on_demand", top_k=2)

    assert "far" in set(result.selected_candidates["candidate_id"])
    assert result.selected_candidates["selection_step"].tolist() == [1, 2]
    far = result.selected_candidates[result.selected_candidates["candidate_id"] == "far"].iloc[0]
    assert float(far["batch_diversity_score"]) > 0.0


def test_active_influence_on_demand_falls_back_when_classifier_is_disabled() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True,
            "cboot_cload_ratio": 1.2, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.4, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.5, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "fallback",
            "cboot_cload_ratio": 1.15, "pullup_pulldown_ratio": 1.0,
            "ron_pullup_cload_proxy": 0.45, "ron_pulldown_cload_proxy": 0.4,
            "vgh_vth_margin": 2.4, "vgl_off_margin": 2.0, "clk_slew_proxy": 0.5,
        }
    ])

    result = select_candidates(
        candidates,
        history,
        strategy="active_influence_on_demand",
        top_k=1,
        config={"classifier_level_hybrid": {"enabled": False}},
    )

    selected = result.selected_candidates.iloc[0]
    assert selected["candidate_id"] == "fallback"
    assert selected["model_status"] == "classifier_disabled"
    assert selected["active_uncertainty_score"] == 0.5
    assert "aiod_components_json" in result.all_candidates.columns
