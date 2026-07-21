"""LLSO (Level-based Learning Search Optimization) offspring generation.

This module implements the true LLSO algorithm where teachers come from
L1 (best) levels and learners come from L2/L3 (weaker) levels. This is
distinct from the simple elite-mutation generators in candidate_generator.py
which use basic mutation without level-based learning.

Generation formula:
    child = learner + r1 * (teacher - learner) + r2 * (elite - learner) + noise

where:
- teacher and elite are sampled from L1 (best) rows
- learner is sampled from L2/L3 (weaker) rows
- r1, r2 are uniform random factors
- noise is Gaussian with scale proportional to parameter range
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from goa_eval.circuit_profiles import load_circuit_profiles, resolve_circuit_profile
from goa_eval.domain.parameter_profiles import (
    CircuitParameterProfile,
    ParameterSpec,
    project_parameter_value,
)


def infer_parameter_bounds(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    parameter_columns: list[str],
) -> dict[str, tuple[float, float]]:
    """Infer safe parameter bounds from observed data.

    Returns a dict mapping parameter column name to (lower, upper) tuple.
    Bounds are expanded slightly beyond observed range for exploration.
    """
    bounds: dict[str, tuple[float, float]] = {}
    for col in parameter_columns:
        if col not in history.columns and col not in candidates.columns:
            continue
        all_values = []
        if col in history.columns:
            all_values.append(history[col].dropna())
        if col in candidates.columns:
            all_values.append(candidates[col].dropna())
        if not all_values:
            continue
        combined = pd.concat(all_values)
        if not np.isfinite(combined).all():
            continue
        data_min = combined.min()
        data_max = combined.max()
        data_range = data_max - data_min
        if data_range == 0:
            data_range = abs(data_min) * 0.1 if data_min != 0 else 1.0
        margin = data_range * 0.1
        bounds[col] = (float(data_min - margin), float(data_max + margin))
    return bounds


def generate_llso_offspring(
    history: pd.DataFrame,
    seed_candidates: pd.DataFrame,
    config: Mapping[str, Any],
    generation: int,
    offspring_count: int,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Generate LLSO offspring using level-based teacher-learner optimization.

    Generation formula:
        child = learner + r1*(teacher - learner) + r2*(elite - learner) + noise

    - teacher/elite from L1 (best) rows
    - learner from L2/L3 (weaker) rows
    - fallback: top-scoring hard-pass rows, then best available
    """
    rng = np.random.RandomState(random_seed + generation)

    llso_cfg = config.get("llso_offspring", {})
    param_cols = list(config.get("parameter_columns", []))
    if not param_cols:
        return pd.DataFrame()
    parameter_profile = _parameter_profile_from_config(config)

    teacher_level = llso_cfg.get("teacher_level", "L1")
    learner_levels = llso_cfg.get("learner_levels", ["L2", "L3"])
    teacher_fraction = float(llso_cfg.get("teacher_fraction", 0.5))
    elite_fraction = float(llso_cfg.get("elite_fraction", 0.25))
    mutation_fraction = float(llso_cfg.get("mutation_fraction", 0.05))
    min_history = int(llso_cfg.get("min_history_rows", 4))
    dedupe_places = int(llso_cfg.get("dedupe_decimal_places", 6))
    max_attempts = offspring_count * int(llso_cfg.get("max_attempt_multiplier", 5))

    if len(history) < min_history:
        if len(seed_candidates) > 0:
            sampled = seed_candidates.sample(
                n=min(offspring_count, len(seed_candidates)),
                replace=True,
                random_state=rng,
            ).copy()
            sampled["generation"] = generation
            sampled["source"] = "llso_offspring"
            sampled["candidate_id"] = [
                f"gen{generation}_offspring_{i}" for i in range(len(sampled))
            ]
            sampled["must_resimulate"] = True
            sampled["data_source"] = "real_simulation_csv"
            sampled["engineering_validity"] = "simulation_only"
            if parameter_profile is not None:
                for parameter in parameter_profile.optimizable_parameters:
                    if parameter.column in sampled.columns:
                        sampled[parameter.column] = sampled[parameter.column].map(
                            lambda value: project_parameter_value(parameter, float(value))
                        )
            return sampled.reset_index(drop=True)
        return pd.DataFrame()

    # Identify teacher and learner pools
    if "level" in history.columns:
        teacher_pool = history[history["level"] == teacher_level]
        learner_pool = history[history["level"].isin(learner_levels)]
    else:
        teacher_pool = history
        learner_pool = history

    # Fallback if no teachers
    if len(teacher_pool) == 0:
        if "hard_constraint_passed" in history.columns and "overall_score" in history.columns:
            teacher_pool = history[history["hard_constraint_passed"].eq(True)].nlargest(
                max(2, len(history) // 2), "overall_score"
            )
        if len(teacher_pool) == 0:
            teacher_pool = history

    # Fallback if no learners
    if len(learner_pool) == 0:
        learner_pool = history

    # Infer bounds
    bounds = infer_parameter_bounds(history, seed_candidates, param_cols)
    parameter_by_column = (
        {parameter.column: parameter for parameter in parameter_profile.parameters}
        if parameter_profile is not None
        else {}
    )
    if parameter_profile is None:
        available_cols = [column for column in param_cols if column in bounds]
        fixed_cols: list[str] = []
    else:
        available_cols = [
            column
            for column in param_cols
            if column in bounds
            and column in parameter_by_column
            and parameter_by_column[column].optimizable
            and parameter_by_column[column].kind == "design"
        ]
        fixed_cols = [
            column
            for column in param_cols
            if column in parameter_by_column
            and column in learner_pool.columns
            and column not in available_cols
        ]
        bounds = _apply_profile_bounds(bounds, parameter_by_column, available_cols)
    coupled_groups = _coupled_parameter_groups(parameter_profile, available_cols)

    if not available_cols:
        return pd.DataFrame()

    # Generate offspring
    offspring_rows: list[dict[str, Any]] = []
    attempts = 0
    seen_vectors: set[tuple[Any, ...]] = set()

    while len(offspring_rows) < offspring_count and attempts < max_attempts:
        attempts += 1

        teacher_idx = rng.randint(0, len(teacher_pool))
        learner_idx = rng.randint(0, len(learner_pool))
        elite_idx = rng.randint(0, len(teacher_pool))

        row: dict[str, Any] = {}

        for col in fixed_cols:
            fixed_value = learner_pool.iloc[learner_idx][col]
            row[col] = fixed_value

        for col in available_cols:
            teacher_val = float(teacher_pool.iloc[teacher_idx][col])
            learner_val = float(learner_pool.iloc[learner_idx][col])
            elite_val = float(teacher_pool.iloc[elite_idx][col])

            r1 = rng.uniform(0, 1) * teacher_fraction
            r2 = rng.uniform(0, 1) * elite_fraction
            lower, upper = bounds[col]
            noise = rng.normal(0, (upper - lower) * mutation_fraction)

            child = learner_val + r1 * (teacher_val - learner_val) + r2 * (elite_val - learner_val) + noise
            child = np.clip(child, lower, upper)
            parameter = parameter_by_column.get(col)
            if parameter is not None:
                child = project_parameter_value(parameter, float(child))
            row[col] = child

        if not _enforce_coupled_groups(
            row,
            learner_pool.iloc[learner_idx],
            coupled_groups,
            bounds,
            parameter_by_column,
        ):
            continue

        vec = [row[column] for column in fixed_cols]
        vec.extend(round(float(row[column]), dedupe_places) for column in available_cols)

        vec_tuple = tuple(vec)
        if vec_tuple in seen_vectors:
            continue
        seen_vectors.add(vec_tuple)

        row["candidate_id"] = f"gen{generation}_offspring_{len(offspring_rows)}"
        row["generation"] = generation
        row["source"] = "llso_offspring"
        row["must_resimulate"] = True
        row["data_source"] = "real_simulation_csv"
        row["engineering_validity"] = "simulation_only"
        offspring_rows.append(row)

    result = pd.DataFrame(offspring_rows)
    return result.reset_index(drop=True)


def _parameter_profile_from_config(config: Mapping[str, Any]) -> CircuitParameterProfile | None:
    transfer = config.get("transfer", {})
    if not isinstance(transfer, Mapping):
        return None
    raw_profile = transfer.get("target_parameter_profile")
    if isinstance(raw_profile, Mapping):
        return CircuitParameterProfile.from_mapping(raw_profile)
    reference = transfer.get("target_circuit_profile", raw_profile)
    if reference is None:
        return None
    if not isinstance(reference, str):
        raise ValueError(
            "transfer.target_parameter_profile must be a mapping or registered circuit-profile name"
        )
    circuit_profile = resolve_circuit_profile(reference, load_circuit_profiles())
    if not circuit_profile.get("parameter_profile"):
        raise ValueError(f"circuit profile {reference!r} does not declare parameter_profile")
    return CircuitParameterProfile.from_circuit_profile(circuit_profile)


def _apply_profile_bounds(
    inferred: dict[str, tuple[float, float]],
    parameters: Mapping[str, ParameterSpec],
    columns: list[str],
) -> dict[str, tuple[float, float]]:
    bounded = dict(inferred)
    for column in columns:
        lower, upper = inferred[column]
        parameter = parameters[column]
        if parameter.lower_bound is not None:
            lower = parameter.lower_bound
        if parameter.upper_bound is not None:
            upper = parameter.upper_bound
        if lower > upper:
            raise ValueError(f"parameter profile bounds for {column} do not overlap the observed range")
        bounded[column] = (float(lower), float(upper))
    return bounded


def _coupled_parameter_groups(
    profile: CircuitParameterProfile | None,
    available_columns: list[str],
) -> list[tuple[str, ...]]:
    if profile is None:
        return []
    available = set(available_columns)
    coupled: list[tuple[str, ...]] = []
    for group, constraint in profile.group_constraints.items():
        if constraint not in {"keep_ratio", "must_change_together"}:
            continue
        columns = tuple(
            parameter.column
            for parameter in profile.optimizable_parameters
            if parameter.group == group and parameter.column in available
        )
        if len(columns) > 1:
            coupled.append(columns)
    return coupled


def _enforce_coupled_groups(
    row: dict[str, Any],
    learner: pd.Series,
    coupled_groups: list[tuple[str, ...]],
    bounds: Mapping[str, tuple[float, float]],
    parameters: Mapping[str, ParameterSpec],
) -> bool:
    """Apply one common multiplicative step to each matched parameter group."""

    for columns in coupled_groups:
        learner_values = [float(learner[column]) for column in columns]
        proposed_values = [float(row[column]) for column in columns]
        if any(value <= 0.0 or not np.isfinite(value) for value in learner_values + proposed_values):
            return False
        log_multiplier = float(
            np.mean(
                [
                    math.log(proposed / current)
                    for proposed, current in zip(proposed_values, learner_values)
                ]
            )
        )
        multiplier = math.exp(log_multiplier)
        lower_multiplier = max(bounds[column][0] / value for column, value in zip(columns, learner_values))
        upper_multiplier = min(bounds[column][1] / value for column, value in zip(columns, learner_values))
        if lower_multiplier > upper_multiplier or upper_multiplier <= 0.0:
            return False
        multiplier = float(np.clip(multiplier, max(lower_multiplier, 0.0), upper_multiplier))
        realized_multipliers: list[float] = []
        for column, learner_value in zip(columns, learner_values):
            child = learner_value * multiplier
            parameter = parameters.get(column)
            if parameter is not None:
                child = project_parameter_value(parameter, child)
            row[column] = child
            realized_multipliers.append(child / learner_value)
        if not np.allclose(
            realized_multipliers,
            realized_multipliers[0],
            rtol=1.0e-9,
            atol=1.0e-12,
        ):
            return False
    return True
