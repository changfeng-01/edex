from __future__ import annotations

import json
import math
from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.electrical_model import V3_CANONICAL_FEATURES, V3_GEOMETRY_FEATURES


GOA_DEFAULT_WEIGHTS = {
    "cboot_cload_ratio": 2.0,
    "pullup_pulldown_ratio": 2.0,
    "ron_pullup_cload_proxy": 1.5,
    "ron_pulldown_cload_proxy": 1.5,
    "vgh_vth_margin": 1.5,
    "vgl_off_margin": 1.5,
    "clk_slew_proxy": 1.2,
}

GOA_V2_WEIGHTS = {
    "cboot_cload_ratio": 1.0,
    "pullup_pulldown_ratio": 1.0,
    "pullup_rc_delay_proxy_v2": 1.5,
    "pulldown_rc_delay_proxy_v2": 1.5,
    "bootstrap_coupling_factor": 1.2,
    "bootstrap_voltage_proxy": 1.2,
    "vgh_vth_margin": 1.5,
    "vgl_off_margin": 1.5,
    "clk_slew_proxy": 1.0,
}

GOA_V3_WEIGHTS = {
    "pullup_overdrive_v": 1.0,
    "pulldown_overdrive_v": 1.0,
    "pullup_effective_resistance_ohm": 1.0,
    "pulldown_effective_resistance_ohm": 1.0,
    "effective_load_capacitance_f": 0.8,
    "pullup_rc_delay_s": 1.5,
    "pulldown_rc_delay_s": 1.5,
    "critical_rc_delay_s": 1.5,
    "bootstrap_coupling_factor_v3": 1.2,
    "bootstrap_headroom_v": 1.2,
    "drive_balance_log_ratio": 1.0,
    "clock_slew_over_rc_ratio": 1.0,
}

GOA_V3_GEOMETRY_WEIGHTS = {
    "pullup_overdrive_supply_ratio": 1.0,
    "pulldown_overdrive_supply_ratio": 1.0,
    "pullup_rc_to_clock_slew_ratio": 1.5,
    "pulldown_rc_to_clock_slew_ratio": 1.5,
    "bootstrap_coupling_factor_v3": 1.2,
    "bootstrap_headroom_supply_ratio": 1.2,
    "drive_balance_log_ratio": 1.0,
}

