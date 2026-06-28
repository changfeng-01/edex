from __future__ import annotations

from heapq import heappop, heappush
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

CAPM_DEFAULT_CONFIG = {
    "lambda_barrier": 1.0,
    "lambda_graph": 1.0,
    "lambda_missing": 1.0,
    "k_neighbors": 4,
    "min_vgh_vth_margin": 0.2,
    "min_vgl_off_margin": 0.2,
    "min_cboot_cload_ratio": 0.35,
    "max_ron_pullup_cload_proxy": 2.0,
    "max_ron_pulldown_cload_proxy": 2.0,
    "min_pullup_pulldown_ratio": 0.5,
    "max_pullup_pulldown_ratio": 2.0,
    "max_clk_slew_proxy": 2.0,
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


def compute_capm_distance(
    phi_a: Mapping[str, Any] | pd.Series,
    phi_b: Mapping[str, Any] | pd.Series,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute constraint-aware physics-manifold distance between two points."""

    cfg = _capm_config(config)
    feature_keys = _capm_feature_keys(phi_a, phi_b, weights)
    if not feature_keys:
        return {
            "status": "unavailable",
            "distance": None,
            "tensor_distance": None,
            "barrier_cost": 0.0,
            "missing_penalty": 1.0,
            "reason": "no_shared_physics_features",
        }
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
    couplings = _resolve_couplings(cfg)
    tensor_total += _coupling_distance(phi_a, phi_b, couplings)
    tensor_distance = float(np.sqrt(max(tensor_total, 0.0)))
    barrier_cost = max(constraint_barrier_score(phi_a, cfg), constraint_barrier_score(phi_b, cfg))
    missing_penalty = missing_count / max(len(feature_keys), 1)
    distance = tensor_distance + float(cfg["lambda_barrier"]) * barrier_cost + float(cfg["lambda_missing"]) * missing_penalty
    return {
        "status": "ok",
        "distance": float(distance),
        "tensor_distance": tensor_distance,
        "barrier_cost": float(barrier_cost),
        "missing_penalty": float(missing_penalty),
        "feature_count": int(len(feature_keys)),
        "missing_feature_count": int(missing_count),
    }


def physics_geodesic_distance_to_l1(
    candidates_phi: pd.DataFrame,
    history_phi: pd.DataFrame,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Attach CAPM direct and kNN-graph distances from candidates to L1 samples."""

    output = candidates_phi.copy()
    if output.empty:
        return output
    cfg = _capm_config(config)
    l1 = history_phi[history_phi.get("level_label", "") == "L1"] if "level_label" in history_phi.columns else history_phi.iloc[0:0]
    if l1.empty:
        output["capm_distance_to_l1"] = float("inf")
        output["capm_geodesic_distance_to_l1"] = float("inf")
        output["capm_barrier_score"] = [constraint_barrier_score(row, cfg) for _, row in output.iterrows()]
        output["capm_missing_penalty"] = 1.0
        output["capm_status"] = "unavailable:no_l1_samples"
        return output

    candidate_records = output.to_dict("records")
    history_records = history_phi.to_dict("records")
    all_records = candidate_records + history_records
    l1_offsets = {len(candidate_records) + index for index, row in enumerate(history_records) if str(row.get("level_label", "")) == "L1"}
    graph = _capm_graph(all_records, weights, cfg)
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(candidate_records):
        direct = _nearest_l1_capm(row, l1, weights, cfg)
        geodesic = _shortest_distance_to_targets(graph, index, l1_offsets)
        geodesic_distance = geodesic if np.isfinite(geodesic) else direct["distance"]
        rows.append(
            {
                "capm_distance_to_l1": direct["distance"],
                "capm_geodesic_distance_to_l1": geodesic_distance,
                "capm_barrier_score": constraint_barrier_score(row, cfg),
                "capm_missing_penalty": direct["missing_penalty"],
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
    if config:
        nested = config.get("capm_distance", config)
        if isinstance(nested, Mapping):
            cfg.update(nested)
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
    return float(np.exp(alpha * abs(delta) / threshold) - 1.0)


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


def _capm_graph(
    records: list[dict[str, Any]],
    weights: Mapping[str, float] | None,
    config: Mapping[str, Any],
) -> list[list[tuple[int, float]]]:
    k_neighbors = max(1, int(config.get("k_neighbors", 4)))
    graph: list[list[tuple[int, float]]] = [[] for _ in records]
    pair_distances: list[tuple[int, int, float]] = []
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            result = compute_capm_distance(records[left], records[right], weights, config)
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
