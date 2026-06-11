from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def compute_attention(
    candidate_z: np.ndarray,
    history_z: np.ndarray,
    physics_distance: Sequence[float] | None = None,
    alpha: float = 0.2,
) -> tuple[np.ndarray, str]:
    candidate = np.asarray(candidate_z, dtype=float)
    history = np.asarray(history_z, dtype=float)
    if candidate.size == 0 or history.size == 0:
        return np.array([], dtype=float), "diagnostic_unavailable"
    if history.ndim == 1:
        history = history.reshape(1, -1)
    scale = np.sqrt(max(candidate.shape[0], 1))
    scores = history.dot(candidate) / scale
    if physics_distance is not None:
        scores = scores - alpha * np.asarray(physics_distance, dtype=float)
    scores = scores - np.max(scores)
    weights = np.exp(scores)
    total = weights.sum()
    if total <= 0:
        return np.zeros_like(weights), "diagnostic_unavailable"
    return weights / total, "ok"


def attention_to_l1_mass(attention_weights: Sequence[float], history_levels: Sequence[str]) -> float:
    weights = np.asarray(attention_weights, dtype=float)
    return float(sum(weight for weight, level in zip(weights, history_levels) if level == "L1"))


def aggregate_history_context(attention_weights: Sequence[float], history_values: Sequence[float]) -> float:
    weights = np.asarray(attention_weights, dtype=float)
    values = np.asarray(history_values, dtype=float)
    if weights.size == 0 or values.size == 0:
        return 0.0
    return float(np.dot(weights, values[: weights.size]))


def topk_attention_explanations(candidate: dict[str, Any], history: Sequence[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    rows = sorted(history, key=lambda row: float(row.get("attention_score", 0.0)), reverse=True)[:k]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "top_attention_sample_ids": [row.get("sample_id") for row in rows],
        "top_attention_levels": [row.get("level_label") for row in rows],
        "top_attention_scores": [row.get("attention_score", 0.0) for row in rows],
        "attention_status": "ok" if rows else "diagnostic_unavailable",
    }
