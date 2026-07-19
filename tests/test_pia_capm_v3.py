from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

import goa_eval.pia_ca_llso.selector as selector_module
from goa_eval.pia_ca_llso.benchmark import run_ablation_benchmark
from goa_eval.pia_ca_llso.features import extract_physics_features
from goa_eval.pia_ca_llso.loop import suggest_next_run
from goa_eval.pia_ca_llso.physics_distance import (
    build_capm_distance_context,
    compute_capm_distance,
    constraint_barrier_score,
)
from goa_eval.pia_ca_llso.selector import select_capm_distance


V3_FEATURES = {
    "pullup_overdrive_v": 1.0,
    "pulldown_overdrive_v": 1.0,
    "pullup_effective_resistance_ohm": 10.0,
    "pulldown_effective_resistance_ohm": 12.0,
    "effective_load_capacitance_f": 2.0e-12,
    "pullup_rc_delay_s": 2.0e-11,
    "pulldown_rc_delay_s": 2.4e-11,
    "critical_rc_delay_s": 2.4e-11,
    "bootstrap_coupling_factor_v3": 0.6,
    "bootstrap_headroom_v": 0.8,
    "drive_balance_log_ratio": -0.18,
    "clock_slew_over_rc_ratio": 0.5,
}


def _device_config(pullup_polarity: str = "n") -> dict[str, object]:
    return {
        "model": "tft_square_law_v1",
        "units": {"geometry": "um", "capacitance": "pF", "time": "ns"},
        "devices": {
            "pullup": {
                "polarity": pullup_polarity,
                "width_column": "M_pullup_W",
                "length_column": "M_pullup_L",
                "mobility_column": "mu_pullup_cm2_v_s",
                "cox_column": "cox_f_per_cm2",
                "threshold_column": "pullup_vth_v",
                "vgs_column": "pullup_vgs_v",
                "vds_column": "pullup_vds_v",
                "observed_resistance_column": "pullup_observed_r_ohm",
            },
            "pulldown": {
                "polarity": "n",
                "width_column": "M_pulldown_W",
                "length_column": "M_pulldown_L",
                "mobility_column": "mu_pulldown_cm2_v_s",
                "cox_column": "cox_f_per_cm2",
                "threshold_column": "pulldown_vth_v",
                "vgs_column": "pulldown_vgs_v",
                "vds_column": "pulldown_vds_v",
                "observed_resistance_column": "pulldown_observed_r_ohm",
            },
            "bootstrap": {
                "polarity": "n",
                "width_column": "M_bootstrap_W",
                "length_column": "M_bootstrap_L",
                "mobility_column": "mu_bootstrap_cm2_v_s",
                "cox_column": "cox_f_per_cm2",
                "threshold_column": "bootstrap_vth_v",
                "vgs_column": "bootstrap_vgs_v",
                "vds_column": "bootstrap_vds_v",
            },
        },
    }


def _base_row() -> dict[str, float | str]:
    return {
        "sample_id": "d1",
        "M_pullup_W": 10.0,
        "M_pullup_L": 1.0,
        "M_pulldown_W": 10.0,
        "M_pulldown_L": 1.0,
        "M_reset_W": 2.0,
        "M_reset_L": 1.0,
        "M_bootstrap_W": 5.0,
        "M_bootstrap_L": 1.0,
        "C_load": 2.0,
        "C_boot": 4.0,
        "VDD": 5.0,
        "VSS": 0.0,
        "VGH": 5.0,
        "VGL": 0.0,
        "Vth_shift": 1.0,
        "CLK_amp": 3.0,
        "CLK_rise_time": 0.01,
        "CLK_fall_time": 0.01,
        "mu_pullup_cm2_v_s": 100.0,
        "mu_pulldown_cm2_v_s": 100.0,
        "mu_bootstrap_cm2_v_s": 100.0,
        "cox_f_per_cm2": 1.0e-8,
        "pullup_vth_v": 1.0,
        "pullup_vgs_v": 3.0,
        "pullup_vds_v": 1.0,
        "pulldown_vth_v": 1.0,
        "pulldown_vgs_v": 3.0,
        "pulldown_vds_v": 1.0,
        "bootstrap_vth_v": 1.0,
        "bootstrap_vgs_v": 1.5,
        "bootstrap_vds_v": 0.5,
    }


