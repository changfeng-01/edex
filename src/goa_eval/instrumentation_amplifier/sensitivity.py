from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from goa_eval.transfer import SensitivityArtifact


def estimate_central_log_sensitivity(
    response: Callable[[dict[str, float]], Mapping[str, Any]],
    operating_point: Mapping[str, Any],
    *,
    effect_names: Sequence[str],
    relative_step: float = 1.0e-3,
    profile: str,
    scenario_key: str,
    physics_version: str = "instrumentation_amplifier_three_opamp_v1",
    task_head_version: str = "instrumentation_amplifier_task_v1",
) -> SensitivityArtifact:
    step = float(relative_step)
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("relative_step must be finite and positive")
    jacobian = {name: {} for name in effect_names}
    usable_parameters = {
        str(name): float(value)
        for name, value in operating_point.items()
        if _positive(value)
    }
    for parameter, value in usable_parameters.items():
        plus = dict(usable_parameters)
        minus = dict(usable_parameters)
        plus[parameter] = value * math.exp(step)
        minus[parameter] = value * math.exp(-step)
        positive = response(plus)
        negative = response(minus)
        for effect in effect_names:
            high = _finite(positive.get(effect))
            low = _finite(negative.get(effect))
            if high is not None and low is not None:
                jacobian[effect][parameter] = (high - low) / (2.0 * step)
    return SensitivityArtifact(
        profile=profile,
        physics_version=physics_version,
        task_head_version=task_head_version,
        scenario_jacobians={scenario_key: jacobian},
        normalized_uncertainty={name: 0.25 for name in effect_names},
        evidence_status="analytic_model_proxy",
        corner_set=(scenario_key,),
    )


def estimate_csv_sensitivity(
    frame: pd.DataFrame,
    *,
    effect_names: Sequence[str],
    profile: str = "instrumentation_amplifier_three_opamp_compensated_v1",
) -> SensitivityArtifact:
    required = {"baseline_id", "scenario_key", "parameter", "perturbation_sign", "log_step"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("sensitivity CSV missing columns: " + ", ".join(missing))
    jacobians: dict[str, dict[str, dict[str, float]]] = {}
    for (baseline, scenario, parameter), group in frame.groupby(
        ["baseline_id", "scenario_key", "parameter"], dropna=False
    ):
        signs = {int(value) for value in group["perturbation_sign"]}
        if not {-1, 1} <= signs:
            raise ValueError(
                f"CSV sensitivity requires positive and negative perturbations for "
                f"{baseline}/{scenario}/{parameter}"
            )
        negative = group[group["perturbation_sign"].astype(int) == -1].iloc[0]
        positive = group[group["perturbation_sign"].astype(int) == 1].iloc[0]
        high_step = abs(float(positive["log_step"]))
        low_step = abs(float(negative["log_step"]))
        if not math.isclose(high_step, low_step, rel_tol=1.0e-9, abs_tol=1.0e-12):
            raise ValueError("CSV sensitivity perturbation pair must use the same log_step")
        if high_step <= 0.0:
            raise ValueError("CSV sensitivity log_step must be positive")
        scenario_rows = jacobians.setdefault(str(scenario), {})
        for effect in effect_names:
            if effect not in frame.columns:
                continue
            high = _finite(positive[effect])
            low = _finite(negative[effect])
            if high is not None and low is not None:
                scenario_rows.setdefault(str(effect), {})[str(parameter)] = (
                    high - low
                ) / (2.0 * high_step)
    baseline_ids = {str(value) for value in frame["baseline_id"]}
    if len(baseline_ids) != 1:
        raise ValueError("CSV sensitivity artifact must contain exactly one baseline_id")
    return SensitivityArtifact(
        profile=profile,
        physics_version="instrumentation_amplifier_three_opamp_v1",
        task_head_version="instrumentation_amplifier_task_v1",
        scenario_jacobians=jacobians,
        normalized_uncertainty={name: 0.0 for name in effect_names},
        evidence_status="observed",
        baseline_id=next(iter(baseline_ids)),
        corner_set=tuple(sorted(jacobians)),
    )


def merge_sensitivity_artifacts(
    analytic: SensitivityArtifact, observed: SensitivityArtifact | None
) -> SensitivityArtifact:
    if observed is None:
        return analytic
    merged = {
        scenario: {
            effect: dict(parameters)
            for effect, parameters in effects.items()
        }
        for scenario, effects in analytic.scenario_jacobians.items()
    }
    for scenario, effects in observed.scenario_jacobians.items():
        for effect, parameters in effects.items():
            merged.setdefault(scenario, {}).setdefault(effect, {}).update(parameters)
    uncertainty = dict(analytic.normalized_uncertainty)
    uncertainty.update(observed.normalized_uncertainty)
    return SensitivityArtifact(
        profile=analytic.profile,
        physics_version=analytic.physics_version,
        task_head_version=analytic.task_head_version,
        scenario_jacobians=merged,
        normalized_uncertainty=uncertainty,
        evidence_status="observed_over_analytic",
        baseline_id=observed.baseline_id,
        corner_set=tuple(sorted(merged)),
    )


def _positive(value: object) -> bool:
    parsed = _finite(value)
    return parsed is not None and parsed > 0.0


def _finite(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
