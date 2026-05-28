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
    best_candidate = (state.get("leaderboard_summary") or {}).get("best_candidate", {})
    warnings = state.get("warnings", [])
    failures = state.get("failures", [])
    lines = [
        "# CircuitPilot Multi-Agent Decision Report",
        "",
        "## Boundary",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- Current results are simulation-only engineering evidence. They must not be described as silicon validation, physical chip validation, or industrial-grade full automation.",
        "",
        "## Task Objective",
        "",
        f"- task_name: `{state.get('task_name')}`",
        f"- task_type: `{state.get('task_type')}`",
        f"- profile: `{state.get('profile')}`",
        f"- primary_objective: `{(state.get('objectives') or {}).get('primary')}`",
        "",
        "## Agent Routing",
        "",
        f"- SupervisorAgent initialized the shared state and preserved `{state.get('data_source')}` / `{state.get('engineering_validity')}`.",
        f"- RouterAgent selected `{state.get('selected_domain_agent')}`.",
        f"- Routing reason: `{state.get('routing_reason', '')}`",
        f"- Agents used: `{', '.join(agents)}`",
        f"- Tools used: `{', '.join(tools)}`",
        "",
        "## Tool Calls",
        "",
        "| Agent | Tool | Status | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for item in trace:
        if item.get("tool_name"):
            lines.append(
                f"| `{item.get('agent_name')}` | `{item.get('tool_name')}` | `{item.get('status')}` | `{_short(item.get('output_summary', {}), 180)}` |"
            )
    if not tools:
        lines.append("| n/a | n/a | n/a | No tool calls recorded. |")
    lines.extend(
        [
            "",
            "## Evaluation Summary",
            "",
            f"- best_candidate: `{_short(best_candidate)}`",
            f"- score_summary: `{_short(state.get('score_summary', {}))}`",
            f"- metrics_summary: `{_short(state.get('metrics_summary', {}))}`",
            "",
            "## Domain Diagnosis",
            "",
            f"- domain_diagnosis: `{_short(state.get('domain_diagnosis', {}))}`",
            "",
            "## Candidate Generation Rationale",
            "",
            f"- next_candidates_generated: `{bool(state.get('candidate_summary', {}).get('candidate_count'))}`",
            f"- candidate_summary: `{_short(state.get('candidate_summary', {}))}`",
            "- Candidates, when present, were produced by registered deterministic optimizer wrappers under param_space constraints.",
            "- Candidate priority is derived from existing leaderboard and metric signals such as ripple, overlap, delay, and false-trigger indicators.",
            "",
            "## Optimization Loop",
            "",
            f"- loop_record: `{state.get('generated_files', {}).get('optimization_loop_record')}`",
            f"- decision_card: `{state.get('generated_files', {}).get('optimization_decision_card')}`",
            "",
            "## Netlist Review",
            "",
            f"- netlist_summary: `{_short(state.get('netlist_summary', {}))}`",
            "",
            "## Critic Review",
            "",
        ]
    )
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
            f"- warnings: `{warnings}`",
            f"- failures: `{failures}`",
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


def _short(value: Any, limit: int = 500) -> str:
    text = str(value)
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."
