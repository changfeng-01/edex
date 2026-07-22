from __future__ import annotations

import json

import pandas as pd
import pytest

from goa_eval.circuit_profiles import load_circuit_profiles, resolve_circuit_profile
from goa_eval.domain import CircuitParameterProfile
from goa_eval.instrumentation_amplifier import (
    InstrumentationAmplifierPhysicsAdapter,
    aggregate_scenario_results,
    estimate_central_log_sensitivity,
    estimate_csv_sensitivity,
    load_observed_scenarios,
)
from goa_eval.multi_agent.agents.instrumentation_amplifier_agent import (
    run_instrumentation_amplifier_agent,
)
from goa_eval.multi_agent.critic import run_critic_checks


DESIGN = {
    "R": 10.0e3,
    "RG": 2.0e3,
    "RD": 10.0e3,
    "KD_plus": 1.2,
    "KD_minus": 1.2,
    "CF": 10.0e-12,
}


def test_registered_circuit_profile_has_six_design_actions_and_required_gain_target() -> None:
    profile = resolve_circuit_profile(
        "instrumentation_amplifier_three_opamp_compensated_v1",
        load_circuit_profiles(),
    )
    parameter_profile = CircuitParameterProfile.from_circuit_profile(profile)

    assert [item.column for item in parameter_profile.optimizable_parameters] == [
        "R",
        "RG",
        "RD",
        "KD_plus",
        "KD_minus",
        "CF",
    ]
    assert profile["objectives"]["required_inputs"] == ["target_differential_gain"]
    assert profile["metrics"]["power_w"]["required"] is False


def test_observed_long_table_uses_fixed_scenario_key_and_overrides_proxy_fields(tmp_path) -> None:
    path = tmp_path / "scenarios.csv"
    pd.DataFrame(
        [
            {
                "sample_id": "amp-1",
                "corner": "SS",
                "temperature_c": 85.0,
                "supply_v": 4.5,
                "differential_gain": 12.7,
                "bandwidth_hz": 8000.0,
            },
            {
                "sample_id": "other",
                "corner": "TT",
                "temperature_c": 25.0,
                "supply_v": 5.0,
                "differential_gain": 999.0,
            },
        ]
    ).to_csv(path, index=False)

    observed = load_observed_scenarios(path, sample_id="amp-1")
    adapter = InstrumentationAmplifierPhysicsAdapter()
    result = adapter.evaluate_scenario(
        DESIGN,
        {"corner": "SS", "temperature_c": 85.0, "supply_v": 4.5},
        objectives={"target_differential_gain": 13.2},
        opamp_model={"A0": 1.0e5, "GBW": 1.0e6},
        observation=observed["SS|85|4.5"],
    )

    assert result["scenario_key"] == "SS|85|4.5"
    assert result["metrics"]["differential_gain"] == pytest.approx(12.7)
    assert result["metrics"]["bandwidth_hz"] == pytest.approx(8000.0)
    assert result["metric_status"]["differential_gain"] == "observed"
    assert result["metric_status"]["cmrr_db"] == "missing"
    assert result["pvt_status"] == "partial_observed"
    assert result["data_source"] == "real_simulation_csv"


def test_non_nominal_pvt_without_observation_or_explicit_coefficients_is_missing() -> None:
    adapter = InstrumentationAmplifierPhysicsAdapter()

    result = adapter.evaluate_scenario(
        DESIGN,
        {"corner": "SS", "temperature_c": 85.0, "supply_v": 4.5},
        objectives={"target_differential_gain": 13.2},
        opamp_model={"A0": 1.0e5, "GBW": 1.0e6},
    )

    assert result["pvt_status"] == "missing"
    assert result["status"] == "not_evaluable"
    assert result["metrics"] == {}


