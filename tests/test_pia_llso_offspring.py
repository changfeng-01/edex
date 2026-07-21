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


def test_llso_offspring_only_mutates_optimizable_design_parameters() -> None:
    history = _make_labeled_history().assign(
        vdd_v=[3.3, 2.7, 3.3, 2.7, 3.3, 2.7, 3.3, 2.7, 3.3, 2.7]
    )
    candidates = _make_seed_candidates().assign(vdd_v=[3.3, 2.7, 3.3, 2.7, 3.3, 2.7])
    config = _make_default_config()
    config["parameter_columns"] = ["x1", "vdd_v"]
    config["transfer"] = {
        "target_parameter_profile": {
            "name": "goa_parameter_space",
            "task_type": "goa",
            "parameters": {
                "pullup_width": {
                    "column": "x1",
                    "role": "pullup",
                    "property": "width",
                    "kind": "design",
                    "optimizable": True,
                    "bounds": [2.0, 8.0],
                    "quantization": 0.5,
                    "mapping_fidelity": "exact",
                },
                "supply": {
                    "column": "vdd_v",
                    "role": "environment",
                    "property": "supply_v",
                    "kind": "environment",
                    "optimizable": False,
                    "mapping_fidelity": "exact",
                },
            },
        }
    }

    offspring = generate_llso_offspring(
        history=history,
        seed_candidates=candidates,
        config=config,
        generation=1,
        offspring_count=12,
        random_seed=42,
    )

    assert len(offspring) > 0
    assert offspring["x1"].between(2.0, 8.0).all()
    assert (((offspring["x1"] - 2.0) / 0.5).round(10) % 1 == 0).all()
    assert set(offspring["vdd_v"]).issubset({2.7, 3.3})
    assert offspring["vdd_v"].notna().all()


def test_llso_offspring_preserves_keep_ratio_parameter_groups() -> None:
    history = _make_labeled_history()
    history["x2"] = 2.0 * history["x1"]
    candidates = _make_seed_candidates()
    candidates["x2"] = 2.0 * candidates["x1"]
    config = _make_default_config()
    config["transfer"] = {
        "target_parameter_profile": {
            "name": "matched_pair",
            "task_type": "ota",
            "parameters": {
                "left_width": {
                    "column": "x1",
                    "role": "input_pair",
                    "property": "width",
                    "kind": "design",
                    "optimizable": True,
                    "group": "input_pair",
                    "mapping_fidelity": "exact",
                },
                "right_width": {
                    "column": "x2",
                    "role": "input_pair",
                    "property": "width",
                    "kind": "design",
                    "optimizable": True,
                    "group": "input_pair",
                    "mapping_fidelity": "exact",
                },
            },
            "parameter_groups": {"input_pair": {"constraint": "keep_ratio"}},
        }
    }

    offspring = generate_llso_offspring(
        history=history,
        seed_candidates=candidates,
        config=config,
        generation=1,
        offspring_count=12,
        random_seed=42,
    )

    assert len(offspring) > 0
    assert np.allclose(offspring["x2"] / offspring["x1"], 2.0, rtol=1e-9, atol=1e-9)
