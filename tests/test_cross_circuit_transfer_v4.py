from __future__ import annotations

import json

import pandas as pd
import pytest

from goa_eval.domain import CanonicalAction, CircuitDomain, decode_action, domain_distance, source_domain_weights
from goa_eval.physics import (
    BootstrapNetwork,
    DeviceBias,
    DeviceSpec,
    FidelityLevel,
    ParasiticComponent,
    conserve_bootstrap_charge,
    evaluate_tft_phase_charge,
    resolve_parasitic_components,
    PhaseEdge,
    PhaseNetwork,
    PVTScenario,
    classify_pvt_scenarios,
    solve_phase_network,
)
from goa_eval.pia_ca_llso.physics_distance import (
    build_capm_distance_context,
    calibrate_v4_distance,
    classify_v4_constraint_risks,
    compute_capm_distance,
)
from goa_eval.pia_ca_llso.selector import select_candidates, select_capm_distance
from goa_eval.product.models import OptimizationExperimentRecord
from goa_eval.product.pia_experiment_adapter import PiaExperimentAdapter
from goa_eval.pia_ca_llso.features import extract_physics_features
from goa_eval.transfer import (
    CrossCircuitTransferEngine,
    HierarchicalPhysicsResidual,
    TransferGateInput,
    compute_propensity_weights,
    evaluate_transfer_gate,
    estimate_local_elasticities,
    leave_one_circuit_out,
)


def test_phase_charge_model_preserves_polarity_mirror_and_depletion_threshold() -> None:
    n = evaluate_tft_phase_charge(
        DeviceSpec("pullup", "n", 10e-6, 1e-6, 1e-2, 1e-4, 1.0),
        DeviceBias(vgs_v=3.0, vds_v=1.0),
    )
    p = evaluate_tft_phase_charge(
        DeviceSpec("pullup", "p", 10e-6, 1e-6, 1e-2, 1e-4, -1.0),
        DeviceBias(vgs_v=-3.0, vds_v=-1.0),
    )
    depletion = evaluate_tft_phase_charge(
        DeviceSpec("pullup", "n", 10e-6, 1e-6, 1e-2, 1e-4, -0.5),
        DeviceBias(vgs_v=0.0, vds_v=0.2),
    )

    assert p.overdrive_v == pytest.approx(n.overdrive_v)
    assert abs(p.drain_current_a) == pytest.approx(abs(n.drain_current_a))
    assert p.drain_current_a < 0.0 < n.drain_current_a
    assert depletion.region == "linear"
    assert depletion.large_signal_resistance_ohm > 0.0
    assert depletion.small_signal_resistance_ohm > 0.0
    assert depletion.trajectory_resistance_ohm > 0.0
    assert depletion.fidelity == FidelityLevel.F2_MODEL


def test_phase_charge_model_is_source_drain_symmetric_and_has_subthreshold() -> None:
    spec = DeviceSpec("pulldown", "n", 8e-6, 1e-6, 8e-3, 1.2e-4, 0.8)
    forward = evaluate_tft_phase_charge(spec, DeviceBias(vgs_v=1.5, vds_v=0.4))
    reverse = evaluate_tft_phase_charge(spec, DeviceBias(vgs_v=1.5, vds_v=-0.4))
    weak = evaluate_tft_phase_charge(spec, DeviceBias(vgs_v=0.75, vds_v=0.4))

    assert forward.drain_current_a == pytest.approx(-reverse.drain_current_a)
    assert forward.trajectory_resistance_ohm == pytest.approx(reverse.trajectory_resistance_ohm)
    assert weak.region == "subthreshold"
    assert 0.0 < weak.drain_current_a < forward.drain_current_a


def test_bootstrap_uses_charge_conservation_and_target_device_headroom() -> None:
    network = BootstrapNetwork(
        boot_capacitance_f=4e-12,
        target_gate_capacitance_f=1e-12,
        output_load_capacitance_f=2e-12,
        parasitic_loss_capacitance_f=1e-12,
        clock_step_v=4.0,
        initial_gate_v=2.0,
        leakage_charge_c=0.4e-12,
    )
    result = conserve_bootstrap_charge(network, target_threshold_v=1.0, polarity="n")

    expected_delta = (4e-12 * 4.0 - 0.4e-12) / 8e-12
    assert result.gate_boost_v == pytest.approx(expected_delta)
    assert result.target_headroom_v == pytest.approx(2.0 + expected_delta - 1.0)
    assert result.charge_residual_c == pytest.approx(0.0, abs=1e-24)


