from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.selector import select_candidates


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
