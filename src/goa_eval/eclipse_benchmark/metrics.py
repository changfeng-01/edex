from __future__ import annotations

import math
from typing import Any

import pandas as pd

from goa_eval.eclipse_benchmark.schema import ROLE_NAMES


def compute_run_metrics(
    history: pd.DataFrame,
    *,
    candidate_audit: pd.DataFrame | None = None,
    attention_audit: pd.DataFrame | None = None,
    score_threshold: float = 80.0,
) -> dict[str, Any]:
    frame = history.reset_index(drop=True).copy()
    curve = compute_convergence_curve(frame)
    feasible = _feasible_mask(frame)
    best_feasible = _best_feasible_row(frame, feasible)
    best_any_score = _col_max(frame, "overall_score")
    candidate_metrics = compute_candidate_selection_metrics(frame, candidate_audit, score_threshold=score_threshold)
    attention_metrics = compute_attention_metrics(attention_audit)
    metrics: dict[str, Any] = {
        "simulation_count": int(len(frame)),
        "target_score_threshold": float(score_threshold),
        "best_any_score": best_any_score,
        "best_feasible_score": None,
        "best_feasible_round": None,
        "best_feasible_candidate_id": None,
        "best_feasible_status": "no_feasible_candidate",
        "normalized_convergence_auc": _normalized_auc(curve),
        "fe_at_target_score": _fe_at_target(curve, score_threshold),
        "first_feasible_round": _first_index(_basic_feasible_mask(frame)),
        "first_target_pass_round": _first_index(_target_pass_mask(frame)),
        "hard_constraint_pass_rate": _bool_rate(frame, "hard_constraint_passed", value=True),
        "target_pass_rate": _bool_rate(frame, "target_passed", value=True),
        "not_evaluable_rate": _status_rate(frame, "not_evaluable"),
        "hard_fail_rate": _hard_fail_rate(frame),
        "simulation_failure_rate": _simulation_failure_rate(frame),
        "mean_constraint_violation_proxy": _constraint_violation_proxy(frame),
        "evidence_boundary_preserved": _evidence_boundary_preserved(frame),
    }
    if best_feasible is not None:
        metrics.update(
            {
                "best_feasible_score": _as_float(best_feasible.get("overall_score")),
                "best_feasible_round": _round_number(best_feasible),
                "best_feasible_candidate_id": best_feasible.get("candidate_id") or best_feasible.get("run_id"),
                "best_feasible_status": "found",
            }
        )
    metrics.update(candidate_metrics)
    metrics.update(attention_metrics)
    return metrics