def test_parasitic_resolution_tracks_each_component_provenance() -> None:
    requested = {
        "output_capacitance_f": ParasiticComponent(2e-12, "F", "sidecar_observed"),
        "pullup_resistance_ohm": ParasiticComponent(30.0, "ohm", "row_observed"),
    }
    resolved = resolve_parasitic_components(
        requested,
        required=(
            "output_capacitance_f",
            "bootstrap_loss_capacitance_f",
            "pullup_resistance_ohm",
        ),
    )

    assert resolved["output_capacitance_f"].status == "observed"
    assert resolved["pullup_resistance_ohm"].status == "physical"
    assert resolved["bootstrap_loss_capacitance_f"].status == "missing"
    assert resolved["bootstrap_loss_capacitance_f"].value_si == 0.0


def test_domain_distance_and_action_decoder_are_semantic_not_column_positional() -> None:
    source = CircuitDomain(
        topology_family="goa_11t2c",
        technology_family="igzo_tft",
        supply_v=10.0,
        clock_period_s=1e-6,
        load_capacitance_f=2e-12,
        role_signature=("pullup", "pulldown", "bootstrap"),
    )
    target = CircuitDomain(
        topology_family="goa_12t3c",
        technology_family="igzo_tft",
        supply_v=5.0,
        clock_period_s=0.5e-6,
        load_capacitance_f=4e-12,
        role_signature=("pullup", "pulldown", "bootstrap", "reset"),
    )
    action = CanonicalAction(role="pullup", parameter="width", operation="log_scale", magnitude=0.2)
    decoded = decode_action(
        action,
        {"role_parameter_map": {"pullup.width": "M1_W"}, "bounds": {"M1_W": [1.0, 12.0]}},
        {"M1_W": 10.0},
    )

    assert domain_distance(source, source).total == pytest.approx(0.0)
    assert domain_distance(source, target).total > 0.0
    assert decoded.column == "M1_W"
    assert decoded.value == pytest.approx(12.0)
    assert decoded.clipped is True


def test_transfer_gate_and_hierarchical_residual_fail_closed_for_ood() -> None:
    gate = evaluate_transfer_gate(
        TransferGateInput(
            domain_distance=0.8,
            feature_ood_score=0.9,
            predictive_std=0.4,
            effective_source_samples=1.5,
            physics_coverage=0.5,
        ),
        {"max_domain_distance": 0.5, "max_feature_ood": 0.6, "max_predictive_std": 0.3, "min_effective_samples": 3.0},
    )
    model = HierarchicalPhysicsResidual(ridge=1e-6).fit(
        pd.DataFrame({"physics": [1.0, 2.0, 1.0, 2.0], "domain": ["a", "a", "b", "b"], "fidelity": [2, 2, 3, 3]}),
        [2.0, 4.0, 3.0, 5.0],
        physics_column="physics",
    )

    assert gate.allowed is False
    assert {"domain_distance", "feature_ood", "predictive_uncertainty", "source_support"} <= set(gate.reasons)
    prediction = model.predict(pd.DataFrame({"physics": [1.5], "domain": ["b"], "fidelity": [3]}))
    assert prediction[0] == pytest.approx(4.0, rel=0.15)


def test_propensity_weights_reduce_observed_selection_bias() -> None:
    weights = compute_propensity_weights([0.9, 0.5, 0.1], minimum_propensity=0.2, max_weight=4.0)

    assert weights.tolist() == pytest.approx([1 / 0.9, 2.0, 4.0])


