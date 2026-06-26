from __future__ import annotations

import json

import pandas as pd

from goa_eval.pia_ca_llso.candidate_generator import generate_constraint_repair_candidates
from goa_eval.pia_ca_llso.constraint_ledger import attach_constraint_ledger
from goa_eval.pia_ca_llso.loop import suggest_next_run


def test_constraint_ledger_marks_failed_constraints_without_dropping_rows() -> None:
    frame = pd.DataFrame([{"sample_id": "s1", "delay": 12.0, "power": 2.0}])

    ledgered = attach_constraint_ledger(
        frame,
        {"constraints": {"delay": {"max": 10.0}, "power": {"max": 5.0}}},
    )

    assert ledgered.loc[0, "constraint_violation"] > 0
    assert "delay" in ledgered.loc[0, "constraint_ledger_json"]


def test_constraint_ledger_repair_generates_margin_and_ron_candidates() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "overall_score": 90, "hard_constraint_passed": True,
            "TFT_pullup_W": 10.0, "TFT_pulldown_W": 10.0, "C_load": 1.0,
            "C_boot": 1.0, "VGH": 8.0, "VGL": -6.0, "Vth_shift": 1.0,
            "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        },
        {
            "sample_id": "h2", "overall_score": 20, "hard_constraint_passed": False,
            "TFT_pullup_W": 1.0, "TFT_pulldown_W": 10.0, "C_load": 4.0,
            "C_boot": 0.5, "VGH": 1.05, "VGL": -6.0, "Vth_shift": 1.0,
            "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "bad",
            "TFT_pullup_W": 1.0, "TFT_pulldown_W": 10.0, "C_load": 4.0,
            "C_boot": 0.5, "VGH": 1.05, "VGL": -6.0, "Vth_shift": 1.0,
            "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
            "vgh_vth_margin": 0.05, "ron_pullup_cload_proxy": 4.0,
        }
    ])

    repairs = generate_constraint_repair_candidates(
        history,
        candidates,
        {"repair_candidates": {"max_repair_candidates": 4, "step_fraction": 0.25}},
    )

    assert not repairs.empty
    assert set(repairs["source"]) == {"constraint_ledger_repair"}
    assert set(repairs["engineering_validity"]) == {"simulation_only"}
    assert repairs["must_resimulate"].all()
    assert {"VGH", "TFT_pullup_W"} & set(repairs["repair_parameter"])


def test_repair_candidates_skip_unknown_or_unbounded_parameters() -> None:
    history = pd.DataFrame([{"sample_id": "h1", "VGH": 1.0, "Vth_shift": 1.0}])
    candidates = pd.DataFrame([
        {"candidate_id": "bad", "VGH": 1.0, "Vth_shift": 1.0, "vgh_vth_margin": 0.0}
    ])

    repairs = generate_constraint_repair_candidates(
        history,
        candidates,
        {"repair_candidates": {"max_repair_candidates": 4, "step_fraction": 0.25}},
    )

    assert repairs.empty


def test_pia_suggest_merges_repair_candidates_before_selection() -> None:
    history = pd.DataFrame([
        {
            "sample_id": "h1", "overall_score": 90, "hard_constraint_passed": True,
            "TFT_pullup_W": 10.0, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 1.0, "C_boot": 1.0, "VGH": 8.0, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        },
        {
            "sample_id": "h2", "overall_score": 20, "hard_constraint_passed": False,
            "TFT_pullup_W": 1.0, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 4.0, "C_boot": 0.5, "VGH": 1.05, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        },
    ])
    candidates = pd.DataFrame([
        {
            "candidate_id": "bad",
            "TFT_pullup_W": 1.0, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 4.0, "C_boot": 0.5, "VGH": 1.05, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        }
    ])

    result = suggest_next_run(
        history,
        candidates,
        {
            "physics_features": {"profile": "goa"},
            "repair_candidates": {"max_repair_candidates": 4, "step_fraction": 0.25},
        },
        strategy="adaptive_pia_capm",
        top_k=4,
    )

    assert "constraint_ledger_repair" in set(result.all_candidates["source"])
    assert "repair_candidates" in result.feature_report
    assert result.feature_report["repair_candidates"]["generated_count"] > 0


