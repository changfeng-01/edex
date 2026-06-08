from __future__ import annotations

from typing import Any

import pandas as pd


def build_markdown_report(*, summary: dict[str, Any], leaderboard: pd.DataFrame) -> str:
    lines = [
        "# ECLIPSE Optimizer Benchmark Report",
        "",
        "data_source = real_simulation_csv",
        "engineering_validity = simulation_only",
        "",
        "This benchmark is an independent model/algorithm evaluation benchmark. It does not replace the existing strategy benchmark, GOA proxy benchmark, or multi-agent benchmark.",
        "",
        "predicted scores are not final benchmark evidence; predicted_score is internal acquisition evidence only.",
        "physics_score is not a final optimization result; it is proxy or diagnostic evidence only.",
        "attention_score is diagnostic only and must not be used as proof of optimization improvement.",
        "eclipse_benchmark_score is a summary index, not a replacement for primary metrics.",
        "",
        "## Primary Metrics",
        "",
        "- best_feasible_score",
        "- normalized_convergence_auc",
        "- FE@target",
        "- hard_constraint_pass_rate",
        "- not_evaluable_rate",
        "- candidate_hit_rate",
        "",
        "## Sorting Rule",
        "",
        "Sorting rule: best_feasible_score_mean desc, normalized_convergence_auc_mean desc, fe_at_target_score_mean asc with null last, target_pass_rate_mean desc, hard_constraint_pass_rate_mean desc, not_evaluable_rate_mean asc, simulation_failure_rate_mean asc, eclipse_benchmark_score_mean desc.",
        "",
        "## Leaderboard",
        "",
    ]
    if leaderboard.empty:
        lines.append("No algorithm runs were available.")
    else:
        columns = [
            "algorithm",
            "best_feasible_score_mean",
            "normalized_convergence_auc_mean",
            "fe_at_target_score_mean",
            "hard_constraint_pass_rate_mean",
            "not_evaluable_rate_mean",
            "eclipse_benchmark_score_mean",
        ]
        present = [column for column in columns if column in leaderboard]
        lines.append("| " + " | ".join(present) + " |")
        lines.append("| " + " | ".join(["---"] * len(present)) + " |")
        for _, row in leaderboard.iterrows():
            lines.append("| " + " | ".join(str(row.get(column, "")) for column in present) + " |")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Only real evaluation outputs, existing real-simulation CSV-derived history, and score_real_evaluation-style fields may prove algorithm advantage.",
            "- not_evaluable is tracked independently from failed, skipped, and passed.",
            "- mock or proxy evidence must not be described as silicon validation.",
            f"- score_threshold: `{summary.get('score_threshold', '')}`",
        ]
    )
    return "\n".join(lines) + "\n"