def test_v4_history_scale_and_selector_emit_transfer_diagnostics() -> None:
    history = pd.DataFrame(
        [
            {"sample_id": f"h{i}", "level_label": "L1" if i >= 3 else "L2", "critical_rc_delay_s": 1e-9 * (i + 1)}
            for i in range(7)
        ]
    )
    context = build_capm_distance_context(
        history,
        weights={"critical_rc_delay_s": 1.0},
        config={"metric_version": "v4", "normalization_enabled": True, "coupling_enabled": False},
    )

    assert context.metric_version == "v4"
    assert context.calibration_status.startswith("crossfit_")
    assert calibrate_v4_distance(context.distance_scale, context) == pytest.approx(0.5)

    candidates = pd.DataFrame([{"candidate_id": "c0", "critical_rc_delay_s": 2.5e-9}])
    selected = select_capm_distance(
        candidates,
        history,
        top_k=1,
        weights={"critical_rc_delay_s": 1.0},
        config={
            "capm_distance": {"metric_version": "v4", "geodesic_enabled": False, "coupling_enabled": False},
            "transfer": {
                "source_domain": {"topology_family": "goa_11t2c", "technology_family": "igzo_tft"},
                "target_domain": {"topology_family": "goa_12t3c", "technology_family": "igzo_tft"},
            },
        },
    )
    diagnostics = json.loads(selected.loc[0, "capm_transfer_diagnostics_json"])
    assert selected.loc[0, "capm_metric_version"] == "v4"
    assert selected.loc[0, "data_source"] == "real_simulation_csv"
    assert selected.loc[0, "engineering_validity"] == "simulation_only"
    assert bool(selected.loc[0, "must_resimulate"]) is True
    assert diagnostics["model"] == "hierarchical_physics_residual_v1"
    assert diagnostics["gate"]["allowed"] is False


def test_v4_log_feature_metric_is_invariant_to_consistent_unit_rescaling() -> None:
    seconds = pd.DataFrame(
        [
            {"level_label": "L1" if index >= 3 else "L2", "critical_rc_delay_s": value * 1e-9}
            for index, value in enumerate((1.00, 1.01, 1.02, 1.03, 1.04, 1.05, 1.06))
        ]
    )
    nanoseconds = seconds.copy()
    nanoseconds["critical_rc_delay_s"] *= 1e9
    config = {
        "metric_version": "v4",
        "normalization_enabled": True,
        "coupling_enabled": False,
        "barrier_enabled": False,
        "geodesic_enabled": False,
    }
    weights = {"critical_rc_delay_s": 1.0}
    seconds_context = build_capm_distance_context(seconds, weights=weights, config=config)
    nanoseconds_context = build_capm_distance_context(nanoseconds, weights=weights, config=config)

    seconds_distance = compute_capm_distance(
        {"critical_rc_delay_s": 1.015e-9},
        {"critical_rc_delay_s": 1.055e-9},
        weights=weights,
        config=config,
        context=seconds_context,
    )["distance"]
    nanoseconds_distance = compute_capm_distance(
        {"critical_rc_delay_s": 1.015},
        {"critical_rc_delay_s": 1.055},
        weights=weights,
        config=config,
        context=nanoseconds_context,
    )["distance"]

    assert nanoseconds_distance == pytest.approx(seconds_distance, rel=1e-12, abs=1e-12)


def _integrated_feature_config(tmp_path=None) -> dict:
    pvt = {}
    if tmp_path is not None:
        pvt["observations_csv"] = str(tmp_path / "pvt.csv")
    return {
        "profile": "transistor_level",
        "electrical_model": {
            "model": "tft_phase_charge_v1",
            "units": {"geometry": "um", "capacitance": "pF", "time": "ns"},
            "devices": {
                role: {
                    "polarity": "n",
                    "width_column": f"{role}_w",
                    "length_column": f"{role}_l",
                    "mobility_column": "shared_mu",
                    "cox_column": "cox",
                    "threshold_column": f"{role}_vth",
                    "vgs_column": f"{role}_vgs",
                    "vds_column": f"{role}_vds",
                }
                for role in ("pullup", "pulldown", "bootstrap")
            },
        },
        "parasitics": {
            "direct_columns": {
                "output_capacitance": {"column": "cpar", "unit": "pF"},
                "pullup_resistance": {"column": "rpar", "unit": "ohm"},
            }
        },
        "pvt": pvt,
    }


