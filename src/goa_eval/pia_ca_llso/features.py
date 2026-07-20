from __future__ import annotations

import json
from typing import Iterable, Any, Mapping

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.electrical_model import attach_v3_electrical_features

DEFAULT_FORBIDDEN_METRIC_NAMES = [
    "delay",
    "rise_time",
    "fall_time",
    "power",
    "waveform_score",
    "output_high",
    "output_low",
    "overshoot",
    "undershoot",
    "holding_droop",
    "total_score",
    "overall_score",
    "hard_constraint_passed",
]


def _safe_div(a: pd.Series | float, b: pd.Series | float) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.asarray(b, dtype=float) != 0, np.asarray(a, dtype=float) / np.asarray(b, dtype=float), 0.0)


def _series(frame: pd.DataFrame, name: str, missing: set[str], default: float = 0.0) -> pd.Series:
    if name in frame.columns:
        return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    missing.add(name)
    return pd.Series(default, index=frame.index, dtype="float64")


def _first_series(frame: pd.DataFrame, names: Iterable[str], missing: set[str], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    for name in names:
        missing.add(name)
    return pd.Series(default, index=frame.index, dtype="float64")


def _optional_series(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[name], errors="coerce")


def _attach_electrical_features(
    features: pd.DataFrame,
    frame: pd.DataFrame,
    c_load: pd.Series,
    c_boot: pd.Series,
    pullup_w_l: pd.Series | np.ndarray,
    pulldown_w_l: pd.Series | np.ndarray,
    vgh_margin: pd.Series | np.ndarray,
    vgl_margin: pd.Series | np.ndarray,
) -> None:
    epsilon = 1e-12
    mu_pullup = _optional_series(frame, "mu_pullup_cm2_v_s")
    mu_pulldown = _optional_series(frame, "mu_pulldown_cm2_v_s")
    cox = _optional_series(frame, "cox_f_per_cm2")
    c_parasitic = _optional_series(frame, "C_parasitic")
    clk_amp = _optional_series(frame, "CLK_amp")

    c_parasitic_effective = c_parasitic.fillna(0.0).clip(lower=0.0)
    effective_load = c_load.astype(float) + c_parasitic_effective
    pu_physical = mu_pullup.notna() & cox.notna()
    pd_physical = mu_pulldown.notna() & cox.notna()
    pu_factor = mu_pullup.where(pu_physical, 1.0) * cox.where(pu_physical, 1.0)
    pd_factor = mu_pulldown.where(pd_physical, 1.0) * cox.where(pd_physical, 1.0)
    pu_drive = (
        pu_factor.to_numpy(dtype=float)
        * np.asarray(pullup_w_l, dtype=float)
        * np.maximum(np.asarray(vgh_margin, dtype=float), epsilon)
    )
    pd_drive = (
        pd_factor.to_numpy(dtype=float)
        * np.asarray(pulldown_w_l, dtype=float)
        * np.maximum(np.asarray(vgl_margin, dtype=float), epsilon)
    )
    clk_effective = clk_amp.fillna(0.0).clip(lower=0.0)
    bootstrap_denominator = c_boot.astype(float) + effective_load

    features["effective_load_capacitance"] = effective_load
    features["pullup_rc_delay_proxy_v2"] = _safe_div(effective_load, np.maximum(pu_drive, epsilon))
    features["pulldown_rc_delay_proxy_v2"] = _safe_div(effective_load, np.maximum(pd_drive, epsilon))
    features["bootstrap_charge_proxy"] = c_boot.astype(float) * clk_effective
    features["bootstrap_coupling_factor"] = _safe_div(c_boot, bootstrap_denominator.replace(0, np.nan))
    features["bootstrap_voltage_proxy"] = clk_effective * features["bootstrap_coupling_factor"]

    statuses: list[str] = []
    for index in frame.index:
        load_status = "physical" if pd.notna(c_parasitic.loc[index]) else "proxy_fallback"
        clock_status = "physical" if pd.notna(clk_amp.loc[index]) else "missing"
        pu_status = "physical" if bool(pu_physical.loc[index]) and load_status == "physical" else "proxy_fallback"
        pd_status = "physical" if bool(pd_physical.loc[index]) and load_status == "physical" else "proxy_fallback"
        if clock_status == "missing":
            bootstrap_voltage_status = "missing"
        else:
            bootstrap_voltage_status = "physical" if load_status == "physical" else "proxy_fallback"
        status = {
            "effective_load_capacitance": load_status,
            "pullup_rc_delay_proxy_v2": pu_status,
            "pulldown_rc_delay_proxy_v2": pd_status,
            "bootstrap_charge_proxy": clock_status,
            "bootstrap_coupling_factor": load_status,
            "bootstrap_voltage_proxy": bootstrap_voltage_status,
        }
        statuses.append(json.dumps(status, ensure_ascii=True, sort_keys=True))
    features["physics_feature_status_json"] = statuses


def extract_physics_features(frame: pd.DataFrame, profile_config: dict[str, Any] | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    config = profile_config or {}
    profile = config.get("profile", "generic")
    missing: set[str] = set()
    features = pd.DataFrame(index=frame.index)

    w = _series(frame, "W", missing)
    length = _series(frame, "L", missing, 1.0)
    c_load = _series(frame, "C_load", missing, 1.0)
    c_boot = _series(frame, "C_boot", missing, 1.0)
    r_eq = _series(frame, "R_eq", missing)
    vgh = _series(frame, "VGH", missing)
    vgl = _series(frame, "VGL", missing)
    vth = _series(frame, "Vth_shift", missing)
    features["w_l"] = _safe_div(w, length)
    features["c_load_c_boot_ratio"] = _safe_div(c_load, c_boot)
    features["r_eq_c_load"] = r_eq * c_load
    features["v_swing"] = vgh - vgl
    features["voltage_margin"] = vgh - vth
    features["drive_ratio"] = _safe_div(w, c_load)
    features["load_ratio"] = _safe_div(c_load, w.replace(0, np.nan))
    features["normalized_slew"] = _series(frame, "CLK_rise_time", missing) + _series(frame, "CLK_fall_time", missing)
    features["capacitance_ratio"] = _safe_div(c_boot, c_load)

    if profile == "goa":
        pu_w = _series(frame, "TFT_pullup_W", missing)
        pu_l = _series(frame, "TFT_pullup_L", missing, 1.0)
        pd_w = _series(frame, "TFT_pulldown_W", missing)
        pd_l = _series(frame, "TFT_pulldown_L", missing, 1.0)
        rst_w = _series(frame, "TFT_reset_W", missing)
        rst_l = _series(frame, "TFT_reset_L", missing, 1.0)
        boot_w = _series(frame, "TFT_bootstrap_W", missing)
        boot_l = _series(frame, "TFT_bootstrap_L", missing, 1.0)
        features["pullup_w_l"] = _safe_div(pu_w, pu_l)
        features["pulldown_w_l"] = _safe_div(pd_w, pd_l)
        features["reset_w_l"] = _safe_div(rst_w, rst_l)
        features["bootstrap_w_l"] = _safe_div(boot_w, boot_l)
        features["pullup_pulldown_ratio"] = _safe_div(features["pullup_w_l"], features["pulldown_w_l"].replace(0, np.nan))
        features["cboot_cload_ratio"] = _safe_div(c_boot, c_load)
        features["ron_pullup_cload_proxy"] = _safe_div(c_load, features["pullup_w_l"].replace(0, np.nan))
        features["ron_pulldown_cload_proxy"] = _safe_div(c_load, features["pulldown_w_l"].replace(0, np.nan))
        features["clk_slew_proxy"] = _series(frame, "CLK_rise_time", missing) + _series(frame, "CLK_fall_time", missing)
        features["vgh_vth_margin"] = vgh - vth
        features["vgl_off_margin"] = np.abs(vgl) - np.abs(vth)
        features["holding_droop_proxy"] = _safe_div(c_load, c_boot + c_load)
        if config.get("electrical_features_enabled", True) is not False:
            _attach_electrical_features(
                features,
                frame,
                c_load,
                c_boot,
                features["pullup_w_l"],
                features["pulldown_w_l"],
                features["vgh_vth_margin"],
                features["vgl_off_margin"],
            )

    if profile == "transistor_level":
        pu_w = _first_series(frame, ["M_pullup_W", "TFT_pullup_W"], missing)
        pu_l = _first_series(frame, ["M_pullup_L", "TFT_pullup_L"], missing, 1.0)
        pd_w = _first_series(frame, ["M_pulldown_W", "TFT_pulldown_W"], missing)
        pd_l = _first_series(frame, ["M_pulldown_L", "TFT_pulldown_L"], missing, 1.0)
        rst_w = _first_series(frame, ["M_reset_W", "TFT_reset_W"], missing)
        rst_l = _first_series(frame, ["M_reset_L", "TFT_reset_L"], missing, 1.0)
        boot_w = _first_series(frame, ["M_bootstrap_W", "TFT_bootstrap_W"], missing)
        boot_l = _first_series(frame, ["M_bootstrap_L", "TFT_bootstrap_L"], missing, 1.0)
        vdd = _series(frame, "VDD", missing)
        vss = _series(frame, "VSS", missing)
        clk_rise = _series(frame, "CLK_rise_time", missing)
        clk_fall = _series(frame, "CLK_fall_time", missing)
        pullup_w_l = _safe_div(pu_w, pu_l)
        pulldown_w_l = _safe_div(pd_w, pd_l)
        reset_w_l = _safe_div(rst_w, rst_l)
        bootstrap_w_l = _safe_div(boot_w, boot_l)
        total_w = pu_w + pd_w + rst_w + boot_w
        features["pullup_w_l"] = pullup_w_l
        features["pulldown_w_l"] = pulldown_w_l
        features["reset_w_l"] = reset_w_l
        features["bootstrap_w_l"] = bootstrap_w_l
        features["pullup_pulldown_ratio"] = _safe_div(pullup_w_l, pd.Series(pulldown_w_l, index=frame.index).replace(0, np.nan))
        features["drive_to_load_ratio"] = _safe_div(pullup_w_l + pulldown_w_l, c_load.replace(0, np.nan))
        features["cboot_cload_ratio"] = _safe_div(c_boot, c_load)
        features["ron_pullup_cload_proxy"] = _safe_div(c_load, pd.Series(pullup_w_l, index=frame.index).replace(0, np.nan))
        features["ron_pulldown_cload_proxy"] = _safe_div(c_load, pd.Series(pulldown_w_l, index=frame.index).replace(0, np.nan))
        features["clk_slew_proxy"] = clk_rise + clk_fall
        features["vgh_vth_margin"] = vgh - vth
        features["vgl_off_margin"] = np.abs(vgl) - np.abs(vth)
        features["supply_swing"] = vdd - vss
        features["holding_droop_proxy"] = _safe_div(c_load, c_boot + c_load)
        features["area_proxy"] = total_w * (pu_l + pd_l + rst_l + boot_l) / 4.0
        if config.get("electrical_features_enabled", True) is not False:
            _attach_electrical_features(
                features,
                frame,
                c_load,
                c_boot,
                features["pullup_w_l"],
                features["pulldown_w_l"],
                features["vgh_vth_margin"],
                features["vgl_off_margin"],
            )

    electrical_report: dict[str, Any] = {}
    electrical_model = config.get("electrical_model", {})
    if (
        profile in {"goa", "transistor_level"}
        and config.get("electrical_features_enabled", True) is not False
        and isinstance(electrical_model, dict)
        and str(electrical_model.get("model", "")).lower() in {"tft_square_law_v1", "tft_charge_sheet_v2"}
    ):
        electrical_report = attach_v3_electrical_features(features, frame, config)

    features = features.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    forbidden = config.get("forbidden_metric_names", DEFAULT_FORBIDDEN_METRIC_NAMES)
    leaked = validate_no_leakage(features.columns, forbidden)
    report = build_feature_report(features, missing)
    report["profile"] = profile
    report["electrical_features_enabled"] = bool(
        profile in {"goa", "transistor_level"} and config.get("electrical_features_enabled", True) is not False
    )
    report.update(electrical_report)
    report["leakage_violations"] = leaked
    return features, report


def resolve_physics_feature_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(config or {})
    nested = source.get("physics_features", source)
    resolved = dict(nested) if isinstance(nested, Mapping) else {}
    for block in ("electrical_model", "parasitics", "pvt"):
        value = source.get(block)
        if isinstance(value, Mapping):
            resolved[block] = dict(value)
    return resolved


def infer_feature_columns(frame: pd.DataFrame, profile: str = "generic") -> list[str]:
    features, _ = extract_physics_features(frame, {"profile": profile})
    return list(features.columns)


def validate_no_leakage(feature_names: Iterable[str], forbidden_metric_names: Iterable[str]) -> list[str]:
    forbidden = {name.lower() for name in forbidden_metric_names}
    return [name for name in feature_names if name.lower() in forbidden]


def build_feature_report(feature_frame: pd.DataFrame, missing_inputs: Iterable[str]) -> dict[str, Any]:
    return {
        "feature_count": int(len(feature_frame.columns)),
        "feature_names": list(feature_frame.columns),
        "missing_inputs": sorted(set(missing_inputs)),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }
