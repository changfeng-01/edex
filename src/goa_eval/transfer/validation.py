from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd


def leave_one_circuit_out(
    frame: pd.DataFrame,
    *,
    domain_column: str,
    target_column: str,
    predictor: Callable[[pd.DataFrame, pd.DataFrame], np.ndarray],
) -> pd.DataFrame:
    """Evaluate transfer with the complete target circuit held out of fitting."""

    rows: list[dict[str, float | int | str]] = []
    for domain in sorted(frame[domain_column].dropna().astype(str).unique()):
        held_out = frame[frame[domain_column].astype(str) == domain].copy()
        train = frame[frame[domain_column].astype(str) != domain].copy()
        predicted = np.asarray(predictor(train, held_out), dtype=float)
        actual = pd.to_numeric(held_out[target_column], errors="coerce").to_numpy(dtype=float)
        if predicted.shape != actual.shape:
            raise ValueError("LOCO predictor must return one prediction per held-out row")
        error = predicted - actual
        rows.append(
            {
                "held_out_domain": domain,
                "train_domain_count": int(train[domain_column].nunique()),
                "test_count": int(len(held_out)),
                "mae": float(np.mean(np.abs(error))),
                "rmse": float(np.sqrt(np.mean(error**2))),
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        )
    return pd.DataFrame(rows)
