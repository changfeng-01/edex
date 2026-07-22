from __future__ import annotations

import math
import json

import pandas as pd
import pytest

from goa_eval.circuit_profiles import load_circuit_profiles, resolve_circuit_profile
from goa_eval.domain import (
    CanonicalAction,
    CircuitParameterProfile,
    CircuitTaskHead,
    audit_parameter_profile,
    decode_action_set,
    evaluate_task_head,
)
from goa_eval.transfer import (
    compute_task_parameter_importance,
    estimate_local_sensitivity_matrix,
    project_physical_effect,
)
from goa_eval.pia_ca_llso.selector import select_capm_distance


def _parameter_profile() -> CircuitParameterProfile:
    return CircuitParameterProfile.from_mapping(
        {
            "name": "goa_shift_register",
            "task_type": "goa",
            "parameters": {
                "pullup_a_width": {
                    "column": "M1_W",
                    "role": "pullup",
                    "property": "width",
                    "kind": "design",
                    "unit": "um",
                    "optimizable": True,
                    "bounds": [1.0, 20.0],
                    "quantization": 0.5,
                    "group": "pullup_array",
                    "mapping_fidelity": "exact",
                },
                "pullup_b_width": {
                    "column": "M2_W",
                    "role": "pullup",
                    "property": "width",
                    "kind": "design",
                    "unit": "um",
                    "optimizable": True,
                    "bounds": [1.0, 20.0],
                    "quantization": 0.5,
                    "group": "pullup_array",
                    "mapping_fidelity": "exact",
                },
                "supply": {
                    "column": "VDD",
                    "role": "supply",
                    "property": "voltage",
                    "kind": "environment",
                    "unit": "V",
                    "optimizable": False,
                },
                "mobility": {
                    "column": "mu",
                    "role": "device_model",
                    "property": "mobility",
                    "kind": "model",
                    "optimizable": False,
                },
            },
        }
    )


def test_parameter_profile_separates_design_environment_and_model_inputs() -> None:
    profile = _parameter_profile()
    audit = audit_parameter_profile({"M1_W": 8.0, "M2_W": 10.0, "VDD": 5.0}, profile)

    assert [spec.column for spec in profile.optimizable_parameters] == ["M1_W", "M2_W"]
    assert profile.parameters_by_kind["environment"][0].column == "VDD"
    assert profile.parameters_by_kind["model"][0].column == "mu"
    assert audit.status == "incomplete_model_inputs"
    assert audit.optimizable_coverage == pytest.approx(1.0)
    assert audit.declared_coverage == pytest.approx(0.75)
    assert audit.missing_columns == ("mu",)


def test_canonical_action_decodes_to_multiple_local_parameters_and_rejects_environment() -> None:
    profile = _parameter_profile()
    row = {"M1_W": 19.0, "M2_W": 10.0, "VDD": 5.0}

    decoded = decode_action_set(
        CanonicalAction("pullup", "width", "log_scale", math.log(1.2)),
        profile,
        row,
    )
    environment = decode_action_set(
        CanonicalAction("supply", "voltage", "add", 0.5),
        profile,
        row,
    )

    assert decoded.status == "one_to_many"
    assert decoded.mapping_fidelity == "exact"
    assert [update.column for update in decoded.updates] == ["M1_W", "M2_W"]
    assert decoded.updates[0].value == pytest.approx(20.0)
    assert decoded.updates[0].clipped is True
    assert decoded.updates[1].value == pytest.approx(12.0)
    assert environment.status == "not_optimizable"
    assert environment.updates == ()


