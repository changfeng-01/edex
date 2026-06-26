from __future__ import annotations

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