def _integrated_row() -> dict:
    row = {
        "sample_id": "s1",
        "C_load": 2.0,
        "C_boot": 4.0,
        "CLK_amp": 3.0,
        "CLK_rise_time": 0.01,
        "CLK_fall_time": 0.01,
        "VDD": 5.0,
        "VSS": 0.0,
        "VGH": 5.0,
        "VGL": 0.0,
        "Vth_shift": 1.0,
        "shared_mu": 100.0,
        "cox": 1e-8,
        "cpar": 1.0,
        "rpar": 20.0,
    }
    for role in ("pullup", "pulldown", "bootstrap"):
        row.update({f"{role}_w": 10.0, f"{role}_l": 1.0, f"{role}_vth": 1.0, f"{role}_vgs": 3.0, f"{role}_vds": 1.0})
    return row


def test_v4_electrical_model_is_routed_through_feature_extraction() -> None:
    config = _integrated_feature_config()
    row = _integrated_row()
    row["pullup_vth"] = -0.5
    row["pullup_vgs"] = 0.0

    features, report = extract_physics_features(pd.DataFrame([row]), config)
    electrical = json.loads(features.loc[0, "capm_electrical_status_json"])

    assert report["electrical_model_version"] == "v4"
    assert electrical["model"] == "tft_phase_charge_v1"
    assert electrical["devices"]["pullup"]["region"] == "linear"
    assert electrical["devices"]["pullup"]["fidelity"] == 2
    assert electrical["parasitics"]["components"]["output_capacitance_f"]["status"] == "physical"
    assert electrical["parasitics"]["components"]["bootstrap_loss_capacitance_f"]["status"] == "missing"


def test_v4_pvt_projection_scales_shared_columns_once_and_partial_observation_wins(tmp_path) -> None:
    pd.DataFrame(
        [
            {
                "sample_id": "s1",
                "corner": "ss",
                "temperature_c": 25.0 + 1e-10,
                "supply_v": 5.0,
                "critical_rc_delay_s": 7.5e-9,
            }
        ]
    ).to_csv(tmp_path / "pvt.csv", index=False)
    config = _integrated_feature_config(tmp_path)
    config["pvt"].update(
        {
            "reference_temperature_c": 25.0,
            "reference_supply_v": 5.0,
            "sample_id_column": "sample_id",
            "observation_match_tolerance": 1e-8,
            "mobility_temperature_exponent": 0.0,
            "vth_temperature_coefficient_v_per_c": 0.0,
            "supply_bias_exponent": 1.0,
            "scenarios": [{"corner": "ss", "temperature_c": 25.0, "supply_v": 5.0}],
            "corner_models": {
                "ss": {
                    "mu_multiplier": 0.5,
                    "vth_shift_v": 0.0,
                    "resistance_multiplier": 1.0,
                    "capacitance_multiplier": 1.0,
                }
            },
        }
    )

    features, _ = extract_physics_features(pd.DataFrame([_integrated_row()]), config)
    scenario = json.loads(features.loc[0, "capm_pvt_features_json"])["ss|25|5"]
    diagnostics = json.loads(features.loc[0, "capm_pvt_diagnostics_json"])["scenarios"]["ss|25|5"]

    nominal_r = float(features.loc[0, "pullup_effective_resistance_ohm"])
    assert scenario["pullup_effective_resistance_ohm"] == pytest.approx(2.0 * (nominal_r - 20.0) + 20.0)
    assert scenario["critical_rc_delay_s"] == pytest.approx(7.5e-9)
    assert diagnostics["status"] == "mixed_observed_projected"
    assert diagnostics["observed_fields"] == ["critical_rc_delay_s"]


