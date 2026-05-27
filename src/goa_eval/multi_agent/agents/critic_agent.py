from __future__ import annotations

from goa_eval.multi_agent.critic import run_critic_checks
from goa_eval.multi_agent.trace import record_step


def run_critic_agent(state: dict) -> dict:
    state["active_agent"] = "CriticAgent"
    verdicts = run_critic_checks(state)
    for verdict in verdicts:
        payload = verdict.to_dict()
        state.setdefault("critic_verdicts", []).append(payload)
        if verdict.verdict == "warning":
            _extend_unique(state.setdefault("warnings", []), verdict.issues)
        elif verdict.verdict == "reject":
            failure_issues, warning_issues = _split_issues_by_risk(payload)
            _extend_unique(state.setdefault("failures", []), failure_issues)
            _extend_unique(state.setdefault("warnings", []), warning_issues)
        record_step(
            state,
            agent_name="CriticAgent",
            node_name="critic",
            step_id=verdict.step_id,
            status=verdict.verdict,
            reason=verdict.reason,
            output_summary={"issues": verdict.issues},
            critic_verdict=verdict.verdict,
        )
    return state


def _split_issues_by_risk(verdict: dict) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    for risk in verdict.get("risks", []):
        issue = risk.get("issue")
        if not issue:
            continue
        if risk.get("severity") in {"critical", "major"}:
            failures.append(issue)
        else:
            warnings.append(issue)
    return failures, warnings


def _extend_unique(target: list[str], values: list[str]) -> None:
    seen = set(target)
    for value in values:
        if value not in seen:
            target.append(value)
            seen.add(value)
