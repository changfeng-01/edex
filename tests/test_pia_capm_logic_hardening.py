from __future__ import annotations

import json

import pandas as pd
import pytest

from goa_eval.pia_ca_llso.electrical_model import V3_GEOMETRY_FEATURES
from goa_eval.pia_ca_llso.features import extract_physics_features
from goa_eval.pia_ca_llso.physics_distance import build_capm_distance_context, compute_capm_distance
from goa_eval.pia_ca_llso.selector import select_capm_distance

from test_pia_capm_v3 import _base_row, _feature_config, _v3_history


def test_v3_geometric_identity_separates_point_risk() -> None:
    risky = {
        "critical_rc_delay_s": 4.0,
        "pullup_overdrive_v": -0.2,
        "pulldown_overdrive_v": 0.5,
        "pullup_region_code": 0.0,
        "pulldown_region_code": 2.0,
    }
    config = {
        "metric_version": "v3",
        "normalization_enabled": False,
        "coupling_enabled": False,
        "max_critical_rc_delay_s": 1.0,
        "min_device_overdrive_v": 0.1,
    }
    context = build_capm_distance_context(
        pd.DataFrame([risky, {**risky, "critical_rc_delay_s": 2.0}]),
        weights={"critical_rc_delay_s": 1.0},
        config=config,
    )

    result = compute_capm_distance(risky, risky, context=context, config=config)

    assert result["distance"] == pytest.approx(0.0)
    assert result["geometric_distance"] == pytest.approx(0.0)
    assert result["point_risk_cost"] > 0.0
    assert result["decision_cost"] > result["distance"]


def test_v3_default_metric_uses_dimensionless_state_and_shrinkage_precision() -> None:
    rows = []
    for index in range(8):
        scale = 1.0 + 0.1 * index
        rows.append(
            {
                "level_label": "L1" if index > 3 else "L2",
                "pullup_overdrive_supply_ratio": 0.4 * scale,
                "pulldown_overdrive_supply_ratio": 0.5 / scale,
                "pullup_rc_to_clock_slew_ratio": 0.8 * scale,
                "pulldown_rc_to_clock_slew_ratio": 0.9 * scale,
                "bootstrap_coupling_factor_v3": 0.6 / scale,
                "bootstrap_headroom_supply_ratio": 0.2 * scale,
                "drive_balance_log_ratio": 0.1 * index,
            }
        )

    context = build_capm_distance_context(pd.DataFrame(rows), config={"metric_version": "v3"})

    assert context.feature_keys == V3_GEOMETRY_FEATURES
    assert context.metric_basis == "dimensionless_shrinkage_mahalanobis"
    assert context.covariance_shrinkage > 0.0
    assert len(context.precision_matrix) == len(V3_GEOMETRY_FEATURES)


def test_tft_charge_sheet_v2_is_continuous_and_bootstrap_is_self_consistent() -> None:
    config = _feature_config()
    config["electrical_model"]["model"] = "tft_charge_sheet_v2"
    config["electrical_model"]["devices"]["pullup"]["channel_length_modulation_per_v"] = 0.3
    config["electrical_model"]["bootstrap_solver"] = {
        "enabled": True,
        "target_role": "pullup",
        "max_iterations": 20,
        "tolerance_v": 1.0e-10,
        "relaxation": 0.7,
        "gate_capacitance_f": 2.0e-13,
    }
    below = {**_base_row(), "pullup_vds_v": 1.0 - 1.0e-8}
    above = {**_base_row(), "pullup_vds_v": 1.0 + 1.0e-8}

    features, _ = extract_physics_features(pd.DataFrame([below, above]), config)
    left = json.loads(features.loc[0, "capm_electrical_status_json"])
    right = json.loads(features.loc[1, "capm_electrical_status_json"])

    i_left = left["devices"]["pullup"]["drain_current_a"]
    i_right = right["devices"]["pullup"]["drain_current_a"]
    assert i_left == pytest.approx(i_right, rel=1.0e-6)
    assert left["bootstrap_solver"]["status"] == "converged"
    assert left["bootstrap_solver"]["charge_residual_v"] <= 1.0e-10
    assert left["bootstrap_solver"]["boosted_overdrive_v"] > left["devices"]["bootstrap"]["overdrive_v"]


def test_non_reference_pvt_requires_complete_explicit_coefficients() -> None:
    config = _feature_config()
    config["pvt"] = {
        "reference_temperature_c": 25.0,
        "reference_supply_v": 5.0,
        "scenarios": [{"corner": "ss", "temperature_c": 125.0, "supply_v": 4.0}],
        "corner_models": {
            "ss": {
                "mu_multiplier": 0.7,
                "vth_shift_v": 0.15,
                "resistance_multiplier": 1.2,
                "capacitance_multiplier": 1.1,
            }
        },
    }

    features, _ = extract_physics_features(pd.DataFrame([_base_row()]), config)
    diagnostics = json.loads(features.loc[0, "capm_pvt_diagnostics_json"])

    assert features.loc[0, "capm_pvt_status"] == "missing"
    assert diagnostics["scenarios"]["ss|125|4"]["missing_coefficients"] == [
        "mobility_temperature_exponent",
        "supply_bias_exponent",
        "vth_temperature_coefficient_v_per_c",
    ]