def _classifier_history() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "sample_id": "h1", "overall_score": 95, "hard_constraint_passed": True,
            "TFT_pullup_W": 10.0, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 1.0, "C_boot": 1.2, "VGH": 8.0, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        },
        {
            "sample_id": "h2", "overall_score": 90, "hard_constraint_passed": True,
            "TFT_pullup_W": 9.0, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 1.1, "C_boot": 1.2, "VGH": 7.5, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        },
        {
            "sample_id": "h3", "overall_score": 20, "hard_constraint_passed": False,
            "TFT_pullup_W": 1.0, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 4.0, "C_boot": 0.5, "VGH": 1.05, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.9, "CLK_fall_time": 0.9,
        },
        {
            "sample_id": "h4", "overall_score": 25, "hard_constraint_passed": False,
            "TFT_pullup_W": 1.2, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 9.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 4.2, "C_boot": 0.5, "VGH": 1.10, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.9, "CLK_fall_time": 0.9,
        },
    ])


def _classifier_candidates() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "candidate_id": "safe",
            "TFT_pullup_W": 9.5, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 1.0, "C_boot": 1.2, "VGH": 8.0, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.4, "CLK_fall_time": 0.4,
        },
        {
            "candidate_id": "risky",
            "TFT_pullup_W": 1.0, "TFT_pullup_L": 1.0,
            "TFT_pulldown_W": 10.0, "TFT_pulldown_L": 1.0,
            "TFT_reset_W": 5.0, "TFT_reset_L": 1.0,
            "TFT_bootstrap_W": 5.0, "TFT_bootstrap_L": 1.0,
            "C_load": 4.0, "C_boot": 0.5, "VGH": 1.05, "VGL": -6.0,
            "Vth_shift": 1.0, "CLK_rise_time": 0.9, "CLK_fall_time": 0.9,
        },
    ])


def test_pia_suggest_attaches_classifier_predictions_before_selection() -> None:
    result = suggest_next_run(
        _classifier_history(),
        _classifier_candidates(),
        {
            "physics_features": {"profile": "goa"},
            "repair_candidates": {"enabled": False},
            "evaluation_scheduler": {"enabled": True},
        },
        strategy="classifier_level_hybrid",
        top_k=2,
    )

    for column in ["p_l1", "predicted_level", "predicted_score", "p_hard_pass", "model_status", "classifier_hybrid_score"]:
        assert column in result.selected_candidates.columns
    assert result.model_report["strategy"] == "classifier_level_hybrid"
    assert result.model_report["classifier_model_status"] in {"ok", "insufficient_data"}


def test_evaluation_scheduler_assigns_window_and_constraint_plan() -> None:
    result = suggest_next_run(
        _classifier_history(),
        _classifier_candidates(),
        {
            "physics_features": {"profile": "goa"},
            "repair_candidates": {"enabled": False},
            "evaluation_scheduler": {"enabled": True, "full_frame_top_k": 1},
        },
        strategy="classifier_level_hybrid",
        top_k=2,
    )

    selected = result.selected_candidates
    for column in ["evaluation_state", "simulation_window", "constraint_eval_plan_json", "evidence_state", "must_resimulate"]:
        assert column in selected.columns
    assert selected["must_resimulate"].eq(True).all()
    assert set(selected["simulation_window"]).issubset({"short_window", "event_window", "full_frame"})
    assert selected.iloc[0]["simulation_window"] == "full_frame"
    plan = json.loads(selected.iloc[0]["constraint_eval_plan_json"])
    assert plan["constraints"]
    assert result.feature_report["evaluation_scheduler"]["enabled"] is True
