"""Tests for LLSO offspring generation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.offspring import (
    infer_parameter_bounds,
    generate_llso_offspring,
)


def _make_labeled_history() -> pd.DataFrame:
    """Create a small labeled history DataFrame for testing."""
    np.random.seed(42)
    n = 10
    return pd.DataFrame({
        "candidate_id": [f"h{i}" for i in range(n)],
        "level": np.random.choice(["L1", "L2", "L3", "L4"], size=n),
        "overall_score": np.random.uniform(50, 100, size=n),
        "hard_constraint_passed": np.random.choice([True, False], size=n),
        "x1": np.random.uniform(0, 10, size=n),
        "x2": np.random.uniform(0, 10, size=n),
    })


def _make_seed_candidates() -> pd.DataFrame:
    """Create a small seed candidate pool."""
    return pd.DataFrame({
        "candidate_id": [f"c{i}" for i in range(6)],
        "x1": np.random.uniform(0, 10, size=6),
        "x2": np.random.uniform(0, 10, size=6),
    })


def _make_default_config() -> dict:
    """Return a minimal config for LLSO offspring tests."""
    return {
        "parameter_columns": ["x1", "x2"],
        "llso_offspring": {
            "enabled": True,
            "teacher_level": "L1",
            "learner_levels": ["L2", "L3"],
            "teacher_fraction": 0.5,
            "elite_fraction": 0.25,
            "mutation_fraction": 0.05,
            "min_history_rows": 4,
            "dedupe_decimal_places": 6,
            "max_attempt_multiplier": 5,
        },
    }


def test_infer_parameter_bounds_from_data() -> None:
    """Bounds are inferred from observed data with config margins."""
    history = _make_labeled_history()
    candidates = _make_seed_candidates()

    bounds = infer_parameter_bounds(
        history=history,
        candidates=candidates,
        parameter_columns=["x1", "x2"],
    )

    assert "x1" in bounds
    assert "x2" in bounds
    for col in ["x1", "x2"]:
        lower, upper = bounds[col]
        assert lower < upper
        all_values = pd.concat([history[col], candidates[col]])
        assert lower <= all_values.min()
        assert upper >= all_values.max()


def test_llso_offspring_generates_children() -> None:
    """LLSO offspring generation produces children with required metadata."""
    history = _make_labeled_history()
    candidates = _make_seed_candidates()
    config = _make_default_config()

    offspring = generate_llso_offspring(
        history=history,
        seed_candidates=candidates,
        config=config,
        generation=1,
        offspring_count=8,
        random_seed=42,
    )

    assert len(offspring) > 0
    assert "candidate_id" in offspring.columns
    assert "generation" in offspring.columns
    assert "source" in offspring.columns
    assert all(offspring["source"] == "llso_offspring")
    assert "x1" in offspring.columns
    assert "x2" in offspring.columns


def test_llso_offspring_clamps_to_inferred_bounds() -> None:
    """Offspring parameter values are clamped to inferred bounds."""
    history = _make_labeled_history()
    candidates = _make_seed_candidates()
    config = _make_default_config()

    bounds = infer_parameter_bounds(history, candidates, ["x1", "x2"])
    offspring = generate_llso_offspring(
        history=history,
        seed_candidates=candidates,
        config=config,
        generation=1,
        offspring_count=20,
        random_seed=42,
    )

    for col in ["x1", "x2"]:
        lower, upper = bounds[col]
        assert offspring[col].min() >= lower
        assert offspring[col].max() <= upper


def test_llso_offspring_deduplicates_parameter_vectors() -> None:
    """Offspring rows are deduplicated by parameter vector."""
    history = _make_labeled_history()
    candidates = _make_seed_candidates()
    config = _make_default_config()

    offspring = generate_llso_offspring(
        history=history,
        seed_candidates=candidates,
        config=config,
        generation=1,
        offspring_count=10,
        random_seed=42,
    )

    param_cols = ["x1", "x2"]
    if len(offspring) > 1:
        rounded = offspring[param_cols].round(6)
        dupes = rounded.duplicated()
        assert not dupes.any(), f"Found duplicate parameter vectors: {dupes.sum()}"


def test_llso_offspring_falls_back_when_l1_missing() -> None:
    """When no L1 rows exist, offspring still generates from best available."""
    history = _make_labeled_history()
    history = history[history["level"] != "L1"].copy()
    candidates = _make_seed_candidates()
    config = _make_default_config()

    offspring = generate_llso_offspring(
        history=history,
        seed_candidates=candidates,
        config=config,
        generation=1,
        offspring_count=4,
        random_seed=42,
    )

    assert len(offspring) > 0
    assert all(offspring["source"] == "llso_offspring")