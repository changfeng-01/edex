from __future__ import annotations

import json
from typing import Any, Mapping

import pandas as pd


PRIORITY_FEATURES = [
    "vgh_vth_margin",
    "vgl_off_margin",
    "ron_pullup_cload_proxy",
    "ron_pulldown_cload_proxy",
    "clk_slew_proxy",
    "cboot_cload_ratio",
]


def attach_evaluation_schedule(
    selected: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    scheduler_config = dict((config or {}).get("evaluation_scheduler", {}))
    enabled = scheduler_config.get("enabled", True)
    output = selected.copy()
    if not enabled or output.empty:
        return output, {"enabled": bool(enabled), "scheduled_count": 0}
    full_frame_top_k = max(0, int(scheduler_config.get("full_frame_top_k", 1)))
    states = []
    windows = []
    evidence = []
    plans = []
    for index, row in output.reset_index(drop=True).iterrows():
        state, window, evidence_state = _schedule_row(row, index, full_frame_top_k)
        states.append(state)
        windows.append(window)
        evidence.append(evidence_state)
        plans.append(json.dumps(_constraint_plan(row), ensure_ascii=False, sort_keys=True))
    output["evaluation_state"] = states
    output["simulation_window"] = windows
    output["constraint_eval_plan_json"] = plans
    output["evidence_state"] = evidence
    output["must_resimulate"] = True
    output["data_source"] = output.get("data_source", "real_simulation_csv")
    output["engineering_validity"] = output.get("engineering_validity", "simulation_only")
    return output, {
        "enabled": True,
        "scheduled_count": int(len(output)),
        "full_frame_top_k": full_frame_top_k,
        "windows": {name: int((output["simulation_window"] == name).sum()) for name in ["short_window", "event_window", "full_frame"]},
    }


def _schedule_row(row: pd.Series, index: int, full_frame_top_k: int) -> tuple[str, str, str]:
    if str(row.get("status", "")) in {"evaluated_feasible", "rerun_confirmed", "decision_ready"}:
        return "decision_ready", "full_frame", "decision_ready"
    barrier = _number(row.get("capm_barrier_score"), 0.0)
    p_hard = _number(row.get("p_hard_pass"), 0.5)
    p_l1 = _number(row.get("p_l1"), 0.5)
    predicted_l1 = str(row.get("predicted_level", "")) == "L1" or p_l1 >= 0.7
    if index < full_frame_top_k and predicted_l1 and p_hard >= 0.6 and barrier <= 0.0:
        return "needs_full_frame", "full_frame", "needs_full_frame"
    if barrier > 0.0 or p_hard < 0.5:
        return "partial_constraint_evaluated", "short_window", "partial_constraint_evaluated"
    if str(row.get("predicted_level", "")) == "L1" or p_l1 >= 0.7:
        return "pending_simulation", "event_window", "pending_simulation"
    return "pending_simulation", "short_window", "pending_simulation"


def _constraint_plan(row: pd.Series) -> dict[str, Any]:
    constraints = []
    for feature in PRIORITY_FEATURES:
        value = _number(row.get(feature), None)
        if value is None:
            continue
        priority = "review"
        if feature.endswith("margin") and value < 0.2:
            priority = "high"
        if feature.startswith("ron_") and value > 2.0:
            priority = "high"
        if feature == "clk_slew_proxy" and value > 2.0:
            priority = "high"
        if feature == "cboot_cload_ratio" and value < 0.35:
            priority = "high"
        constraints.append({"feature": feature, "value": value, "priority": priority})
    constraints.sort(key=lambda item: 0 if item["priority"] == "high" else 1)
    if not constraints:
        constraints.append({"feature": "overall_candidate", "value": None, "priority": "review"})
    return {
        "constraints": constraints,
        "claim_boundary": "next-run simulation suggestions",
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }


def _number(value: Any, default: float | None) -> float | None:
    try:
        if value is None:
            return default
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(numeric):
        return default
    return numeric