def test_phase_network_delay_is_monotone_in_resistance_and_capacitance() -> None:
    base = PhaseNetwork(
        nodes=("out",),
        capacitance_f={"out": 2e-12},
        edges=(PhaseEdge("vdd", "out", 1e3),),
        fixed_voltages_v={"vdd": 5.0},
        initial_voltages_v={"out": 0.0},
    )
    slow_r = PhaseNetwork(**{**base.__dict__, "edges": (PhaseEdge("vdd", "out", 2e3),)})
    slow_c = PhaseNetwork(**{**base.__dict__, "capacitance_f": {"out": 4e-12}})

    nominal = solve_phase_network(base, duration_s=20e-9, time_step_s=0.1e-9, threshold_fraction=0.5)
    resistance = solve_phase_network(slow_r, duration_s=20e-9, time_step_s=0.1e-9, threshold_fraction=0.5)
    capacitance = solve_phase_network(slow_c, duration_s=20e-9, time_step_s=0.1e-9, threshold_fraction=0.5)

    assert resistance.threshold_delay_s > nominal.threshold_delay_s
    assert capacitance.threshold_delay_s > nominal.threshold_delay_s
    assert nominal.fidelity == FidelityLevel.F2_MODEL


def test_pvt_catalog_does_not_treat_deterministic_corners_as_probabilities() -> None:
    catalog = classify_pvt_scenarios(
        [
            PVTScenario("tt", 25.0, 5.0, kind="deterministic_corner"),
            PVTScenario("ss", 125.0, 4.0, kind="deterministic_corner"),
            PVTScenario("mc", 25.0, 5.0, kind="statistical_sample", probability=0.02),
        ]
    )

    assert [item.corner for item in catalog.deterministic] == ["tt", "ss"]
    assert catalog.statistical[0].probability == pytest.approx(0.02)
    assert catalog.deterministic_probability is None


def test_source_weights_and_local_elasticities_support_semantic_transfer() -> None:
    target = CircuitDomain("goa_12t3c", "igzo_tft", 5.0, 1e-6, 2e-12)
    sources = {
        "near": CircuitDomain("goa_12t3c", "igzo_tft", 5.5, 1e-6, 2e-12),
        "far": CircuitDomain("inverter", "cmos", 1.0, 1e-9, 1e-15),
    }
    weights = source_domain_weights(sources, target, temperature=0.2)
    elasticity = estimate_local_elasticities(
        lambda values: values["r"] * values["c"],
        {"r": 10.0, "c": 2.0},
        relative_step=1e-4,
    )

    assert weights["near"] > weights["far"]
    assert sum(weights.values()) == pytest.approx(1.0)
    assert elasticity["r"] == pytest.approx(1.0, rel=1e-3)
    assert elasticity["c"] == pytest.approx(1.0, rel=1e-3)


def test_v4_pvt_aggregation_separates_corners_from_probability() -> None:
    config = {
        "metric_version": "v4",
        "normalization_enabled": False,
        "coupling_enabled": False,
        "barrier_enabled": False,
        "pvt_worst_case_weight": 0.5,
    }
    history = pd.DataFrame(
        [
            {"level_label": "L1", "critical_rc_delay_s": 0.0},
            {"level_label": "L2", "critical_rc_delay_s": 4.0},
        ]
    )
    context = build_capm_distance_context(history, weights={"critical_rc_delay_s": 1.0}, config=config)
    diagnostics = json.dumps(
        {
            "scenarios": {
                "tt|25|5": {"status": "observed", "kind": "deterministic_corner", "weight": 0.99},
                "ss|125|4": {"status": "proxy_projected", "kind": "deterministic_corner", "weight": 0.01},
            }
        }
    )
    left = {
        "critical_rc_delay_s": 0.0,
        "capm_pvt_features_json": json.dumps({"tt|25|5": {"critical_rc_delay_s": 0.0}, "ss|125|4": {"critical_rc_delay_s": 0.0}}),
        "capm_pvt_diagnostics_json": diagnostics,
    }
    right = {
        "critical_rc_delay_s": 1.0,
        "capm_pvt_features_json": json.dumps({"tt|25|5": {"critical_rc_delay_s": 1.0}, "ss|125|4": {"critical_rc_delay_s": 3.0}}),
        "capm_pvt_diagnostics_json": diagnostics,
    }

    result = compute_capm_distance(left, right, weights={"critical_rc_delay_s": 1.0}, config=config, context=context)

    assert result["pvt_deterministic_mean_distance"] == pytest.approx(2.0)
    assert result["pvt_deterministic_worst_distance"] == pytest.approx(3.0)
    assert result["distance"] == pytest.approx(2.5)
    assert result["pvt_violation_probability"] is None


