from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from goa_eval.multi_agent.schemas import AgentContract


DomainRunner = Callable[[dict], dict]


@dataclass(frozen=True)
class CircuitAgentSpec:
    agent_name: str
    node_name: str
    runner: DomainRunner
    contract: AgentContract
    profiles: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    task_types: tuple[str, ...] = ()
    profile_prefixes: tuple[str, ...] = ()
    task_keywords: tuple[str, ...] = ()
    fallback_input_keys: tuple[str, ...] = ()
    fallback_priority: int = 100
    physics_adapter_name: str = ""


class DomainAgentRegistry:
    def __init__(self, specs: tuple[CircuitAgentSpec, ...] = ()) -> None:
        self._specs: dict[str, CircuitAgentSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: CircuitAgentSpec) -> None:
        if spec.agent_name in self._specs:
            raise ValueError(f"domain agent is already registered: {spec.agent_name}")
        if any(item.node_name == spec.node_name for item in self._specs.values()):
            raise ValueError(f"domain node is already registered: {spec.node_name}")
        self._specs[spec.agent_name] = spec

    def get(self, agent_name: str) -> CircuitAgentSpec:
        try:
            return self._specs[agent_name]
        except KeyError as exc:
            raise KeyError(f"unknown domain agent: {agent_name}") from exc

    def specs(self) -> tuple[CircuitAgentSpec, ...]:
        return tuple(self._specs.values())

    def contracts(self) -> dict[str, AgentContract]:
        return {spec.agent_name: spec.contract for spec in self.specs()}

    def resolve(self, task_type: str, profile: str, inputs: dict) -> dict[str, str]:
        task = str(task_type or "").strip().lower()
        profile_name = str(profile or "").strip().lower()
        input_keys = {str(key) for key in (inputs or {})}
        for spec in self.specs():
            exact_profiles = {value.lower() for value in (*spec.profiles, *spec.aliases)}
            if profile_name and profile_name in exact_profiles:
                return _decision(spec, "exact profile or alias match")
        for spec in self.specs():
            if task and task in {value.lower() for value in spec.task_types}:
                return _decision(spec, "exact task type match")
            if profile_name and any(profile_name.startswith(prefix.lower()) for prefix in spec.profile_prefixes):
                return _decision(spec, "profile prefix match")
            if task and any(keyword.lower() in task for keyword in spec.task_keywords):
                return _decision(spec, "task type keyword match")
        fallbacks = sorted(self.specs(), key=lambda item: item.fallback_priority)
        for spec in fallbacks:
            if spec.fallback_input_keys and input_keys.intersection(spec.fallback_input_keys):
                return _decision(spec, "input type fallback")
        return {
            "selected_domain_agent": "unsupported",
            "handoff_to": "CriticAgent",
            "reason": "insufficient inputs for domain routing",
        }


def _decision(spec: CircuitAgentSpec, reason: str) -> dict[str, str]:
    return {
        "selected_domain_agent": spec.agent_name,
        "handoff_to": spec.agent_name,
        "reason": reason,
    }


