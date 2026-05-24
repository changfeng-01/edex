from __future__ import annotations

import math

from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


def score_real_evaluation(summary: dict, stage_rows: list[dict], spec: dict) -> dict:
    hard_constraints = evaluate_hard_constraints(summary, spec)
    failures = [item["reason"] for item in hard_constraints.values() if not item["passed"]]
    warnings = warning_reasons(summary, spec)
    metric_penalties = evaluate_metric_penalties(summary, spec)
    function_score = 100.0 if not failures else max(0.0, 100.0 - 20.0 * len(failures))
    quality_score = _quality_score(metric_penalties)
    stability_score = min(
        metric_penalties["Max_ripple"]["score"],
        metric_penalties["Max_voltage_loss"]["score"],
    )
    consistency_score = min(
        metric_penalties["Delay_std"]["score"],
        metric_penalties["Width_std"]["score"],
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
        "metric_penalties": metric_penalties,
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


def evaluate_metric_penalties(summary: dict, spec: dict) -> dict[str, dict]:
    voh_min = _finite(summary.get("VOH_min"))
    high_threshold = _finite(summary.get("high_threshold", spec.get("high_threshold")))
    margin = voh_min - high_threshold if voh_min is not None and high_threshold is not None else None
    return {
        "Max_overlap_ratio": _upper_limit_penalty(
            "Max_overlap_ratio",
            summary.get("Max_overlap_ratio"),
            spec.get("max_overlap_ratio"),
            "相邻级合法脉冲重叠比例越高，时序串扰风险越高。",
        ),
        "Max_ripple": _upper_limit_penalty(
            "Max_ripple",
            summary.get("Max_ripple"),
            spec.get("max_ripple_v"),
            "非选通窗口纹波越高，保持稳定性风险越高。",
        ),
        "Max_voltage_loss": _upper_limit_penalty(
            "Max_voltage_loss",
            summary.get("Max_voltage_loss"),
            spec.get("max_voltage_loss_v"),
            "保持窗口电压损失越高，高电平保持裕量越低。",
        ),
        "Delay_std": _upper_limit_penalty(
            "Delay_std",
            summary.get("Delay_std"),
            spec.get("max_delay_std"),
            "级间延迟离散度越高，长级联一致性风险越高。",
        ),
        "Width_std": _upper_limit_penalty(
            "Width_std",
            summary.get("Width_std"),
            spec.get("pulse_width_tolerance"),
            "脉宽离散度越高，扫描窗口一致性风险越高。",
        ),
        "Width_mean": _target_penalty(
            "Width_mean",
            summary.get("Width_mean"),
            spec.get("target_pulse_width"),
            spec.get("pulse_width_tolerance"),
            "平均脉宽偏离目标越多，有效选通窗口风险越高。",
        ),
        "VOH_min_margin": _lower_margin_penalty(
            "VOH_min_margin",
            margin,
            spec.get("min_voh_margin_v"),
            "最低高电平裕量越低，读出可靠性风险越高。",
        ),
        "FalseTriggerCount": _upper_limit_penalty(
            "FalseTriggerCount",
            summary.get("FalseTriggerCount", summary.get("False_trigger_count", 0)),
            0,
            "误触发数量必须为 0；非零误触发属于严重功能风险。",
        ),
    }


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


def _quality_score(metric_penalties: dict[str, dict]) -> float:
    return min(
        metric_penalties["VOH_min_margin"]["score"],
        metric_penalties["Width_mean"]["score"],
        metric_penalties["Max_overlap_ratio"]["score"],
    )


def _target_penalty(metric: str, value, target, tolerance, reason: str) -> dict:
    value = _finite(value)
    target = _finite(target)
    tolerance = _finite(tolerance)
    if value is None or target is None or tolerance in (None, 0):
        score = 100.0
        ratio = None
        severity = "unknown"
    else:
        ratio = abs(value - target) / tolerance
        score = _ratio_score(ratio)
        severity = _ratio_severity(ratio)
    return _penalty(metric, value, tolerance, "target", score, severity, reason, ratio=ratio, target=target)


def _upper_limit_penalty(metric: str, value, limit, reason: str) -> dict:
    value = _finite(value)
    limit = _finite(limit)
    if value is None or limit is None:
        score = 100.0
        ratio = None
        severity = "unknown"
    elif limit == 0:
        ratio = 0.0 if value <= 0 else None
        score = 100.0 if value <= 0 else 0.0
        severity = "pass" if value <= 0 else "critical"
    else:
        ratio = max(0.0, value) / limit
        score = _ratio_score(ratio)
        severity = _ratio_severity(ratio)
    return _penalty(metric, value, limit, "upper_limit", score, severity, reason, ratio=ratio)


def _lower_margin_penalty(metric: str, value, minimum, reason: str) -> dict:
    value = _finite(value)
    minimum = _finite(minimum)
    if value is None or minimum in (None, 0):
        score = 100.0
        ratio = None
        severity = "unknown"
    elif value >= minimum:
        ratio = value / minimum
        score = 100.0
        severity = "pass"
    else:
        ratio = value / minimum
        score = _clamp(100.0 * max(0.0, ratio))
        severity = "critical" if value < 0 else "fail"
    return _penalty(metric, value, minimum, "lower_margin", score, severity, reason, ratio=ratio)


def _ratio_score(ratio: float | None) -> float:
    if ratio is None:
        return 100.0
    if math.isinf(ratio):
        return 0.0
    return _clamp(100.0 / (1.0 + ratio * ratio))


def _ratio_severity(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio <= 1.0:
        return "pass"
    if ratio <= 2.0:
        return "fail"
    return "critical"


def _penalty(metric: str, current, threshold, limit_type: str, score: float, severity: str, reason: str, **extra) -> dict:
    return {
        "metric": metric,
        "current_value": current,
        "threshold": threshold,
        "limit_type": limit_type,
        "severity": severity,
        "score": _clamp(score),
        "deduction": _clamp(100.0 - score),
        "reason": reason,
        **extra,
    }


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