def compute_convergence_curve(history: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    best_feasible: float | None = None
    best_any: float | None = None
    for index, row in history.reset_index(drop=True).iterrows():
        score = _as_float(row.get("overall_score"))
        if score is not None and (best_any is None or score > best_any):
            best_any = score
        if _is_feasible(row) and score is not None and (best_feasible is None or score > best_feasible):
            best_feasible = score
        rows.append(
            {
                "simulation_index": index + 1,
                "current_best_feasible_score": best_feasible,
                "current_best_any_score": best_any,
                "hard_constraint_passed": _as_bool(row.get("hard_constraint_passed")),
                "target_passed": _as_bool(row.get("target_passed")),
                "rank_status": row.get("rank_status", ""),
                "not_evaluable_metric_count": int(_as_float(row.get("not_evaluable_metric_count")) or 0),
            }
        )
    curve = pd.DataFrame(rows)
    if "current_best_feasible_score" in curve:
        curve["current_best_feasible_score"] = curve["current_best_feasible_score"].astype(object)
        curve.loc[curve["current_best_feasible_score"].isna(), "current_best_feasible_score"] = None
    return curve


def compute_candidate_selection_metrics(
    history: pd.DataFrame,
    candidate_audit: pd.DataFrame | None,
    *,
    score_threshold: float = 80.0,
) -> dict[str, Any]:
    if candidate_audit is None or candidate_audit.empty:
        return _empty_candidate_metrics(role_available=False)
    audit = candidate_audit.copy()
    selected_count = len(audit)
    l1_ids = _true_l1_ids(history, score_threshold=score_threshold)
    hits = audit["candidate_id"].astype(str).isin(l1_ids) if "candidate_id" in audit else pd.Series([False] * selected_count)
    metrics = {
        "selected_candidate_count": int(selected_count),
        "candidate_hit_rate": _safe_div(int(hits.sum()), selected_count),
        "l1_discovery_count": int(hits.sum()),
        "true_l1_rate": _safe_div(len(l1_ids), len(history)),
        "role_metrics_available": "candidate_role" in audit.columns,
        "role_hit_rate": None,
        **{f"{role}_hit_rate": None for role in ROLE_NAMES},
    }
    if "candidate_role" not in audit.columns:
        return metrics
    metrics["role_hit_rate"] = metrics["candidate_hit_rate"]
    audit = audit.assign(_hit=hits.values)
    for role in ROLE_NAMES:
        role_rows = audit[audit["candidate_role"].astype(str).eq(role)]
        metrics[f"{role}_hit_rate"] = _safe_div(int(role_rows["_hit"].sum()), len(role_rows)) if len(role_rows) else None
    return metrics


def compute_attention_metrics(attention_audit: pd.DataFrame | None) -> dict[str, Any]:
    columns = {
        "attention_to_real_l1": "mean_attention_to_real_l1",
        "attention_real_sim_mass": "mean_attention_real_sim_mass",
        "attention_proxy_mass": "mean_attention_proxy_mass",
        "attention_explanation_consistency": "attention_explanation_consistency",
    }
    if attention_audit is None or attention_audit.empty or not any(col in attention_audit for col in columns):
        return {
            "attention_metrics_available": False,
            "mean_attention_to_real_l1": None,
            "mean_attention_real_sim_mass": None,
            "mean_attention_proxy_mass": None,
            "attention_explanation_consistency": None,
        }
    metrics: dict[str, Any] = {"attention_metrics_available": True}
    for source, target in columns.items():
        metrics[target] = _col_mean(attention_audit, source)
    return metrics


def _empty_candidate_metrics(*, role_available: bool) -> dict[str, Any]:
    return {
        "selected_candidate_count": None,
        "candidate_hit_rate": None,
        "l1_discovery_count": None,
        "true_l1_rate": None,
        "role_metrics_available": role_available,
        "role_hit_rate": None,
        **{f"{role}_hit_rate": None for role in ROLE_NAMES},
    }


def _feasible_mask(frame: pd.DataFrame) -> pd.Series:
    return frame.apply(_is_feasible, axis=1) if not frame.empty else pd.Series(dtype=bool)


def _basic_feasible_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    return frame.apply(
        lambda row: str(row.get("rank_status", "evaluated")) == "evaluated" and _as_bool(row.get("hard_constraint_passed")) is True,
        axis=1,
    )


def _target_pass_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    return frame.apply(
        lambda row: str(row.get("rank_status", "evaluated")) == "evaluated"
        and _as_bool(row.get("hard_constraint_passed")) is True
        and _as_bool(row.get("target_passed")) is True,
        axis=1,
    )


def _is_feasible(row: pd.Series | dict[str, Any]) -> bool:
    rank_status = str(row.get("rank_status", "evaluated") or "evaluated")
    score = _as_float(row.get("overall_score"))
    not_evaluable = int(_as_float(row.get("not_evaluable_metric_count")) or 0)
    return (
        rank_status == "evaluated"
        and _as_bool(row.get("hard_constraint_passed")) is True
        and _as_bool(row.get("target_passed")) is True
        and not_evaluable == 0
        and score is not None
        and math.isfinite(score)
    )


def _best_feasible_row(frame: pd.DataFrame, mask: pd.Series) -> pd.Series | None:
    if frame.empty or mask.empty or not bool(mask.any()):
        return None
    feasible = frame[mask].copy()
    feasible["_score"] = pd.to_numeric(feasible["overall_score"], errors="coerce")
    return feasible.sort_values("_score", ascending=False, kind="mergesort").iloc[0]


def _true_l1_ids(history: pd.DataFrame, *, score_threshold: float) -> set[str]:
    if history.empty or "candidate_id" not in history:
        return set()
    feasible = history[_feasible_mask(history)].copy()
    if feasible.empty:
        return set()
    feasible["_score"] = pd.to_numeric(feasible["overall_score"], errors="coerce")
    finite = feasible[feasible["_score"].notna()]
    if len(finite) >= 5:
        cutoff = finite["_score"].quantile(0.8)
    else:
        cutoff = score_threshold
    return set(finite[finite["_score"] >= cutoff]["candidate_id"].astype(str))


def _normalized_auc(curve: pd.DataFrame) -> float:
    if curve.empty:
        return 0.0
    values = [(_as_float(value) or 0.0) / 100.0 for value in curve["current_best_feasible_score"]]
    return max(0.0, min(1.0, sum(values) / len(values)))


def _fe_at_target(curve: pd.DataFrame, threshold: float) -> int | None:
    if curve.empty:
        return None
    for _, row in curve.iterrows():
        score = _as_float(row.get("current_best_feasible_score"))
        if score is not None and score >= threshold:
            return int(row["simulation_index"])
    return None


def _first_index(mask: pd.Series) -> int | None:
    if mask.empty or not bool(mask.any()):
        return None
    return int(mask[mask].index[0]) + 1


def _round_number(row: pd.Series) -> int | None:
    value = _as_float(row.get("round_index"))
    return int(value) if value is not None else None


def _hard_fail_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    count = 0
    for _, row in frame.iterrows():
        if str(row.get("rank_status", "evaluated")) == "evaluated" and _as_bool(row.get("hard_constraint_passed")) is False:
            count += 1
    return count / len(frame)


def _simulation_failure_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    count = 0
    for _, row in frame.iterrows():
        status = str(row.get("status", "") or "").lower()
        rank = str(row.get("rank_status", "") or "").lower()
        if status in {"sim_failed", "failed"} or "sim_failed" in rank:
            count += 1
    return count / len(frame)


def _status_rate(frame: pd.DataFrame, status_name: str) -> float:
    if frame.empty:
        return 0.0
    return float(frame.get("rank_status", pd.Series([""] * len(frame))).astype(str).eq(status_name).mean())


def _bool_rate(frame: pd.DataFrame, column: str, *, value: bool) -> float:
    if frame.empty or column not in frame:
        return 0.0
    return sum(1 for item in frame[column] if _as_bool(item) is value) / len(frame)


def _constraint_violation_proxy(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    columns = ["hard_constraint_failure_count", "constraint_violation_count", "metric_penalty_count"]
    for column in columns:
        if column in frame:
            values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
            return float(values.mean())
    if "failure_reasons" in frame:
        counts = [len([item for item in str(value).split(";") if item]) for value in frame["failure_reasons"]]
        return sum(counts) / len(counts) if counts else 0.0
    return _hard_fail_rate(frame)


def _evidence_boundary_preserved(frame: pd.DataFrame) -> bool:
    if frame.empty:
        return True
    data_ok = "data_source" not in frame or set(frame["data_source"].dropna().astype(str)) <= {"real_simulation_csv"}
    validity_ok = "engineering_validity" not in frame or set(frame["engineering_validity"].dropna().astype(str)) <= {"simulation_only"}
    return bool(data_ok and validity_ok)


def _col_max(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.max()) if not values.empty else None


def _col_mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame is None or frame.empty or column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return round(float(values.mean()), 12) if not values.empty else None


def _safe_div(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return float(numerator) / float(denominator)


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "passed"}:
        return True
    if text in {"false", "0", "no", "failed"}:
        return False
    return None