def test_v4_pvt_uses_fixed_union_and_marks_missing_scenario() -> None:
    config = {"metric_version": "v4", "normalization_enabled": False, "coupling_enabled": False, "barrier_enabled": False}
    history = pd.DataFrame(
        [
            {
                "level_label": "L1",
                "critical_rc_delay_s": 1.0,
                "capm_pvt_features_json": json.dumps(
                    {"tt|25|5": {"critical_rc_delay_s": 1.0}, "ss|125|4": {"critical_rc_delay_s": 2.0}}
                ),
            },
            {"level_label": "L2", "critical_rc_delay_s": 3.0},
        ]
    )
    context = build_capm_distance_context(history, weights={"critical_rc_delay_s": 1.0}, config=config)
    left = {
        "critical_rc_delay_s": 1.0,
        "capm_pvt_features_json": json.dumps({"tt|25|5": {"critical_rc_delay_s": 1.0}}),
    }
    right = {
        "critical_rc_delay_s": 2.0,
        "capm_pvt_features_json": json.dumps(
            {"tt|25|5": {"critical_rc_delay_s": 2.0}, "ss|125|4": {"critical_rc_delay_s": 3.0}}
        ),
    }

    result = compute_capm_distance(left, right, weights={"critical_rc_delay_s": 1.0}, config=config, context=context)

    assert result["pvt_expected_scenario_count"] == 2
    assert result["pvt_missing_scenario_count"] == 1
    assert result["pvt_status"] == "incomplete_scenario_coverage"
    assert result["missing_penalty"] >= 0.5


def test_v4_constraint_classes_do_not_promote_heuristics_to_hard_failures() -> None:
    config = {
        "metric_version": "v4",
        "constraint_classes": {
            "hard": [{"feature": "supply_v", "direction": "low", "threshold": 3.0}],
            "validated_risk": [{"feature": "critical_rc_delay_s", "direction": "high", "threshold": 2e-9}],
            "heuristic_warning": [{"feature": "drive_balance_log_ratio", "direction": "abs_high", "threshold": 0.5}],
        },
    }
    report = classify_v4_constraint_risks(
        {"supply_v": 5.0, "critical_rc_delay_s": 4e-9, "drive_balance_log_ratio": 0.8},
        config,
    )

    assert report["hard_constraint_passed"] is True
    assert report["validated_risk_score"] > 0.0
    assert report["heuristic_warning_score"] > 0.0
    assert report["hard_violation_score"] == 0.0


def test_product_mapping_persists_v4_transfer_audit_payload() -> None:
    experiment = OptimizationExperimentRecord(
        experiment_id="e1",
        project_id="p1",
        baseline_design_version_id="v1",
    )
    diagnostics = {"model": "hierarchical_physics_residual_v1", "gate": {"allowed": False}}
    candidate = PiaExperimentAdapter._candidate_from_row(
        experiment,
        0,
        {
            "candidate_id": "c1",
            "x": 1.0,
            "selection_score": 0.8,
            "capm_transfer_trust_score": 0.25,
            "capm_transfer_status": "target_only_exploration",
            "capm_transfer_diagnostics_json": json.dumps(diagnostics),
            "capm_calibration_status": "crossfit_history_p90",
        },
        ("x",),
    )

    assert candidate.selection_scores["capm_transfer_trust_score"] == pytest.approx(0.25)
    assert candidate.selection_scores["capm_transfer_status"] == "target_only_exploration"
    assert candidate.selection_scores["capm_transfer_diagnostics"] == diagnostics
    assert candidate.must_resimulate is True