def test_domain_task_heads_assign_different_value_to_the_same_physical_state() -> None:
    goa = CircuitTaskHead.from_mapping(
        {
            "name": "goa",
            "metrics": {
                "boost": {
                    "feature": "bootstrap_headroom_v",
                    "direction": "larger_better",
                    "minimum": 1.0,
                    "scale": 0.5,
                    "weight": 0.8,
                },
                "delay": {
                    "feature": "critical_rc_delay_s",
                    "direction": "smaller_better",
                    "maximum": 2e-6,
                    "scale": 1e-6,
                    "weight": 0.2,
                },
            },
        }
    )
    storage_driver = CircuitTaskHead.from_mapping(
        {
            "name": "storage_driver",
            "metrics": {
                "holding": {
                    "feature": "holding_droop_v",
                    "direction": "smaller_better",
                    "maximum": 0.1,
                    "scale": 0.1,
                    "weight": 0.9,
                },
                "delay": {
                    "feature": "critical_rc_delay_s",
                    "direction": "smaller_better",
                    "maximum": 2e-6,
                    "scale": 1e-6,
                    "weight": 0.1,
                },
            },
        }
    )
    state = {"bootstrap_headroom_v": 2.0, "critical_rc_delay_s": 1e-6, "holding_droop_v": 0.3}

    goa_result = evaluate_task_head(state, goa)
    storage_result = evaluate_task_head(state, storage_driver)

    assert goa_result.status == "ok"
    assert storage_result.status == "ok"
    assert goa_result.score > 0.8
    assert storage_result.score < 0.3
    assert goa_result.metric_results["boost"].satisfied is True
    assert storage_result.metric_results["holding"].satisfied is False


def test_task_head_fails_closed_when_a_required_metric_is_missing() -> None:
    task = CircuitTaskHead.from_mapping(
        {
            "name": "goa",
            "missing_metric_policy": "not_evaluable",
            "metrics": {
                "boost": {
                    "feature": "bootstrap_headroom_v",
                    "direction": "larger_better",
                    "minimum": 1.0,
                    "weight": 1.0,
                }
            },
        }
    )

    result = evaluate_task_head({}, task)

    assert result.status == "missing_required_metrics"
    assert result.score is None
    assert result.missing_features == ("bootstrap_headroom_v",)


def test_task_head_reweights_when_only_optional_metric_is_missing() -> None:
    task = CircuitTaskHead.from_mapping(
        {
            "name": "amplifier",
            "metrics": {
                "gain": {
                    "feature": "gain",
                    "direction": "larger_better",
                    "minimum": 10.0,
                    "weight": 0.75,
                },
                "power": {
                    "feature": "power_w",
                    "direction": "smaller_better",
                    "maximum": 0.1,
                    "weight": 0.25,
                    "required": False,
                },
            },
        }
    )

    result = evaluate_task_head({"gain": 12.0}, task)

    assert result.status == "partial"
    assert result.score == result.metric_results["gain"].score
    assert result.missing_features == ("power_w",)


def test_variation_parameters_are_valid_but_never_optimizable() -> None:
    profile = CircuitParameterProfile.from_mapping(
        {
            "name": "variation_profile",
            "task_type": "amplifier",
            "parameters": {
                "delta_r1": {
                    "kind": "variation",
                    "role": "resistor_1",
                    "property": "relative_error",
                    "optimizable": True,
                }
            },
        }
    )

    assert profile.parameters[0].kind == "variation"
    assert profile.optimizable_parameters == ()


def test_local_sensitivity_and_task_weights_make_parameter_importance_domain_specific() -> None:
    point = {"pullup_w": 10.0, "storage_c": 2.0}

    def response(values: dict[str, float]) -> dict[str, float]:
        return {
            "bootstrap_headroom_v": values["pullup_w"] ** 0.8,
            "holding_droop_v": 1.0 / values["storage_c"],
            "signed_margin_v": values["pullup_w"] - 10.0,
        }

    sensitivity = estimate_local_sensitivity_matrix(response, point)
    goa = CircuitTaskHead.from_mapping(
        {
            "name": "goa",
            "metrics": {
                "boost": {"feature": "bootstrap_headroom_v", "direction": "larger_better", "minimum": 5.0, "weight": 1.0}
            },
        }
    )
    storage = CircuitTaskHead.from_mapping(
        {
            "name": "storage",
            "metrics": {
                "holding": {"feature": "holding_droop_v", "direction": "smaller_better", "maximum": 0.2, "weight": 1.0}
            },
        }
    )

    goa_importance = compute_task_parameter_importance(sensitivity, goa, response(point))
    storage_importance = compute_task_parameter_importance(sensitivity, storage, response(point))

    assert sensitivity["bootstrap_headroom_v"]["pullup_w"] == pytest.approx(0.8, rel=1e-4)
    assert math.isfinite(sensitivity["signed_margin_v"]["pullup_w"])
    assert goa_importance["pullup_w"] > goa_importance["storage_c"]
    assert storage_importance["storage_c"] > storage_importance["pullup_w"]


