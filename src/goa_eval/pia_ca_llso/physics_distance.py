from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


GOA_DEFAULT_WEIGHTS = {
    "cboot_cload_ratio": 2.0,
    "pullup_pulldown_ratio": 2.0,
    "ron_pullup_cload_proxy": 1.5,
    "ron_pulldown_cload_proxy": 1.5,
    "vgh_vth_margin": 1.5,
    "vgl_off_margin": 1.5,
    "clk_slew_proxy": 1.2,
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
    min_value = np.nanmin(finite)
    max_value = np.nanmax(finite)
    if not np.isfinite(min_value) or not np.isfinite(max_value) or max_value == min_value:
        return np.zeros_like(array, dtype=float)
    return np.nan_to_num((array - min_value) / (max_value - min_value), nan=1.0, posinf=1.0, neginf=0.0)
