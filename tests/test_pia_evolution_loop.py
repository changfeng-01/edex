"""Tests for PIA closed-loop evolution orchestrator."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.evolution import run_evolution_loop


def _make_history() -> pd.DataFrame:
    """Create labeled history with enough rows for LLSO."""
    np.random.seed(42)
    n = 10
    return pd.DataFrame({
        "candidate_id": [f"h{i}" for i in range(n)],
        "level": np.random.choice(["L1", "L2", "L3"], size=n),
        "overall_score": np.random.uniform(50, 100, size=n),
        "hard_constraint_passed": np.random.choice([True, False], size=n),
        "x1": np.random.uniform(0, 10, size=n),
        "x2": np.random.uniform(0, 10, size=n),
    })


def _make_candidates() -> pd.DataFrame:
    return pd.DataFrame({
        "candidate_id": [f"c{i}" for i in range(6)],
        "x1": np.random.uniform(0, 10, size=6),
        "x2": np.random.uniform(0, 10, size=6),
    })


def _make_config() -> dict:
    return {
        "parameter_columns": ["x1", "x2"],
        "problem_name": "test_evolution",
        "evolution_loop": {
            "enabled": True,
            "generations": 2,
            "offspring_per_generation": 8,
            "top_k": 4,
            "patience_generations": 2,
            "min_improvement": 0.01,
            "simulation_budget": 20,
            "random_seed": 42,
        },
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
        "simulation_executor": {
            "mode": "offline",
            "result_required_columns": [
                "candidate_id", "overall_score", "hard_constraint_passed",
            ],
        },
        "labeling": {},
        "acquisition_weights": {},
        "evaluation_scheduler": {"enabled": True},
        "repair_candidates": {"enabled": False},
        "target_score": 100.0,
        "benchmark": {"strategies": []},
    }


def test_evolution_offline_writes_first_generation_batch() -> None:
    """Offline evolution writes complete generation artifacts and stops pending."""
    history = _make_history()
    candidates = _make_candidates()
    config = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        summary = run_evolution_loop(
            history=history,
            candidates=candidates,
            config=config,
            output_dir=output_dir,
            strategy="ca_llso_raw_distance",
            generations=2,
            offspring_per_generation=8,
            top_k=4,
            random_seed=42,
        )

        assert summary["stop_reason"] == "pending_simulation_results"
        gen0_dir = output_dir / "generation_000"
        assert gen0_dir.exists()
        assert (gen0_dir / "offspring_candidates.csv").exists()
        assert (gen0_dir / "pia_selected_candidates.csv").exists()
        assert (gen0_dir / "simulation_batch.csv").exists()
        assert (gen0_dir / "simulation_manifest.json").exists()
        assert (gen0_dir / "imported_results.csv").exists()
        assert (gen0_dir / "generation_summary.json").exists()
        assert (output_dir / "evolution_report.md").exists()
        assert (output_dir / "generation_state.jsonl").exists()


def test_evolution_stops_when_target_score_reached() -> None:
    """Evolution stops when best score reaches target."""
    history = _make_history()
    history.loc[0, "overall_score"] = 99.0
    history.loc[0, "level"] = "L1"
    candidates = _make_candidates()
    config = _make_config()
    config["target_score"] = 80.0

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        summary = run_evolution_loop(
            history=history,
            candidates=candidates,
            config=config,
            output_dir=output_dir,
            strategy="ca_llso_raw_distance",
            generations=2,
            offspring_per_generation=8,
            top_k=4,
            random_seed=42,
        )

        assert summary["stop_reason"] == "target_score_reached"


def test_evolution_preserves_simulation_only_boundary() -> None:
    """Evolution summary preserves simulation-only boundary labels."""
    history = _make_history()
    candidates = _make_candidates()
    config = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        summary = run_evolution_loop(
            history=history,
            candidates=candidates,
            config=config,
            output_dir=output_dir,
            strategy="ca_llso_raw_distance",
            generations=2,
            offspring_per_generation=8,
            top_k=4,
            random_seed=42,
        )

        assert summary["data_source"] == "real_simulation_csv"
        assert summary["engineering_validity"] == "simulation_only"
