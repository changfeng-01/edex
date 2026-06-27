from __future__ import annotations

from typing import Any

import pandas as pd


def render_candidate_report(selected: pd.DataFrame, report: dict[str, Any]) -> str:
    lines = [
        "# PIA-CA-LLSO Candidate Report",
        "",
        "These rows are next-run simulation suggestions, not physical validation results.",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        f"- strategy = {report.get('strategy', 'unknown')}",
        "",
        "| rank | candidate_id | role | acquisition_score | reason |",
        "|---:|---|---|---:|---|",
    ]
    for _, row in selected.iterrows():
        lines.append(
            f"| {row.get('selected_rank', '')} | {row.get('candidate_id', '')} | {row.get('candidate_role', '')} | "
            f"{float(row.get('acquisition_score', 0.0)):.3f} | {row.get('selection_reason', '')} |"
        )
    return "\n".join(lines) + "\n"


def render_evolution_report(summary: dict[str, Any]) -> str:
    """Render a markdown evolution summary report."""
    lines = [
        "# PIA-CA-LLSO Closed-Loop Evolution Report",
        "",
        "## Summary",
        "",
        f"- **Stop reason:** {summary.get('stop_reason', 'N/A')}",
        f"- **Best simulation score:** {summary.get('best_score', 'N/A')}",
        f"- **Generations run:** {summary.get('generations_run', 0)}",
        f"- **Simulation budget used:** {summary.get('simulations_used', 0)}",
        f"- **Target reached:** {summary.get('target_reached', False)}",
        f"- **Latest simulation batch:** {summary.get('latest_simulation_batch', 'N/A')}",
        "",
        "## Evidence Boundary",
        "",
        f"- `data_source = {summary.get('data_source', 'N/A')}`",
        f"- `engineering_validity = {summary.get('engineering_validity', 'N/A')}`",
        "- `must_resimulate = true` for pre-simulation suggestions",
        f"- {summary.get('claim_boundary', '')}",
        "",
        "**Important:** All results in this report are simulation-only evidence.",
        "They do not constitute physical validation, silicon validation,",
        "lab validation, or tapeout validation.",
        "",
    ]
    artifacts = summary.get("generation_artifacts", [])
    if artifacts:
        lines.extend(["## Generation Artifacts", ""])
        for artifact in artifacts:
            lines.append(f"- `{artifact}`")
        lines.append("")
    return "\n".join(lines)