def test_transfer_engine_and_loco_validation_are_domain_held_out() -> None:
    target = CircuitDomain("goa_12t3c", "igzo_tft", 5.0, 1e-6, 2e-12)
    domains = {
        "a": CircuitDomain("goa_12t3c", "igzo_tft", 5.5, 1e-6, 2e-12),
        "b": CircuitDomain("inverter", "cmos", 1.2, 1e-9, 1e-15),
    }
    history = pd.DataFrame(
        {"domain_id": ["a", "a", "b", "b"], "x": [1.0, 2.0, 10.0, 12.0], "target": [2.0, 4.0, 20.0, 24.0]}
    )
    assessment = CrossCircuitTransferEngine(domains, target).assess(
        history,
        {"x": 1.5},
        feature_columns=("x",),
        predictive_std=0.1,
        physics_coverage=1.0,
    )
    report = leave_one_circuit_out(
        history,
        domain_column="domain_id",
        target_column="target",
        predictor=lambda train, test: test["x"].to_numpy() * 2.0,
    )

    assert assessment.source_weights["a"] > assessment.source_weights["b"]
    assert assessment.feature_ood_score < 0.5
    assert set(report["held_out_domain"]) == {"a", "b"}
    assert report["mae"].max() == pytest.approx(0.0)


@pytest.mark.parametrize(
    "strategy",
    [
        "pia_capm_distance",
        "adaptive_pia_capm",
        "classifier_level_hybrid",
        "active_uncertainty_diversity",
        "active_influence_on_demand",
        "literature_ensemble_hybrid",
    ],
)
def test_v4_reaches_existing_strategy_entrypoints_without_renaming(strategy: str) -> None:
    history = pd.DataFrame(
        [
            {
                "sample_id": f"h{i}",
                "level_label": "L1" if i >= 4 else "L2",
                "critical_rc_delay_s": 1e-9 * (i + 1),
                "overall_score": 70.0 + i * 3.0,
                "hard_constraint_passed": i >= 2,
            }
            for i in range(8)
        ]
    )
    candidates = pd.DataFrame(
        [
            {"candidate_id": "c0", "critical_rc_delay_s": 2.5e-9},
            {"candidate_id": "c1", "critical_rc_delay_s": 4.5e-9},
        ]
    )
    config = {
        "capm_distance": {"metric_version": "v4", "geodesic_enabled": False, "coupling_enabled": False},
        "transfer": {
            "source_domain": {"topology_family": "goa_11t2c", "technology_family": "igzo_tft"},
            "target_domain": {"topology_family": "goa_12t3c", "technology_family": "igzo_tft"},
        },
    }

    result = select_candidates(candidates, history, strategy=strategy, top_k=1, config=config)

    assert len(result.selected_candidates) == 1
    assert result.selected_candidates.iloc[0]["capm_metric_version"] == "v4"
    assert result.selected_candidates.iloc[0]["data_source"] == "real_simulation_csv"
    assert bool(result.selected_candidates.iloc[0]["must_resimulate"]) is True


def test_v4_rejects_ambiguous_duplicate_pvt_observations(tmp_path) -> None:
    pd.DataFrame(
        [
            {"sample_id": "s1", "corner": "ss", "temperature_c": 25.0, "supply_v": 5.0, "critical_rc_delay_s": 1e-9},
            {"sample_id": "s1", "corner": "ss", "temperature_c": 25.0, "supply_v": 5.0, "critical_rc_delay_s": 2e-9},
        ]
    ).to_csv(tmp_path / "pvt.csv", index=False)
    config = _integrated_feature_config(tmp_path)
    config["pvt"].update(
        {
            "reference_temperature_c": 25.0,
            "reference_supply_v": 5.0,
            "mobility_temperature_exponent": 0.0,
            "vth_temperature_coefficient_v_per_c": 0.0,
            "supply_bias_exponent": 1.0,
            "scenarios": [{"corner": "ss", "temperature_c": 25.0, "supply_v": 5.0}],
            "corner_models": {
                "ss": {
                    "mu_multiplier": 1.0,
                    "vth_shift_v": 0.0,
                    "resistance_multiplier": 1.0,
                    "capacitance_multiplier": 1.0,
                }
            },
        }
    )

    features, _ = extract_physics_features(pd.DataFrame([_integrated_row()]), config)
    diagnostics = json.loads(features.loc[0, "capm_pvt_diagnostics_json"])["scenarios"]["ss|25|5"]

    assert features.loc[0, "capm_pvt_status"] == "missing"
    assert diagnostics["reason"] == "ambiguous_duplicate_observations"
    assert diagnostics["observation_match_count"] == 2
