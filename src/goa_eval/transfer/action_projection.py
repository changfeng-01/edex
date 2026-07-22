from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from goa_eval.domain.parameter_profiles import (
    CircuitParameterProfile,
    ParameterUpdate,
    project_parameter_value,
)


@dataclass(frozen=True)
class ActionProjection:
    status: str
    accepted: bool
    updates: tuple[ParameterUpdate, ...]
    alignment: float
    residual_norm: float
    relative_residual: float
    active_parameters: tuple[str, ...]
    target_features: tuple[str, ...]
    matrix_rank: int = 0
    required_rank: int = 0
    condition_number: float = float("inf")
    normalized_uncertainty: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "accepted": self.accepted,
            "alignment": self.alignment,
            "residual_norm": self.residual_norm,
            "relative_residual": self.relative_residual,
            "active_parameters": list(self.active_parameters),
            "target_features": list(self.target_features),
            "matrix_rank": self.matrix_rank,
            "required_rank": self.required_rank,
            "condition_number": self.condition_number,
            "normalized_uncertainty": self.normalized_uncertainty,
            "updates": [
                {
                    "column": update.column,
                    "value": update.value,
                    "unclipped_value": update.unclipped_value,
                    "clipped": update.clipped,
                    "canonical_key": update.canonical_key,
                }
                for update in self.updates
            ],
        }


def project_physical_effect(
    target_effect: Mapping[str, float],
    target_jacobian: Mapping[str, Mapping[str, float]],
    profile: CircuitParameterProfile,
    row: Mapping[str, Any],
    *,
    feature_weights: Mapping[str, float] | None = None,
    regularization: float = 1.0e-3,
    minimum_alignment: float = 0.5,
    max_log_step: float = 0.5,
    maximum_relative_residual: float = 0.5,
    reject_rank_deficient: bool = False,
    maximum_condition_number: float = 1.0e6,
    normalized_uncertainty: float = 0.0,
    maximum_normalized_uncertainty: float = 0.5,
) -> ActionProjection:
    parameters = [
        parameter
        for parameter in profile.optimizable_parameters
        if parameter.column in row
        and _finite(row.get(parameter.column))
        and float(row[parameter.column]) > 0.0
        and any(parameter.column in derivatives for derivatives in target_jacobian.values())
    ]
    features = [
        feature
        for feature, value in target_effect.items()
        if feature in target_jacobian and _finite(value)
    ]
    if not features or not parameters:
        return ActionProjection(
            "unsupported_effect", False, (), 0.0, float("inf"), float("inf"), (), tuple(features)
        )
    matrix = np.asarray(
        [
            [float(target_jacobian[feature].get(parameter.column, 0.0)) for parameter in parameters]
            for feature in features
        ],
        dtype=float,
    )
    target = np.asarray([float(target_effect[feature]) for feature in features], dtype=float)
    weights = np.asarray(
        [max(float((feature_weights or {}).get(feature, 1.0)), 0.0) for feature in features],
        dtype=float,
    )
    if not np.any(weights > 0.0) or not np.any(np.abs(matrix) > 0.0):
        return ActionProjection(
            "unsupported_effect", False, (), 0.0, float("inf"), float("inf"), (), tuple(features)
        )
    matrix_rank = int(np.linalg.matrix_rank(matrix))
    # Transfer actions must be locally identifiable in the parameter space.  A
    # one-effect/two-parameter system can fit the effect but cannot determine a
    # unique circuit action, so the robust coordinator treats it as rank poor.
    required_rank = matrix.shape[1]
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    condition_number = (
        float(singular_values[0] / singular_values[-1])
        if singular_values.size and singular_values[-1] > 0.0
        else float("inf")
    )
    gate_status = ""
    if reject_rank_deficient and matrix_rank < required_rank:
        gate_status = "rank_deficient"
    elif reject_rank_deficient and condition_number > maximum_condition_number:
        gate_status = "ill_conditioned"
    elif normalized_uncertainty > maximum_normalized_uncertainty:
        gate_status = "high_uncertainty"
    if gate_status:
        return ActionProjection(
            status=gate_status,
            accepted=False,
            updates=(),
            alignment=0.0,
            residual_norm=float("inf"),
            relative_residual=float("inf"),
            active_parameters=tuple(parameter.column for parameter in parameters),
            target_features=tuple(features),
            matrix_rank=matrix_rank,
            required_rank=required_rank,
            condition_number=condition_number,
            normalized_uncertainty=float(normalized_uncertainty),
        )
    root_weights = np.sqrt(weights)
    weighted_matrix = root_weights[:, None] * matrix
    weighted_target = root_weights * target
    ridge = max(float(regularization), 0.0)
    if ridge > 0.0:
        design_matrix = np.vstack(
            [weighted_matrix, math.sqrt(ridge) * np.eye(len(parameters))]
        )
        design_target = np.concatenate([weighted_target, np.zeros(len(parameters))])
    else:
        design_matrix = weighted_matrix
        design_target = weighted_target
    log_delta = np.linalg.lstsq(design_matrix, design_target, rcond=None)[0]
    log_delta = np.clip(log_delta, -abs(max_log_step), abs(max_log_step))

    updates: list[ParameterUpdate] = []
    applied_delta: list[float] = []
    for parameter, delta in zip(parameters, log_delta):
        current = float(row[parameter.column])
        proposed = current * math.exp(float(delta))
        value = project_parameter_value(parameter, proposed)
        applied_delta.append(math.log(value / current))
        updates.append(
            ParameterUpdate(
                column=parameter.column,
                value=value,
                unclipped_value=proposed,
                clipped=not math.isclose(value, proposed, rel_tol=1.0e-12, abs_tol=1.0e-12),
                canonical_key=parameter.canonical_key,
            )
        )
    realized = matrix @ np.asarray(applied_delta, dtype=float)
    weighted_realized = root_weights * realized
    denominator = float(np.linalg.norm(weighted_target) * np.linalg.norm(weighted_realized))
    alignment = float(np.dot(weighted_target, weighted_realized) / denominator) if denominator > 0.0 else 0.0
    residual = float(np.linalg.norm(root_weights * (realized - target)))
    target_norm = float(np.linalg.norm(weighted_target))
    relative_residual = residual / max(target_norm, 1.0e-12)
    direction_ok = bool(np.isfinite(alignment) and alignment >= float(minimum_alignment))
    magnitude_ok = bool(
        np.isfinite(relative_residual)
        and relative_residual <= max(float(maximum_relative_residual), 0.0)
    )
    accepted = direction_ok and magnitude_ok
    if accepted:
        status = "ok"
    elif not direction_ok:
        status = "response_mismatch"
    else:
        status = "effect_magnitude_mismatch"
    return ActionProjection(
        status=status,
        accepted=accepted,
        updates=tuple(updates),
        alignment=alignment,
        residual_norm=residual,
        relative_residual=relative_residual,
        active_parameters=tuple(parameter.column for parameter in parameters),
        target_features=tuple(features),
        matrix_rank=matrix_rank,
        required_rank=required_rank,
        condition_number=condition_number,
        normalized_uncertainty=float(normalized_uncertainty),
    )


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
