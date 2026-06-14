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
