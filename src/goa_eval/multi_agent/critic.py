from __future__ import annotations

from pathlib import Path

import pandas as pd

from goa_eval.multi_agent.agent_contracts import is_tool_allowed
from goa_eval.multi_agent.schemas import CriticVerdict
from goa_eval.multi_agent.tools import BAD_CELL_STRINGS, check_schema_and_boundary, inspect_candidates


def run_critic_checks(state: dict) -> list[CriticVerdict]:
    verdicts: list[CriticVerdict] = []
    issues: list[str] = []

    for label, path_text in (state.get("generated_files") or {}).items():
        path = Path(str(path_text))
        if not path.exists():
            issues.append(f"missing output file: {label} -> {path}")
            continue
        if path.suffix.lower() in {".json", ".csv"}:
            boundary = check_schema_and_boundary(path, state.get("data_source", "real_simulation_csv"), state.get("engineering_validity", "simulation_only"))
            issues.extend(boundary.warnings)
        if path.suffix.lower() == ".csv":
            issues.extend(_bad_metric_cell_issues(path))

    if state.get("data_source") != "real_simulation_csv":
        issues.append(f"data_source mismatch: {state.get('data_source')}")
    if state.get("engineering_validity") != "simulation_only":
        issues.append(f"engineering_validity mismatch: {state.get('engineering_validity')}")
    bad_metric_count = int((state.get("metrics_summary") or {}).get("bad_cell_count") or 0)
    if bad_metric_count:
        issues.append(f"bad metric cell count {bad_metric_count} in inspected metrics")
    if state.get("selected_domain_agent") == "unsupported" or state.get("profile") == "unknown":
        issues.append("unsupported profile routed to critic")
    if not state.get("handoff_records"):
        issues.append("handoff record missing")

    candidate_path = (state.get("generated_files") or {}).get("next_candidates")
    param_space = (state.get("inputs") or {}).get("param_space")
    if candidate_path and Path(str(candidate_path)).exists() and param_space:
        result = inspect_candidates(candidate_path, param_space, int((state.get("limits") or {}).get("max_parameter_changes_per_candidate", 2)))
        issues.extend(result.warnings)

    for agent_name, results in (state.get("tool_results") or {}).items():
        for result in results:
            tool_name = result.get("tool_name")
            if tool_name and not is_tool_allowed(agent_name, tool_name):
                issues.append(f"unauthorized tool call: {agent_name} -> {tool_name}")

    report_path = (state.get("generated_files") or {}).get("multi_agent_decision_report")
    if report_path and Path(str(report_path)).exists():
        text = Path(str(report_path)).read_text(encoding="utf-8", errors="replace").lower()
        forbidden = ["silicon validation", "physical validation", "industrial-grade full automation"]
        for phrase in forbidden:
            if phrase in text and "not" not in text[max(0, text.find(phrase) - 20) : text.find(phrase)]:
                issues.append(f"report may overclaim forbidden phrase: {phrase}")

    verdict = "pass" if not issues else "warning"
    verdicts.append(
        CriticVerdict(
            step_id=f"critic-{len(state.get('critic_verdicts', [])) + 1}",
            agent_name="CriticAgent",
            verdict=verdict,
            issues=issues,
            reason="critic checks completed",
            suggested_next_action="continue with simulation-only reporting" if verdict == "pass" else "review warnings before using outputs",
        )
    )
    return verdicts


def _bad_metric_cell_issues(path: Path) -> list[str]:
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return [f"csv unreadable: {path}: {exc}"]
    issues = []
    bad_mask = frame.isna()
    for column in frame.columns:
        bad_mask[column] = bad_mask[column] | frame[column].astype(str).str.lower().isin(BAD_CELL_STRINGS)
    count = int(bad_mask.sum().sum())
    if count:
        issues.append(f"bad metric cell count {count} in {path}")
    return issues
