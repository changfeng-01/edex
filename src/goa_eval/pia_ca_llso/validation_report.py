"""Markdown report renderer for Phase 3 PIA validation."""
from __future__ import annotations

from typing import Any

import pandas as pd


def render_validation_report(
    protocol: dict[str, Any],
    run_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    win_rate_frame: pd.DataFrame,
) -> str:
    lines = [
        "# PIA-CA-LLSO Experimental Validation",
        "",
        "## Purpose",
        "Evaluate whether PIA-CA-LLSO closed-loop evolution improves simulation-only outcomes under fixed budgets, multiple seeds, and ablations.",
        "",
        "## Protocol",
        f"- primary_outcome = {protocol.get('primary_outcome', 'simulations_to_target')}",
        f"- target_score = {protocol.get('target_score', 'N/A')}",
        f"- run_count = {len(run_frame)}",
        "",
        "## Scenarios",
        _bullet_values(_scenario_ids(protocol)),
        "",
        "## Methods",
        _bullet_values(protocol.get("methods", [])),
        "",
        "## Ablations",
        _bullet_values(protocol.get("ablations", [])),
        "",
        "## Primary outcome",
        "`simulations_to_target` counts imported simulation result rows needed to reach the configured target score.",
        "",
        "## Secondary outcomes",
        "- target_hit_rate",
        "- best_score_final",
        "- best_score_delta",
        "- convergence_auc",
        "- hard_pass_rate",
        "- mean_constraint_violation",
        "- boundary_audit_passed",
        "- invalid_result_rejection_count",
        "",
        "## Per-run details",
        _table(_select_columns(run_frame, [
            "scenario_id",
            "method",
            "ablation",
            "seed",
            "budget",
            "target_hit",
            "simulations_to_target",
            "best_score_final",
            "convergence_auc",
            "hard_pass_rate",
            "best_so_far_curve_path",
        ])),
        "",
        "## Method scenario budget summary",
        _table(summary_frame),
        "",
        "## Pairwise matrix win rates",
        _table(win_rate_frame),
        "",
        "## Failure cases",
        _failure_cases(run_frame),
        "",
        "## Boundary statement",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "These results are simulation-only evidence, not physical validation.",
        "",
        "## Limitations",
        "- Local fixture runs are CI behavior checks and do not replace external simulator case packs.",
        "- Multiple comparisons are reported together; claims should not be cherry-picked from a single seed or ablation.",
        "- Imported simulator CSV rows remain simulation-only evidence.",
        "",
        "## Next algorithmic upgrades",
        "- Add more real simulation case packs before making stronger benchmark claims.",
        "- Track scenario-level failures where hard constraints dominate score gains.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _scenario_ids(protocol: dict[str, Any]) -> list[str]:
    ids = []
    for scenario in protocol.get("scenarios", []):
        if isinstance(scenario, dict):
            ids.append(str(scenario.get("scenario_id", scenario)))
        else:
            ids.append(str(scenario))
    return ids


def _bullet_values(values: Any) -> str:
    items = list(values or [])
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def _table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows available._"
    text_frame = frame.fillna("").astype(str)
    columns = list(text_frame.columns)
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in text_frame.iterrows():
        rows.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return "\n".join(rows)


def _select_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    present = [column for column in columns if column in frame.columns]
    return frame[present] if present else frame


def _failure_cases(run_frame: pd.DataFrame) -> str:
    if run_frame.empty or "boundary_audit_passed" not in run_frame.columns:
        return "_No failure cases recorded._"
    failures = run_frame[run_frame["boundary_audit_passed"] == False]  # noqa: E712
    if failures.empty:
        return "_No failure cases recorded._"
    columns = [column for column in ["scenario_id", "method", "ablation", "seed", "budget", "boundary_issue_count"] if column in failures]
    return _table(failures[columns])
