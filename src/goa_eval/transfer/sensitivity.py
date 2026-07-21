from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from goa_eval.domain.task_heads import CircuitTaskHead, evaluate_task_head


def estimate_local_elasticities(
    response: Callable[[dict[str, float]], float],
    point: Mapping[str, float],
    *,
    relative_step: float = 1.0e-3,
) -> dict[str, float]:
    """Estimate d(log y)/d(log x) with a symmetric multiplicative step."""

    step = max(float(relative_step), 1.0e-8)
    output: dict[str, float] = {}
    for name, value in point.items():
        if value <= 0.0:
            output[name] = float("nan")
            continue
        plus = dict(point)
        minus = dict(point)
        plus[name] = value * math.exp(step)
        minus[name] = value * math.exp(-step)
        upper = float(response(plus))
        lower = float(response(minus))
        if upper <= 0.0 or lower <= 0.0:
            output[name] = float("nan")
        else:
            output[name] = (math.log(upper) - math.log(lower)) / (2.0 * step)
    return output


def estimate_local_sensitivity_matrix(
    response: Callable[[dict[str, float]], Mapping[str, float]],
    point: Mapping[str, float],
    *,
    relative_step: float = 1.0e-3,
    response_scales: Mapping[str, float] | None = None,
) -> dict[str, dict[str, float]]:
    """Estimate a task-agnostic local response matrix in transformed coordinates."""

    step = max(float(relative_step), 1.0e-8)
    base_response = dict(response(dict(point)))
    output: dict[str, dict[str, float]] = {str(metric): {} for metric in base_response}
    for parameter, raw_value in point.items():
        value = float(raw_value)
        plus = dict(point)
        minus = dict(point)
        if value > 0.0:
            plus[parameter] = value * math.exp(step)
            minus[parameter] = value * math.exp(-step)
            denominator = 2.0 * step
        else:
            parameter_scale = max(abs(value), 1.0)
            plus[parameter] = value + step * parameter_scale
            minus[parameter] = value - step * parameter_scale
            denominator = math.asinh(plus[parameter] / parameter_scale) - math.asinh(
                minus[parameter] / parameter_scale
            )
        upper = dict(response(plus))
        lower = dict(response(minus))
        for metric in sorted(set(base_response) | set(upper) | set(lower)):
            high = _optional_float(upper.get(metric))
            low = _optional_float(lower.get(metric))
            if high is None or low is None or denominator == 0.0:
                output.setdefault(str(metric), {})[str(parameter)] = float("nan")
                continue
            if high > 0.0 and low > 0.0:
                numerator = math.log(high) - math.log(low)
            else:
                base = _optional_float(base_response.get(metric)) or 0.0
                scale = max(float((response_scales or {}).get(metric, abs(base) or 1.0)), 1.0e-12)
                numerator = math.asinh(high / scale) - math.asinh(low / scale)
            output.setdefault(str(metric), {})[str(parameter)] = numerator / denominator
    return output


def compute_task_parameter_importance(
    sensitivity_matrix: Mapping[str, Mapping[str, float]],
    task: CircuitTaskHead,
    metric_values: Mapping[str, Any],
) -> dict[str, float]:
    """Aggregate local sensitivities using circuit-specific metric weights and risk."""

    evaluation = evaluate_task_head(metric_values, task)
    parameters = sorted(
        {
            str(parameter)
            for derivatives in sensitivity_matrix.values()
            for parameter in derivatives
        }
    )
    raw = {parameter: 0.0 for parameter in parameters}
    for metric in task.metrics:
        result = evaluation.metric_results.get(metric.name)
        risk_multiplier = 1.0 + (result.violation if result is not None else 0.0)
        derivatives = sensitivity_matrix.get(metric.feature, {})
        for parameter in parameters:
            derivative = _optional_float(derivatives.get(parameter))
            if derivative is not None and math.isfinite(derivative):
                raw[parameter] += metric.weight * risk_multiplier * abs(derivative)
    total = sum(raw.values())
    return {parameter: value / total for parameter, value in raw.items()} if total > 0.0 else raw


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