def test_explicit_pvt_coefficients_produce_proxy_and_worse_ss_barrier() -> None:
    adapter = InstrumentationAmplifierPhysicsAdapter()
    opamp = {
        "A0": 1.0e5,
        "GBW": 2.0e6,
        "SR": 1.0e6,
        "Rout": 50.0,
        "input_common_min_v": -2.0,
        "input_common_max_v": 2.0,
        "output_low_v": -4.0,
        "output_high_v": 4.0,
    }
    coefficients = {
        "corners": {"SS": {"A0": 0.7, "GBW": 0.4, "SR": 0.4, "Rout": 2.0}},
        "temperature": {"reference_c": 25.0, "A0_per_c": -0.001, "GBW_per_c": -0.003, "SR_per_c": -0.003, "Rout_per_c": 0.004},
        "supply": {"reference_v": 5.0, "GBW_exponent": 1.0, "SR_exponent": 1.0},
    }
    nominal = adapter.evaluate_scenario(
        DESIGN,
        {"corner": "TT", "temperature_c": 25.0, "supply_v": 5.0},
        objectives={"target_differential_gain": 13.2},
        opamp_model=opamp,
    )
    slow = adapter.evaluate_scenario(
        DESIGN,
        {"corner": "SS", "temperature_c": 85.0, "supply_v": 4.5},
        objectives={"target_differential_gain": 13.2},
        opamp_model=opamp,
        pvt_coefficients=coefficients,
    )

    assert nominal["pvt_status"] == "nominal_model"
    assert slow["pvt_status"] == "proxy"
    assert slow["metrics"]["bandwidth_hz"] < nominal["metrics"]["bandwidth_hz"]
    assert slow["barrier"]["value"] >= nominal["barrier"]["value"]


def test_incomplete_non_nominal_pvt_coefficients_are_missing_not_silent_nominal() -> None:
    adapter = InstrumentationAmplifierPhysicsAdapter()

    result = adapter.evaluate_scenario(
        DESIGN,
        {"corner": "SS", "temperature_c": 85.0, "supply_v": 4.5},
        objectives={"target_differential_gain": 13.2},
        opamp_model={"A0": 1.0e5, "GBW": 1.0e6, "SR": 1.0e6, "Rout": 50.0},
        pvt_coefficients={"corners": {"SS": {"A0": 0.7, "GBW": 0.5}}},
    )

    assert result["status"] == "not_evaluable"
    assert result["pvt_status"] == "missing"
    assert result["scenario_key"] == "SS|85|4.5"
    assert "temperature" in result["missing_required_inputs"][0]


def test_domain_agent_keeps_valid_scenarios_when_one_pvt_scenario_is_missing(tmp_path) -> None:
    state = {
        "profile": "instrumentation_amplifier_three_opamp_compensated_v1",
        "objectives": {"target_differential_gain": 13.2},
        "inputs": {
            "operating_point": DESIGN,
            "opamp_model": {"A0": 1.0e5, "GBW": 1.0e6, "SR": 1.0e6, "Rout": 50.0},
            "pvt_scenarios": [
                {"corner": "TT", "temperature_c": 25.0, "supply_v": 5.0},
                {"corner": "SS", "temperature_c": 85.0, "supply_v": 4.5},
            ],
            "pvt_coefficients": {"corners": {"SS": {"A0": 0.7, "GBW": 0.5}}},
        },
        "output_dir": str(tmp_path),
    }

    diagnosis = run_instrumentation_amplifier_agent(state)["instrumentation_agent_diagnosis"]

    assert [item["scenario_key"] for item in diagnosis["scenario_results"]] == [
        "TT|25|5",
        "SS|85|4.5",
    ]
    assert diagnosis["scenario_results"][0]["pvt_status"] == "nominal_model"
    assert diagnosis["scenario_results"][1]["pvt_status"] == "missing"
    assert diagnosis["pvt_aggregate"]["usable_scenario_count"] == 1


def test_missing_required_gain_target_is_not_evaluable_but_power_is_optional() -> None:
    adapter = InstrumentationAmplifierPhysicsAdapter()

    missing_target = adapter.evaluate_scenario(DESIGN, {}, objectives={})
    no_power = adapter.evaluate_scenario(
        DESIGN,
        {},
        objectives={"target_differential_gain": 13.2},
        opamp_model={
            "A0": 1.0e5,
            "GBW": 1.0e6,
            "SR": 1.0e6,
            "input_common_min_v": -2.0,
            "input_common_max_v": 2.0,
        },
    )

    assert missing_target["status"] == "not_evaluable"
    assert "target_differential_gain" in missing_target["missing_required_inputs"]
    assert no_power["task_evaluation"]["status"] == "partial"
    assert no_power["task_evaluation"]["score"] is not None