def _feature_config(pullup_polarity: str = "n") -> dict[str, object]:
    return {
        "profile": "transistor_level",
        "electrical_features_enabled": True,
        "electrical_model": _device_config(pullup_polarity),
        "parasitics": {
            "direct_columns": {
                "output_capacitance": {"column": "parasitic_output_cap", "unit": "pF"},
                "bootstrap_loss_capacitance": {"column": "parasitic_boot_loss_cap", "unit": "pF"},
                "pullup_resistance": {"column": "parasitic_pullup_r", "unit": "ohm"},
                "pulldown_resistance": {"column": "parasitic_pulldown_r", "unit": "ohm"},
            }
        },
    }


def test_v3_electrical_kernel_uses_si_units_regions_and_parasitics() -> None:
    row = {
        **_base_row(),
        "parasitic_output_cap": 1.0,
        "parasitic_boot_loss_cap": 0.5,
        "parasitic_pullup_r": 100.0,
        "parasitic_pulldown_r": 200.0,
    }

    features, report = extract_physics_features(pd.DataFrame([row]), _feature_config())

    assert features.loc[0, "effective_load_capacitance_f"] == pytest.approx(3.0e-12)
    assert features.loc[0, "pullup_effective_resistance_ohm"] > 100.0
    assert features.loc[0, "pulldown_rc_delay_s"] > features.loc[0, "pullup_rc_delay_s"]
    assert 0.0 < features.loc[0, "bootstrap_coupling_factor_v3"] < 1.0
    electrical = json.loads(features.loc[0, "capm_electrical_status_json"])
    assert electrical["devices"]["pullup"]["region"] == "linear"
    assert electrical["features"]["pullup_rc_delay_s"] == "physical"
    assert report["electrical_model_version"] == "v3"


def test_v3_polarity_normalization_mirrors_n_and_p_devices() -> None:
    n_features, _ = extract_physics_features(pd.DataFrame([_base_row()]), _feature_config("n"))
    p_row = {**_base_row(), "pullup_vgs_v": -3.0, "pullup_vds_v": -1.0}
    p_features, _ = extract_physics_features(pd.DataFrame([p_row]), _feature_config("p"))

    assert p_features.loc[0, "pullup_overdrive_v"] == pytest.approx(n_features.loc[0, "pullup_overdrive_v"])
    assert p_features.loc[0, "pullup_effective_resistance_ohm"] == pytest.approx(
        n_features.loc[0, "pullup_effective_resistance_ohm"]
    )


def test_v3_missing_bias_falls_back_without_fabricating_region() -> None:
    row = _base_row()
    row.pop("pullup_vgs_v")

    features, _ = extract_physics_features(pd.DataFrame([row]), _feature_config())

    electrical = json.loads(features.loc[0, "capm_electrical_status_json"])
    assert electrical["devices"]["pullup"]["region"] == "unknown"
    assert electrical["features"]["pullup_rc_delay_s"] == "proxy_fallback"
    assert json.loads(features.loc[0, "physics_feature_status_json"])["pullup_rc_delay_s"] == "proxy_fallback"


def test_v3_unsupported_units_degrade_explicitly_instead_of_crashing() -> None:
    config = _feature_config()
    config["electrical_model"]["units"]["capacitance"] = "unknown_cap_unit"

    features, report = extract_physics_features(pd.DataFrame([_base_row()]), config)

    electrical = json.loads(features.loc[0, "capm_electrical_status_json"])
    assert electrical["status"] == "missing"
    assert "unsupported electrical unit" in electrical["reason"].lower()
    assert features.loc[0, "critical_rc_delay_s"] == 0.0
    assert report["electrical_model_version"] == "v3"


def test_v3_barrier_reads_only_canonical_features() -> None:
    safe = {**V3_FEATURES, "pullup_region_code": 2.0, "pulldown_region_code": 2.0}
    risky = {**safe, "pullup_overdrive_v": -0.1, "critical_rc_delay_s": 9.0e-9}
    config = {
        "metric_version": "v3",
        "min_device_overdrive_v": 0.1,
        "max_critical_rc_delay_s": 1.0e-9,
        "min_bootstrap_coupling_factor_v3": 0.3,
        "min_bootstrap_headroom_v": 0.1,
        "max_abs_drive_balance_log_ratio": 1.0,
        "max_clock_slew_over_rc_ratio": 2.0,
    }

    assert constraint_barrier_score(safe, config) == 0.0
    assert constraint_barrier_score(risky, config) > 0.0
    assert constraint_barrier_score({**safe, "ron_pullup_cload_proxy": 1.0e9}, config) == 0.0


