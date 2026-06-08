from __future__ import annotations

import math

import pandas as pd

from goa_eval.eclipse_benchmark.metrics import (
    compute_attention_metrics,
    compute_candidate_selection_metrics,
    compute_convergence_curve,
    compute_run_metrics,
)


def test_best_feasible_score_ignores_high_scoring_hard_failures() -> None:
    history = pd.DataFrame(
        [
            {
                "candidate_id": "sample_a",
                "overall_score": 95,
                "hard_constraint_passed": False,
                "target_passed": True,
                "rank_status": "evaluated",
                "not_evaluable_metric_count": 0,
            },
            {
                "candidate_id": "sample_b",
                "overall_score": 82,
                "hard_constraint_passed": True,
                "target_passed": True,
                "rank_status": "evaluated",
                "not_evaluable_metric_count": 0,
                "round_index": 2,
            },
            {
                "candidate_id": "sample_c",
                "overall_score": 88,
                "hard_constraint_passed": True,
                "target_passed": True,
                "rank_status": "not_evaluable",
                "not_evaluable_metric_count": 1,
            },
            {
                "candidate_id": "sample_d",
                "overall_score": 99,
                "rank_status": "predicted_only",
            },
        ]
    )

    metrics = compute_run_metrics(history, score_threshold=80)

    assert metrics["best_feasible_score"] == 82.0
    assert metrics["best_feasible_candidate_id"] == "sample_b"
    assert metrics["best_feasible_round"] == 2
    assert metrics["best_feasible_status"] == "found"


def test_convergence_auc_uses_only_feasible_scores_for_best_feasible_curve() -> None:
    history = pd.DataFrame(
        [
            {"overall_score": 90, "hard_constraint_passed": False, "target_passed": False, "rank_status": "evaluated"},
            {"overall_score": 60, "hard_constraint_passed": True, "target_passed": True, "rank_status": "evaluated"},
            {"overall_score": 90, "hard_constraint_passed": False, "target_passed": True, "rank_status": "evaluated"},
            {"overall_score": 80, "hard_constraint_passed": True, "target_passed": True, "rank_status": "evaluated"},
        ]
    )

    curve = compute_convergence_curve(history)
    metrics = compute_run_metrics(history, score_threshold=80)

    assert curve["current_best_feasible_score"].tolist() == [None, 60.0, 60.0, 80.0]
    assert metrics["fe_at_target_score"] == 4
    assert math.isclose(metrics["normalized_convergence_auc"], (0 + 0.6 + 0.6 + 0.8) / 4)


def test_constraint_statuses_are_counted_separately() -> None:
    history = pd.DataFrame(
        [
            {"overall_score": 82, "hard_constraint_passed": True, "target_passed": True, "rank_status": "evaluated"},
            {"overall_score": 55, "hard_constraint_passed": False, "target_passed": False, "rank_status": "evaluated"},
            {"overall_score": None, "hard_constraint_passed": False, "target_passed": False, "rank_status": "not_evaluable"},
            {"overall_score": None, "status": "sim_failed", "rank_status": "failed"},
        ]
    )

    metrics = compute_run_metrics(history)

    assert metrics["hard_constraint_pass_rate"] == 0.25
    assert metrics["hard_fail_rate"] == 0.25
    assert metrics["not_evaluable_rate"] == 0.25
    assert metrics["simulation_failure_rate"] == 0.25


def test_candidate_role_metrics_are_optional() -> None:
    no_role = compute_candidate_selection_metrics(pd.DataFrame(), pd.DataFrame([{"candidate_id": "c1"}]))
    assert no_role["role_metrics_available"] is False
    assert no_role["role_hit_rate"] is None

    history = pd.DataFrame(
        [
            {
                "candidate_id": "c1",
                "overall_score": 90,
                "hard_constraint_passed": True,
                "target_passed": True,
                "rank_status": "evaluated",
            },
            {
                "candidate_id": "c2",
                "overall_score": 30,
                "hard_constraint_passed": False,
                "target_passed": False,
                "rank_status": "evaluated",
            },
        ]
    )
    audit = pd.DataFrame(
        [
            {"candidate_id": "c1", "candidate_role": "exploitation"},
            {"candidate_id": "c2", "candidate_role": "boundary_learning"},
        ]
    )

    metrics = compute_candidate_selection_metrics(history, audit, score_threshold=80)

    assert metrics["role_metrics_available"] is True
    assert metrics["selected_candidate_count"] == 2
    assert metrics["candidate_hit_rate"] == 0.5
    assert metrics["role_hit_rate"] == 0.5
    assert metrics["exploitation_hit_rate"] == 1.0
    assert metrics["boundary_learning_hit_rate"] == 0.0


def test_attention_metrics_are_optional() -> None:
    unavailable = compute_attention_metrics(pd.DataFrame([{"candidate_id": "c1"}]))
    assert unavailable["attention_metrics_available"] is False
    assert unavailable["mean_attention_to_real_l1"] is None

    audit = pd.DataFrame(
        [
            {
                "attention_to_real_l1": 0.8,
                "attention_real_sim_mass": 0.7,
                "attention_proxy_mass": 0.1,
                "attention_explanation_consistency": 1.0,
            },
            {
                "attention_to_real_l1": 0.4,
                "attention_real_sim_mass": 0.5,
                "attention_proxy_mass": 0.2,
                "attention_explanation_consistency": 0.0,
            },
        ]
    )

    metrics = compute_attention_metrics(audit)

    assert metrics["attention_metrics_available"] is True
    assert metrics["mean_attention_to_real_l1"] == 0.6
    assert metrics["mean_attention_real_sim_mass"] == 0.6
    assert metrics["mean_attention_proxy_mass"] == 0.15
    assert metrics["attention_explanation_consistency"] == 0.5
