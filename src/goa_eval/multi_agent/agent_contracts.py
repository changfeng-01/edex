from __future__ import annotations

from goa_eval.multi_agent.schemas import AgentContract


def get_agent_contracts() -> dict[str, AgentContract]:
    return {
        "SupervisorAgent": AgentContract(
            agent_name="SupervisorAgent",
            role="Global execution supervisor",
            description="Maintains shared state and controls the local multi-agent flow without evaluating metrics directly.",
            allowed_tools=["inspect_task_inputs"],
            input_schema=["task", "shared_state"],
            output_schema=["agent_plan", "next_agent"],
            handoff_policy={"next": ["RouterAgent", "CriticAgent"]},
            failure_policy={"on_invalid_task": "handoff_to_CriticAgent"},
        ),
        "RouterAgent": AgentContract(
            agent_name="RouterAgent",
            role="Profile-aware router",
            description="Selects the domain specialist from task_type, profile, and available inputs.",
            allowed_tools=["inspect_task_inputs"],
            input_schema=["task_type", "profile", "inputs"],
            output_schema=["selected_domain_agent", "routing_reason"],
            handoff_policy={"next": ["GOAAgent", "SKY130Agent", "GenericWaveformAgent", "NetlistAgent", "CriticAgent"]},
            failure_policy={"on_unsupported_profile": "handoff_to_CriticAgent"},
        ),
        "GOAAgent": AgentContract(
            agent_name="GOAAgent",
            role="Domain specialist for GOA / 8T1C waveform evaluation",
            description="Interprets GOA metrics, stage risk, overlap, ripple, voltage loss, and false triggers.",
            allowed_tools=["inspect_real_metrics", "inspect_score_summary", "inspect_leaderboard"],
            input_schema=["task", "shared_state", "available_files"],
            output_schema=["goa_summary", "goa_failure_diagnosis", "goa_next_action"],
            handoff_policy={"next": ["EvaluationAgent", "OptimizationAgent", "CriticAgent"]},
            failure_policy={"on_missing_metrics": "handoff_to_CriticAgent", "on_unsupported_profile": "reject_with_reason"},
        ),
        "SKY130Agent": AgentContract(
            agent_name="SKY130Agent",
            role="Domain specialist for SKY130 / ngspice low-voltage circuits",
            description="Interprets timing, hard constraints, score, candidate risk, and param_space boundaries.",
            allowed_tools=["inspect_real_metrics", "inspect_score_summary", "inspect_leaderboard", "inspect_candidates"],
            input_schema=["task", "shared_state", "available_files"],
            output_schema=["sky130_summary", "best_candidate_summary", "timing_summary", "sky130_next_action"],
            handoff_policy={"next": ["EvaluationAgent", "OptimizationAgent", "CriticAgent"]},
            failure_policy={"on_missing_leaderboard": "handoff_to_CriticAgent"},
        ),
        "GenericWaveformAgent": AgentContract(
            agent_name="GenericWaveformAgent",
            role="Generic waveform evaluation specialist",
            description="Summarizes available waveform-derived outputs when the profile is not domain-specific.",
            allowed_tools=["inspect_real_metrics", "inspect_score_summary", "inspect_leaderboard"],
            input_schema=["inputs", "shared_state"],
            output_schema=["generic_summary", "detected_available_inputs", "generic_next_action"],
            handoff_policy={"next": ["EvaluationAgent", "CriticAgent"]},
            failure_policy={"on_missing_inputs": "handoff_to_CriticAgent"},
        ),
        "NetlistAgent": AgentContract(
            agent_name="NetlistAgent",
            role="Netlist inspection specialist",
            description="Provides a lightweight netlist summary or a not_implemented_yet handoff when waveform data is absent.",
            allowed_tools=["inspect_task_inputs"],
            input_schema=["inputs", "shared_state"],
            output_schema=["netlist_summary", "limitations", "next_steps"],
            handoff_policy={"next": ["CriticAgent", "ReportAgent"]},
            failure_policy={"on_parser_gap": "not_implemented_yet"},
        ),
        "EvaluationAgent": AgentContract(
            agent_name="EvaluationAgent",
            role="Shared evaluation result interpreter",
            description="Reads existing leaderboard, score_summary, and real_metrics outputs via tools.",
            allowed_tools=["inspect_leaderboard", "inspect_score_summary", "inspect_real_metrics"],
            input_schema=["inputs", "shared_state"],
            output_schema=["leaderboard_summary", "score_summary", "metrics_summary"],
            handoff_policy={"next": ["OptimizationAgent", "CriticAgent"]},
            failure_policy={"on_missing_evaluation": "handoff_to_CriticAgent"},
        ),
        "OptimizationAgent": AgentContract(
            agent_name="OptimizationAgent",
            role="Shared deterministic candidate generation agent",
            description="Generates next candidates only through optimizer wrappers and inspects candidate risk.",
            allowed_tools=["generate_candidates", "inspect_candidates"],
            input_schema=["leaderboard", "param_space", "limits"],
            output_schema=["candidate_summary", "next_candidates_path"],
            handoff_policy={"next": ["CriticAgent", "ReportAgent"]},
            failure_policy={"on_missing_param_space": "skip_optimization_with_warning"},
        ),
        "CriticAgent": AgentContract(
            agent_name="CriticAgent",
            role="Engineering boundary and contract critic",
            description="Checks files, schemas, boundaries, metrics, candidate risk, tool permissions, and handoffs.",
            allowed_tools=["check_schema_and_boundary", "inspect_candidates"],
            input_schema=["shared_state", "tool_results", "handoff_records"],
            output_schema=["critic_verdicts", "warnings", "failures"],
            handoff_policy={"next": ["EvaluationAgent", "OptimizationAgent", "ReportAgent"]},
            failure_policy={"on_reject": "write_failure_report"},
        ),
        "ReportAgent": AgentContract(
            agent_name="ReportAgent",
            role="Final local report writer",
            description="Summarizes the run without inventing results or exceeding simulation-only scope.",
            allowed_tools=["write_multi_agent_report"],
            input_schema=["final_state", "memory", "trace", "critic_report"],
            output_schema=["multi_agent_decision_report"],
            handoff_policy={"next": ["END"]},
            failure_policy={"on_report_error": "record_failure"},
        ),
    }


def is_tool_allowed(agent_name: str, tool_name: str) -> bool:
    contract = get_agent_contracts().get(agent_name)
    return bool(contract and tool_name in contract.allowed_tools)
