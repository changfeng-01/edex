from __future__ import annotations

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import inspect_leaderboard, inspect_real_metrics, inspect_score_summary


def run_generic_waveform_agent(state: dict) -> dict:
    state["active_agent"] = "GenericWaveformAgent"
    inputs = state.get("inputs", {})
    detected = []
    if inputs.get("leaderboard"):
        result = inspect_leaderboard(inputs["leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "GenericWaveformAgent", result)
        detected.append("leaderboard")
    if inputs.get("score_summary"):
        result = inspect_score_summary(inputs["score_summary"])
        state["score_summary"] = result.data
        store_tool_result(state, "GenericWaveformAgent", result)
        detected.append("score_summary")
    if inputs.get("real_metrics"):
        result = inspect_real_metrics(inputs["real_metrics"])
        state["metrics_summary"] = result.data
        store_tool_result(state, "GenericWaveformAgent", result)
        detected.append("real_metrics")
    add_message(
        state,
        "GenericWaveformAgent",
        {
            "generic_summary": "Generic waveform-derived artifacts inspected.",
            "detected_available_inputs": detected,
            "evaluation_summary": {
                "leaderboard": bool(state.get("leaderboard_summary")),
                "score_summary": bool(state.get("score_summary")),
                "metrics_summary": bool(state.get("metrics_summary")),
            },
            "generic_next_action": "use shared evaluation and report generation",
        },
    )
    append_handoff(state, "GenericWaveformAgent", "EvaluationAgent", "generic waveform artifacts inspected", ["inputs", "metrics_summary"])
    return state