def test_v3_context_rejects_legacy_or_arbitrary_distance_weights() -> None:
    history = _v3_history()
    history["ron_pullup_cload_proxy"] = 99.0

    context = build_capm_distance_context(
        history,
        weights={"critical_rc_delay_s": 1.0, "ron_pullup_cload_proxy": 100.0},
        config={"metric_version": "v3"},
    )

    assert "critical_rc_delay_s" in context.feature_keys
    assert "ron_pullup_cload_proxy" not in context.feature_keys
    assert set(context.feature_keys) <= set(V3_FEATURES)
    raw_context = build_capm_distance_context(
        pd.DataFrame([{"sample_id": "h", "level_label": "L1", "x": 1.0}]),
        config={"metric_version": "v3"},
    )
    assert raw_context.feature_keys == ()


def _v3_history() -> pd.DataFrame:
    rows = []
    for index in range(7):
        row = {
            "sample_id": f"h{index}",
            "level_label": "L1" if index >= 4 else "L2",
            **{key: value * (1.0 + 0.08 * index) for key, value in V3_FEATURES.items()},
            "physics_feature_status_json": json.dumps({key: "physical" for key in V3_FEATURES}),
            "capm_electrical_status_json": json.dumps({"status": "physical"}),
            "capm_pvt_status": "nominal_only",
            "capm_pvt_diagnostics_json": "{}",
        }
        rows.append(row)
    return pd.DataFrame(rows)


def test_v3_selector_uses_history_calibration_not_candidate_pool() -> None:
    history = _v3_history()
    target = {"candidate_id": "target", **history.iloc[2].to_dict()}
    peer = {"candidate_id": "peer", **history.iloc[4].to_dict()}
    outlier = {"candidate_id": "outlier", **history.iloc[0].to_dict(), "critical_rc_delay_s": 1.0}
    config = {"capm_distance": {"metric_version": "v3", "geodesic_enabled": False, "barrier_enabled": False}}

    single = select_capm_distance(pd.DataFrame([target, peer]), history, top_k=2, config=config)
    pooled = select_capm_distance(pd.DataFrame([target, peer, outlier]), history, top_k=3, config=config)
    pooled_target = pooled.loc[pooled["candidate_id"] == "target"].iloc[0]

    assert pooled_target["capm_distance_to_l1_normalized"] == pytest.approx(
        single.loc[single["candidate_id"] == "target", "capm_distance_to_l1_normalized"].iloc[0]
    )
    assert pooled_target["capm_calibration_status"] == "history_p90"
    assert json.loads(pooled_target["capm_distance_calibration_json"])["candidate_pool_fitted"] is False
    assert pooled_target["capm_electrical_status_json"] == target["capm_electrical_status_json"]


def test_v3_degenerate_history_has_deterministic_calibration_status() -> None:
    history = pd.DataFrame(
        [{"sample_id": f"h{i}", "level_label": "L1", **V3_FEATURES} for i in range(3)]
    )
    context = build_capm_distance_context(history, config={"metric_version": "v3"})

    assert context.distance_scale == 0.0
    assert context.calibration_status == "degenerate_history"


def test_v3_pvt_projection_and_observation_precedence(tmp_path) -> None:
    observations = pd.DataFrame(
        [
            {
                "sample_id": "d1",
                "corner": "ss",
                "temperature_c": 125.0,
                "supply_v": 4.0,
                "pullup_observed_r_ohm": 900000.0,
                "pulldown_observed_r_ohm": 800000.0,
            }
        ]
    )
    observation_path = tmp_path / "pvt.csv"
    observations.to_csv(observation_path, index=False)
    config = _feature_config()
    config["pvt"] = {
        "reference_temperature_c": 25.0,
        "reference_supply_v": 5.0,
        "mobility_temperature_exponent": 1.5,
        "vth_temperature_coefficient_v_per_c": 0.001,
        "sample_id_column": "sample_id",
        "observations_csv": str(observation_path),
        "scenarios": [
            {"corner": "tt", "temperature_c": 25.0, "supply_v": 5.0},
            {"corner": "ss", "temperature_c": 125.0, "supply_v": 4.0},
        ],
        "corner_models": {
            "tt": {"mu_multiplier": 1.0, "vth_shift_v": 0.0, "resistance_multiplier": 1.0, "capacitance_multiplier": 1.0},
            "ss": {"mu_multiplier": 0.6, "vth_shift_v": 0.2, "resistance_multiplier": 1.3, "capacitance_multiplier": 1.2},
        },
    }

    features, _ = extract_physics_features(pd.DataFrame([_base_row()]), config)
    scenarios = json.loads(features.loc[0, "capm_pvt_features_json"])
    diagnostics = json.loads(features.loc[0, "capm_pvt_diagnostics_json"])

    assert scenarios["ss|125|4"]["pullup_effective_resistance_ohm"] == pytest.approx(900000.0)
    assert scenarios["ss|125|4"]["critical_rc_delay_s"] > scenarios["tt|25|5"]["critical_rc_delay_s"]
    assert diagnostics["scenarios"]["ss|125|4"]["status"] == "mixed_observed_projected"
    assert features.loc[0, "capm_pvt_status"] == "mixed_observed_projected"


