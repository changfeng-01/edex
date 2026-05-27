from __future__ import annotations

from pathlib import Path
from typing import Any


def write_decision_report(
    output_dir: Path,
    state: dict,
    memory: dict[str, Any],
    trace: list[dict],
    handoff_trace: list[dict],
    critic_report: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "multi_agent_decision_report.md"
    agents = sorted({item.get("agent_name") for item in trace if item.get("agent_name")})
    tools = sorted({item.get("tool_name") for item in trace if item.get("tool_name")})
    critic_verdicts = critic_report.get("verdicts", [])
    lines = [
        "# CircuitPilot Multi-Agent Decision Report",
        "",
        "## Boundary",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- Current results are simulation-only engineering evidence. They must not be described as silicon validation, physical chip validation, or industrial-grade full automation.",
        "",
        "## Task",
        "",
        f"- task_name: `{state.get('task_name')}`",
        f"- task_type: `{state.get('task_type')}`",
        f"- profile: `{state.get('profile')}`",
        f"- primary_objective: `{(state.get('objectives') or {}).get('primary')}`",
        "",
        "## Agent Plan",
        "",
        f"- SupervisorAgent initialized the shared state and preserved `{state.get('data_source')}` / `{state.get('engineering_validity')}`.",
        f"- RouterAgent selected `{state.get('selected_domain_agent')}`.",
        f"- Routing reason: `{state.get('routing_reason', '')}`",
        f"- Agents used: `{', '.join(agents)}`",
        f"- Tools used: `{', '.join(tools)}`",
        "",
        "## Evaluation Summary",
        "",
        f"- best_candidate: `{_short(state.get('leaderboard_summary', {}).get('best_candidate', {}))}`",
        f"- score_summary: `{_short(state.get('score_summary', {}))}`",
        f"- metrics_summary: `{_short(state.get('metrics_summary', {}))}`",
        "",
        "## Candidate Generation",
        "",
        f"- next_candidates_generated: `{bool(state.get('candidate_summary', {}).get('candidate_count'))}`",
        f"- candidate_summary: `{_short(state.get('candidate_summary', {}))}`",
        "- Candidates, when present, were produced by registered deterministic optimizer wrappers under param_space constraints.",
        "",
        "## Critic Review",
        "",
    ]
    if critic_verdicts:
        for verdict in critic_verdicts:
            lines.append(f"- `{verdict.get('verdict')}`: {verdict.get('reason')} issues={verdict.get('issues', [])}")
    else:
        lines.append("- No critic verdicts recorded.")
    lines.extend(
        [
            "",
            "## Warnings And Failures",
            "",
            f"- warnings: `{state.get('warnings', [])}`",
            f"- failures: `{state.get('failures', [])}`",
            "",
            "## Handoff Trace",
            "",
        ]
    )
    for record in handoff_trace:
        lines.append(f"- `{record.get('from_agent')}` -> `{record.get('to_agent')}`: {record.get('reason')}")
    lines.extend(
        [
            "",
            "## Suggested Next Actions",
            "",
        ]
    )
    for item in memory.get("suggested_next_actions", []):
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _short(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 500 else text[:497] + "..."
