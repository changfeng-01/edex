from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from goa_eval.eclipse_benchmark.benchmark import run_offline_replay_benchmark
from goa_eval.eclipse_benchmark.scoring import build_algorithm_leaderboard, compute_eclipse_benchmark_score


def test_eclipse_score_is_summary_index_not_predicted_evidence() -> None:
    score = compute_eclipse_benchmark_score(
        {
            "best_feasible_score": 80,
            "normalized_convergence_auc": 0.5,
            "fe_at_target_score": 4,
            "simulation_count": 8,
            "first_feasible_round": 2,
            "hard_constraint_pass_rate": 0.5,
            "not_evaluable_rate": 0.25,
            "simulation_failure_rate": 0.0,
            "mean_constraint_violation_proxy": 0.25,
            "candidate_hit_rate": 0.5,
            "l1_discovery_count": 1,
            "selected_candidate_count": 2,
            "role_hit_rate": None,
            "evidence_boundary_preserved": True,
            "attention_metrics_available": False,
        }
    )

    assert 0 < score < 1


def test_leaderboard_sorts_by_feasible_score_before_raw_best_score() -> None:
    runs = pd.DataFrame(
        [
            {
                "algorithm": "raw_high_no_feasible",
                "seed": "1",
                "best_any_score": 99.0,
                "best_feasible_score": None,
                "normalized_convergence_auc": 0.0,
                "fe_at_target_score": None,
                "target_pass_rate": 0.0,
                "hard_constraint_pass_rate": 0.0,
                "not_evaluable_rate": 0.0,
                "simulation_failure_rate": 0.0,
                "eclipse_benchmark_score": 0.2,
            },
            {
                "algorithm": "best_feasible",
                "seed": "1",
                "best_any_score": 85.0,
                "best_feasible_score": 85.0,
                "normalized_convergence_auc": 0.4,
                "fe_at_target_score": 4,
                "target_pass_rate": 1.0,
                "hard_constraint_pass_rate": 1.0,
                "not_evaluable_rate": 0.0,
                "simulation_failure_rate": 0.0,
                "eclipse_benchmark_score": 0.8,
            },
            {
                "algorithm": "lower_feasible_high_auc",
                "seed": "1",
                "best_any_score": 80.0,
                "best_feasible_score": 80.0,
                "normalized_convergence_auc": 0.9,
                "fe_at_target_score": 2,
                "target_pass_rate": 1.0,
                "hard_constraint_pass_rate": 1.0,
                "not_evaluable_rate": 0.0,
                "simulation_failure_rate": 0.0,
                "eclipse_benchmark_score": 0.7,
            },
        ]
    )

    leaderboard = build_algorithm_leaderboard(runs)

    assert leaderboard["algorithm"].tolist()[:2] == ["best_feasible", "lower_feasible_high_auc"]
    assert leaderboard.iloc[-1]["algorithm"] == "raw_high_no_feasible"


def test_offline_replay_benchmark_writes_independent_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "eclipse_opt" / "seed_1"
    run_dir.mkdir(parents=True)
    history = {
        "history": [
            {
                "candidate_id": "c1",
                "overall_score": 60,
                "hard_constraint_passed": True,
                "target_passed": True,
                "rank_status": "evaluated",
                "round_index": 1,
            },
            {
                "candidate_id": "c2",
                "overall_score": 82,
                "hard_constraint_passed": True,
                "target_passed": True,
                "rank_status": "evaluated",
                "round_index": 2,
            },
        ]
    }
    (run_dir / "optimization_history.json").write_text(json.dumps(history), encoding="utf-8")
    pd.DataFrame(history["history"]).to_csv(run_dir / "optimization_leaderboard.csv", index=False)

    summary = run_offline_replay_benchmark(
        runs_root=tmp_path / "runs",
        output_root=tmp_path / "out",
        score_threshold=80,
        baseline="random",
    )

    assert summary["benchmark_type"] == "eclipse_model_benchmark"
    assert summary["engineering_validity"] == "simulation_only"
    for filename in [
        "eclipse_benchmark_summary.json",
        "eclipse_algorithm_leaderboard.csv",
        "eclipse_algorithm_runs.csv",
        "eclipse_convergence_curves.csv",
        "eclipse_candidate_selection_audit.csv",
        "eclipse_metric_audit.json",
        "eclipse_benchmark_report.md",
    ]:
        assert (tmp_path / "out" / filename).exists(), filename
