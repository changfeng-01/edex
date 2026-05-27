from __future__ import annotations

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import inspect_leaderboard, inspect_real_metrics, inspect_score_summary


def run_sky130_agent(state: dict) -> dict:
    state["active_agent"] = "SKY130Agent"
    inputs = state.get("inputs", {})
    if inputs.get("leaderboard"):
        result = inspect_leaderboard(inputs["leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("score_summary"):
        result = inspect_score_summary(inputs["score_summary"])
        state["score_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("real_metrics"):
        result = inspect_real_metrics(inputs["real_metrics"])
        state["metrics_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    add_message(
        state,
        "SKY130Agent",
        {
            "sky130_summary": "SKY130 leaderboard and scoring artifacts inspected.",
            "best_candidate_summary": state.get("leaderboard_summary", {}).get("best_candidate", {}),
            "timing_summary": {
                key: state.get("metrics_summary", {}).get("metric_stats", {}).get(key)
                for key in ["Delay", "RiseTime", "FallTime"]
            },
            "score_summary": state.get("score_summary", {}),
            "candidate_risk_summary": state.get("candidate_summary", {}),
            "sky130_next_action": "generate next candidates through optimizer wrapper if param_space is available",
        },
    )
    append_handoff(state, "SKY130Agent", "EvaluationAgent", "domain artifacts inspected", ["leaderboard_summary", "score_summary", "metrics_summary"])
    return state
