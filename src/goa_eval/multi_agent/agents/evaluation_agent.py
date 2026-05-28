from __future__ import annotations

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import inspect_artifact_bundle, inspect_leaderboard, inspect_real_metrics, inspect_score_summary


def run_evaluation_agent(state: dict) -> dict:
    state["active_agent"] = "EvaluationAgent"
    inputs = state.get("inputs", {})
    result = inspect_artifact_bundle(inputs)
    state["artifact_bundle_summary"] = result.data
    store_tool_result(state, "EvaluationAgent", result)
    if inputs.get("leaderboard") and not state.get("leaderboard_summary"):
        result = inspect_leaderboard(inputs["leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "EvaluationAgent", result)
    if inputs.get("score_summary") and not state.get("score_summary"):
        result = inspect_score_summary(inputs["score_summary"])
        state["score_summary"] = result.data
        store_tool_result(state, "EvaluationAgent", result)
    if inputs.get("real_metrics") and not state.get("metrics_summary"):
        result = inspect_real_metrics(inputs["real_metrics"])
        state["metrics_summary"] = result.data
        store_tool_result(state, "EvaluationAgent", result)
    add_message(
        state,
        "EvaluationAgent",
        {
            "evaluation_summary": {
                "artifact_completeness": {
                    "found_count": len(state.get("artifact_bundle_summary", {}).get("found_artifacts", {})),
                    "missing_count": len(state.get("artifact_bundle_summary", {}).get("missing_artifacts", [])),
                },
                "leaderboard_available": bool(state.get("leaderboard_summary")),
                "score_summary_available": bool(state.get("score_summary")),
                "real_metrics_available": bool(state.get("metrics_summary")),
            }
        },
    )
    append_handoff(
        state,
        "EvaluationAgent",
        "OptimizationAgent",
        "evaluation artifacts interpreted",
        ["artifact_bundle_summary", "leaderboard_summary", "score_summary", "metrics_summary"],
    )
    return state
