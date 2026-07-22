from __future__ import annotations

from goa_eval.multi_agent.domain_registry import default_domain_agent_registry
from goa_eval.multi_agent.schemas import AgentContract


def get_agent_contracts() -> dict[str, AgentContract]:
    registry = default_domain_agent_registry()
    domain_agent_names = [spec.agent_name for spec in registry.specs()]
    contracts = {
        "SupervisorAgent": AgentContract(
            agent_name="SupervisorAgent",
            role="Global execution supervisor",
            description="Maintains shared state and controls the local multi-agent flow without evaluating metrics directly.",
            allowed_tools=["inspect_task_inputs", "inspect_artifact_bundle"],
            input_schema=["task", "shared_state"],
            output_schema=["agent_plan", "next_agent"],
            handoff_policy={"next": ["RouterAgent", "CriticAgent"]},
            failure_policy={"on_invalid_task": "handoff_to_CriticAgent"},
        ),
        "RouterAgent": AgentContract(
            agent_name="RouterAgent",
            role="Profile-aware router",
            description="Selects a registered domain specialist from task type, profile, and inputs.",
            allowed_tools=["inspect_task_inputs", "inspect_artifact_bundle"],
            input_schema=["task_type", "profile", "inputs"],
            output_schema=["selected_domain_agent", "routing_reason"],
            handoff_policy={"next": [*domain_agent_names, "CriticAgent"]},
            failure_policy={"on_unsupported_profile": "handoff_to_CriticAgent"},
        ),
        "EvaluationAgent": AgentContract(
            agent_name="EvaluationAgent",
            role="Shared evaluation result interpreter",
            description="Reads existing leaderboard, score summary, and metric outputs via tools.",
            allowed_tools=[
                "inspect_leaderboard",
                "inspect_score_summary",
                "inspect_real_metrics",
                "inspect_artifact_bundle",
            ],
            input_schema=["inputs", "shared_state"],
            output_schema=["leaderboard_summary", "score_summary", "metrics_summary"],
            handoff_policy={
                "next": ["TransferCoordinatorAgent", "OptimizationAgent", "CriticAgent"]
            },
            failure_policy={"on_missing_evaluation": "handoff_to_CriticAgent"},
        ),
        "OptimizationAgent": AgentContract(
            agent_name="OptimizationAgent",
            role="Shared deterministic candidate generation agent",
            description="Projects bounds and coupling constraints, evaluates barriers, deduplicates, and exports candidates.",
            allowed_tools=[
                "generate_candidates",
                "inspect_candidates",
                "inspect_optimization_history",
                "inspect_optimization_leaderboard",
            ],
            input_schema=["leaderboard", "param_space", "transfer_projection", "limits"],
            output_schema=["candidate_summary", "next_candidates_path"],
            handoff_policy={"next": ["CriticAgent", "ReportAgent"]},
            failure_policy={"on_missing_param_space": "skip_optimization_with_warning"},
        ),
        "TransferCoordinatorAgent": AgentContract(
            agent_name="TransferCoordinatorAgent",
            role="Shared cross-circuit physical-effect coordinator",
            description="Checks effect intersection, OOD diagnostics and target identifiability before projecting actions.",
            allowed_tools=[],
            input_schema=["source_effect_packet", "target_sensitivity", "parameter_profile"],
            output_schema=["transfer_projection", "transfer_diagnostics"],
            handoff_policy={"next": ["CriticAgent", "OptimizationAgent"]},
            failure_policy={"on_reject": "continue_without_projected_action"},
        ),
        "CriticAgent": AgentContract(
            agent_name="CriticAgent",
            role="Engineering boundary and contract critic",
            description="Checks files, schemas, boundaries, metrics, candidate risk, tool permissions, and handoffs.",
            allowed_tools=[
                "check_schema_and_boundary",
                "inspect_candidates",
                "inspect_netlist_integrity",
                "inspect_artifact_bundle",
                "inspect_validation_summary",
                "inspect_existing_reports",
            ],
            input_schema=["shared_state", "tool_results", "handoff_records"],
            output_schema=[
                "critic_verdicts",
                "warnings",
                "failures",
                "severity",
                "risk_type",
                "risks",
            ],
            handoff_policy={
                "next": ["EvaluationAgent", "OptimizationAgent", "ReportAgent"]
            },
            failure_policy={"on_reject": "write_failure_report"},
        ),
        "ReportAgent": AgentContract(
            agent_name="ReportAgent",
            role="Final local report writer",
            description="Summarizes the run without inventing results or exceeding simulation-only scope.",
            allowed_tools=["write_multi_agent_report"],
            input_schema=["final_state", "memory", "trace", "critic_report"],
            output_schema=[
                "multi_agent_decision_report",
                "optimization_loop_record",
                "optimization_decision_card",
            ],
            handoff_policy={"next": ["END"]},
            failure_policy={"on_report_error": "record_failure"},
        ),
    }
    contracts.update(registry.contracts())
    return contracts


def is_tool_allowed(agent_name: str, tool_name: str) -> bool:
    contract = get_agent_contracts().get(agent_name)
    return bool(contract and tool_name in contract.allowed_tools)
