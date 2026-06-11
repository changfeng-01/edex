from __future__ import annotations

from typing import Any

import numpy as np

from goa_eval.pia_ca_llso.schema import SimulationRecord


def compute_constraint_violation(record: SimulationRecord, problem_spec: Any) -> float:
    if record.constraint_violation is not None:
        return float(record.constraint_violation)
    return 0.0 if record.hard_pass else 1.0


def compute_soft_score(record: SimulationRecord, problem_spec: Any) -> float:
    if record.score is not None:
        score = float(record.score)
    else:
        score = float(record.metrics.get("overall_score", record.metrics.get("score", 0.0)))
    return score / 100.0 if score > 1.0 else score


def is_external_evaluable(record: SimulationRecord) -> bool:
    return record.status != "predicted_only"


def compute_real_score(record: SimulationRecord, problem_spec: Any) -> float | None:
    if not is_external_evaluable(record):
        return None
    if record.status == "not_evaluable":
        return 0.0
    if record.status == "sim_failed":
        return 5.0
    if record.hard_pass:
        return float(100.0 * compute_soft_score(record, problem_spec))
    violation = float(np.clip(compute_constraint_violation(record, problem_spec), 0.0, 1.0))
    return float(20.0 - 20.0 * violation)
