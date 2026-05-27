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
            state.setdefault("warnings", []).extend(verdict.issues)
        elif verdict.verdict == "reject":
            state.setdefault("failures", []).extend(verdict.issues)
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
