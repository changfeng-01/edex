from __future__ import annotations

from typing import Any

import pandas as pd


def summarize_metric(values: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {"mean": None, "std": None, "min": None, "max": None, "median": None, "seed_count": int(len(values))}
    return {
        "mean": float(numeric.mean()),
        "std": float(numeric.std(ddof=0)),
        "min": float(numeric.min()),
        "max": float(numeric.max()),
        "median": float(numeric.median()),
        "seed_count": int(len(values)),
    }


def statistical_test_status() -> dict[str, Any]:
    try:
        import scipy  # noqa: F401
    except Exception:
        return {"statistical_test_available": False, "reason": "scipy unavailable"}
    return {"statistical_test_available": True, "wilcoxon_vs_baseline": "not_run"}
