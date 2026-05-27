from __future__ import annotations

from pathlib import Path

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import generate_candidates, inspect_candidates


def run_optimization_agent(state: dict) -> dict:
    state["active_agent"] = "OptimizationAgent"
    inputs = state.get("inputs", {})
    leaderboard = inputs.get("leaderboard")
    param_space = inputs.get("param_space")
    if not leaderboard or not param_space:
        state.setdefault("warnings", []).append("skip optimization: leaderboard or param_space missing")
        state["candidate_summary"] = {"candidate_count": 0, "skipped": True}
        add_message(state, "OptimizationAgent", {"skip_optimization": "leaderboard or param_space missing"})
        append_handoff(state, "OptimizationAgent", "CriticAgent", "optimization skipped", ["candidate_summary"])
        return state
    result = generate_candidates(leaderboard, param_space, state["output_dir"], int((state.get("limits") or {}).get("max_candidates", 10)))
    state["candidate_summary"] = result.data
    if result.data.get("next_candidates_path"):
        state.setdefault("generated_files", {})["next_candidates"] = result.data["next_candidates_path"]
    store_tool_result(state, "OptimizationAgent", result)
    candidate_path = result.data.get("next_candidates_path")
    if candidate_path and Path(candidate_path).exists():
        inspected = inspect_candidates(candidate_path, param_space, int((state.get("limits") or {}).get("max_parameter_changes_per_candidate", 2)))
        state["candidate_summary"]["risk_summary"] = inspected.data
        store_tool_result(state, "OptimizationAgent", inspected)
    add_message(state, "OptimizationAgent", {"candidate_summary": state.get("candidate_summary")})
    append_handoff(state, "OptimizationAgent", "CriticAgent", "candidate generation completed through optimizer wrapper", ["candidate_summary"])
    return state
