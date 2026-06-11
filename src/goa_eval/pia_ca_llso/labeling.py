from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

import pandas as pd

VALID_STATUSES = {"evaluated_feasible", "evaluated_soft_fail", "sim_failed", "not_evaluable", "predicted_only"}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "passed"}
    return bool(value)


def infer_record_status(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("status", "")).strip()
    if explicit in VALID_STATUSES:
        return explicit
    if _truthy(row.get("predicted_only", False)):
        return "predicted_only"
    if "sim_success" in row and not _truthy(row.get("sim_success")):
        return "sim_failed"
    if "simulation_status" in row and str(row.get("simulation_status")).lower() in {"failed", "sim_failed"}:
        return "sim_failed"
    if "hard_constraint_passed" in row or "hard_pass" in row:
        return "evaluated_feasible" if _truthy(row.get("hard_constraint_passed", row.get("hard_pass"))) else "evaluated_soft_fail"
    if row.get("overall_score") is None and row.get("score") is None:
        return "not_evaluable"
    return "evaluated_feasible"


def assign_level_labels(
    frame: pd.DataFrame,
    score_col: str = "overall_score",
    hard_pass_col: str = "hard_constraint_passed",
) -> pd.DataFrame:
    labeled = frame.copy()
    if "status" not in labeled.columns:
        labeled["status"] = [infer_record_status(row) for row in labeled.to_dict("records")]
    else:
        labeled["status"] = [infer_record_status(row) for row in labeled.to_dict("records")]
    if hard_pass_col not in labeled.columns:
        labeled[hard_pass_col] = labeled["status"].eq("evaluated_feasible")
    if score_col not in labeled.columns:
        labeled[score_col] = 0.0

    hard_pass = labeled[hard_pass_col].map(_truthy)
    feasible = labeled[labeled["status"].eq("evaluated_feasible") & hard_pass].copy()
    labels = pd.Series("L4", index=labeled.index, dtype="object")
    reasons = pd.Series("not externally feasible", index=labeled.index, dtype="object")

    soft_fail_mask = labeled["status"].eq("evaluated_soft_fail") | (~hard_pass & labeled["status"].eq("evaluated_feasible"))
    labels.loc[soft_fail_mask] = "L3"
    reasons.loc[soft_fail_mask] = "hard constraints failed; retained for boundary learning"

    if not feasible.empty:
        scores = pd.to_numeric(feasible[score_col], errors="coerce").fillna(0.0)
        if len(feasible) <= 3:
            top_cut = scores.max()
            mid_cut = max(scores.median(), 0.75 * float(top_cut))
        else:
            top_cut = scores.quantile(0.80)
            mid_cut = scores.quantile(0.40)
        l1_indices = feasible.index[scores >= top_cut].tolist()
        if len(l1_indices) == len(feasible) and len(feasible) > 1:
            l1_indices = [int(scores.idxmax())]
        labels.loc[l1_indices] = "L1"
        reasons.loc[l1_indices] = "top feasible score band"
        l2_indices = feasible.index[(scores >= mid_cut) & (~feasible.index.isin(l1_indices))]
        labels.loc[l2_indices] = "L2"
        reasons.loc[l2_indices] = "feasible middle score band"
        l3_indices = feasible.index[(scores < mid_cut) & (~feasible.index.isin(l1_indices))]
        labels.loc[l3_indices] = "L3"
        reasons.loc[l3_indices] = "feasible but weak soft score"

    terminal = labeled["status"].isin(["sim_failed", "not_evaluable", "predicted_only"])
    labels.loc[terminal] = "L4"
    reasons.loc[labeled["status"].eq("sim_failed")] = "simulation failed"
    reasons.loc[labeled["status"].eq("not_evaluable")] = "not externally evaluable"
    reasons.loc[labeled["status"].eq("predicted_only")] = "predicted_only cannot enter external benchmark"

    labeled["level_label"] = labels
    labeled["label_reason"] = reasons
    return labeled


def summarize_label_distribution(frame: pd.DataFrame) -> dict[str, int]:
    counts = Counter(frame.get("level_label", pd.Series(dtype="object")).fillna("unlabeled"))
    return {label: int(counts.get(label, 0)) for label in ["L1", "L2", "L3", "L4", "unlabeled"]}