def test_physical_effect_projection_uses_target_jacobian_and_target_constraints() -> None:
    profile = _parameter_profile()
    projection = project_physical_effect(
        target_effect={"bootstrap_headroom_v": 0.2, "critical_rc_delay_s": -0.1},
        target_jacobian={
            "bootstrap_headroom_v": {"M1_W": 0.8, "M2_W": 0.4},
            "critical_rc_delay_s": {"M1_W": -0.4, "M2_W": -0.2},
        },
        profile=profile,
        row={"M1_W": 10.0, "M2_W": 10.0},
        regularization=1e-6,
        minimum_alignment=0.95,
    )

    assert projection.status == "ok"
    assert projection.accepted is True
    assert projection.alignment > 0.99
    assert {update.column for update in projection.updates} == {"M1_W", "M2_W"}
    assert all(1.0 <= update.value <= 20.0 for update in projection.updates)


def test_physical_effect_projection_rejects_an_unreachable_target_direction() -> None:
    projection = project_physical_effect(
        target_effect={"boost": 0.0, "holding": 1.0},
        target_jacobian={"boost": {"M1_W": 1.0}, "holding": {"M1_W": 0.0}},
        profile=_parameter_profile(),
        row={"M1_W": 10.0},
        minimum_alignment=0.5,
    )

    assert projection.status == "response_mismatch"
    assert projection.accepted is False
    assert projection.alignment == pytest.approx(0.0)


def test_physical_effect_projection_rejects_aligned_but_too_small_effect() -> None:
    projection = project_physical_effect(
        target_effect={"boost": 10.0},
        target_jacobian={"boost": {"M1_W": 1.0}},
        profile=_parameter_profile(),
        row={"M1_W": 10.0},
        minimum_alignment=0.9,
        max_log_step=0.06,
        maximum_relative_residual=0.5,
    )

    assert projection.alignment > 0.99
    assert projection.relative_residual > 0.9
    assert projection.status == "effect_magnitude_mismatch"
    assert projection.accepted is False


def test_physical_effect_projection_handles_rank_deficient_jacobian_without_ridge() -> None:
    projection = project_physical_effect(
        target_effect={"boost": 0.2},
        target_jacobian={"boost": {"M1_W": 1.0, "M2_W": 1.0}},
        profile=_parameter_profile(),
        row={"M1_W": 10.0, "M2_W": 10.0},
        regularization=0.0,
        minimum_alignment=0.9,
    )

    assert projection.accepted is True
    assert projection.status == "ok"
    assert projection.relative_residual < 0.1


def test_task_head_can_reuse_existing_circuit_profile_objective() -> None:
    profile = resolve_circuit_profile("transistor_level_goa", load_circuit_profiles())

    task = CircuitTaskHead.from_circuit_profile(profile)
    parameter_profile = CircuitParameterProfile.from_circuit_profile(profile)
    evaluation = evaluate_task_head(
        {
            "delay_s": 1e-6,
            "rise_time_s": 1e-6,
            "fall_time_s": 1e-6,
            "power_w": 0.05,
            "voh_min_v": 12.0,
            "constraint_violation": 0.0,
        },
        task,
    )

    weights = {metric.name: metric.weight for metric in task.metrics}
    assert task.name == "transistor_level_goa"
    assert weights["voh_min_v"] == pytest.approx(0.20)
    assert len(parameter_profile.optimizable_parameters) == 9
    assert parameter_profile.parameters_by_kind["environment"][0].column == "C_load"
    assert evaluation.status == "ok"
    assert evaluation.score is not None and evaluation.score > 0.5


