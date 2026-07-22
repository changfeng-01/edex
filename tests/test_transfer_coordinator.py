from __future__ import annotations

import pytest

from goa_eval.domain import CircuitParameterProfile
from goa_eval.multi_agent.agents.transfer_coordinator_agent import (
    coordinate_transfer,
    run_transfer_coordinator_agent,
)
from goa_eval.multi_agent.agents.optimization_agent import run_optimization_agent
from goa_eval.transfer import (
    BarrierResult,
    LocalElectricalState,
    PhysicalEffect,
    PhysicalEffectPacket,
    SensitivityArtifact,
    build_goa_effect_packet,
    project_physical_effect,
)


def _profile() -> CircuitParameterProfile:
    return CircuitParameterProfile.from_mapping(
        {
            "name": "instrumentation_amplifier_three_opamp_compensated_v1",
            "task_type": "instrumentation_amplifier",
            "parameters": {
                "resistance": {
                    "column": "R",
                    "role": "first_stage",
                    "property": "resistance",
                    "kind": "design",
                    "unit": "ohm",
                    "optimizable": True,
                    "bounds": [5.0e3, 50.0e3],
                },
                "gain_resistance": {
                    "column": "RG",
                    "role": "gain",
                    "property": "resistance",
                    "kind": "design",
                    "unit": "ohm",
                    "optimizable": True,
                    "bounds": [0.5e3, 20.0e3],
                },
            },
        }
    )


def _packet() -> PhysicalEffectPacket:
    return PhysicalEffectPacket(
        source_agent="GOAAgent",
        source_profile="goa_8t1c_720",
        model_version="v4",
        scenario_key="TT|25|5",
        effects={
            "critical_time_log_delta": PhysicalEffect("supported", 0.10, 0.02),
            "output_headroom_normalized_delta": PhysicalEffect("supported", 0.05, 0.01),
            "bootstrap_coupling_delta": PhysicalEffect("supported", 0.30, 0.01),
            "tft_region_margin_delta": PhysicalEffect("not_applicable"),
            "power_log_delta": PhysicalEffect("missing"),
        },
        raw_si={"critical_rc_delay_s": 1.0e-6},
        applicability={"circuit_family": "GOA"},
        evidence={
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        },
    )


def test_goa_adapter_uses_canonical_improvement_directions_without_exporting_local_formulas() -> None:
    packet = build_goa_effect_packet(
        {
            "critical_rc_delay_s": 2.0e-6,
            "voh_min_v": 10.0,
            "power_w": 0.1,
            "bootstrap_coupling_factor_v3": 0.4,
            "tft_region_margin_v": 0.5,
        },
        {
            "critical_rc_delay_s": 1.0e-6,
            "voh_min_v": 11.0,
            "power_w": 0.05,
            "bootstrap_coupling_factor_v3": 0.5,
            "tft_region_margin_v": 0.7,
        },
    )

    assert packet.effects["critical_time_log_delta"].value > 0.0
    assert packet.effects["output_headroom_normalized_delta"].value > 0.0
    assert packet.effects["power_log_delta"].value > 0.0
    assert packet.effects["task_gain_margin_delta"].status == "not_applicable"


def test_physics_protocol_preserves_missing_and_not_applicable_without_zero_fill() -> None:
    packet = _packet()
    payload = packet.as_dict()
    state = LocalElectricalState(
        scenario_key="TT|25|5",
        values_si={"critical_time_s": 1.0e-6},
        feature_status={"critical_time_s": "observed"},
        model_status="observed",
    )
    barrier = BarrierResult(
        value=0.25,
        status="violated",
        violations=("headroom",),
        scenario_key="TT|25|5",
    )

    assert payload["schema_version"] == "circuitpilot.physical-effect.v1"
    assert payload["effects"]["power_log_delta"] == {
        "status": "missing",
        "value": None,
        "uncertainty": None,
    }
    assert payload["effects"]["tft_region_margin_delta"]["status"] == "not_applicable"
    assert state.as_dict()["values_si"]["critical_time_s"] == pytest.approx(1.0e-6)
    assert barrier.as_dict()["violations"] == ["headroom"]


