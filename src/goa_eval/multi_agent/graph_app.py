from __future__ import annotations

import json
from pathlib import Path

import yaml

from goa_eval.multi_agent.availability import LANGGRAPH_REQUIRED_MESSAGE, check_langgraph_availability
from goa_eval.multi_agent.agents.critic_agent import run_critic_agent
from goa_eval.multi_agent.agents.evaluation_agent import run_evaluation_agent
from goa_eval.multi_agent.agents.generic_waveform_agent import run_generic_waveform_agent
from goa_eval.multi_agent.agents.goa_agent import run_goa_agent
from goa_eval.multi_agent.agents.netlist_agent import run_netlist_agent
from goa_eval.multi_agent.agents.optimization_agent import run_optimization_agent
from goa_eval.multi_agent.agents.report_agent import run_report_agent
from goa_eval.multi_agent.agents.router_agent import run_router_agent
from goa_eval.multi_agent.agents.sky130_agent import run_sky130_agent
from goa_eval.multi_agent.agents.supervisor_agent import run_supervisor_agent
from goa_eval.multi_agent.memory import write_memory
from goa_eval.multi_agent.schemas import MultiAgentTask
from goa_eval.multi_agent.state import new_state_from_task
from goa_eval.multi_agent.trace import write_trace
from goa_eval.multi_agent.handoff import write_handoff_trace


def load_task(path: Path) -> MultiAgentTask:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return MultiAgentTask(
        task_name=str(raw.get("task_name", path.stem)),
        task_type=str(raw.get("task_type", "")),
        profile=str(raw.get("profile", "")),
        inputs=dict(raw.get("inputs", {}) or {}),
        objectives=dict(raw.get("objectives", {}) or {}),
        limits=dict(raw.get("limits", {}) or {}),
        validity=dict(raw.get("validity", {}) or {}),
    )


def build_multi_agent_graph():
    if not check_langgraph_availability()["available"]:
        raise RuntimeError(LANGGRAPH_REQUIRED_MESSAGE)
    from langgraph.graph import END, StateGraph

    graph = StateGraph(dict)
    graph.add_node("supervisor", run_supervisor_agent)
    graph.add_node("router", run_router_agent)
    graph.add_node("goa", run_goa_agent)
    graph.add_node("sky130", run_sky130_agent)
    graph.add_node("generic_waveform", run_generic_waveform_agent)
    graph.add_node("netlist", run_netlist_agent)
    graph.add_node("critic_after_domain", run_critic_agent)
    graph.add_node("evaluation", run_evaluation_agent)
    graph.add_node("critic_after_evaluation", run_critic_agent)
    graph.add_node("optimization", run_optimization_agent)
    graph.add_node("critic_after_optimization", run_critic_agent)
    graph.add_node("report", run_report_agent)

    graph.set_entry_point("supervisor")
    graph.add_edge("supervisor", "router")
    graph.add_conditional_edges(
        "router",
        _route_from_state,
        {
            "GOAAgent": "goa",
            "SKY130Agent": "sky130",
            "GenericWaveformAgent": "generic_waveform",
            "NetlistAgent": "netlist",
            "unsupported": "critic_after_domain",
        },
    )
    graph.add_edge("goa", "critic_after_domain")
    graph.add_edge("sky130", "critic_after_domain")
    graph.add_edge("generic_waveform", "critic_after_domain")
    graph.add_edge("netlist", "critic_after_domain")
    graph.add_conditional_edges(
        "critic_after_domain",
        _after_domain,
        {"evaluation": "evaluation", "report": "report"},
    )
    graph.add_edge("evaluation", "critic_after_evaluation")
    graph.add_edge("critic_after_evaluation", "optimization")
    graph.add_edge("optimization", "critic_after_optimization")
    graph.add_edge("critic_after_optimization", "report")
    graph.add_edge("report", END)
    return graph.compile()


def run_multi_agent_task(task_path: Path, output_dir: Path) -> dict:
    availability = check_langgraph_availability()
    if not availability["available"]:
        raise RuntimeError(LANGGRAPH_REQUIRED_MESSAGE)
    output_dir.mkdir(parents=True, exist_ok=True)
    task = load_task(task_path)
    state = new_state_from_task(task, str(output_dir))
    _write_plan(output_dir, state)
    app = build_multi_agent_graph()
    final_state = app.invoke(state)
    _write_outputs(output_dir, final_state)
    return final_state


def _write_outputs(output_dir: Path, state: dict) -> None:
    _write_plan(output_dir, state)
    write_trace(output_dir / "multi_agent_trace.jsonl", state.get("trace_records", []))
    write_handoff_trace(output_dir / "multi_agent_handoff_trace.jsonl", state.get("handoff_records", []))
    critic_report = {"verdicts": state.get("critic_verdicts", [])}
    (output_dir / "critic_report.json").write_text(json.dumps(critic_report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_memory(output_dir / "multi_agent_memory.json", state)


def _write_plan(output_dir: Path, state: dict) -> None:
    plan = {
        "schema_version": "1.0",
        "result_version": "1.0",
        "task_name": state.get("task_name"),
        "task_type": state.get("task_type"),
        "profile": state.get("profile"),
        "selected_domain_agent": state.get("selected_domain_agent"),
        "data_source": state.get("data_source"),
        "engineering_validity": state.get("engineering_validity"),
    }
    (output_dir / "multi_agent_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def _route_from_state(state: dict) -> str:
    return state.get("selected_domain_agent") or "unsupported"


def _after_domain(state: dict) -> str:
    if state.get("selected_domain_agent") in {"unsupported", "NetlistAgent"}:
        return "report"
    return "evaluation"
