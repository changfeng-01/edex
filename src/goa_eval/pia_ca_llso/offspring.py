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

from typing import Any, Mapping

import numpy as np
import pandas as pd


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
            teacher_pool = history[history["hard_constraint_passed"] == True].nlargest(
                max(2, len(history) // 2), "overall_score"
            )
        if len(teacher_pool) == 0:
            teacher_pool = history

    # Fallback if no learners
    if len(learner_pool) == 0:
        learner_pool = history

    # Infer bounds
    bounds = infer_parameter_bounds(history, seed_candidates, param_cols)
    available_cols = [c for c in param_cols if c in bounds]

    if not available_cols:
        return pd.DataFrame()

    # Generate offspring
    offspring_rows: list[dict[str, Any]] = []
    attempts = 0
    seen_vectors: set[tuple[float, ...]] = set()

    while len(offspring_rows) < offspring_count and attempts < max_attempts:
        attempts += 1

        teacher_idx = rng.randint(0, len(teacher_pool))
        learner_idx = rng.randint(0, len(learner_pool))
        elite_idx = rng.randint(0, len(teacher_pool))

        row: dict[str, Any] = {}
        vec: list[float] = []

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
            row[col] = child
            vec.append(round(child, dedupe_places))

        vec_tuple = tuple(vec)
        if vec_tuple in seen_vectors:
            continue
        seen_vectors.add(vec_tuple)

        row["candidate_id"] = f"gen{generation}_offspring_{len(offspring_rows)}"
        row["generation"] = generation
        row["source"] = "llso_offspring"
        offspring_rows.append(row)

    result = pd.DataFrame(offspring_rows)
    return result.reset_index(drop=True)