def default_domain_agent_registry() -> DomainAgentRegistry:
    from goa_eval.multi_agent.agents.generic_waveform_agent import run_generic_waveform_agent
    from goa_eval.multi_agent.agents.goa_agent import run_goa_agent
    from goa_eval.multi_agent.agents.instrumentation_amplifier_agent import (
        run_instrumentation_amplifier_agent,
    )
    from goa_eval.multi_agent.agents.netlist_agent import run_netlist_agent

    return DomainAgentRegistry(
        (
            CircuitAgentSpec(
                agent_name="GOAAgent",
                node_name="goa",
                runner=run_goa_agent,
                profiles=("goa_8t1c_720",),
                profile_prefixes=("goa",),
                task_keywords=("goa",),
                physics_adapter_name="goa_existing_physics_v4",
                contract=AgentContract(
                    agent_name="GOAAgent",
                    role="Domain specialist for GOA / 8T1C waveform evaluation",
                    description="Interprets existing GOA metrics without changing GOA formulas.",
                    allowed_tools=["inspect_real_summary", "inspect_real_metrics", "inspect_score_summary", "inspect_leaderboard", "inspect_existing_reports"],
                    input_schema=["task", "shared_state", "available_files"],
                    output_schema=["goa_summary", "goa_failure_diagnosis", "goa_next_action"],
                    handoff_policy={"next": ["EvaluationAgent", "TransferCoordinatorAgent", "OptimizationAgent", "CriticAgent"]},
                    failure_policy={"on_missing_metrics": "handoff_to_CriticAgent", "on_unsupported_profile": "reject_with_reason"},
                ),
            ),
            CircuitAgentSpec(
                agent_name="InstrumentationAmplifierAgent",
                node_name="instrumentation_amplifier",
                runner=run_instrumentation_amplifier_agent,
                profiles=("instrumentation_amplifier_three_opamp_compensated_v1",),
                aliases=("three_opamp_7r", "instrumentation_amplifier", "three_opamp_lm324"),
                task_types=("instrumentation_amplifier_optimization",),
                task_keywords=("instrumentation_amplifier",),
                physics_adapter_name="instrumentation_amplifier_three_opamp_v1",
                contract=AgentContract(
                    agent_name="InstrumentationAmplifierAgent",
                    role="Domain specialist for compensated three-op-amp instrumentation amplifiers",
                    description="Evaluates circuit-local electrical state and exports canonical transfer effects.",
                    allowed_tools=["inspect_real_metrics", "inspect_score_summary", "inspect_leaderboard", "inspect_existing_reports"],
                    input_schema=["task", "shared_state", "profile", "scenario_data"],
                    output_schema=["instrumentation_agent_diagnosis", "physical_effect_packet", "target_sensitivity"],
                    handoff_policy={"next": ["EvaluationAgent", "TransferCoordinatorAgent", "CriticAgent"]},
                    failure_policy={"on_missing_objective": "handoff_to_CriticAgent", "on_model_failure": "reject_with_reason"},
                ),
            ),
            CircuitAgentSpec(
                agent_name="GenericWaveformAgent",
                node_name="generic_waveform",
                runner=run_generic_waveform_agent,
                fallback_input_keys=("waveform", "real_metrics", "score_summary", "leaderboard"),
                fallback_priority=10,
                contract=AgentContract(
                    agent_name="GenericWaveformAgent",
                    role="Generic waveform evaluation specialist",
                    description="Summarizes waveform-derived outputs when no circuit specialist matches.",
                    allowed_tools=["inspect_real_metrics", "inspect_score_summary", "inspect_leaderboard"],
                    input_schema=["inputs", "shared_state"],
                    output_schema=["generic_summary", "detected_available_inputs", "generic_next_action"],
                    handoff_policy={"next": ["EvaluationAgent", "CriticAgent"]},
                    failure_policy={"on_missing_inputs": "handoff_to_CriticAgent"},
                ),
            ),
            CircuitAgentSpec(
                agent_name="NetlistAgent",
                node_name="netlist",
                runner=run_netlist_agent,
                task_types=("netlist_inspection",),
                profiles=("generic_netlist",),
                fallback_input_keys=("netlist",),
                fallback_priority=20,
                contract=AgentContract(
                    agent_name="NetlistAgent",
                    role="Netlist inspection specialist",
                    description="Provides a lightweight netlist summary without inventing waveform evidence.",
                    allowed_tools=["inspect_netlist_integrity"],
                    input_schema=["inputs", "shared_state"],
                    output_schema=["netlist_summary", "limitations", "next_steps"],
                    handoff_policy={"next": ["CriticAgent", "ReportAgent"]},
                    failure_policy={"on_parser_gap": "not_implemented_yet"},
                ),
            ),
        )
    )