def test_scenario_aggregation_is_half_weighted_mean_half_worst_and_barrier_max() -> None:
    aggregated = aggregate_scenario_results(
        [
            {"scenario_key": "TT", "distance": 0.2, "weight": 1.0, "barrier": {"value": 0.1}},
            {"scenario_key": "SS", "distance": 0.8, "weight": 1.0, "barrier": {"value": 0.9}},
        ]
    )

    assert aggregated["distance"] == pytest.approx(0.5 * 0.5 + 0.5 * 0.8)
    assert aggregated["barrier"] == pytest.approx(0.9)
    assert aggregated["worst_scenario"] == "SS"


def test_central_log_sensitivity_and_csv_override_require_matched_pairs() -> None:
    artifact = estimate_central_log_sensitivity(
        lambda values: {"effect": 2.0 * values["R"]},
        {"R": 10.0, "RG": 2.0},
        effect_names=("effect",),
        relative_step=1.0e-4,
        profile="amp",
        scenario_key="TT",
    )
    frame = pd.DataFrame(
        [
            {"baseline_id": "b1", "scenario_key": "TT", "parameter": "R", "perturbation_sign": -1, "log_step": 0.01, "effect": 0.8},
            {"baseline_id": "b1", "scenario_key": "TT", "parameter": "R", "perturbation_sign": 1, "log_step": 0.01, "effect": 1.2},
        ]
    )
    observed = estimate_csv_sensitivity(frame, effect_names=("effect",))

    assert artifact.scenario_jacobians["TT"]["effect"]["R"] == pytest.approx(20.0, rel=1.0e-4)
    assert observed.scenario_jacobians["TT"]["effect"]["R"] == pytest.approx(20.0)
    broken = frame.iloc[:1]
    with pytest.raises(ValueError, match="positive and negative"):
        estimate_csv_sensitivity(broken, effect_names=("effect",))


def test_domain_agent_writes_all_new_artifacts_with_honest_analytic_boundary(tmp_path) -> None:
    state = {
        "profile": "instrumentation_amplifier_three_opamp_compensated_v1",
        "objectives": {"target_differential_gain": 13.2},
        "inputs": {"operating_point": DESIGN},
        "output_dir": str(tmp_path),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    result = run_instrumentation_amplifier_agent(state)

    diagnosis = json.loads((tmp_path / "instrumentation_agent_diagnosis.json").read_text())
    packet = json.loads((tmp_path / "physical_effect_packet.json").read_text())
    sensitivity = json.loads((tmp_path / "target_sensitivity.json").read_text())
    assert diagnosis["status"] == "not_evaluable"
    assert diagnosis["data_source"] == "analytic_model_proxy"
    assert diagnosis["engineering_validity"] == "simulation_only"
    assert diagnosis["must_resimulate"] is True
    assert packet["schema_version"] == "circuitpilot.physical-effect.v1"
    assert sensitivity["profile"] == state["profile"]
    assert result["generated_files"]["instrumentation_agent_diagnosis"].endswith(
        "instrumentation_agent_diagnosis.json"
    )


def test_critic_accepts_analytic_proxy_as_diagnostic_boundary_for_instrumentation_agent() -> None:
    verdict = run_critic_checks(
        {
            "selected_domain_agent": "InstrumentationAmplifierAgent",
            "profile": "instrumentation_amplifier_three_opamp_compensated_v1",
            "inputs": {},
            "generated_files": {},
            "tool_results": {},
            "handoff_records": [
                {"from_agent": "InstrumentationAmplifierAgent", "to_agent": "CriticAgent"}
            ],
            "data_source": "analytic_model_proxy",
            "engineering_validity": "simulation_only",
        }
    )[0]

    assert not any("data_source mismatch" in issue for issue in verdict.issues)
