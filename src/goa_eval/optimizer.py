from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class OptimizationRequest:
    parameter_space: dict[str, Any]
    objective: str = "overall_score"
    constraints: dict[str, Any] | None = None


@dataclass(frozen=True)
class OptimizationResult:
    status: str
    best_parameters: dict[str, Any] | None
    message: str


class CircuitPilotOptimizer:
    """Placeholder interface for future optimization algorithms."""

    def optimize(self, request: OptimizationRequest) -> OptimizationResult:
        raise NotImplementedError("CircuitPilot optimizer is not implemented in this prototype.")


def load_param_space(path: Path) -> dict[str, list[object]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parameters = raw.get("parameters", raw)
    return {key: list(value) if isinstance(value, list) else [value] for key, value in parameters.items()}


def propose_candidates(param_space: dict[str, list[object]], recommendations: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for recommendation in recommendations:
        rec_id = str(recommendation.get("recommendation_id", ""))
        metric = str(recommendation.get("trigger_metric", ""))
        if "ripple" in rec_id or metric == "Max_ripple":
            _append_if_available(candidates, param_space, "C_store", "increase", 90, recommendation)
            _append_if_available(candidates, param_space, "load_cap", "review", 60, recommendation)
        if "delay" in rec_id or metric == "Delay_mean":
            _append_if_available(candidates, param_space, "R_driver", "decrease", 80, recommendation)
            _append_if_available(candidates, param_space, "W_nmos", "increase", 70, recommendation)
            _append_if_available(candidates, param_space, "W_pmos", "increase", 70, recommendation)
        if "overlap" in rec_id or metric == "Max_overlap_ratio":
            _append_if_available(candidates, param_space, "R_driver", "review_timing", 85, recommendation)
        if "false_trigger" in rec_id or metric == "FalseTriggerCount":
            _append_if_available(candidates, param_space, "VDD", "review_threshold", 75, recommendation)
    return candidates


def rank_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=lambda item: (-float(item.get("priority", 0)), str(item.get("parameter", ""))))


def _append_if_available(candidates: list[dict], param_space: dict[str, list[object]], parameter: str, direction: str, priority: int, recommendation: dict) -> None:
    if parameter not in param_space:
        return
    candidates.append(
        {
            "parameter": parameter,
            "direction": direction,
            "candidate_values": param_space.get(parameter, []),
            "priority": priority,
            "source_recommendation": recommendation.get("recommendation_id"),
            "trigger_metric": recommendation.get("trigger_metric"),
        }
    )
