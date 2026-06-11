from __future__ import annotations

import json

import pandas as pd

from goa_eval.pia_ca_llso.benchmark import compute_run_metrics, run_ablation_benchmark


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
