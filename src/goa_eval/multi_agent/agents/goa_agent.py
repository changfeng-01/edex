from __future__ import annotations

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import inspect_leaderboard, inspect_real_metrics, inspect_score_summary


def run_goa_agent(state: dict) -> dict:
    state["active_agent"] = "GOAAgent"
    inputs = state.get("inputs", {})
    if inputs.get("leaderboard"):
        result = inspect_leaderboard(inputs["leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    if inputs.get("score_summary"):
        result = inspect_score_summary(inputs["score_summary"])
        state["score_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    if inputs.get("real_metrics"):
        result = inspect_real_metrics(inputs["real_metrics"])
        state["metrics_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    add_message(
        state,
        "GOAAgent",
        {
            "goa_summary": "GOA/8T1C evaluation artifacts inspected.",
            "worst_stage": state.get("metrics_summary", {}).get("worst_stage"),
            "first_failed_stage": state.get("score_summary", {}).get("first_failed_stage"),
            "overlap_summary": state.get("metrics_summary", {}).get("metric_stats", {}).get("OverlapRatio"),
            "ripple_summary": state.get("metrics_summary", {}).get("metric_stats", {}).get("Ripple"),
            "voltage_loss_summary": state.get("metrics_summary", {}).get("metric_stats", {}).get("VoltageLoss"),
            "false_trigger_summary": state.get("metrics_summary", {}).get("metric_stats", {}).get("FalseTriggerCount"),
            "goa_next_action": "run shared evaluation and candidate generation only through deterministic tools",
        },
    )
    append_handoff(state, "GOAAgent", "EvaluationAgent", "domain artifacts inspected", ["leaderboard_summary", "score_summary", "metrics_summary"])
    return state