def test_parameter_profile_can_reuse_circuit_profile_parameter_bindings() -> None:
    circuit_profile = {
        "name": "pixel_storage_driver",
        "type": "tft_pixel_driver",
        "parameter_profile": {
            "parameters": {
                "storage_capacitance": {
                    "column": "CST",
                    "role": "storage",
                    "property": "capacitance",
                    "kind": "design",
                    "unit": "pF",
                    "optimizable": True,
                    "bounds": [0.1, 5.0],
                    "mapping_fidelity": "exact",
                },
                "temperature": {
                    "column": "TEMP_C",
                    "role": "environment",
                    "property": "temperature_c",
                    "kind": "environment",
                    "optimizable": False,
                },
            }
        },
    }

    parameter_profile = CircuitParameterProfile.from_circuit_profile(circuit_profile)

    assert parameter_profile.name == "pixel_storage_driver"
    assert parameter_profile.task_type == "tft_pixel_driver"
    assert [parameter.column for parameter in parameter_profile.optimizable_parameters] == ["CST"]


def test_v4_selector_uses_target_task_head_and_emits_parameter_transfer_diagnostics() -> None:
    history = pd.DataFrame(
        [
            {
                "sample_id": f"h{index}",
                "level_label": "L1" if index >= 4 else "L2",
                "critical_rc_delay_s": (index + 1) * 1e-9,
                "boost_metric": 1.0,
                "M1_W": 8.0,
                "VDD": 5.0,
                "mu": 100.0,
            }
            for index in range(7)
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "weak_boost",
                "critical_rc_delay_s": 2.5e-9,
                "boost_metric": 0.5,
                "M1_W": 8.0,
                "VDD": 5.0,
                "mu": 100.0,
            },
            {
                "candidate_id": "strong_boost",
                "critical_rc_delay_s": 2.5e-9,
                "boost_metric": 2.0,
                "M1_W": 8.0,
                "VDD": 5.0,
                "mu": 100.0,
            },
        ]
    )
    config = {
        "capm_distance": {
            "metric_version": "v4",
            "normalization_enabled": True,
            "coupling_enabled": False,
            "barrier_enabled": False,
            "geodesic_enabled": False,
        },
        "transfer": {
            "source_domain": {"topology_family": "goa_11t2c", "technology_family": "igzo_tft"},
            "target_domain": {"topology_family": "goa_12t3c", "technology_family": "igzo_tft"},
            "target_parameter_profile": {
                "name": "goa_target",
                "task_type": "goa",
                "parameters": {
                    "pullup_width": {
                        "column": "M1_W",
                        "role": "pullup",
                        "property": "width",
                        "kind": "design",
                        "optimizable": True,
                        "bounds": [1.0, 20.0],
                        "mapping_fidelity": "exact",
                    },
                    "supply": {
                        "column": "VDD",
                        "role": "supply",
                        "property": "voltage",
                        "kind": "environment",
                        "optimizable": False,
                    },
                    "mobility": {
                        "column": "mu",
                        "role": "device_model",
                        "property": "mobility",
                        "kind": "model",
                        "optimizable": False,
                    },
                },
            },
            "task_head": {
                "name": "goa_voltage_lift",
                "acquisition_weight": 1.0,
                "metrics": {
                    "boost": {
                        "feature": "boost_metric",
                        "direction": "larger_better",
                        "minimum": 1.0,
                        "scale": 0.5,
                        "weight": 1.0,
                    }
                },
            },
            "action_projection": {
                "target_effect": {"boost_metric": 0.2},
                "target_jacobian": {"boost_metric": {"M1_W": 1.0}},
                "minimum_alignment": 0.95,
                "maximum_relative_residual": 0.1,
            },
            "parameter_transfer": {"minimum_parameter_coverage": 1.0},
        },
    }

    result = select_capm_distance(
        candidates,
        history,
        top_k=2,
        weights={"critical_rc_delay_s": 1.0},
        config=config,
        sort_by_acquisition=True,
    ).reset_index(drop=True)
    parameter_diagnostics = json.loads(result.loc[0, "capm_parameter_diagnostics_json"])
    transfer_diagnostics = json.loads(result.loc[0, "capm_transfer_diagnostics_json"])

    assert result.loc[0, "candidate_id"] == "strong_boost"
    assert result.loc[0, "capm_task_head_status"] == "ok"
    assert result.loc[0, "capm_task_alignment_score"] > result.loc[1, "capm_task_alignment_score"]
    assert result.loc[0, "capm_parameter_profile_status"] == "complete"
    assert result.loc[0, "capm_action_transfer_status"] == "eligible"
    assert parameter_diagnostics["profile_name"] == "goa_target"
    assert parameter_diagnostics["action_projection"]["accepted"] is True
    assert transfer_diagnostics["parameter_transfer"]["action_transfer_allowed"] is True
    assert result.loc[0, "data_source"] == "real_simulation_csv"
    assert result.loc[0, "engineering_validity"] == "simulation_only"
    assert bool(result.loc[0, "must_resimulate"]) is True


