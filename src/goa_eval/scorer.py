from __future__ import annotations

import math

from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION
from goa_eval.topology_profiles import load_eval_profiles, resolve_topology_profile


def score_real_evaluation(
    summary: dict,
    stage_rows: list[dict],
    spec: dict,
    *,
    topology: str | None = None,
    analysis_metrics: dict | None = None,
    profiles: dict | None = None,
) -> dict:
    hard_constraints = evaluate_hard_constraints(summary, spec)
    failures = [item["reason"] for item in hard_constraints.values() if not item["passed"]]
    warnings = warning_reasons(summary, spec)
    metric_penalties = evaluate_metric_penalties(summary, spec)
    function_score = _function_score(failures, summary)
    quality_score = _quality_score(metric_penalties)
    stability_score = min(
        metric_penalties["Max_ripple"]["score"],
        metric_penalties["Max_voltage_loss"]["score"],
    )
    consistency_score = min(
        metric_penalties["Delay_std"]["score"],
        metric_penalties["Width_std"]["score"],
    )
    profile = resolve_topology_profile(topology, profiles or load_eval_profiles())
    profile_scores, analysis_penalties, not_evaluable = evaluate_profile_metrics(analysis_metrics or {}, profile)
    cost_score = _cost_score(profile_scores, not_evaluable, profile)
    profile_score = _mean([item["score"] for item in profile_scores.values()])
    objective_score, objective_details = _profile_objective_score(profile_scores, profile)
    hard_gate = "passed" if not failures else "failed"
    if failures:
        objective_score = 0.0
    objective_breakdown = {
        "profile_metric_score": profile_score,
        "profile_objective_score": objective_score,
        "objective_method": objective_details["method"],
        "metric_objective_scores": objective_details["metric_scores"],
        "objective_weight_sum": objective_details["weight_sum"],
        "hard_constraint_gate": hard_gate,
        "missing_required_metric_penalty": float(len(_not_evaluable_required_metrics(profile, not_evaluable))),
        "risk_penalty": 0.0,
    }
    weights = {**spec.get("weights", {}), **profile.get("weights", {})}
    weighted = {
        "function_score": function_score,
        "quality_score": quality_score,
        "stability_score": stability_score,
        "consistency_score": consistency_score,
        "cost_score": cost_score,
    }
    if profile.get("name") != "default" or profile_scores:
        weighted["profile_score"] = profile_score
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
        "analysis_metric_penalties": analysis_penalties,
        "profile_metric_scores": profile_scores,
        "not_evaluable_metrics": not_evaluable,
        "not_evaluable_required_metrics": _not_evaluable_required_metrics(profile, not_evaluable),
        "metric_provenance": _score_metric_provenance(analysis_metrics or {}, profile_scores),
        "topology_profile": profile.get("name", "default"),
        "circuit_profile": profile.get("name", "default"),
        "profile_source": profile.get("profile_source"),
        "objective_score": _clamp(objective_score),
        "objective_breakdown": objective_breakdown,
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


def _function_score(failures: list[str], summary: dict) -> float:
    if not failures:
        return 100.0
    base_score = max(0.0, 100.0 - 20.0 * len(failures))
    activity = _finite(summary.get("WaveformActivityScore"))
    if any("All_pulses_exist" in failure or "Seq_pass" in failure for failure in failures) and activity is not None:
        return min(base_score, max(0.0, activity))
    return base_score


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


def evaluate_profile_metrics(analysis_metrics: dict, profile: dict) -> tuple[dict[str, dict], dict[str, dict], dict[str, str]]:
    scores: dict[str, dict] = {}
    penalties: dict[str, dict] = {}
    not_evaluable = dict(analysis_metrics.get("not_evaluable", {}) or {})
    for metric, rule in (profile.get("metrics", {}) or {}).items():
        source = str(rule.get("source", ""))
        value = (analysis_metrics.get(source) or {}).get(metric) if source else None
        if value is None:
            not_evaluable[metric] = f"missing {source}.{metric}" if source else f"missing {metric}"
            continue
        if "minimum" in rule:
            penalty = _lower_limit_penalty(metric, value, rule.get("minimum"), f"{metric} is below profile minimum")
        elif "maximum" in rule:
            penalty = _upper_limit_penalty(metric, value, rule.get("maximum"), f"{metric} exceeds profile maximum")
        elif "target" in rule:
            penalty = _target_penalty(metric, value, rule.get("target"), rule.get("tolerance"), f"{metric} deviates from profile target")
        else:
            penalty = _penalty(metric, _finite(value), None, "observed", 100.0, "pass", f"{metric} observed")
        scores[metric] = {
            "score": penalty["score"],
            "current_value": penalty["current_value"],
            "threshold": penalty["threshold"],
            "source": source,
        }
        penalties[metric] = penalty
    return scores, penalties, not_evaluable


