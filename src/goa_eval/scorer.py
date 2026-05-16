from __future__ import annotations

import math

from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


def score_real_evaluation(summary: dict, stage_rows: list[dict], spec: dict) -> dict:
    hard_constraints = evaluate_hard_constraints(summary, spec)
    failures = [item["reason"] for item in hard_constraints.values() if not item["passed"]]
    warnings = warning_reasons(summary, spec)
    function_score = 100.0 if not failures else max(0.0, 100.0 - 20.0 * len(failures))
    quality_score = _quality_score(summary, spec)
    stability_score = min(
        _inverse_limit_score(summary.get("Max_ripple"), spec.get("max_ripple_v")),
        _inverse_limit_score(summary.get("Max_voltage_loss"), spec.get("max_voltage_loss_v")),
    )
    consistency_score = min(
        _inverse_limit_score(summary.get("Delay_std"), spec.get("max_delay_std")),
        _inverse_limit_score(summary.get("Width_std"), spec.get("pulse_width_tolerance")),
    )
    cost_score = 100.0
    weights = spec.get("weights", {})
    weighted = {
        "function_score": function_score,
        "quality_score": quality_score,
        "stability_score": stability_score,
        "consistency_score": consistency_score,
        "cost_score": cost_score,
    }
    soft_scores = {
        key: {
            "score": _clamp(value),
            "deduction": _clamp(100.0 - value),
            "weight": float(weights.get(key, 0.0)),
        }
        for key, value in weighted.items()
    }
    weight_sum = sum(float(weights.get(key, 0.0)) for key in weighted) or 1.0
    overall = sum(weighted[key] * float(weights.get(key, 0.0)) for key in weighted) / weight_sum
    return {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "hard_constraint_passed": not failures,
        "hard_constraint_failures": failures,
        "hard_constraints": hard_constraints,
        "failure_reasons": failures,
        "warning_reasons": warnings,
        "soft_scores": soft_scores,
        "score_explanations": soft_scores,
        **{key: _clamp(value) for key, value in weighted.items()},
        "overall_score": _clamp(overall),
    }


def hard_constraint_failures(summary: dict, spec: dict) -> list[str]:
    return [item["reason"] for item in evaluate_hard_constraints(summary, spec).values() if not item["passed"]]


def evaluate_hard_constraints(summary: dict, spec: dict) -> dict[str, dict]:
    constraints = {
        "All_pulses_exist": _check_bool(summary.get("All_pulses_exist", False), True, "All_pulses_exist is false"),
        "Seq_pass": _check_bool(summary.get("Seq_pass", False), True, "Seq_pass is false"),
        "FalseTriggerCount": _check_limit(
            summary.get("FalseTriggerCount", summary.get("False_trigger_count", 0)),
            0,
            "FalseTriggerCount is greater than 0",
            greater_is_fail=True,
        ),
        "Max_overlap_ratio": _check_limit(
            summary.get("Max_overlap_ratio"),
            spec.get("max_overlap_ratio"),
            "Max_overlap_ratio exceeds max_overlap_ratio",
            greater_is_fail=True,
        ),
        "Max_ripple": _check_limit(
            summary.get("Max_ripple"),
            spec.get("max_ripple_v"),
            "Max_ripple exceeds max_ripple_v",
            greater_is_fail=True,
        ),
        "Max_voltage_loss": _check_limit(
            summary.get("Max_voltage_loss"),
            spec.get("max_voltage_loss_v"),
            "Max_voltage_loss exceeds max_voltage_loss_v",
            greater_is_fail=True,
        ),
        "Delay_std": _check_limit(
            summary.get("Delay_std"),
            spec.get("max_delay_std"),
            "Delay_std exceeds max_delay_std",
            greater_is_fail=True,
        ),
    }
    voh_min = _finite(summary.get("VOH_min"))
    high_threshold = _finite(summary.get("high_threshold", spec.get("high_threshold")))
    min_margin = _finite(spec.get("min_voh_margin_v"))
    margin = voh_min - high_threshold if voh_min is not None and high_threshold is not None else None
    constraints["VOH_min_margin"] = {
        "passed": not (margin is not None and min_margin is not None and margin < min_margin),
        "current_value": margin,
        "threshold": min_margin,
        "reason": "VOH_min margin is below min_voh_margin_v",
    }
    return constraints


def warning_reasons(summary: dict, spec: dict) -> list[str]:
    warnings: list[str] = []
    if summary.get("LowFreqStable") == "not_evaluable_with_current_waveform":
        warnings.append("LowFreqStable is not evaluable with current waveform duration")
    if summary.get("DeviceCount") is None:
        warnings.append("DeviceCount is not available")
    return warnings


def _check_bool(value, expected: bool, reason: str) -> dict:
    passed = bool(value) is expected
    return {"passed": passed, "current_value": bool(value), "threshold": expected, "reason": reason}


def _check_limit(value, limit, reason: str, *, greater_is_fail: bool) -> dict:
    current = _finite(value)
    threshold = _finite(limit)
    if current is None or threshold is None:
        passed = True
    elif greater_is_fail:
        passed = current <= threshold
    else:
        passed = current >= threshold
    return {"passed": passed, "current_value": current, "threshold": threshold, "reason": reason}


def _quality_score(summary: dict, spec: dict) -> float:
    voh_min = _finite(summary.get("VOH_min"))
    high_threshold = _finite(summary.get("high_threshold", spec.get("high_threshold")))
    min_margin = _finite(spec.get("min_voh_margin_v"))
    if voh_min is None or high_threshold is None or min_margin in (None, 0):
        voh_score = 100.0
    else:
        voh_score = _clamp(100.0 * (voh_min - high_threshold) / min_margin)
    width_score = _target_score(summary.get("Width_mean"), spec.get("target_pulse_width"), spec.get("pulse_width_tolerance"))
    overlap_score = _inverse_limit_score(summary.get("Max_overlap_ratio"), spec.get("max_overlap_ratio"))
    return min(voh_score, width_score, overlap_score)


def _target_score(value, target, tolerance) -> float:
    value = _finite(value)
    target = _finite(target)
    tolerance = _finite(tolerance)
    if value is None or target is None or tolerance in (None, 0):
        return 100.0
    return _clamp(100.0 * (1.0 - abs(value - target) / tolerance))


def _inverse_limit_score(value, limit) -> float:
    value = _finite(value)
    limit = _finite(limit)
    if value is None or limit in (None, 0):
        return 100.0
    return _clamp(100.0 * (1.0 - value / limit))


def _gt(value, limit) -> bool:
    value = _finite(value)
    limit = _finite(limit)
    return value is not None and limit is not None and value > limit


def _finite(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _clamp(value: float) -> float:
    return float(max(0.0, min(100.0, value)))