def test_v4_selector_resolves_task_and_parameter_spaces_from_one_circuit_profile() -> None:
    history = pd.DataFrame(
        {
            "sample_id": [f"h{index}" for index in range(7)],
            "level_label": ["L2", "L2", "L2", "L2", "L1", "L1", "L1"],
            "critical_rc_delay_s": [(index + 1) * 1e-9 for index in range(7)],
        }
    )
    local_parameters = {
        "M_pullup_W": 8.0,
        "M_pullup_L": 2.0,
        "M_pulldown_W": 8.0,
        "M_pulldown_L": 2.0,
        "M_reset_W": 4.0,
        "M_reset_L": 2.0,
        "M_bootstrap_W": 6.0,
        "M_bootstrap_L": 2.0,
        "C_load": 1.0,
        "C_boot": 2.0,
        "VDD": 5.0,
        "VSS": 0.0,
        "CLK_rise_time": 10.0,
        "CLK_fall_time": 10.0,
    }
    common_metrics = {
        "delay_s": 1e-6,
        "rise_time_s": 1e-6,
        "fall_time_s": 1e-6,
        "power_w": 0.05,
        "constraint_violation": 0.0,
        "critical_rc_delay_s": 2.5e-9,
    }
    candidates = pd.DataFrame(
        [
            {"candidate_id": "low_output", **local_parameters, **common_metrics, "voh_min_v": 8.0},
            {"candidate_id": "high_output", **local_parameters, **common_metrics, "voh_min_v": 12.0},
        ]
    )
    config = {
        "capm_distance": {
            "metric_version": "v4",
            "normalization_enabled": True,
            "coupling_enabled": False,
            "barrier_enabled": False,
            "geodesic_enabled": False,
        },
        "transfer": {
            "target_circuit_profile": "transistor_level_goa",
            "task_acquisition_weight": 1.0,
            "source_domain": {"topology_family": "goa_11t2c"},
            "target_domain": {"topology_family": "goa_12t3c"},
            "parameter_transfer": {"minimum_parameter_coverage": 1.0},
        },
    }

    result = select_capm_distance(
        candidates,
        history,
        top_k=2,
        weights={"critical_rc_delay_s": 1.0},
        config=config,
        sort_by_acquisition=True,
    ).reset_index(drop=True)

    assert result.loc[0, "candidate_id"] == "high_output"
    assert result.loc[0, "capm_task_head_status"] == "ok"
    assert result.loc[0, "capm_parameter_profile_status"] == "complete"
    assert result.loc[0, "capm_action_transfer_status"] == "projection_required"


def test_v4_selector_rejects_unknown_target_circuit_profile() -> None:
    history = pd.DataFrame(
        {
            "sample_id": [f"h{index}" for index in range(7)],
            "level_label": ["L2", "L2", "L2", "L2", "L1", "L1", "L1"],
            "critical_rc_delay_s": [(index + 1) * 1e-9 for index in range(7)],
        }
    )
    candidates = pd.DataFrame(
        [{"candidate_id": "candidate", "critical_rc_delay_s": 2.5e-9}]
    )

    with pytest.raises(ValueError, match="unknown target circuit profile"):
        select_capm_distance(
            candidates,
            history,
            top_k=1,
            weights={"critical_rc_delay_s": 1.0},
            config={
                "capm_distance": {"metric_version": "v4"},
                "transfer": {"target_circuit_profile": "does_not_exist"},
            },
        )
