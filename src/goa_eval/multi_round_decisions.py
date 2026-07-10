from __future__ import annotations

import pandas as pd

from goa_eval.io_utils import as_float


def target_metric_status(row: pd.Series | dict, *, metric: str, threshold: float) -> dict[str, object]:
    metric_value = as_float(row.get(metric))
    stage_count = as_float(row.get("stage_count"))
    status = str(row.get("status", "") or "").lower()
    if metric == "Max_overlap_ratio" and (stage_count is None or stage_count < 2):
        return _not_evaluable(metric, threshold, metric_value)
    if status != "evaluated" or metric_value is None:
        return _not_evaluable(metric, threshold, metric_value)
    passed = metric_value < threshold
    return {
        "target_metric": metric,
        "target_threshold": threshold,
        "target_value": metric_value,
        "target_passed": bool(passed),
        "target_status": "passed" if passed else "failed",
    }


def should_stop_optimization(rounds: list[dict], *, patience: int, min_improvement: float) -> str:
    if len(rounds) <= 1 or patience <= 0:
        return ""
    best = as_float(rounds[0].get("best_score"))
    stale = 0
    for item in rounds[1:]:
        score = as_float(item.get("best_score"))
        if score is None:
            stale += 1
        elif best is None or score >= best + min_improvement:
            best = score
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            return f"no improvement for {patience} round(s)"
    return ""


def _not_evaluable(metric: str, threshold: float, value: float | None) -> dict[str, object]:
    return {
        "target_metric": metric,
        "target_threshold": threshold,
        "target_value": value,
        "target_passed": "",
        "target_status": "not_evaluable",
    }
