from __future__ import annotations

import json

import pandas as pd

from goa_eval.pia_ca_llso.benchmark import compute_run_metrics, run_ablation_benchmark, compute_evolution_metrics


def test_benchmark_metrics_and_outputs(tmp_path) -> None:
    scored = pd.DataFrame(
        [
            {"candidate_id": "c1", "real_score": 20, "hard_pass": False, "status": "evaluated_soft_fail"},
            {"candidate_id": "c2", "real_score": 85, "hard_pass": True, "status": "evaluated_feasible"},
        ]
    )
    metrics = compute_run_metrics(scored, target_score=80)
    assert metrics["best_feasible_score_under_budget"] == 85
    assert metrics["first_feasible_eval"] == 2
    assert metrics["fe_at_target"] == 2

    history = pd.DataFrame([{"sample_id": "h1", "x": 0, "level_label": "L1", "overall_score": 90, "hard_constraint_passed": True}])
    candidates = pd.DataFrame(
        [
            {"candidate_id": "c1", "x": 0.1, "overall_score": 82, "hard_constraint_passed": True, "sim_success": True},
            {"candidate_id": "c2", "x": 0.9, "overall_score": 20, "hard_constraint_passed": False, "sim_success": True},
        ]
    )
    run_ablation_benchmark(history, candidates, tmp_path, strategies=["random", "ca_llso_raw_distance"], target_score=80)
    assert (tmp_path / "pia_ablation_results.csv").exists()
    assert json.loads((tmp_path / "pia_ablation_summary.json").read_text(encoding="utf-8"))["data_source"] == "real_simulation_csv"
    assert "simulation_only" in (tmp_path / "pia_ablation_report.md").read_text(encoding="utf-8")


def test_benchmark_passes_capm_config_to_selector(tmp_path) -> None:
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
                "overall_score": 90,
                "hard_constraint_passed": True,
            }
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "c1",
                "cboot_cload_ratio": 1.2,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 3.5,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 0.05,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
                "overall_score": 82,
                "hard_constraint_passed": True,
            }
        ]
    )

    run_ablation_benchmark(
        history,
        candidates,
        tmp_path,
        strategies=["pia_capm_distance"],
        config={"capm_distance": {"max_ron_pullup_cload_proxy": 4.0, "min_vgh_vth_margin": 0.01}},
    )

    selected = pd.read_csv(tmp_path / "pia_capm_distance_selected_candidates.csv")
    assert bool(selected.loc[0, "capm_hard_risk_passed"]) is True


def test_pia_benchmark_accepts_classifier_level_hybrid_strategy(tmp_path) -> None:
    history = pd.DataFrame(
        [
            {"sample_id": "h1", "x": 0.0, "level_label": "L1", "overall_score": 95, "hard_constraint_passed": True},
            {"sample_id": "h2", "x": 0.1, "level_label": "L1", "overall_score": 90, "hard_constraint_passed": True},
            {"sample_id": "h3", "x": 0.9, "level_label": "L4", "overall_score": 20, "hard_constraint_passed": False},
            {"sample_id": "h4", "x": 1.0, "level_label": "L4", "overall_score": 25, "hard_constraint_passed": False},
        ]
    )
    candidates = pd.DataFrame(
        [
            {"candidate_id": "good", "x": 0.05, "overall_score": 88, "hard_constraint_passed": True},
            {"candidate_id": "bad", "x": 0.95, "overall_score": 20, "hard_constraint_passed": False},
        ]
    )

    run_ablation_benchmark(
        history,
        candidates,
        tmp_path,
        strategies=["classifier_level_hybrid"],
        target_score=80,
        config={"classifier_level_hybrid": {"min_history_rows": 4}},
    )

    selected = pd.read_csv(tmp_path / "classifier_level_hybrid_selected_candidates.csv")
    assert "classifier_hybrid_score" in selected.columns
    assert selected.iloc[0]["candidate_id"] == "good"


def test_pia_benchmark_accepts_evolution_summary() -> None:
    """compute_evolution_metrics extracts closed-loop fields from evolution summary."""
    summary = {
        "stop_reason": "target_score_reached",
        "best_score": 95.0,
        "generations_run": 3,
        "simulations_used": 12,
        "target_reached": True,
    }
    metrics = compute_evolution_metrics(summary, target_score=80)
    assert metrics["evolution_generations_run"] == 3
    assert metrics["evolution_simulations_used"] == 12
    assert metrics["evolution_target_reached"] is True
    assert metrics["evolution_stop_reason"] == "target_score_reached"
    assert metrics["closed_loop_mode"] == "evolution"
    assert metrics["single_step_mode"] == "not_applicable"
