from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TaskMetricSpec:
    name: str
    feature: str
    direction: str
    weight: float
    minimum: float | None = None
    maximum: float | None = None
    target: float | None = None
    scale: float = 1.0


@dataclass(frozen=True)
class CircuitTaskHead:
    name: str
    metrics: tuple[TaskMetricSpec, ...]
    missing_metric_policy: str = "not_evaluable"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CircuitTaskHead":
        raw_metrics = value.get("metrics", {})
        if not isinstance(raw_metrics, Mapping):
            raise ValueError("task head metrics must be a mapping")
        metrics: list[TaskMetricSpec] = []
        for name, raw in raw_metrics.items():
            if not isinstance(raw, Mapping):
                raise ValueError(f"task metric {name} must be a mapping")
            direction = str(raw.get("direction", "larger_better"))
            threshold = raw.get("minimum", raw.get("maximum", raw.get("target", 1.0)))
            fallback_scale = max(abs(float(threshold)), 1.0e-12) if threshold is not None else 1.0
            scale = max(float(raw.get("scale", fallback_scale)), 1.0e-12)
            metrics.append(
                TaskMetricSpec(
                    name=str(name),
                    feature=str(raw.get("feature", name)),
                    direction=direction,
                    weight=max(float(raw.get("weight", 1.0)), 0.0),
                    minimum=_optional_float(raw.get("minimum")),
                    maximum=_optional_float(raw.get("maximum")),
                    target=_optional_float(raw.get("target")),
                    scale=scale,
                )
            )
        return cls(
            name=str(value.get("name", "unknown")),
            metrics=tuple(metrics),
            missing_metric_policy=str(value.get("missing_metric_policy", "not_evaluable")),
        )

    @classmethod
    def from_circuit_profile(
        cls,
        profile: Mapping[str, Any],
        *,
        feature_map: Mapping[str, str] | None = None,
    ) -> "CircuitTaskHead":
        """Adapt the repository circuit-profile objective into a task head.

        Circuit profiles remain the source of metric direction, thresholds and
        objective weights. ``feature_map`` is only needed when a simulator or
        feature extractor uses a different column name for the same metric.
        """

        raw_metrics = profile.get("metrics", {})
        if not isinstance(raw_metrics, Mapping):
            raise ValueError("circuit profile metrics must be a mapping")
        objective = profile.get("objective", {})
        objective = objective if isinstance(objective, Mapping) else {}
        weights = objective.get("weights", {})
        weights = weights if isinstance(weights, Mapping) else {}
        scalarization = objective.get("scalarization", {})
        scalarization = scalarization if isinstance(scalarization, Mapping) else {}
        aliases = feature_map or {}

        metrics: dict[str, dict[str, Any]] = {}
        for name, rule in raw_metrics.items():
            if not isinstance(rule, Mapping):
                raise ValueError(f"circuit profile metric {name} must be a mapping")
            adapted = dict(rule)
            adapted["feature"] = str(aliases.get(str(name), name))
            adapted["weight"] = float(weights.get(name, 1.0))
            metrics[str(name)] = adapted
        return cls.from_mapping(
            {
                "name": profile.get("name", profile.get("type", "unknown")),
                "metrics": metrics,
                "missing_metric_policy": scalarization.get(
                    "missing_metric_policy", "not_evaluable"
                ),
            }
        )


@dataclass(frozen=True)
class TaskMetricEvaluation:
    value: float
    score: float
    normalized_margin: float
    violation: float
    satisfied: bool


@dataclass(frozen=True)
class TaskHeadEvaluation:
    status: str
    score: float | None
    metric_results: dict[str, TaskMetricEvaluation]
    missing_features: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "missing_features": list(self.missing_features),
            "metrics": {
                name: {
                    "value": result.value,
                    "score": result.score,
                    "normalized_margin": result.normalized_margin,
                    "violation": result.violation,
                    "satisfied": result.satisfied,
                }
                for name, result in self.metric_results.items()
            },
        }


def evaluate_task_head(features: Mapping[str, Any], task: CircuitTaskHead) -> TaskHeadEvaluation:
    results: dict[str, TaskMetricEvaluation] = {}
    missing: list[str] = []
    weighted_score = 0.0
    weight_total = 0.0
    for metric in task.metrics:
        value = _optional_float(features.get(metric.feature))
        if value is None or not math.isfinite(value):
            missing.append(metric.feature)
            continue
        margin, score = _metric_margin_and_score(value, metric)
        results[metric.name] = TaskMetricEvaluation(
            value=value,
            score=score,
            normalized_margin=margin,
            violation=max(-margin, 0.0),
            satisfied=margin >= 0.0,
        )
        weighted_score += metric.weight * score
        weight_total += metric.weight
    if missing and task.missing_metric_policy == "not_evaluable":
        return TaskHeadEvaluation("missing_required_metrics", None, results, tuple(missing))
    if weight_total <= 0.0:
        return TaskHeadEvaluation("unavailable", None, results, tuple(missing))
    status = "partial" if missing else "ok"
    return TaskHeadEvaluation(status, weighted_score / weight_total, results, tuple(missing))


def _metric_margin_and_score(value: float, metric: TaskMetricSpec) -> tuple[float, float]:
    if metric.direction in {"smaller_better", "minimize"}:
        reference = metric.maximum if metric.maximum is not None else metric.target
        margin = (float(reference) - value) / metric.scale if reference is not None else -value / metric.scale
        return margin, _sigmoid(margin)
    if metric.direction in {"target", "target_value"}:
        reference = metric.target if metric.target is not None else 0.0
        distance = abs(value - reference) / metric.scale
        return -distance, math.exp(-min(distance, 60.0))
    reference = metric.minimum if metric.minimum is not None else metric.target
    margin = (value - float(reference)) / metric.scale if reference is not None else value / metric.scale
    return margin, _sigmoid(margin)


def _sigmoid(value: float) -> float:
    bounded = min(max(value, -60.0), 60.0)
    return 1.0 / (1.0 + math.exp(-bounded))


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
