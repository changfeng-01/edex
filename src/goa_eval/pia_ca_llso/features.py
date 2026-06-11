from __future__ import annotations

from typing import Iterable, Any

import numpy as np
import pandas as pd

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

    features = features.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    forbidden = config.get("forbidden_metric_names", DEFAULT_FORBIDDEN_METRIC_NAMES)
    leaked = validate_no_leakage(features.columns, forbidden)
    report = build_feature_report(features, missing)
    report["profile"] = profile
    report["leakage_violations"] = leaked
    return features, report


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