def test_weighted_cvar_and_chance_risk_use_unique_pvt_scenarios() -> None:
    config = {
        "metric_version": "v3",
        "normalization_enabled": False,
        "coupling_enabled": False,
        "barrier_enabled": True,
        "max_critical_rc_delay_s": 2.5,
        "pvt_cvar_quantile": 0.9,
        "pvt_cvar_weight": 0.5,
        "pvt_uncertainty_z": 1.0,
        "pvt_max_violation_probability": 0.05,
    }
    history = pd.DataFrame(
        [
            {"level_label": "L1", "critical_rc_delay_s": 0.0},
            {"level_label": "L2", "critical_rc_delay_s": 4.0},
        ]
    )
    context = build_capm_distance_context(
        history,
        weights={"critical_rc_delay_s": 1.0},
        config=config,
    )
    pvt_left = {
        "tt|25|5": {"critical_rc_delay_s": 0.0},
        "ss|125|4": {"critical_rc_delay_s": 2.0},
    }
    pvt_right = {
        "tt|25|5": {"critical_rc_delay_s": 1.0},
        "ss|125|4": {"critical_rc_delay_s": 5.0},
    }
    diagnostics = json.dumps(
        {
            "scenarios": {
                "tt|25|5": {"status": "observed", "weight": 0.9, "distance_uncertainty": 0.0},
                "ss|125|4": {"status": "proxy_projected", "weight": 0.1, "distance_uncertainty": 0.2},
            }
        }
    )
    left = {
        "critical_rc_delay_s": 0.0,
        "capm_pvt_features_json": json.dumps(pvt_left),
        "capm_pvt_diagnostics_json": diagnostics,
    }
    right = {
        "critical_rc_delay_s": 1.0,
        "capm_pvt_features_json": json.dumps(pvt_right),
        "capm_pvt_diagnostics_json": diagnostics,
    }

    result = compute_capm_distance(left, right, context=context, config=config)

    assert result["pvt_weighted_mean_distance"] == pytest.approx(1.2)
    assert result["pvt_cvar_distance"] == pytest.approx(3.2)
    assert result["distance"] == pytest.approx(2.2)
    assert result["pvt_violation_probability"] == pytest.approx(0.1)
    assert result["chance_constraint_excess"] == pytest.approx(0.05)


def test_pvt_scenario_keys_are_deduplicated_before_projection() -> None:
    config = _feature_config()
    config["pvt"] = {
        "reference_temperature_c": 25.0,
        "reference_supply_v": 5.0,
        "mobility_temperature_exponent": 1.5,
        "vth_temperature_coefficient_v_per_c": 0.001,
        "supply_bias_exponent": 1.0,
        "scenarios": [
            {"corner": "tt", "temperature_c": 25.0, "supply_v": 5.0, "weight": 0.8},
            {"corner": "tt", "temperature_c": 25.0, "supply_v": 5.0, "weight": 0.8},
            {"corner": "ss", "temperature_c": 125.0, "supply_v": 4.0, "weight": 0.2},
        ],
        "corner_models": {
            "tt": {"mu_multiplier": 1.0, "vth_shift_v": 0.0, "resistance_multiplier": 1.0, "capacitance_multiplier": 1.0},
            "ss": {"mu_multiplier": 0.7, "vth_shift_v": 0.15, "resistance_multiplier": 1.2, "capacitance_multiplier": 1.1},
        },
    }

    features, _ = extract_physics_features(pd.DataFrame([_base_row()]), config)
    scenarios = json.loads(features.loc[0, "capm_pvt_features_json"])
    diagnostics = json.loads(features.loc[0, "capm_pvt_diagnostics_json"])

    assert len(scenarios) == 2
    assert diagnostics["duplicate_scenario_count"] == 1
    assert diagnostics["scenarios"]["tt|25|5"]["weight"] == pytest.approx(0.8)


def test_selector_exposes_geometry_and_risk_as_separate_outputs() -> None:
    history = _v3_history()
    candidates = pd.DataFrame([{"candidate_id": "c0", **history.iloc[0].to_dict()}])

    result = select_capm_distance(
        candidates,
        history,
        top_k=1,
        config={"capm_distance": {"metric_version": "v3", "geodesic_enabled": False}},
    )

    assert "capm_point_risk_cost" in result.columns
    assert "capm_decision_cost_to_l1" in result.columns
    assert result.loc[0, "capm_decision_cost_to_l1"] >= result.loc[0, "capm_distance_to_l1"]
