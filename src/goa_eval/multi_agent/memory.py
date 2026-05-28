from __future__ import annotations

import json
from pathlib import Path

from goa_eval.multi_agent.schemas import MultiAgentMemory


def build_memory(state: dict) -> MultiAgentMemory:
    executed_agents = [record.get("agent_name") for record in state.get("trace_records", []) if record.get("agent_name")]
    executed_tools = [record.get("tool_name") for record in state.get("trace_records", []) if record.get("tool_name")]
    return MultiAgentMemory(
        task_metadata={"task_name": state.get("task_name"), "task_type": state.get("task_type")},
        selected_profile=state.get("profile"),
        selected_domain_agent=state.get("selected_domain_agent"),
        active_agents=sorted(set(executed_agents)),
        executed_agents=executed_agents,
        executed_tools=executed_tools,
        handoff_records=state.get("handoff_records", []),
        best_candidate_summary=(state.get("leaderboard_summary") or {}).get("best_candidate", {}),
        generated_candidate_summary=state.get("candidate_summary", {}),
        warnings=state.get("warnings", []),
        failures=state.get("failures", []),
        suggested_next_actions=_suggestions(state),
        data_source=state.get("data_source", "real_simulation_csv"),
        engineering_validity=state.get("engineering_validity", "simulation_only"),
    )


def write_memory(path: Path, state: dict) -> dict:
    memory = build_memory(state).to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    return memory


def _suggestions(state: dict) -> list[str]:
    suggestions = []
    domain = state.get("selected_domain_agent")
    if domain == "NetlistAgent":
        suggestions.append("add waveform, score_summary, or leaderboard before optimization")
    if state.get("candidate_summary", {}).get("candidate_count"):
        suggestions.append("replay next_candidates through the existing deterministic simulation flow")
    if (state.get("generated_files") or {}).get("optimization_loop_record"):
        suggestions.append("review optimization_loop_record.json and optimization_decision_card.md before claiming optimization progress")
    if state.get("warnings"):
        suggestions.append("review warnings before presenting results")
    return suggestions or ["continue deterministic evaluation with simulation-only boundary"]