def test_v3_pvt_missing_corner_is_not_silently_treated_as_tt() -> None:
    config = _feature_config()
    config["pvt"] = {
        "reference_temperature_c": 25.0,
        "reference_supply_v": 5.0,
        "scenarios": [{"corner": "ff", "temperature_c": 25.0, "supply_v": 5.0}],
        "corner_models": {},
    }

    features, _ = extract_physics_features(pd.DataFrame([_base_row()]), config)
    scenarios = json.loads(features.loc[0, "capm_pvt_features_json"])
    diagnostics = json.loads(features.loc[0, "capm_pvt_diagnostics_json"])

    assert "ff|25|5" not in scenarios
    assert diagnostics["scenarios"]["ff|25|5"]["status"] == "missing"
    assert features.loc[0, "capm_pvt_status"] == "missing"


def test_v3_pvt_distance_uses_mean_and_worst_case() -> None:
    history = pd.DataFrame(
        [
            {"sample_id": "h0", "level_label": "L1", "critical_rc_delay_s": 0.0},
            {"sample_id": "h1", "level_label": "L2", "critical_rc_delay_s": 4.0},
        ]
    )
    context = build_capm_distance_context(
        history,
        weights={"critical_rc_delay_s": 1.0},
        config={"metric_version": "v3", "normalization_enabled": False, "barrier_enabled": False, "coupling_enabled": False},
    )
    history["capm_pvt_features_json"] = json.dumps(
        {"tt|25|5": {"critical_rc_delay_s": 1.0}, "ss|125|4": {"critical_rc_delay_s": 2.0}}
    )
    context = build_capm_distance_context(
        history,
        weights={"critical_rc_delay_s": 1.0},
        config={"metric_version": "v3", "normalization_enabled": False, "barrier_enabled": False, "coupling_enabled": False},
    )
    left = {
        "critical_rc_delay_s": 0.0,
        "capm_pvt_features_json": json.dumps({"tt|25|5": {"critical_rc_delay_s": 0.0}, "ss|125|4": {"critical_rc_delay_s": 2.0}}),
    }
    right = {
        "critical_rc_delay_s": 1.0,
        "capm_pvt_features_json": json.dumps({"tt|25|5": {"critical_rc_delay_s": 1.0}, "ss|125|4": {"critical_rc_delay_s": 5.0}}),
    }

    result = compute_capm_distance(left, right, context=context, config={"metric_version": "v3", "normalization_enabled": False, "barrier_enabled": False, "coupling_enabled": False})

    assert result["distance"] == pytest.approx(2.5)
    assert result["pvt_status"] == "scenario_aggregated:2"
    assert context.pvt_scenarios == ("ss|125|4", "tt|25|5")


def test_v3_pvt_missing_and_proxy_coverage_feed_distance_penalties() -> None:
    history = pd.DataFrame(
        [
            {"sample_id": "h0", "level_label": "L1", "critical_rc_delay_s": 1.0},
            {"sample_id": "h1", "level_label": "L2", "critical_rc_delay_s": 2.0},
        ]
    )
    config = {
        "metric_version": "v3",
        "normalization_enabled": False,
        "barrier_enabled": False,
        "coupling_enabled": False,
    }
    context = build_capm_distance_context(history, weights={"critical_rc_delay_s": 1.0}, config=config)
    complete = {
        "critical_rc_delay_s": 1.0,
        "capm_pvt_diagnostics_json": json.dumps(
            {"scenarios": {"tt|25|5": {"status": "observed"}, "ss|125|4": {"status": "observed"}}}
        ),
    }
    incomplete = {
        "critical_rc_delay_s": 1.0,
        "capm_pvt_diagnostics_json": json.dumps(
            {"scenarios": {"tt|25|5": {"status": "proxy_projected"}, "ss|125|4": {"status": "missing"}}}
        ),
    }

    result = compute_capm_distance(incomplete, complete, context=context, config=config)

    assert result["missing_penalty"] == pytest.approx(0.5)
    assert result["proxy_fallback_penalty"] == pytest.approx(0.125)
    assert result["distance"] > 0.5


