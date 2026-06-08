from __future__ import annotations

from typing import Any

import pandas as pd

from goa_eval.eclipse_benchmark.schema import PRIMARY_METRICS
from goa_eval.eclipse_benchmark.statistics import summarize_metric


def compute_eclipse_benchmark_score(metrics: dict[str, Any]) -> float:
    feasible_quality = _clip((_num(metrics.get("best_feasible_score")) or 0.0) / 100.0)
    convergence = _convergence_efficiency_score(metrics)
    constraint = _constraint_control_score(metrics)
    candidate = _candidate_selection_score(metrics)
    evidence = _evidence_explainability_score(metrics)
    score = (
        0.35 * feasible_quality
        + 0.25 * convergence
        + 0.20 * constraint
        + 0.10 * candidate
        + 0.10 * evidence
    )
    return round(_clip(score), 6)


def build_algorithm_leaderboard(run_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if run_frame.empty:
        return pd.DataFrame()
    for algorithm, group in run_frame.groupby("algorithm", sort=False):
        row: dict[str, Any] = {"algorithm": algorithm, "seed_count": int(len(group))}
        for metric in PRIMARY_METRICS:
            summary = summarize_metric(group.get(metric, pd.Series(dtype=float)))
            for name, value in summary.items():
                if name != "seed_count":
                    row[f"{metric}_{name}"] = value
        rows.append(row)
    leaderboard = pd.DataFrame(rows)
    if leaderboard.empty:
        return leaderboard
    for column in [
        "best_feasible_score_mean",
        "normalized_convergence_auc_mean",
        "target_pass_rate_mean",
        "hard_constraint_pass_rate_mean",
        "not_evaluable_rate_mean",
        "simulation_failure_rate_mean",
        "eclipse_benchmark_score_mean",
    ]:
        if column not in leaderboard:
            leaderboard[column] = None
    leaderboard["_fe_at_target_sort"] = pd.to_numeric(
        leaderboard.get("fe_at_target_score_mean"), errors="coerce"
    ).fillna(float("inf"))
    leaderboard["_best_feasible_sort"] = pd.to_numeric(
        leaderboard["best_feasible_score_mean"], errors="coerce"
    ).fillna(float("-inf"))
    leaderboard = leaderboard.sort_values(
        [
            "_best_feasible_sort",
            "normalized_convergence_auc_mean",
            "_fe_at_target_sort",
            "target_pass_rate_mean",
            "hard_constraint_pass_rate_mean",
            "not_evaluable_rate_mean",
            "simulation_failure_rate_mean",
            "eclipse_benchmark_score_mean",
        ],
        ascending=[False, False, True, False, False, True, True, False],
        kind="mergesort",
    )
    return leaderboard.drop(columns=["_best_feasible_sort", "_fe_at_target_sort"])


def _convergence_efficiency_score(metrics: dict[str, Any]) -> float:
    auc = _num(metrics.get("normalized_convergence_auc")) or 0.0
    sim_count = max(1.0, _num(metrics.get("simulation_count")) or 1.0)
    fe_at_target = _num(metrics.get("fe_at_target_score"))
    first_feasible = _num(metrics.get("first_feasible_round"))
    fe_score = 0.0 if fe_at_target is None else max(0.0, 1.0 - (fe_at_target - 1.0) / sim_count)
    first_score = 0.0 if first_feasible is None else max(0.0, 1.0 - (first_feasible - 1.0) / sim_count)
    return _clip(0.60 * auc + 0.25 * fe_score + 0.15 * first_score)


def _constraint_control_score(metrics: dict[str, Any]) -> float:
    pass_rate = _num(metrics.get("hard_constraint_pass_rate")) or 0.0
    not_eval = _num(metrics.get("not_evaluable_rate")) or 0.0
    sim_fail = _num(metrics.get("simulation_failure_rate")) or 0.0
    violation = _num(metrics.get("mean_constraint_violation_proxy")) or 0.0
    violation_score = 1.0 / (1.0 + max(0.0, violation))
    return _clip(0.45 * pass_rate + 0.25 * (1.0 - not_eval) + 0.20 * (1.0 - sim_fail) + 0.10 * violation_score)


def _candidate_selection_score(metrics: dict[str, Any]) -> float:
    hit = _num(metrics.get("candidate_hit_rate"))
    l1_count = _num(metrics.get("l1_discovery_count")) or 0.0
    selected = _num(metrics.get("selected_candidate_count")) or 0.0
    role_hit = _num(metrics.get("role_hit_rate"))
    base = hit if hit is not None else 0.0
    discovery = 0.0 if selected <= 0 else min(1.0, l1_count / selected)
    role = role_hit if role_hit is not None else base
    return _clip(0.50 * base + 0.30 * discovery + 0.20 * role)


def _evidence_explainability_score(metrics: dict[str, Any]) -> float:
    boundary = 1.0 if metrics.get("evidence_boundary_preserved") else 0.0
    if not metrics.get("attention_metrics_available"):
        return boundary
    consistency = _num(metrics.get("attention_explanation_consistency")) or 0.0
    mass = _num(metrics.get("mean_attention_real_sim_mass")) or 0.0
    return _clip(0.50 * boundary + 0.25 * consistency + 0.25 * mass)


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