def test_coordinator_projects_only_supported_effect_intersection_and_emits_trust_steps() -> None:
    sensitivity = SensitivityArtifact(
        profile="instrumentation_amplifier_three_opamp_compensated_v1",
        physics_version="instrumentation_amplifier_three_opamp_v1",
        task_head_version="v1",
        scenario_jacobians={
            "TT|25|5": {
                "critical_time_log_delta": {"R": -1.0, "RG": 0.0},
                "output_headroom_normalized_delta": {"R": 0.0, "RG": -1.0},
            }
        },
        normalized_uncertainty={
            "critical_time_log_delta": 0.1,
            "output_headroom_normalized_delta": 0.1,
        },
        evidence_status="analytic_model_proxy",
    )

    result = coordinate_transfer(
        source_packet=_packet(),
        target_sensitivity=sensitivity,
        parameter_profile=_profile(),
        operating_point={"R": 10.0e3, "RG": 2.0e3},
        minimum_alignment=0.5,
        maximum_relative_residual=0.5,
    )

    assert result["status"] == "ok"
    assert result["accepted"] is True
    assert result["supported_effects"] == [
        "critical_time_log_delta",
        "output_headroom_normalized_delta",
    ]
    assert result["rejected_effects"]["bootstrap_coupling_delta"] == "not_applicable_in_target"
    assert result["rejected_effects"]["tft_region_margin_delta"] == "not_applicable"
    assert result["rejected_effects"]["power_log_delta"] == "missing"
    assert [item["scale"] for item in result["trust_region_suggestions"]] == [0.25, 0.5, 1.0]
    assert result["projection"]["matrix_rank"] == 2
    assert result["projection"]["condition_number"] == pytest.approx(1.0)
    assert 0.0 < result["transfer_confidence"] <= 1.0
    assert result["ood_diagnostics"]["status"] == "scope_not_declared"


def test_coordinator_rejects_rank_deficient_ill_conditioned_or_uncertain_projection() -> None:
    rank_deficient = SensitivityArtifact(
        profile="amp",
        physics_version="v1",
        task_head_version="v1",
        scenario_jacobians={
            "TT": {
                "critical_time_log_delta": {"R": 1.0, "RG": 1.0},
                "output_headroom_normalized_delta": {"R": 2.0, "RG": 2.0},
            }
        },
        normalized_uncertainty={"critical_time_log_delta": 0.1},
    )
    uncertain = SensitivityArtifact(
        profile="amp",
        physics_version="v1",
        task_head_version="v1",
        scenario_jacobians={
            "TT": {
                "critical_time_log_delta": {"R": -1.0, "RG": 0.0},
                "output_headroom_normalized_delta": {"R": 0.0, "RG": -1.0},
            }
        },
        normalized_uncertainty={"critical_time_log_delta": 0.8},
    )

    rank_result = coordinate_transfer(
        _packet(), rank_deficient, _profile(), {"R": 10.0e3, "RG": 2.0e3}
    )
    uncertainty_result = coordinate_transfer(
        _packet(), uncertain, _profile(), {"R": 10.0e3, "RG": 2.0e3}
    )

    assert rank_result["status"] == "rank_deficient"
    assert rank_result["accepted"] is False
    assert rank_result["trust_region_suggestions"] == []
    assert uncertainty_result["status"] == "high_uncertainty"
    assert uncertainty_result["accepted"] is False


def test_coordinator_rejects_explicit_target_profile_ood_without_projecting() -> None:
    packet = PhysicalEffectPacket.from_mapping(
        {
            **_packet().as_dict(),
            "applicability": {"target_profiles": ["goa_only_target"]},
        }
    )
    sensitivity = SensitivityArtifact(
        profile="instrumentation_amplifier_three_opamp_compensated_v1",
        physics_version="v1",
        task_head_version="v1",
        scenario_jacobians={
            "TT": {
                "critical_time_log_delta": {"R": -1.0, "RG": 0.0},
                "output_headroom_normalized_delta": {"R": 0.0, "RG": -1.0},
            }
        },
    )

    result = coordinate_transfer(
        packet, sensitivity, _profile(), {"R": 10.0e3, "RG": 2.0e3}
    )

    assert result["status"] == "out_of_distribution"
    assert result["accepted"] is False
    assert result["trust_region_suggestions"] == []


