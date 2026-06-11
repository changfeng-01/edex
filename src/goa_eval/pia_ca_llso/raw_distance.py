from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd


def normalize_raw_parameters(frame: pd.DataFrame, parameter_names: Sequence[str]) -> pd.DataFrame:
    normalized = pd.DataFrame(index=frame.index)
    for name in parameter_names:
        values = pd.to_numeric(frame.get(name, 0.0), errors="coerce").fillna(0.0)
        span = values.max() - values.min()
        normalized[name] = 0.0 if span == 0 else (values - values.min()) / span
    return normalized


def raw_euclidean_distance(x_candidate: dict[str, Any] | pd.Series, x_reference: dict[str, Any] | pd.Series) -> float:
    keys = sorted(set(x_candidate.keys()) & set(x_reference.keys()))
    if not keys:
        return float("inf")
    return float(np.sqrt(sum((float(x_candidate[key]) - float(x_reference[key])) ** 2 for key in keys)))


def distance_to_l1_raw(candidate: pd.Series, l1_frame: pd.DataFrame, parameter_names: Sequence[str] | None = None) -> dict[str, Any]:
    l1 = l1_frame[l1_frame.get("level_label", "") == "L1"] if "level_label" in l1_frame.columns else l1_frame
    if l1.empty:
        return {"status": "unavailable", "distance": None, "reason": "no_l1_samples"}
    params = list(parameter_names or [col for col in l1.columns if col in candidate.index and pd.api.types.is_numeric_dtype(l1[col])])
    distances = [raw_euclidean_distance(candidate[params], row[params]) for _, row in l1.iterrows()]
    return {"status": "ok", "distance": float(min(distances))}


def select_by_raw_distance(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    parameter_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    output = candidates.copy()
    if output.empty:
        return output
    distances = []
    for _, row in output.iterrows():
        result = distance_to_l1_raw(row, history, parameter_names)
        distances.append(result["distance"] if result["distance"] is not None else float("inf"))
    output["raw_distance_to_l1"] = distances
    if np.isinf(output["raw_distance_to_l1"]).all():
        sort_cols = [col for col in ["p_l1", "p_hard_pass", "predicted_score"] if col in output.columns]
        return output.sort_values(sort_cols, ascending=[False] * len(sort_cols)).head(top_k) if sort_cols else output.head(top_k)
    return output.sort_values("raw_distance_to_l1", ascending=True).head(top_k)
