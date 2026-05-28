from __future__ import annotations

from pathlib import Path

import pandas as pd

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import (
    generate_candidates,
    inspect_candidates,
    inspect_optimization_history,
    inspect_optimization_leaderboard,
)


def run_optimization_agent(state: dict) -> dict:
    state["active_agent"] = "OptimizationAgent"
    inputs = state.get("inputs", {})
    existing_candidates = inputs.get("best_next_candidates") or inputs.get("next_candidates")
    if inputs.get("optimization_history"):
        result = inspect_optimization_history(inputs["optimization_history"])
        state["optimization_history_summary"] = result.data
        store_tool_result(state, "OptimizationAgent", result)
    if inputs.get("optimization_leaderboard") and not state.get("leaderboard_summary"):
        result = inspect_optimization_leaderboard(inputs["optimization_leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "OptimizationAgent", result)
    if existing_candidates:
        state["candidate_summary"] = _summarize_existing_candidates(existing_candidates, state)
        if inputs.get("param_space"):
            result = inspect_candidates(
                existing_candidates,
                inputs["param_space"],
                int((state.get("limits") or {}).get("max_parameter_changes_per_candidate", 2)),
            )
            state["candidate_summary"]["risk_summary"] = result.data
            store_tool_result(state, "OptimizationAgent", result)
        add_message(state, "OptimizationAgent", {"candidate_summary": state.get("candidate_summary")})
        append_handoff(
            state,
            "OptimizationAgent",
            "CriticAgent",
            "existing candidate artifact accepted",
            ["candidate_summary", "optimization_history_summary"],
        )
        return state
    leaderboard = inputs.get("leaderboard") or inputs.get("optimization_leaderboard")
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


def _summarize_existing_candidates(path_text: str | Path, state: dict) -> dict:
    path = Path(path_text)
    frame = pd.read_csv(path) if path.exists() else pd.DataFrame()
    has_rerun = any((state.get("inputs") or {}).get(key) for key in ["rerun_run_dir", "rerun_leaderboard", "rerun_score_summary", "rerun_real_metrics"])
    return {
        "source": "existing_artifact",
        "status": "decision_ready" if has_rerun else "awaiting_rerun_results",
        "next_candidates_path": str(path),
        "candidate_count": int(len(frame)),
        "columns": list(frame.columns),
    }