def test_coordinator_reduces_underdetermined_full_row_rank_system_to_identifiable_actions() -> None:
    profile = CircuitParameterProfile.from_mapping(
        {
            "name": "amp",
            "task_type": "amp",
            "parameters": {
                name: {
                    "column": name,
                    "role": name,
                    "property": "value",
                    "kind": "design",
                    "optimizable": True,
                    "bounds": [1.0, 100.0],
                }
                for name in ("x1", "x2", "x3")
            },
        }
    )
    sensitivity = SensitivityArtifact(
        profile="amp",
        physics_version="v1",
        task_head_version="v1",
        scenario_jacobians={
            "TT": {
                "critical_time_log_delta": {"x1": 1.0, "x2": 0.0, "x3": 0.5},
                "output_headroom_normalized_delta": {"x1": 0.0, "x2": 1.0, "x3": 0.5},
            }
        },
        normalized_uncertainty={
            "critical_time_log_delta": 0.1,
            "output_headroom_normalized_delta": 0.1,
        },
    )

    result = coordinate_transfer(
        _packet(), sensitivity, profile, {"x1": 10.0, "x2": 10.0, "x3": 10.0}
    )

    assert result["accepted"] is True
    assert len(result["selected_parameters"]) == 2
    assert len(result["dropped_parameters"]) == 1
    assert result["iteration_diagnostics"][0]["worst_scenario"] == "TT"


def test_original_projection_remains_backward_compatible_unless_robust_gates_are_requested() -> None:
    legacy = project_physical_effect(
        {"effect": 0.2},
        {"effect": {"R": 1.0, "RG": 1.0}},
        _profile(),
        {"R": 10.0e3, "RG": 2.0e3},
        regularization=0.0,
    )
    robust = project_physical_effect(
        {"effect": 0.2},
        {"effect": {"R": 1.0, "RG": 1.0}},
        _profile(),
        {"R": 10.0e3, "RG": 2.0e3},
        regularization=0.0,
        reject_rank_deficient=True,
    )

    assert legacy.accepted is True
    assert robust.accepted is False
    assert robust.status == "rank_deficient"


def test_transfer_coordinator_agent_does_not_fabricate_projection_on_rejection() -> None:
    state = {
        "inputs": {
            "source_effect_packet": _packet().as_dict(),
            "target_sensitivity": SensitivityArtifact(
                profile="amp",
                physics_version="v1",
                task_head_version="v1",
                scenario_jacobians={"TT": {}},
            ).as_dict(),
            "parameter_profile": {
                "name": "amp",
                "task_type": "instrumentation_amplifier",
                "parameters": {},
            },
            "operating_point": {},
        }
    }

    result = run_transfer_coordinator_agent(state)

    assert result["transfer_projection"]["accepted"] is False
    assert result["transfer_projection"]["trust_region_suggestions"] == []
    assert result["handoff_records"][-1]["to_agent"] == "CriticAgent"


def test_coordinator_consumes_domain_sensitivity_and_optimizer_exports_trust_candidates(
    tmp_path,
) -> None:
    state = {
        "profile": "instrumentation_amplifier_three_opamp_compensated_v1",
        "objectives": {"target_differential_gain": 13.2},
        "output_dir": str(tmp_path),
        "inputs": {
            "source_effect_packet": _packet().as_dict(),
            "operating_point": {
                "R": 10.0e3,
                "RG": 2.0e3,
                "RD": 10.0e3,
                "KD_plus": 1.2,
                "KD_minus": 1.2,
                "CF": 10.0e-12,
            },
        },
        "target_sensitivity": SensitivityArtifact(
            profile="instrumentation_amplifier_three_opamp_compensated_v1",
            physics_version="v1",
            task_head_version="v1",
            scenario_jacobians={
                "TT": {
                    "critical_time_log_delta": {"R": -1.0, "RG": 0.0},
                    "output_headroom_normalized_delta": {"R": 0.0, "RG": -1.0},
                }
            },
            normalized_uncertainty={
                "critical_time_log_delta": 0.1,
                "output_headroom_normalized_delta": 0.1,
            },
        ).as_dict(),
        "parameter_profile": _profile(),
    }

    coordinated = run_transfer_coordinator_agent(state)
    optimized = run_optimization_agent(coordinated)

    assert coordinated["transfer_projection"]["accepted"] is True
    assert (tmp_path / "transfer_projection.json").exists()
    assert optimized["candidate_summary"]["candidate_count"] == 3
    assert optimized["candidate_summary"]["source"] == "transfer_projection"
    frame = __import__("pandas").read_csv(
        optimized["generated_files"]["next_candidates"]
    )
    assert frame["trust_region_scale"].tolist() == [0.25, 0.5, 1.0]
    assert frame["must_resimulate"].all()
    assert frame["data_source"].eq("analytic_model_proxy").all()