def _profile_objective_score(profile_scores: dict[str, dict], profile: dict) -> tuple[float, dict]:
    objective = profile.get("objective", {}) or {}
    weights = (objective.get("weights", {}) or {}) if isinstance(objective, dict) else {}
    if not profile_scores:
        return 100.0, {"method": "none", "metric_scores": {}, "weight_sum": 0.0}
    if not weights:
        score = _mean([item["score"] for item in profile_scores.values()])
        return score, {
            "method": "unweighted_mean",
            "metric_scores": {metric: item["score"] for metric, item in profile_scores.items()},
            "weight_sum": float(len(profile_scores)),
        }
    weighted = 0.0
    weight_sum = 0.0
    metric_scores = {}
    for metric, item in profile_scores.items():
        score = float(item.get("score", 100.0))
        weight = float(weights.get(metric, 0.0))
        metric_scores[metric] = {"score": score, "weight": weight}
        if weight <= 0:
            continue
        weighted += score * weight
        weight_sum += weight
    if weight_sum <= 0:
        score = _mean([item["score"] for item in profile_scores.values()])
        return score, {"method": "unweighted_mean", "metric_scores": metric_scores, "weight_sum": 0.0}
    return weighted / weight_sum, {"method": "weighted_sum", "metric_scores": metric_scores, "weight_sum": weight_sum}


def _score_metric_provenance(analysis_metrics: dict, profile_scores: dict[str, dict]) -> dict[str, dict]:
    source = analysis_metrics.get("metric_provenance", {}) if isinstance(analysis_metrics, dict) else {}
    provenance = {}
    for metric, score in profile_scores.items():
        source_key = f"{score.get('source')}.{metric}" if score.get("source") else metric
        provenance[metric] = source.get(
            source_key,
            {
                "unit": "",
                "source_file": "",
                "source_analysis": score.get("source", ""),
                "source_column": metric,
                "parser": "score_real_evaluation",
                "normalization": "profile_metric_score",
                "not_evaluable_reason": "",
            },
        )
    return provenance


def _not_evaluable_required_metrics(profile: dict, not_evaluable: dict[str, str]) -> list[str]:
    required = {str(item) for item in profile.get("required_analyses", []) or []}
    if not required:
        return []
    missing = set()
    for key in not_evaluable:
        lowered = str(key).lower()
        for analysis in required:
            if lowered == f"{analysis}_metrics" or lowered.startswith(f"missing {analysis}_metrics"):
                missing.add(key)
    for metric, rule in (profile.get("metrics", {}) or {}).items():
        if str(rule.get("source_analysis", "")).lower() in required and metric in not_evaluable:
            missing.add(metric)
    return sorted(missing)


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


def _cost_score(profile_scores: dict[str, dict], not_evaluable: dict[str, str], profile: dict) -> float:
    cost_metrics = ["area_proxy", "width_proxy"]
    has_cost_scope = str(profile.get("name", "")).startswith("goa_") or any(metric in (profile.get("metrics", {}) or {}) for metric in cost_metrics)
    if not has_cost_scope:
        return 100.0
    available = [float(profile_scores[metric]["score"]) for metric in cost_metrics if metric in profile_scores]
    if available:
        return _mean(available)
    if any(metric in not_evaluable for metric in cost_metrics):
        return 0.0
    return 100.0


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
    elif value <= limit:
        ratio = value / limit
        score = 100.0
        severity = "pass"
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


def _lower_limit_penalty(metric: str, value, minimum, reason: str) -> dict:
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
        severity = "fail"
    return _penalty(metric, value, minimum, "lower_limit", score, severity, reason, ratio=ratio)


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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 100.0
