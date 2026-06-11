from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd


def fit_latent_encoder(history: pd.DataFrame, input_features: Sequence[str], method: str = "pca_metric") -> dict[str, Any]:
    if method == "torch_encoder_optional":
        try:
            import torch  # noqa: F401
        except Exception:
            return {"status": "unavailable", "reason": "torch_not_installed"}
    if len(history) < 2 or not input_features:
        return {"status": "unavailable", "reason": "insufficient_data"}
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    x = scaler.fit_transform(history[list(input_features)].fillna(0.0))
    pca = PCA(n_components=min(2, x.shape[1], x.shape[0]))
    pca.fit(x)
    return {"status": "ok", "method": method, "scaler": scaler, "encoder": pca, "input_features": list(input_features)}


def transform_latent(encoder: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    if encoder.get("status") != "ok":
        return np.empty((len(frame), 0))
    x = encoder["scaler"].transform(frame[encoder["input_features"]].fillna(0.0))
    return encoder["encoder"].transform(x)


def latent_distance_to_l1(candidate_z: np.ndarray, l1_z: np.ndarray) -> dict[str, Any]:
    if candidate_z.size == 0 or l1_z.size == 0:
        return {"status": "unavailable", "distance": None}
    distances = np.linalg.norm(np.asarray(l1_z) - np.asarray(candidate_z), axis=1)
    return {"status": "ok", "distance": float(distances.min())}


def attention_weighted_l1_distance(candidate_z: np.ndarray, l1_z: np.ndarray, attention_weights: np.ndarray) -> dict[str, Any]:
    if candidate_z.size == 0 or l1_z.size == 0 or attention_weights.size == 0:
        return {"status": "unavailable", "distance": None}
    distances = np.linalg.norm(np.asarray(l1_z) - np.asarray(candidate_z), axis=1)
    weights = attention_weights[: len(distances)]
    weights = weights / weights.sum() if weights.sum() else np.ones_like(weights) / len(weights)
    return {"status": "ok", "distance": float(np.dot(distances, weights))}