CAPM_COUPLINGS = [
    {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
    {"left": "ron_pulldown_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
    {"left": "cboot_cload_ratio", "right": "vgh_vth_margin", "weight": 0.25, "enabled": True},
    {"left": "ron_pullup_cload_proxy", "right": "vgh_vth_margin", "weight": 0.15, "enabled": True},
    {"left": "ron_pulldown_cload_proxy", "right": "vgl_off_margin", "weight": 0.15, "enabled": True},
    {"left": "cboot_cload_ratio", "right": "holding_droop_proxy", "weight": 0.15, "enabled": True},
    {"left": "pullup_pulldown_ratio", "right": "clk_slew_proxy", "weight": 0.10, "enabled": True},
    {"left": "vgh_vth_margin", "right": "vgl_off_margin", "weight": 0.10, "enabled": True},
]

# V3 physical interactions are encoded once in the dimensionless state (RC to
# slew, normalized headroom, and drive balance), so no basis-dependent product
# terms are added to the metric tensor.
CAPM_V3_COUPLINGS: list[dict[str, Any]] = []

CAPM_DEFAULT_CONFIG = {
    "metric_version": "v2",
    "lambda_barrier": 1.0,
    "lambda_graph": 1.0,
    "lambda_missing": 1.0,
    "lambda_fallback": 0.25,
    "k_neighbors": 4,
    "normalization_enabled": True,
    "normalization_min_history_rows": 4,
    "normalization_floor_fraction": 0.05,
    "normalization_clip": 8.0,
    "coupling_enabled": True,
    "coupling_budget": 0.25,
    "barrier_enabled": True,
    "geodesic_enabled": True,
    "missing_penalty_enabled": True,
    "l1_aggregation": "softmin",
    "l1_top_k": 3,
    "softmin_temperature": 0.25,
    "l1_quality_weight": 0.25,
    "min_vgh_vth_margin": 0.2,
    "min_vgl_off_margin": 0.2,
    "min_cboot_cload_ratio": 0.35,
    "max_ron_pullup_cload_proxy": 2.0,
    "max_ron_pulldown_cload_proxy": 2.0,
    "min_pullup_pulldown_ratio": 0.5,
    "max_pullup_pulldown_ratio": 2.0,
    "max_clk_slew_proxy": 2.0,
    "min_device_overdrive_v": 0.0,
    "max_critical_rc_delay_s": 1.0,
    "min_bootstrap_coupling_factor_v3": 0.0,
    "min_bootstrap_headroom_v": 0.0,
    "max_abs_drive_balance_log_ratio": 10.0,
    "max_clock_slew_over_rc_ratio": 1.0e12,
    "pvt_worst_case_weight": 0.5,
    "pvt_cvar_quantile": 0.9,
    "pvt_cvar_weight": 0.5,
    "pvt_uncertainty_z": 1.0,
    "pvt_max_violation_probability": 0.0,
    "metric_covariance_shrinkage": 0.25,
    "metric_covariance_ridge": 1.0e-6,
    "historical_calibration_min_p90_count": 5,
    "couplings": [dict(c) for c in CAPM_COUPLINGS],
    "penalty_config": {},
}

FORBIDDEN_DISTANCE_COLUMNS = {
    "candidate_id",
    "sample_id",
    "source",
    "status",
    "level_label",
    "label_reason",
    "overall_score",
    "total_score",
    "hard_constraint_passed",
    "hard_pass",
    "sim_success",
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
    "physics_feature_status_json",
    "capm_electrical_status_json",
    "capm_pvt_features_json",
    "capm_pvt_status",
    "capm_pvt_diagnostics_json",
}


@dataclass(frozen=True)
class CapmDistanceContext:
    metric_version: str
    feature_keys: tuple[str, ...]
    centers: dict[str, float]
    scales: dict[str, float]
    weights: dict[str, float]
    config: dict[str, Any]
    distance_scale: float = 0.0
    calibration_status: str = "not_applicable"
    calibration_count: int = 0
    pvt_scenarios: tuple[str, ...] = ()
    precision_matrix: tuple[tuple[float, ...], ...] = ()
    covariance_shrinkage: float = 0.0
    metric_basis: str = "diagonal_weighted_euclidean"

    def normalization_payload(self) -> dict[str, Any]:
        return {
            "metric_version": self.metric_version,
            "feature_keys": list(self.feature_keys),
            "centers": self.centers,
            "scales": self.scales,
            "weights": self.weights,
            "normalization_enabled": bool(self.config.get("normalization_enabled", True)),
            "distance_scale": self.distance_scale,
            "calibration_status": self.calibration_status,
            "calibration_count": self.calibration_count,
            "pvt_scenarios": list(self.pvt_scenarios),
            "metric_basis": self.metric_basis,
            "covariance_shrinkage": self.covariance_shrinkage,
            "precision_matrix": [list(row) for row in self.precision_matrix],
        }

    def calibration_payload(self) -> dict[str, Any]:
        return {
            "metric_version": self.metric_version,
            "method": (
                "history_crossfit_rational_p90"
                if self.metric_version == "v4"
                else "history_leave_one_out_p90"
            ),
            "distance_scale": self.distance_scale,
            "calibration_status": self.calibration_status,
            "reference_count": self.calibration_count,
            "candidate_pool_fitted": False,
        }

def compute_physics_distance(phi_a: Mapping[str, Any], phi_b: Mapping[str, Any], weights: Mapping[str, float] | None = None) -> float:
    keys = sorted(set(phi_a.keys()) & set(phi_b.keys()))
    if not keys:
        return float("inf")
    total = 0.0
    for key in keys:
        weight = float((weights or {}).get(key, 1.0))
        total += weight * (float(phi_a.get(key, 0.0)) - float(phi_b.get(key, 0.0))) ** 2
    return float(np.sqrt(total))


def constraint_barrier_score(phi: Mapping[str, Any] | pd.Series, config: Mapping[str, Any] | None = None) -> float:
    """Soft pre-simulation risk score for CAPM distance.

    The score is a proxy-level warning only. It does not classify a candidate
    as physically failed and does not replace re-simulation.
    """

    cfg = _capm_config(config)
    if cfg.get("barrier_enabled", True) is False:
        return 0.0
    if str(cfg.get("metric_version", "v2")).lower() in {"v3", "v4"}:
        return _v3_constraint_barrier_score(phi, cfg)
    penalty_config = cfg.get("penalty_config", {})
    total = 0.0
    total += _apply_penalty(_numeric(phi.get("vgh_vth_margin")), float(cfg["min_vgh_vth_margin"]), "low", penalty_config, "vgh_vth_margin")
    total += _apply_penalty(_numeric(phi.get("vgl_off_margin")), float(cfg["min_vgl_off_margin"]), "low", penalty_config, "vgl_off_margin")
    total += _apply_penalty(_numeric(phi.get("cboot_cload_ratio")), float(cfg["min_cboot_cload_ratio"]), "low", penalty_config, "cboot_cload_ratio")
    total += _apply_penalty(_numeric(phi.get("ron_pullup_cload_proxy")), float(cfg["max_ron_pullup_cload_proxy"]), "high", penalty_config, "ron_pullup_cload_proxy")
    total += _apply_penalty(_numeric(phi.get("ron_pulldown_cload_proxy")), float(cfg["max_ron_pulldown_cload_proxy"]), "high", penalty_config, "ron_pulldown_cload_proxy")
    total += _apply_penalty(_numeric(phi.get("clk_slew_proxy")), float(cfg["max_clk_slew_proxy"]), "high", penalty_config, "clk_slew_proxy")
    ratio = _numeric(phi.get("pullup_pulldown_ratio"))
    if ratio is not None:
        total += _apply_penalty(ratio, float(cfg["min_pullup_pulldown_ratio"]), "low", penalty_config, "pullup_pulldown_ratio")
        total += _apply_penalty(ratio, float(cfg["max_pullup_pulldown_ratio"]), "high", penalty_config, "pullup_pulldown_ratio")
    return float(total)


def _v3_constraint_barrier_score(phi: Mapping[str, Any] | pd.Series, cfg: Mapping[str, Any]) -> float:
    penalty_config = cfg.get("penalty_config", {})
    total = 0.0
    for feature in ("pullup_overdrive_v", "pulldown_overdrive_v"):
        total += _apply_penalty(
            _numeric(phi.get(feature)),
            float(cfg["min_device_overdrive_v"]),
            "low",
            penalty_config,
            feature,
        )
    total += _apply_penalty(
        _numeric(phi.get("critical_rc_delay_s")),
        float(cfg["max_critical_rc_delay_s"]),
        "high",
        penalty_config,
        "critical_rc_delay_s",
    )
    total += _apply_penalty(
        _numeric(phi.get("bootstrap_coupling_factor_v3")),
        float(cfg["min_bootstrap_coupling_factor_v3"]),
        "low",
        penalty_config,
        "bootstrap_coupling_factor_v3",
    )
    total += _apply_penalty(
        _numeric(phi.get("bootstrap_headroom_v")),
        float(cfg["min_bootstrap_headroom_v"]),
        "low",
        penalty_config,
        "bootstrap_headroom_v",
    )
    balance = _numeric(phi.get("drive_balance_log_ratio"))
    total += _apply_penalty(
        abs(balance) if balance is not None else None,
        float(cfg["max_abs_drive_balance_log_ratio"]),
        "high",
        penalty_config,
        "drive_balance_log_ratio",
    )
    total += _apply_penalty(
        _numeric(phi.get("clock_slew_over_rc_ratio")),
        float(cfg["max_clock_slew_over_rc_ratio"]),
        "high",
        penalty_config,
        "clock_slew_over_rc_ratio",
    )
    for feature in ("pullup_region_code", "pulldown_region_code"):
        region = _numeric(phi.get(feature))
        if region is not None and region == 0.0:
            total += 1.0
    return float(total)


def classify_v4_constraint_risks(
    phi: Mapping[str, Any] | pd.Series,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep confirmed constraints, validated risks, and heuristics distinct."""

    cfg = _capm_config(config)
    classes = cfg.get("constraint_classes", {})
    classes = classes if isinstance(classes, Mapping) else {}
    scores: dict[str, float] = {}
    violations: dict[str, list[str]] = {}
    for category in ("hard", "validated_risk", "heuristic_warning"):
        total = 0.0
        names: list[str] = []
        entries = classes.get(category, [])
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, Mapping):
                continue
            feature = str(entry.get("feature", ""))
            value = _numeric(phi.get(feature))
            threshold = _numeric(entry.get("threshold"))
            if value is None or threshold is None:
                continue
            direction = str(entry.get("direction", "high"))
            measured = abs(value) if direction == "abs_high" else value
            mode = "high" if direction in {"high", "abs_high"} else "low"
            penalty = _apply_penalty(measured, threshold, mode, cfg.get("penalty_config", {}), feature)
            total += penalty
            if penalty > 0.0:
                names.append(feature)
        scores[category] = float(total)
        violations[category] = names
    return {
        "hard_constraint_passed": scores["hard"] <= 0.0,
        "hard_violation_score": scores["hard"],
        "validated_risk_score": scores["validated_risk"],
        "heuristic_warning_score": scores["heuristic_warning"],
        "violations": violations,
    }


def build_capm_distance_context(
    history_phi: pd.DataFrame,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
) -> CapmDistanceContext:
    cfg = _capm_config(config)
    version = str(cfg.get("metric_version", "v2")).lower()
    explicit_weights = dict(weights or {})
    if version in {"v3", "v4"}:
        filtered_geometry = {
            key: value
            for key, value in explicit_weights.items()
            if key in V3_GEOMETRY_FEATURES
        }
        filtered_canonical = {
            key: value
            for key, value in explicit_weights.items()
            if key in V3_CANONICAL_FEATURES
        }
        if filtered_geometry:
            preferred_weights = filtered_geometry
        elif filtered_canonical:
            preferred_weights = filtered_canonical
        elif all(key in history_phi.columns for key in V3_GEOMETRY_FEATURES):
            preferred_weights = dict(GOA_V3_GEOMETRY_WEIGHTS)
        else:
            preferred_weights = dict(GOA_V3_WEIGHTS)
    elif explicit_weights:
        preferred_weights = explicit_weights
    elif version == "legacy":
        preferred_weights = dict(GOA_DEFAULT_WEIGHTS)
    else:
        preferred_weights = dict(GOA_V2_WEIGHTS)
        if not any(column in history_phi.columns for column in {"pullup_rc_delay_proxy_v2", "pulldown_rc_delay_proxy_v2"}):
            preferred_weights.update(
                {
                    "ron_pullup_cload_proxy": GOA_DEFAULT_WEIGHTS["ron_pullup_cload_proxy"],
                    "ron_pulldown_cload_proxy": GOA_DEFAULT_WEIGHTS["ron_pulldown_cload_proxy"],
                }
            )
    feature_keys = [
        key
        for key in preferred_weights
        if key in history_phi.columns and key not in FORBIDDEN_DISTANCE_COLUMNS
    ]
    if not feature_keys and version != "v3":
        feature_keys = [
            key
            for key in history_phi.columns
            if key not in FORBIDDEN_DISTANCE_COLUMNS and pd.api.types.is_numeric_dtype(history_phi[key])
        ]
    active_weights = {key: max(float(preferred_weights.get(key, 1.0)), 0.0) for key in feature_keys}
    weight_total = sum(active_weights.values()) or 1.0
    normalized_weights = {key: value / weight_total for key, value in active_weights.items()}
    centers, scales = _fit_feature_normalization(history_phi, tuple(feature_keys), cfg, version)
    pvt_scenarios = tuple(
        sorted(
            {
                scenario
                for record in history_phi.to_dict("records")
                for scenario in _pvt_feature_map(record)
            }
        )
    )
    precision_matrix, covariance_shrinkage, metric_basis = _fit_metric_tensor(
        history_phi,
        tuple(feature_keys),
        centers,
        scales,
        normalized_weights,
        cfg,
        version,
    )
    context = CapmDistanceContext(
        metric_version=version,
        feature_keys=tuple(feature_keys),
        centers=centers,
        scales=scales,
        weights=normalized_weights,
        config=cfg,
        pvt_scenarios=pvt_scenarios,
        precision_matrix=precision_matrix,
        covariance_shrinkage=covariance_shrinkage,
        metric_basis=metric_basis,
    )
    if version not in {"v3", "v4"}:
        return context
    if version == "v4":
        distance_scale, calibration_status, calibration_count = _fit_history_distance_scale_v4(
            history_phi, weights, cfg, context
        )
    else:
        distance_scale, calibration_status, calibration_count = _fit_history_distance_scale(
            history_phi, weights, cfg, context
        )
    return CapmDistanceContext(
        metric_version=context.metric_version,
        feature_keys=context.feature_keys,
        centers=context.centers,
        scales=context.scales,
        weights=context.weights,
        config=context.config,
        distance_scale=distance_scale,
        calibration_status=calibration_status,
        calibration_count=calibration_count,
        pvt_scenarios=context.pvt_scenarios,
        precision_matrix=context.precision_matrix,
        covariance_shrinkage=context.covariance_shrinkage,
        metric_basis=context.metric_basis,
    )


def _fit_metric_tensor(
    history: pd.DataFrame,
    feature_keys: tuple[str, ...],
    centers: Mapping[str, float],
    scales: Mapping[str, float],
    weights: Mapping[str, float],
    cfg: Mapping[str, Any],
    version: str,
) -> tuple[tuple[tuple[float, ...], ...], float, str]:
    size = len(feature_keys)
    if version not in {"v3", "v4"} or size == 0 or cfg.get("normalization_enabled", True) is False:
        return (), 0.0, "diagonal_weighted_euclidean"
    rows: list[list[float]] = []
    clip = max(float(cfg.get("normalization_clip", 8.0)), 0.0)
    for record in history.to_dict("records"):
        values: list[float] = []
        for key in feature_keys:
            value = _numeric(record.get(key))
            if value is None:
                transformed = 0.0
            else:
                if version == "v4":
                    transformed = (_base_v4_transform(value, key) - centers[key]) / max(scales[key], 1e-12)
                else:
                    transformed = float(np.arcsinh((value - centers[key]) / max(scales[key], 1e-12)))
                if clip > 0.0:
                    transformed = float(np.clip(transformed, -clip, clip))
            values.append(transformed if version == "v4" else math.sqrt(max(float(weights.get(key, 0.0)), 0.0)) * transformed)
        rows.append(values)
    if len(rows) < 2:
        return (), 0.0, "diagonal_weighted_euclidean"
    matrix = np.asarray(rows, dtype=float)
    covariance = np.atleast_2d(np.cov(matrix, rowvar=False, ddof=1))
    if covariance.shape != (size, size) or not np.isfinite(covariance).all():
        return (), 0.0, "diagonal_weighted_euclidean"
    shrinkage = float(np.clip(float(cfg.get("metric_covariance_shrinkage", 0.25)), 0.0, 1.0))
    diagonal = np.diag(np.maximum(np.diag(covariance), 1.0e-12))
    shrunk = (1.0 - shrinkage) * covariance + shrinkage * diagonal
    ridge = max(float(cfg.get("metric_covariance_ridge", 1.0e-6)), 0.0)
    shrunk += ridge * np.eye(size)
    precision = np.linalg.pinv(shrunk, hermitian=True)
    mean_diagonal = float(np.mean(np.diag(precision)))
    if mean_diagonal > 0.0:
        precision /= mean_diagonal
    return (
        tuple(tuple(float(value) for value in row) for row in precision),
        shrinkage,
        (
            "feature_typed_weighted_shrinkage_mahalanobis"
            if version == "v4"
            else "dimensionless_shrinkage_mahalanobis"
            if feature_keys == V3_GEOMETRY_FEATURES
            else "shrinkage_mahalanobis"
        ),
    )


def _fit_feature_normalization(
    history: pd.DataFrame,
    feature_keys: tuple[str, ...],
    cfg: Mapping[str, Any],
    version: str,
) -> tuple[dict[str, float], dict[str, float]]:
    centers: dict[str, float] = {}
    scales: dict[str, float] = {}
    epsilon = 1e-12
    floor_fraction = max(float(cfg.get("normalization_floor_fraction", 0.05)), 0.0)
    min_rows = max(int(cfg.get("normalization_min_history_rows", 4)), 1)
    configured_scales = cfg.get("normalization_fallback_scales", {})
    for key in feature_keys:
        raw = pd.to_numeric(history[key], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        values = raw.map(lambda value: _base_v4_transform(float(value), key)) if version == "v4" else raw
        median = float(values.median()) if not values.empty else 0.0
        center = median if len(values) >= min_rows else 0.0
        mad = float((values - median).abs().median()) if not values.empty else 0.0
        robust_scale = 1.4826 * mad if len(values) >= min_rows else 0.0
        if version == "v4":
            # V4 centers positive features in log space.  A floor derived from
            # ``abs(median)`` would therefore depend on the arbitrary unit
            # origin (seconds versus nanoseconds).  Keep both defaults in the
            # transformed, dimensionless coordinate system instead.
            floor = floor_fraction
            fallback = float(configured_scales.get(key, 1.0))
        else:
            floor = floor_fraction * abs(median)
            fallback = float(configured_scales.get(key, abs(median) if abs(median) > epsilon else 1.0))
        scale = max(robust_scale, floor, epsilon)
        if robust_scale <= epsilon and floor <= epsilon:
            scale = max(abs(fallback), epsilon)
        centers[key] = center
        scales[key] = scale
    return centers, scales


def _fit_history_distance_scale(
    history_phi: pd.DataFrame,
    weights: Mapping[str, float] | None,
    cfg: Mapping[str, Any],
    context: CapmDistanceContext,
) -> tuple[float, str, int]:
    records = history_phi.to_dict("records")
    l1_indices = [index for index, row in enumerate(records) if str(row.get("level_label", "")) == "L1"]
    references: list[float] = []
    for index, row in enumerate(records):
        targets = [target for target in l1_indices if target != index]
        if not targets:
            continue
        distances = [
            compute_capm_distance(row, records[target], weights, cfg, context).get("distance")
            for target in targets
        ]
        finite = [float(value) for value in distances if value is not None and np.isfinite(float(value))]
        if finite:
            references.append(min(finite))
    positive = [value for value in references if value > 1e-12]
    count = len(positive)
    if count == 0:
        return 0.0, "degenerate_history", 0
    min_p90_count = max(int(cfg.get("historical_calibration_min_p90_count", 5)), 1)
    if count >= min_p90_count:
        return float(np.quantile(np.asarray(positive, dtype=float), 0.9)), "history_p90", count
    return float(max(positive)), "history_max_small_sample", count


def _fit_history_distance_scale_v4(
    history_phi: pd.DataFrame,
    weights: Mapping[str, float] | None,
    cfg: Mapping[str, Any],
    context: CapmDistanceContext,
) -> tuple[float, str, int]:
    """Cross-fit all history-dependent metric state before measuring a row."""

    records = history_phi.to_dict("records")
    l1_indices = [index for index, row in enumerate(records) if str(row.get("level_label", "")) == "L1"]
    references: list[float] = []
    for held_out, row in enumerate(records):
        targets = [index for index in l1_indices if index != held_out]
        if not targets:
            continue
        train = history_phi.drop(history_phi.index[held_out]).reset_index(drop=True)
        centers, scales = _fit_feature_normalization(train, context.feature_keys, cfg, "v4")
        precision, shrinkage, basis = _fit_metric_tensor(
            train,
            context.feature_keys,
            centers,
            scales,
            context.weights,
            cfg,
            "v4",
        )
        fold_context = CapmDistanceContext(
            metric_version="v4",
            feature_keys=context.feature_keys,
            centers=centers,
            scales=scales,
            weights=context.weights,
            config=context.config,
            pvt_scenarios=context.pvt_scenarios,
            precision_matrix=precision,
            covariance_shrinkage=shrinkage,
            metric_basis=basis,
        )
        distances = [
            compute_capm_distance(row, records[target], weights, cfg, fold_context).get("distance")
            for target in targets
        ]
        finite = [float(value) for value in distances if value is not None and np.isfinite(float(value))]
        if finite:
            references.append(min(finite))
    positive = [value for value in references if value > 1.0e-12]
    count = len(positive)
    if count == 0:
        return 0.0, "crossfit_degenerate_history", 0
    min_p90_count = max(int(cfg.get("historical_calibration_min_p90_count", 5)), 1)
    if count >= min_p90_count:
        return float(np.quantile(np.asarray(positive, dtype=float), 0.9)), "crossfit_history_p90", count
    return float(max(positive)), "crossfit_history_max_small_sample", count


def _pvt_feature_map(row: Mapping[str, Any] | pd.Series) -> dict[str, dict[str, Any]]:
    raw = row.get("capm_pvt_features_json")
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {
        str(key): dict(value)
        for key, value in payload.items()
        if isinstance(value, Mapping)
    }


def calibrate_v3_distance(value: float, context: CapmDistanceContext) -> float:
    if not np.isfinite(value):
        return 1.0
    if context.distance_scale > 1e-12:
        return float(np.clip(value / context.distance_scale, 0.0, 1.0))
    return 0.0 if value <= 1e-12 else 1.0


def calibrate_v4_distance(value: float, context: CapmDistanceContext) -> float:
    """Map distance smoothly to [0, 1) using history-only cross-fit scale."""

    if not np.isfinite(value):
        return 1.0
    if context.distance_scale > 1.0e-12:
        nonnegative = max(float(value), 0.0)
        return nonnegative / (nonnegative + context.distance_scale)
    return 0.0 if value <= 1.0e-12 else 1.0


def compute_capm_distance(
    phi_a: Mapping[str, Any] | pd.Series,
    phi_b: Mapping[str, Any] | pd.Series,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
    context: CapmDistanceContext | None = None,
) -> dict[str, Any]:
    """Compute constraint-aware physics-manifold distance between two points."""

    cfg = _capm_config(config)
    version = str(cfg.get("metric_version", "v2")).lower()
    if version == "legacy":
        return _compute_capm_distance_legacy(phi_a, phi_b, weights, cfg)
    if context is None:
        context = build_capm_distance_context(pd.DataFrame([dict(phi_a), dict(phi_b)]), weights, cfg)
    if version in {"v3", "v4"}:
        scenario_a = _pvt_feature_map(phi_a)
        scenario_b = _pvt_feature_map(phi_b)
        common_scenarios = sorted(set(scenario_a) & set(scenario_b))
        if common_scenarios:
            scenario_results = []
            for key in common_scenarios:
                scenario_result = _compute_context_distance(scenario_a[key], scenario_b[key], cfg, context)
                metadata_a = _pvt_scenario_metadata(phi_a, key)
                metadata_b = _pvt_scenario_metadata(phi_b, key)
                scenario_result["scenario_key"] = key
                scenario_result["scenario_weight"] = max(
                    float(metadata_a.get("weight", 1.0)),
                    float(metadata_b.get("weight", 1.0)),
                    0.0,
                )
                scenario_result["distance_uncertainty"] = max(
                    float(metadata_a.get("distance_uncertainty", 0.0)),
                    float(metadata_b.get("distance_uncertainty", 0.0)),
                    0.0,
                )
                scenario_result["scenario_kind"] = str(
                    metadata_a.get("kind", metadata_b.get("kind", "deterministic_corner"))
                )
                probability_a = _numeric(metadata_a.get("probability"))
                probability_b = _numeric(metadata_b.get("probability"))
                scenario_result["scenario_probability"] = (
                    max(value for value in (probability_a, probability_b) if value is not None)
                    if probability_a is not None or probability_b is not None
                    else None
                )
                scenario_results.append(scenario_result)
            expected_scenarios = (
                sorted(set(context.pvt_scenarios) | set(scenario_a) | set(scenario_b))
                if version == "v4"
                else common_scenarios
            )
            result = _aggregate_pvt_results(scenario_results, cfg, len(common_scenarios))
            if version == "v4":
                missing_scenarios = len(expected_scenarios) - len(common_scenarios)
                result["pvt_expected_scenario_count"] = len(expected_scenarios)
                result["pvt_missing_scenario_count"] = missing_scenarios
                if missing_scenarios > 0:
                    coverage_penalty = missing_scenarios / max(len(expected_scenarios), 1)
                    result["missing_penalty"] = float(result.get("missing_penalty", 0.0)) + coverage_penalty
                    result["point_risk_cost"] = float(result.get("point_risk_cost", 0.0)) + float(
                        cfg.get("lambda_missing", 1.0)
                    ) * coverage_penalty
                    result["decision_cost"] = float(result["distance"]) + float(result["point_risk_cost"])
                    result["pvt_status"] = "incomplete_scenario_coverage"
            return _apply_pvt_coverage_penalties(result, phi_a, phi_b, cfg)
    result = _compute_context_distance(phi_a, phi_b, cfg, context)
    if version in {"v3", "v4"}:
        result["pvt_status"] = "nominal_only"
        result = _apply_pvt_coverage_penalties(result, phi_a, phi_b, cfg)
    return result


def _compute_context_distance(
    phi_a: Mapping[str, Any] | pd.Series,
    phi_b: Mapping[str, Any] | pd.Series,
    cfg: Mapping[str, Any],
    context: CapmDistanceContext,
) -> dict[str, Any]:
    feature_keys = list(context.feature_keys)
    if not feature_keys:
        return _unavailable_capm_result(context.metric_version)

    transformed_a: dict[str, float] = {}
    transformed_b: dict[str, float] = {}
    missing_weight = 0.0
    missing_count = 0
    fallback_weight = 0.0
    for key in feature_keys:
        weight = float(context.weights.get(key, 0.0))
        left = _numeric(phi_a.get(key))
        right = _numeric(phi_b.get(key))
        if left is None or right is None:
            missing_weight += weight
            missing_count += 1
            continue
        transformed_a[key] = _transform_feature(left, key, context)
        transformed_b[key] = _transform_feature(right, key, context)
        if "proxy_fallback" in {_feature_status(phi_a, key), _feature_status(phi_b, key)}:
            fallback_weight += weight

    common_keys = [key for key in feature_keys if key in transformed_a and key in transformed_b]
    differences = np.asarray(
        [
            math.sqrt(max(float(context.weights.get(key, 0.0)), 0.0))
            * (transformed_a[key] - transformed_b[key])
            for key in common_keys
        ],
        dtype=float,
    )
    if context.precision_matrix and common_keys:
        indices = [feature_keys.index(key) for key in common_keys]
        precision = np.asarray(context.precision_matrix, dtype=float)[np.ix_(indices, indices)]
        tensor_total = float(differences @ precision @ differences)
    else:
        tensor_total = float(differences @ differences)
    couplings = _resolve_couplings(cfg) if cfg.get("coupling_enabled", True) is not False else []
    tensor_total += _normalized_coupling_distance(transformed_a, transformed_b, couplings, cfg)
    similarity_distance = float(np.sqrt(max(tensor_total, 0.0)))
    barrier_a = constraint_barrier_score(phi_a, cfg)
    barrier_b = constraint_barrier_score(phi_b, cfg)
    barrier_cost = max(barrier_a, barrier_b)
    missing_penalty = missing_weight if cfg.get("missing_penalty_enabled", True) is not False else 0.0
    proxy_fallback_penalty = fallback_weight if cfg.get("missing_penalty_enabled", True) is not False else 0.0
    point_risk_cost = (
        + float(cfg["lambda_barrier"]) * barrier_cost
        + float(cfg["lambda_missing"]) * missing_penalty
        + float(cfg.get("lambda_fallback", 0.25)) * proxy_fallback_penalty
    )
    reported_distance = similarity_distance if context.metric_version in {"v3", "v4"} else similarity_distance + point_risk_cost
    return {
        "status": "ok",
        "distance": float(reported_distance),
        "geometric_distance": similarity_distance,
        "decision_cost": float(similarity_distance + point_risk_cost),
        "point_risk_cost": float(point_risk_cost),
        "tensor_distance": similarity_distance,
        "similarity_distance": similarity_distance,
        "barrier_cost": float(barrier_cost),
        "path_risk_cost": float(barrier_cost),
        "missing_penalty": float(missing_penalty),
        "proxy_fallback_penalty": float(proxy_fallback_penalty),
        "feature_count": int(len(feature_keys)),
        "missing_feature_count": int(missing_count),
        "metric_version": context.metric_version,
    }


def _aggregate_pvt_results(
    results: Sequence[Mapping[str, Any]],
    cfg: Mapping[str, Any],
    scenario_count: int,
) -> dict[str, Any]:
    usable = [result for result in results if result.get("distance") is not None]
    if not usable:
        result = _unavailable_capm_result("v3")
        result["pvt_status"] = "unavailable"
        return result
    if str(cfg.get("metric_version", "v3")).lower() == "v4":
        return _aggregate_v4_pvt_results(usable, cfg, scenario_count)
    raw_weights = np.asarray([max(float(result.get("scenario_weight", 1.0)), 0.0) for result in usable], dtype=float)
    weights = raw_weights / raw_weights.sum() if raw_weights.sum() > 0.0 else np.full(len(usable), 1.0 / len(usable))
    distances = np.asarray([float(result.get("distance", 0.0)) for result in usable], dtype=float)
    uncertainties = np.asarray([max(float(result.get("distance_uncertainty", 0.0)), 0.0) for result in usable])
    upper_distances = distances + max(float(cfg.get("pvt_uncertainty_z", 1.0)), 0.0) * uncertainties
    weighted_mean_distance = float(np.dot(weights, distances))
    cvar_distance = _weighted_cvar(
        upper_distances,
        weights,
        float(cfg.get("pvt_cvar_quantile", 0.9)),
    )
    cvar_weight = float(np.clip(float(cfg.get("pvt_cvar_weight", cfg.get("pvt_worst_case_weight", 0.5))), 0.0, 1.0))
    geometric_distance = (1.0 - cvar_weight) * weighted_mean_distance + cvar_weight * cvar_distance
    violation_probability = float(
        sum(weight for weight, result in zip(weights, usable) if float(result.get("barrier_cost", 0.0)) > 0.0)
    )
    allowed_probability = float(np.clip(float(cfg.get("pvt_max_violation_probability", 0.0)), 0.0, 1.0))
    chance_excess = max(violation_probability - allowed_probability, 0.0)
    barrier_cost = max(float(result.get("barrier_cost", 0.0)) for result in usable)
    missing_penalty = max(float(result.get("missing_penalty", 0.0)) for result in usable)
    fallback_penalty = float(np.dot(weights, [float(result.get("proxy_fallback_penalty", 0.0)) for result in usable]))
    point_risk = (
        float(cfg.get("lambda_barrier", 1.0)) * barrier_cost
        + float(cfg.get("lambda_missing", 1.0)) * missing_penalty
        + float(cfg.get("lambda_fallback", 0.25)) * fallback_penalty
        + chance_excess
    )

    return {
        "status": "ok",
        "distance": float(geometric_distance),
        "geometric_distance": float(geometric_distance),
        "decision_cost": float(geometric_distance + point_risk),
        "point_risk_cost": float(point_risk),
        "tensor_distance": float(geometric_distance),
        "similarity_distance": float(geometric_distance),
        "barrier_cost": barrier_cost,
        "path_risk_cost": max(float(result.get("path_risk_cost", 0.0)) for result in usable),
        "missing_penalty": missing_penalty,
        "proxy_fallback_penalty": fallback_penalty,
        "feature_count": max(int(result.get("feature_count", 0)) for result in usable),
        "missing_feature_count": max(int(result.get("missing_feature_count", 0)) for result in usable),
        "metric_version": str(usable[0].get("metric_version", cfg.get("metric_version", "v3"))),
        "pvt_status": f"scenario_aggregated:{scenario_count}",
        "pvt_weighted_mean_distance": weighted_mean_distance,
        "pvt_cvar_distance": float(cvar_distance),
        "pvt_violation_probability": violation_probability,
        "chance_constraint_excess": float(chance_excess),
    }


def _aggregate_v4_pvt_results(
    usable: Sequence[Mapping[str, Any]],
    cfg: Mapping[str, Any],
    scenario_count: int,
) -> dict[str, Any]:
    deterministic = [result for result in usable if result.get("scenario_kind") != "statistical_sample"]
    statistical = [result for result in usable if result.get("scenario_kind") == "statistical_sample"]
    base = deterministic or list(usable)
    deterministic_distances = np.asarray([float(result["distance"]) for result in base], dtype=float)
    deterministic_mean = float(np.mean(deterministic_distances))
    deterministic_worst = float(np.max(deterministic_distances))
    worst_weight = float(np.clip(float(cfg.get("pvt_worst_case_weight", 0.5)), 0.0, 1.0))
    deterministic_distance = (1.0 - worst_weight) * deterministic_mean + worst_weight * deterministic_worst

    statistical_mean: float | None = None
    violation_probability: float | None = None
    chance_excess = 0.0
    if statistical:
        raw_probability = np.asarray(
            [max(float(result.get("scenario_probability") or 0.0), 0.0) for result in statistical], dtype=float
        )
        probability = raw_probability / raw_probability.sum() if raw_probability.sum() > 0.0 else np.full(
            len(statistical), 1.0 / len(statistical)
        )
        statistical_mean = float(np.dot(probability, [float(result["distance"]) for result in statistical]))
        violation_probability = float(
            sum(weight for weight, result in zip(probability, statistical) if float(result.get("barrier_cost", 0.0)) > 0.0)
        )
        allowed = float(np.clip(float(cfg.get("pvt_max_violation_probability", 0.0)), 0.0, 1.0))
        chance_excess = max(violation_probability - allowed, 0.0)
    statistical_weight = float(np.clip(float(cfg.get("pvt_statistical_weight", 0.0)), 0.0, 1.0))
    geometric_distance = (
        (1.0 - statistical_weight) * deterministic_distance + statistical_weight * statistical_mean
        if statistical_mean is not None
        else deterministic_distance
    )
    barrier_cost = max(float(result.get("barrier_cost", 0.0)) for result in usable)
    missing_penalty = max(float(result.get("missing_penalty", 0.0)) for result in usable)
    fallback_penalty = float(np.mean([float(result.get("proxy_fallback_penalty", 0.0)) for result in usable]))
    point_risk = (
        float(cfg.get("lambda_barrier", 1.0)) * barrier_cost
        + float(cfg.get("lambda_missing", 1.0)) * missing_penalty
        + float(cfg.get("lambda_fallback", 0.25)) * fallback_penalty
        + chance_excess
    )
    return {
        "status": "ok",
        "distance": float(geometric_distance),
        "geometric_distance": float(geometric_distance),
        "decision_cost": float(geometric_distance + point_risk),
        "point_risk_cost": float(point_risk),
        "tensor_distance": float(geometric_distance),
        "similarity_distance": float(geometric_distance),
        "barrier_cost": barrier_cost,
        "path_risk_cost": max(float(result.get("path_risk_cost", 0.0)) for result in usable),
        "missing_penalty": missing_penalty,
        "proxy_fallback_penalty": fallback_penalty,
        "feature_count": max(int(result.get("feature_count", 0)) for result in usable),
        "missing_feature_count": max(int(result.get("missing_feature_count", 0)) for result in usable),
        "metric_version": "v4",
        "pvt_status": f"scenario_aggregated:{scenario_count}",
        "pvt_deterministic_mean_distance": deterministic_mean,
        "pvt_deterministic_worst_distance": deterministic_worst,
        "pvt_statistical_mean_distance": statistical_mean,
        "pvt_violation_probability": violation_probability,
        "chance_constraint_excess": float(chance_excess),
    }


def _weighted_cvar(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    if values.size == 0:
        return float("inf")
    tail_mass = max(1.0 - float(np.clip(quantile, 0.0, 1.0)), 1.0e-12)
    order = np.argsort(values)[::-1]
    remaining = tail_mass
    total = 0.0
    used = 0.0
    for index in order:
        take = min(float(weights[index]), remaining)
        if take > 0.0:
            total += take * float(values[index])
            used += take
            remaining -= take
        if remaining <= 1.0e-12:
            break
    return float(total / used) if used > 0.0 else float(np.max(values))


def _apply_pvt_coverage_penalties(
    result: dict[str, Any],
    phi_a: Mapping[str, Any] | pd.Series,
    phi_b: Mapping[str, Any] | pd.Series,
    cfg: Mapping[str, Any],
) -> dict[str, Any]:
    missing_a, fallback_a = _pvt_coverage_penalty(phi_a)
    missing_b, fallback_b = _pvt_coverage_penalty(phi_b)
    missing = max(missing_a, missing_b)
    fallback = max(fallback_a, fallback_b)
    result["missing_penalty"] = float(result.get("missing_penalty", 0.0)) + missing
    result["proxy_fallback_penalty"] = float(result.get("proxy_fallback_penalty", 0.0)) + fallback
    added_risk = float(cfg.get("lambda_missing", 1.0)) * missing + float(cfg.get("lambda_fallback", 0.25)) * fallback
    result["point_risk_cost"] = float(result.get("point_risk_cost", 0.0)) + added_risk
    if result.get("distance") is not None:
        result["decision_cost"] = float(result["distance"]) + float(result["point_risk_cost"])
    return result


def _pvt_scenario_metadata(row: Mapping[str, Any] | pd.Series, key: str) -> dict[str, Any]:
    raw = row.get("capm_pvt_diagnostics_json")
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    scenarios = payload.get("scenarios", {}) if isinstance(payload, Mapping) else {}
    value = scenarios.get(key, {}) if isinstance(scenarios, Mapping) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _pvt_coverage_penalty(row: Mapping[str, Any] | pd.Series) -> tuple[float, float]:
    raw = row.get("capm_pvt_diagnostics_json")
    if not isinstance(raw, str) or not raw:
        return 0.0, 0.0
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0, 0.0
    scenarios = payload.get("scenarios", {}) if isinstance(payload, Mapping) else {}
    if not isinstance(scenarios, Mapping) or not scenarios:
        return 0.0, 0.0
    statuses = [
        str(value.get("status", "missing")) if isinstance(value, Mapping) else "missing"
        for value in scenarios.values()
    ]
    count = len(statuses)
    missing = sum(status == "missing" for status in statuses) / count
    projected = sum(status == "proxy_projected" for status in statuses)
    mixed = sum(status == "mixed_observed_projected" for status in statuses)
    fallback = 0.25 * (projected + 0.5 * mixed) / count
    return float(missing), float(fallback)


def _compute_capm_distance_legacy(
    phi_a: Mapping[str, Any] | pd.Series,
    phi_b: Mapping[str, Any] | pd.Series,
    weights: Mapping[str, float] | None,
    cfg: Mapping[str, Any],
) -> dict[str, Any]:
    feature_keys = _capm_feature_keys(phi_a, phi_b, weights)
    if not feature_keys:
        return _unavailable_capm_result("legacy")
    tensor_total = 0.0
    missing_count = 0
    for key in feature_keys:
        left = _numeric(phi_a.get(key))
        right = _numeric(phi_b.get(key))
        if left is None or right is None:
            missing_count += 1
            continue
        weight = float((weights or {}).get(key, GOA_DEFAULT_WEIGHTS.get(key, 1.0)))
        tensor_total += weight * (left - right) ** 2
    couplings = _resolve_couplings(cfg) if cfg.get("coupling_enabled", True) is not False else []
    tensor_total += _coupling_distance(phi_a, phi_b, couplings)
    tensor_distance = float(np.sqrt(max(tensor_total, 0.0)))
    barrier_cost = max(constraint_barrier_score(phi_a, cfg), constraint_barrier_score(phi_b, cfg))
    missing_penalty = missing_count / max(len(feature_keys), 1) if cfg.get("missing_penalty_enabled", True) is not False else 0.0
    distance = tensor_distance + float(cfg["lambda_barrier"]) * barrier_cost + float(cfg["lambda_missing"]) * missing_penalty
    return {
        "status": "ok",
        "distance": float(distance),
        "tensor_distance": tensor_distance,
        "similarity_distance": tensor_distance,
        "barrier_cost": float(barrier_cost),
        "path_risk_cost": float(barrier_cost),
        "missing_penalty": float(missing_penalty),
        "proxy_fallback_penalty": 0.0,
        "feature_count": int(len(feature_keys)),
        "missing_feature_count": int(missing_count),
        "metric_version": "legacy",
    }


def _unavailable_capm_result(metric_version: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "distance": None,
        "tensor_distance": None,
        "similarity_distance": None,
        "geometric_distance": None,
        "decision_cost": None,
        "point_risk_cost": 0.0,
        "barrier_cost": 0.0,
        "path_risk_cost": 0.0,
        "missing_penalty": 1.0,
        "proxy_fallback_penalty": 0.0,
        "metric_version": metric_version,
        "reason": "no_shared_physics_features",
    }


def physics_geodesic_distance_to_l1(
    candidates_phi: pd.DataFrame,
    history_phi: pd.DataFrame,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
    context: CapmDistanceContext | None = None,
) -> pd.DataFrame:
    """Attach CAPM direct and kNN-graph distances from candidates to L1 samples."""

    output = candidates_phi.copy()
    if output.empty:
        return output
    cfg = _capm_config(config)
    version = str(cfg.get("metric_version", "v2")).lower()
    l1 = history_phi[history_phi.get("level_label", "") == "L1"] if "level_label" in history_phi.columns else history_phi.iloc[0:0]
    if l1.empty:
        output["capm_distance_to_l1"] = float("inf")
        output["capm_geodesic_distance_to_l1"] = float("inf")
        output["capm_similarity_distance_to_l1"] = float("inf")
        output["capm_barrier_score"] = [constraint_barrier_score(row, cfg) for _, row in output.iterrows()]
        output["capm_path_risk_cost"] = output["capm_barrier_score"]
        output["capm_point_risk_cost"] = output["capm_barrier_score"]
        output["capm_decision_cost_to_l1"] = float("inf")
        output["capm_missing_penalty"] = 1.0
        output["capm_proxy_fallback_penalty"] = 0.0
        output["capm_metric_version"] = version
        output["capm_l1_aggregation_status"] = "unavailable:no_l1_samples"
        output["capm_normalization_json"] = "{}"
        output["capm_distance_to_l1_calibrated"] = 1.0
        output["capm_distance_calibration_json"] = "{}"
        output["capm_calibration_status"] = "unavailable:no_l1_samples"
        output["capm_status"] = "unavailable:no_l1_samples"
        return output

    if version == "legacy":
        return _legacy_geodesic_distance_to_l1(output, history_phi, l1, weights, cfg)

    context = context or build_capm_distance_context(history_phi, weights, cfg)
    candidate_records = output.to_dict("records")
    history_records = history_phi.to_dict("records")
    l1_indices = [index for index, row in enumerate(history_records) if str(row.get("level_label", "")) == "L1"]
    history_graph = _capm_graph(history_records, weights, cfg, context=context)
    normalization_json = json.dumps(context.normalization_payload(), ensure_ascii=True, sort_keys=True)
    calibration_json = json.dumps(context.calibration_payload(), ensure_ascii=True, sort_keys=True)
    rows: list[dict[str, Any]] = []
    for row in candidate_records:
        direct_results = [
            compute_capm_distance(row, history_records[index], weights, cfg, context)
            for index in l1_indices
        ]
        direct = _aggregate_l1_results(direct_results, [history_records[index] for index in l1_indices], cfg)
        geodesic_values = _candidate_geodesic_distances(
            row,
            history_records,
            history_graph,
            l1_indices,
            weights,
            cfg,
            context,
        )
        geodesic_distance, aggregation_status = _aggregate_l1_values(
            geodesic_values,
            [history_records[index] for index in l1_indices],
            cfg,
        )
        if cfg.get("geodesic_enabled", True) is False or not np.isfinite(geodesic_distance):
            geodesic_distance = float(direct["distance"])
            aggregation_status = f"direct:{direct['aggregation_status']}"
        rows.append(
            {
                "capm_distance_to_l1": direct["distance"],
                "capm_geodesic_distance_to_l1": geodesic_distance,
                "capm_similarity_distance_to_l1": direct["similarity_distance"],
                "capm_barrier_score": constraint_barrier_score(row, cfg),
                "capm_path_risk_cost": direct["barrier_cost"],
                "capm_point_risk_cost": direct["point_risk_cost"],
                "capm_decision_cost_to_l1": direct["decision_cost"],
                "capm_missing_penalty": direct["missing_penalty"],
                "capm_proxy_fallback_penalty": direct["proxy_fallback_penalty"],
                "capm_metric_version": version,
                "capm_l1_aggregation_status": aggregation_status,
                "capm_normalization_json": normalization_json,
                "capm_distance_to_l1_calibrated": (
                    calibrate_v4_distance(geodesic_distance, context)
                    if version == "v4"
                    else calibrate_v3_distance(geodesic_distance, context)
                    if version == "v3"
                    else float("nan")
                ),
                "capm_distance_calibration_json": calibration_json if version in {"v3", "v4"} else "{}",
                "capm_calibration_status": context.calibration_status if version in {"v3", "v4"} else "not_applicable",
                "capm_status": direct["status"],
            }
        )
    return pd.concat([output.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def _legacy_geodesic_distance_to_l1(
    output: pd.DataFrame,
    history_phi: pd.DataFrame,
    l1: pd.DataFrame,
    weights: Mapping[str, float] | None,
    cfg: Mapping[str, Any],
) -> pd.DataFrame:
    candidate_records = output.to_dict("records")
    history_records = history_phi.to_dict("records")
    all_records = candidate_records + history_records
    l1_offsets = {len(candidate_records) + index for index, row in enumerate(history_records) if str(row.get("level_label", "")) == "L1"}
    graph = _capm_graph(all_records, weights, cfg)
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(candidate_records):
        direct = _nearest_l1_capm(row, l1, weights, cfg)
        geodesic = _shortest_distance_to_targets(graph, index, l1_offsets)
        geodesic_distance = geodesic if np.isfinite(geodesic) and cfg.get("geodesic_enabled", True) is not False else direct["distance"]
        rows.append(
            {
                "capm_distance_to_l1": direct["distance"],
                "capm_geodesic_distance_to_l1": geodesic_distance,
                "capm_similarity_distance_to_l1": direct.get("similarity_distance", direct["distance"]),
                "capm_barrier_score": constraint_barrier_score(row, cfg),
                "capm_path_risk_cost": direct.get("barrier_cost", 0.0),
                "capm_point_risk_cost": direct.get("point_risk_cost", 0.0),
                "capm_decision_cost_to_l1": direct.get("decision_cost", direct["distance"]),
                "capm_missing_penalty": direct["missing_penalty"],
                "capm_proxy_fallback_penalty": 0.0,
                "capm_metric_version": "legacy",
                "capm_l1_aggregation_status": "nearest:legacy",
                "capm_normalization_json": "{}",
                "capm_distance_to_l1_calibrated": float("nan"),
                "capm_distance_calibration_json": "{}",
                "capm_calibration_status": "not_applicable",
                "capm_status": direct["status"],
            }
        )
    return pd.concat([output.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def estimate_feature_weights(history: pd.DataFrame, feature_cols: Sequence[str], target_col: str = "overall_score") -> dict[str, float]:
    if len(history) < 4 or target_col not in history.columns:
        return {col: GOA_DEFAULT_WEIGHTS.get(col, 1.0) for col in feature_cols}
    try:
        from sklearn.ensemble import RandomForestRegressor
    except Exception:
        return {col: GOA_DEFAULT_WEIGHTS.get(col, 1.0) for col in feature_cols}
    model = RandomForestRegressor(n_estimators=32, random_state=42)
    x = history[list(feature_cols)].fillna(0.0)
    y = pd.to_numeric(history[target_col], errors="coerce").fillna(0.0)
    model.fit(x, y)
    return {col: float(max(importance, 0.01)) for col, importance in zip(feature_cols, model.feature_importances_)}


def distance_to_l1_physics(candidate_phi: Mapping[str, Any] | pd.Series, l1_phi: pd.DataFrame, weights: Mapping[str, float] | None = None) -> dict[str, Any]:
    if l1_phi.empty:
        return {"status": "unavailable", "distance": None, "reason": "no_l1_samples"}
    distances = [compute_physics_distance(candidate_phi, row, weights) for row in l1_phi.to_dict("records")]
    return {"status": "ok", "distance": float(min(distances))}


def physics_distance_matrix(candidates_phi: pd.DataFrame, history_phi: pd.DataFrame, weights: Mapping[str, float] | None = None) -> np.ndarray:
    return np.array(
        [
            [compute_physics_distance(candidate, history, weights) for history in history_phi.to_dict("records")]
            for candidate in candidates_phi.to_dict("records")
        ],
        dtype=float,
    )


def normalize_distance(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return array
    finite = np.where(np.isfinite(array), array, np.nan)
    if np.isnan(finite).all():
        return np.zeros_like(array, dtype=float)
    min_value = np.nanmin(finite)
    max_value = np.nanmax(finite)
    if not np.isfinite(min_value) or not np.isfinite(max_value) or max_value == min_value:
        return np.zeros_like(array, dtype=float)
    return np.nan_to_num((array - min_value) / (max_value - min_value), nan=1.0, posinf=1.0, neginf=0.0)


def _capm_config(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(CAPM_DEFAULT_CONFIG)
    nested: Mapping[str, Any] = {}
    if config:
        nested = config.get("capm_distance", config)
        if isinstance(nested, Mapping):
            cfg.update(nested)
        for block in ("constraint_classes", "historical_calibration"):
            value = config.get(block)
            if isinstance(value, Mapping):
                cfg[block] = dict(value)
    if str(cfg.get("metric_version", "v2")).lower() in {"v3", "v4"} and "couplings" not in nested:
        cfg["couplings"] = [dict(coupling) for coupling in CAPM_V3_COUPLINGS]
    return cfg


def _capm_feature_keys(
    phi_a: Mapping[str, Any] | pd.Series,
    phi_b: Mapping[str, Any] | pd.Series,
    weights: Mapping[str, float] | None = None,
) -> list[str]:
    keys = sorted(set(phi_a.keys()) | set(phi_b.keys()))
    preferred = set(GOA_DEFAULT_WEIGHTS) | set(weights or {})
    usable = [key for key in keys if key not in FORBIDDEN_DISTANCE_COLUMNS and key in preferred]
    if usable:
        return usable
    return [key for key in keys if key not in FORBIDDEN_DISTANCE_COLUMNS and _numeric(phi_a.get(key, phi_b.get(key))) is not None]


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


def _transform_feature(value: float, key: str, context: CapmDistanceContext) -> float:
    if context.config.get("normalization_enabled", True) is False:
        return float(value)
    center = float(context.centers.get(key, 0.0))
    scale = max(float(context.scales.get(key, 1.0)), 1e-12)
    clip = max(float(context.config.get("normalization_clip", 8.0)), 0.0)
    if context.metric_version == "v4":
        transformed = (_base_v4_transform(value, key) - center) / scale
    else:
        transformed = float(np.arcsinh((value - center) / scale))
    return float(np.clip(transformed, -clip, clip)) if clip > 0 else transformed


def _base_v4_transform(value: float, key: str) -> float:
    """Apply a transform matched to the feature's physical support."""

    if key in {
        "pullup_effective_resistance_ohm",
        "pulldown_effective_resistance_ohm",
        "effective_load_capacitance_f",
        "pullup_rc_delay_s",
        "pulldown_rc_delay_s",
        "critical_rc_delay_s",
        "pullup_rc_to_clock_slew_ratio",
        "pulldown_rc_to_clock_slew_ratio",
    }:
        return float(math.log(max(value, 1.0e-30)))
    if key == "bootstrap_coupling_factor_v3":
        probability = float(np.clip(value, 1.0e-9, 1.0 - 1.0e-9))
        return float(math.log(probability / (1.0 - probability)))
    return float(np.arcsinh(value))


def _feature_status(row: Mapping[str, Any] | pd.Series, key: str) -> str:
    raw = row.get("physics_feature_status_json")
    if not isinstance(raw, str) or not raw:
        return "unknown"
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "unknown"
    return str(payload.get(key, "unknown")) if isinstance(payload, Mapping) else "unknown"


def _midpoint_features(
    phi_a: Mapping[str, Any] | pd.Series,
    phi_b: Mapping[str, Any] | pd.Series,
    feature_keys: Sequence[str],
) -> dict[str, float]:
    midpoint: dict[str, float] = {}
    keys = set(feature_keys) | set(phi_a.keys()) | set(phi_b.keys())
    for key in keys:
        if key in FORBIDDEN_DISTANCE_COLUMNS:
            continue
        left = _numeric(phi_a.get(key))
        right = _numeric(phi_b.get(key))
        if left is not None and right is not None:
            midpoint[key] = (left + right) / 2.0
    return midpoint


def _normalized_coupling_distance(
    transformed_a: Mapping[str, float],
    transformed_b: Mapping[str, float],
    couplings: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> float:
    available = [
        entry
        for entry in couplings
        if entry["left"] in transformed_a
        and entry["right"] in transformed_a
        and entry["left"] in transformed_b
        and entry["right"] in transformed_b
    ]
    total_weight = sum(max(float(entry.get("weight", 0.0)), 0.0) for entry in available)
    if total_weight <= 0.0:
        return 0.0
    raw = 0.0
    for entry in available:
        left_key = str(entry["left"])
        right_key = str(entry["right"])
        weight = max(float(entry.get("weight", 0.0)), 0.0)
        delta = transformed_a[left_key] * transformed_a[right_key] - transformed_b[left_key] * transformed_b[right_key]
        raw += weight * delta**2
    return float(max(float(config.get("coupling_budget", 0.25)), 0.0) * raw)


def _linear_penalty(delta: float, threshold: float) -> float:
    """Linear penalty: |delta| / threshold."""
    if threshold <= 0:
        return 0.0
    return float(abs(delta) / threshold)


def _quadratic_penalty(delta: float, threshold: float) -> float:
    """Quadratic penalty: (delta / threshold)^2."""
    if threshold <= 0:
        return 0.0
    return float((delta / threshold) ** 2)


def _exponential_penalty(delta: float, threshold: float, alpha: float = 2.0) -> float:
    """Exponential penalty: exp(alpha * |delta| / threshold) - 1."""
    if threshold <= 0:
        return 0.0
    exponent = min(alpha * abs(delta) / threshold, 60.0)
    return float(np.exp(exponent) - 1.0)


PENALTY_FUNCTIONS = {
    "linear": _linear_penalty,
    "quadratic": _quadratic_penalty,
    "exponential": _exponential_penalty,
}

DEFAULT_PENALTY_TYPE = "exponential"
DEFAULT_PENALTY_ALPHA = 2.0


def _apply_penalty(
    value: float | None,
    threshold: float,
    direction: str,
    penalty_config: Mapping[str, Any] | None = None,
    feature_name: str = "",
) -> float:
    """Apply configured penalty function for a feature constraint.

    Args:
        value: The observed value.
        threshold: The constraint threshold.
        direction: "low" (value must be >= threshold) or "high" (value must be <= threshold).
        penalty_config: Per-feature penalty configuration from YAML.
        feature_name: Name of the feature (used to look up per-feature config).

    Returns:
        Penalty score (0.0 if constraint is satisfied).
    """
    if value is None or threshold <= 0:
        return 0.0

    if direction == "low":
        if value >= threshold:
            return 0.0
        delta = threshold - value
    elif direction == "high":
        if value <= threshold:
            return 0.0
        delta = value - threshold
    else:
        return 0.0

    # Resolve penalty type and alpha for this feature
    pcfg = (penalty_config or {}).get(feature_name, {}) if penalty_config else {}
    penalty_type = str(pcfg.get("type", DEFAULT_PENALTY_TYPE)).lower()
    alpha = float(pcfg.get("alpha", DEFAULT_PENALTY_ALPHA))

    if penalty_type not in PENALTY_FUNCTIONS:
        penalty_type = DEFAULT_PENALTY_TYPE

    fn = PENALTY_FUNCTIONS[penalty_type]
    if penalty_type == "exponential":
        return fn(delta, threshold, alpha)
    return fn(delta, threshold)


def _low_margin_penalty(value: float | None, threshold: float) -> float:
    if value is None or threshold <= 0:
        return 0.0
    if value >= threshold:
        return 0.0
    return _quadratic_penalty(threshold - value, threshold)


def _high_proxy_penalty(value: float | None, threshold: float) -> float:
    if value is None or threshold <= 0:
        return 0.0
    if value <= threshold:
        return 0.0
    return _quadratic_penalty(value - threshold, threshold)


def _resolve_couplings(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Resolve enabled coupling pairs with per-pair weights from config.

    Supports both new per-pair config and legacy global coupling_weight.
    """
    couplings_cfg = config.get("couplings", [])
    if not couplings_cfg:
        # Legacy fallback: use CAPM_COUPLINGS with global coupling_weight
        legacy_weight = float(config.get("coupling_weight", 0.25))
        return [
            {"left": c["left"], "right": c["right"], "weight": legacy_weight}
            for c in CAPM_COUPLINGS
        ]
    # New per-pair config
    resolved = []
    for entry in couplings_cfg:
        if not isinstance(entry, dict):
            continue
        if not entry.get("enabled", True):
            continue
        resolved.append({
            "left": str(entry["left"]),
            "right": str(entry["right"]),
            "weight": float(entry.get("weight", 0.25)),
        })
    return resolved


def _coupling_distance(
    phi_a: Mapping[str, Any],
    phi_b: Mapping[str, Any],
    couplings: list[dict[str, Any]],
) -> float:
    total = 0.0
    for entry in couplings:
        left_key = entry["left"]
        right_key = entry["right"]
        weight = float(entry.get("weight", 0.25))
        a_left = _numeric(phi_a.get(left_key))
        a_right = _numeric(phi_a.get(right_key))
        b_left = _numeric(phi_b.get(left_key))
        b_right = _numeric(phi_b.get(right_key))
        if None in {a_left, a_right, b_left, b_right}:
            continue
        total += weight * ((a_left * a_right) - (b_left * b_right)) ** 2
    return float(total)


def _nearest_l1_capm(
    row: Mapping[str, Any],
    l1: pd.DataFrame,
    weights: Mapping[str, float] | None,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    results = [compute_capm_distance(row, record, weights, config) for record in l1.to_dict("records")]
    ok = [result for result in results if result.get("distance") is not None]
    if not ok:
        return {"status": "unavailable", "distance": float("inf"), "missing_penalty": 1.0}
    return min(ok, key=lambda item: float(item["distance"]))


def _aggregate_l1_results(
    results: Sequence[Mapping[str, Any]],
    l1_records: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    distances = [float(result["distance"]) if result.get("distance") is not None else float("inf") for result in results]
    distance, status = _aggregate_l1_values(distances, l1_records, config)
    similarities = [
        float(result["similarity_distance"])
        if result.get("similarity_distance") is not None
        else float("inf")
        for result in results
    ]
    similarity, _ = _aggregate_l1_values(similarities, l1_records, config)
    decisions = [
        float(result.get("decision_cost", result["distance"]))
        if result.get("distance") is not None
        else float("inf")
        for result in results
    ]
    decision_cost, _ = _aggregate_l1_values(decisions, l1_records, config)
    finite_results = [result for result in results if result.get("distance") is not None and np.isfinite(float(result["distance"]))]
    if not finite_results:
        return {
            "status": "unavailable",
            "distance": float("inf"),
            "similarity_distance": float("inf"),
            "barrier_cost": 0.0,
            "point_risk_cost": 0.0,
            "decision_cost": float("inf"),
            "missing_penalty": 1.0,
            "proxy_fallback_penalty": 0.0,
            "aggregation_status": status,
        }
    nearest = min(finite_results, key=lambda result: float(result["distance"]))
    return {
        "status": "ok",
        "distance": distance,
        "similarity_distance": similarity,
        "barrier_cost": float(nearest.get("barrier_cost", 0.0)),
        "point_risk_cost": float(nearest.get("point_risk_cost", 0.0)),
        "decision_cost": float(decision_cost),
        "missing_penalty": float(nearest.get("missing_penalty", 0.0)),
        "proxy_fallback_penalty": float(nearest.get("proxy_fallback_penalty", 0.0)),
        "aggregation_status": status,
    }


def _aggregate_l1_values(
    values: Sequence[float],
    l1_records: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> tuple[float, str]:
    finite = [
        (float(value), record)
        for value, record in zip(values, l1_records)
        if np.isfinite(float(value))
    ]
    if not finite:
        return float("inf"), "unavailable"
    finite.sort(key=lambda item: item[0])
    top_k = max(int(config.get("l1_top_k", 3)), 1)
    selected = finite[:top_k]
    if str(config.get("l1_aggregation", "softmin")).lower() != "softmin" or len(selected) == 1:
        return selected[0][0], "nearest"
    scores = np.asarray([_numeric(record.get("overall_score")) or 0.0 for _, record in selected], dtype=float)
    if np.ptp(scores) > 0:
        normalized_scores = (scores - scores.min()) / np.ptp(scores)
    else:
        normalized_scores = np.zeros_like(scores)
    quality_weight = max(float(config.get("l1_quality_weight", 0.25)), 0.0)
    quality = 1.0 + quality_weight * normalized_scores
    distances = np.asarray([value for value, _ in selected], dtype=float)
    temperature = max(float(config.get("softmin_temperature", 0.25)), 1e-9)
    minimum = float(distances.min())
    mean_exp = float(np.sum(quality * np.exp(-(distances - minimum) / temperature)) / np.sum(quality))
    aggregated = minimum - temperature * np.log(max(mean_exp, 1e-300))
    return float(aggregated), f"softmin:{len(selected)}"


def _candidate_geodesic_distances(
    candidate: Mapping[str, Any],
    history_records: Sequence[Mapping[str, Any]],
    history_graph: list[list[tuple[int, float]]],
    l1_indices: Sequence[int],
    weights: Mapping[str, float] | None,
    config: Mapping[str, Any],
    context: CapmDistanceContext,
) -> list[float]:
    if config.get("geodesic_enabled", True) is False:
        return [float("inf") for _ in l1_indices]
    pair_distances: list[tuple[float, int]] = []
    for index, record in enumerate(history_records):
        result = compute_capm_distance(candidate, record, weights, config, context)
        if result.get("distance") is not None and np.isfinite(float(result["distance"])):
            pair_distances.append((float(result["distance"]), index))
    graph = [list(edges) for edges in history_graph]
    source = len(graph)
    graph.append([])
    k_neighbors = max(int(config.get("k_neighbors", 4)), 1)
    lambda_graph = float(config.get("lambda_graph", 1.0))
    for distance, target in sorted(pair_distances)[:k_neighbors]:
        edge = lambda_graph * distance
        graph[source].append((target, edge))
        graph[target].append((source, edge))
    target_distances = _shortest_distances_to_targets(graph, source, set(l1_indices))
    return [target_distances.get(index, float("inf")) for index in l1_indices]


def _capm_graph(
    records: list[dict[str, Any]],
    weights: Mapping[str, float] | None,
    config: Mapping[str, Any],
    context: CapmDistanceContext | None = None,
) -> list[list[tuple[int, float]]]:
    k_neighbors = max(1, int(config.get("k_neighbors", 4)))
    graph: list[list[tuple[int, float]]] = [[] for _ in records]
    pair_distances: list[tuple[int, int, float]] = []
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            result = compute_capm_distance(records[left], records[right], weights, config, context)
            distance = float(result["distance"]) if result.get("distance") is not None else float("inf")
            if np.isfinite(distance):
                pair_distances.append((left, right, distance))
    neighbors: dict[int, list[tuple[float, int]]] = {index: [] for index in range(len(records))}
    for left, right, distance in pair_distances:
        neighbors[left].append((distance, right))
        neighbors[right].append((distance, left))
    for source, items in neighbors.items():
        for distance, target in sorted(items)[:k_neighbors]:
            edge = float(config.get("lambda_graph", 1.0)) * distance
            graph[source].append((target, edge))
            graph[target].append((source, edge))
    return graph


def _shortest_distance_to_targets(graph: list[list[tuple[int, float]]], source: int, targets: set[int]) -> float:
    if not targets:
        return float("inf")
    queue: list[tuple[float, int]] = [(0.0, source)]
    seen: set[int] = set()
    while queue:
        distance, node = heappop(queue)
        if node in seen:
            continue
        if node in targets:
            return float(distance)
        seen.add(node)
        for target, edge in graph[node]:
            if target not in seen:
                heappush(queue, (distance + edge, target))
    return float("inf")


def _shortest_distances_to_targets(
    graph: list[list[tuple[int, float]]],
    source: int,
    targets: set[int],
) -> dict[int, float]:
    if not targets:
        return {}
    queue: list[tuple[float, int]] = [(0.0, source)]
    best: dict[int, float] = {source: 0.0}
    found: dict[int, float] = {}
    while queue and len(found) < len(targets):
        distance, node = heappop(queue)
        if distance > best.get(node, float("inf")):
            continue
        if node in targets:
            found[node] = distance
        for target, edge in graph[node]:
            candidate_distance = distance + edge
            if candidate_distance < best.get(target, float("inf")):
                best[target] = candidate_distance
                heappush(queue, (candidate_distance, target))
    return found
