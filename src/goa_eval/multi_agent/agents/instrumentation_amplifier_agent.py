from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from goa_eval.instrumentation_amplifier import (
    InstrumentationAmplifierPhysicsAdapter,
    aggregate_scenario_results,
    estimate_csv_sensitivity,
    load_observed_scenarios,
    merge_sensitivity_artifacts,
    scenario_key,
)
from goa_eval.multi_agent.agents._utils import add_message
from goa_eval.multi_agent.handoff import append_handoff


def run_instrumentation_amplifier_agent(state: dict) -> dict:
    state["active_agent"] = "InstrumentationAmplifierAgent"
    inputs = state.get("inputs", {})
    objectives = state.get("objectives", {})
    design = dict(inputs.get("operating_point", {}) or {})
    adapter = InstrumentationAmplifierPhysicsAdapter()
    scenarios = list(inputs.get("pvt_scenarios", []) or [{}])
    observations: dict[str, dict] = {}
    if inputs.get("scenario_csv") and inputs.get("sample_id"):
        observations = load_observed_scenarios(
            inputs["scenario_csv"], sample_id=str(inputs["sample_id"])
        )
    scenario_results = []
    for scenario in scenarios:
        key = scenario_key(scenario)
        try:
            scenario_results.append(
                adapter.evaluate_scenario(
                    design,
                    scenario,
                    objectives=objectives,
                    opamp_model=dict(inputs.get("opamp_model", {}) or {}),
                    observation=observations.get(key),
                    pvt_coefficients=inputs.get("pvt_coefficients"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            scenario_results.append(
                {
                "scenario_key": key,
                "status": "not_evaluable",
                "pvt_status": "missing",
                "missing_required_inputs": [str(exc)],
                "metrics": {},
                "metric_status": {},
                "data_source": "analytic_model_proxy",
                }
            )
    aggregate = aggregate_scenario_results(scenario_results)
    if any(result.get("status") == "not_evaluable" for result in scenario_results):
        status = "not_evaluable"
    else:
        status = aggregate["status"]
    data_source = (
        "real_simulation_csv"
        if any(result.get("data_source") == "real_simulation_csv" for result in scenario_results)
        else "analytic_model_proxy"
    )
    diagnosis = {
        "domain": "three_opamp_instrumentation_amplifier",
        "profile": state.get("profile"),
        "physics_version": adapter.physics_version,
        "task_head_version": adapter.task_head_version,
        "status": status,
        "data_source": data_source,
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
        "scenario_results": scenario_results,
        "pvt_aggregate": aggregate,
        "calibration_namespace": {
            "agent": "InstrumentationAmplifierAgent",
            "profile": state.get("profile"),
            "physics_version": adapter.physics_version,
            "task_head_version": adapter.task_head_version,
            "corner_set": [result.get("scenario_key") for result in scenario_results],
        },
    }
    first_result = scenario_results[0]
    local_state = adapter._state_from_result(first_result)
    packet = adapter.to_canonical_effects(local_state, local_state)
    sensitivity = adapter.estimate_sensitivity(
        None,
        {
            **design,
            "target_differential_gain": objectives.get("target_differential_gain", 1.0),
        },
    )
    if inputs.get("sensitivity_csv"):
        observed_sensitivity = estimate_csv_sensitivity(
            pd.read_csv(inputs["sensitivity_csv"]),
            effect_names=tuple(packet.effects),
            profile=str(state.get("profile") or adapter.profile_name),
        )
        sensitivity = merge_sensitivity_artifacts(sensitivity, observed_sensitivity)
    state["instrumentation_agent_diagnosis"] = diagnosis
    state["domain_diagnosis"] = diagnosis
    state["physical_effect_packet"] = packet.as_dict()
    state["target_sensitivity"] = sensitivity.as_dict()
    output_dir = Path(state.get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "instrumentation_agent_diagnosis": (
            output_dir / "instrumentation_agent_diagnosis.json",
            diagnosis,
        ),
        "physical_effect_packet": (
            output_dir / "physical_effect_packet.json",
            packet.as_dict(),
        ),
        "target_sensitivity": (
            output_dir / "target_sensitivity.json",
            sensitivity.as_dict(),
        ),
    }
    for name, (path, payload) in artifacts.items():
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.setdefault("generated_files", {})[name] = str(path)
    add_message(state, "InstrumentationAmplifierAgent", diagnosis)
    append_handoff(
        state,
        "InstrumentationAmplifierAgent",
        "EvaluationAgent",
        "instrumentation-amplifier domain state prepared",
        [
            "instrumentation_agent_diagnosis",
            "physical_effect_packet",
            "target_sensitivity",
        ],
    )
    return state