def test_v3_parasitic_summary_maps_nets_and_converts_units(tmp_path) -> None:
    summary_path = tmp_path / "parasitic_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "has_rc_data": True,
                "resistance_unit": "kOhm",
                "capacitance_unit": "fF",
                "grouped_by_net": [
                    {"net": "OUT", "capacitance": 1000.0},
                    {"net": "BOOT", "capacitance": 500.0},
                    {"net": "PU", "resistance": 2.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    row = {**_base_row(), "parasitic_summary_path": str(summary_path)}
    config = _feature_config()
    config["parasitics"] = {
        "summary_path_column": "parasitic_summary_path",
        "net_role_map": {"OUT": "output", "BOOT": "bootstrap_loss", "PU": "pullup_path"},
    }

    features, _ = extract_physics_features(pd.DataFrame([row]), config)
    electrical = json.loads(features.loc[0, "capm_electrical_status_json"])

    assert features.loc[0, "effective_load_capacitance_f"] == pytest.approx(3.0e-12)
    assert features.loc[0, "bootstrap_coupling_factor_v3"] == pytest.approx(4.0 / 7.5)
    assert electrical["parasitics"]["source"] == "summary"


def test_v3_pvt_corner_multipliers_apply_to_mapped_parasitic_summary(tmp_path) -> None:
    summary_path = tmp_path / "parasitic_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "has_rc_data": True,
                "resistance_unit": "ohm",
                "capacitance_unit": "pF",
                "grouped_by_net": [
                    {"net": "OUT", "capacitance": 1.0},
                    {"net": "PU", "resistance": 100.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    row = {**_base_row(), "parasitic_summary_path": str(summary_path)}
    config = _feature_config()
    config["parasitics"] = {
        "summary_path_column": "parasitic_summary_path",
        "net_role_map": {"OUT": "output", "PU": "pullup_path"},
    }
    config["pvt"] = {
        "reference_temperature_c": 25.0,
        "reference_supply_v": 5.0,
        "scenarios": [
            {"corner": "tt", "temperature_c": 25.0, "supply_v": 5.0},
            {"corner": "ss", "temperature_c": 25.0, "supply_v": 5.0},
        ],
        "corner_models": {
            "tt": {"mu_multiplier": 1.0, "vth_shift_v": 0.0, "resistance_multiplier": 1.0, "capacitance_multiplier": 1.0},
            "ss": {"mu_multiplier": 1.0, "vth_shift_v": 0.0, "resistance_multiplier": 2.0, "capacitance_multiplier": 2.0},
        },
    }

    features, _ = extract_physics_features(pd.DataFrame([row]), config)
    scenarios = json.loads(features.loc[0, "capm_pvt_features_json"])

    assert scenarios["ss|25|5"]["effective_load_capacitance_f"] > scenarios["tt|25|5"]["effective_load_capacitance_f"]
    assert scenarios["ss|25|5"]["pullup_effective_resistance_ohm"] > scenarios["tt|25|5"]["pullup_effective_resistance_ohm"]


def _raw_v3_config() -> dict[str, object]:
    return {
        "physics_features": {"profile": "transistor_level", "electrical_features_enabled": True},
        "electrical_model": _device_config(),
        "parasitics": {},
        "pvt": {
            "reference_temperature_c": 25.0,
            "reference_supply_v": 5.0,
            "scenarios": [{"corner": "tt", "temperature_c": 25.0, "supply_v": 5.0}],
            "corner_models": {
                "tt": {"mu_multiplier": 1.0, "vth_shift_v": 0.0, "resistance_multiplier": 1.0, "capacitance_multiplier": 1.0}
            },
        },
        "capm_distance": {"metric_version": "v3", "geodesic_enabled": False},
        "repair_candidates": {"enabled": False},
    }


def _raw_history_and_candidates() -> tuple[pd.DataFrame, pd.DataFrame]:
    history_rows = []
    for index in range(7):
        history_rows.append(
            {
                **_base_row(),
                "sample_id": f"h{index}",
                "M_pullup_W": 8.0 + index,
                "overall_score": 45.0 + 8.0 * index,
                "hard_constraint_passed": index >= 3,
                "status": "ok",
            }
        )
    candidates = pd.DataFrame(
        [
            {**_base_row(), "sample_id": "c1", "candidate_id": "c1", "M_pullup_W": 11.5},
            {**_base_row(), "sample_id": "c2", "candidate_id": "c2", "M_pullup_W": 7.0},
        ]
    )
    return pd.DataFrame(history_rows), candidates


def test_v3_loop_merges_explicit_top_level_contract_and_preserves_boundaries() -> None:
    history, candidates = _raw_history_and_candidates()

    result = suggest_next_run(history, candidates, _raw_v3_config(), "pia_capm_distance", 2)

    assert set(result.all_candidates["capm_metric_version"]) == {"v3"}
    assert "critical_rc_delay_s" in result.all_candidates
    assert set(result.all_candidates["capm_pvt_status"]) == {"proxy_projected"}
    assert set(result.selected_candidates["data_source"]) == {"real_simulation_csv"}
    assert set(result.selected_candidates["engineering_validity"]) == {"simulation_only"}
    assert result.selected_candidates["must_resimulate"].map(bool).all()


def test_v3_benchmark_extracts_canonical_features_from_raw_rows(tmp_path) -> None:
    history, candidates = _raw_history_and_candidates()
    candidates["overall_score"] = [82.0, 30.0]
    candidates["hard_constraint_passed"] = [True, False]

    run_ablation_benchmark(
        history,
        candidates,
        tmp_path,
        strategies=["pia_capm_distance"],
        top_k=2,
        config=_raw_v3_config(),
    )

    selected = pd.read_csv(tmp_path / "pia_capm_distance_selected_candidates.csv")
    assert set(selected["capm_metric_version"]) == {"v3"}
    assert "critical_rc_delay_s" in selected
    assert set(selected["engineering_validity"]) == {"simulation_only"}
    summary = json.loads((tmp_path / "pia_ablation_summary.json").read_text(encoding="utf-8"))
    assert summary["must_resimulate"] is True


def test_transistor_profile_enables_v3_contract_without_unverified_corner_coefficients() -> None:
    profile = yaml.safe_load(Path("config/pia_ca_llso_transistor_profile.yaml").read_text(encoding="utf-8"))

    assert profile["capm_distance"]["metric_version"] == "v3"
    assert profile["electrical_model"]["model"] == "tft_square_law_v1"
    assert profile["pvt"]["corner_models"]["tt"]["mu_multiplier"] == 1.0
    assert set(profile["pvt"]["corner_models"]) == {"tt"}
    assert profile["metadata"] == {
        "circuit_profile": "transistor_level_goa",
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }


@pytest.mark.parametrize(
    "strategy",
    [
        "adaptive_pia_capm",
        "classifier_level_hybrid",
        "active_uncertainty_diversity",
        "active_influence_on_demand",
        "literature_ensemble_hybrid",
    ],
)
def test_v3_all_capm_strategy_call_chains_share_the_new_metric(strategy: str) -> None:
    history, candidates = _raw_history_and_candidates()

    result = suggest_next_run(history, candidates, _raw_v3_config(), strategy, 2)

    assert set(result.all_candidates["capm_metric_version"]) == {"v3"}
    assert result.all_candidates["capm_distance_to_l1_normalized"].between(0.0, 1.0).all()
    assert set(result.all_candidates["capm_calibration_status"]) <= {
        "history_p90",
        "history_max_small_sample",
        "degenerate_history",
    }


def test_v3_active_distance_calls_reuse_a_history_context(monkeypatch) -> None:
    history, candidates = _raw_history_and_candidates()
    original = selector_module.compute_capm_distance
    contexts = []
    compared_feature_sets = []

    def recording_distance(*args, **kwargs):
        context = kwargs.get("context")
        if context is None and len(args) >= 5:
            context = args[4]
        contexts.append(context)
        compared_feature_sets.append((set(args[0].index), set(args[1].index)))
        return original(*args, **kwargs)

    monkeypatch.setattr(selector_module, "compute_capm_distance", recording_distance)

    suggest_next_run(history, candidates, _raw_v3_config(), "active_influence_on_demand", 2)

    assert contexts
    assert all(context is not None for context in contexts)
    assert all(context.metric_version == "v3" for context in contexts)
    assert all("critical_rc_delay_s" in left and "critical_rc_delay_s" in right for left, right in compared_feature_sets)
