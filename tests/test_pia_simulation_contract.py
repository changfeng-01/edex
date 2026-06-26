"""Tests for PIA simulation batch contract and result import."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.simulation_contract import (
    build_simulation_batch,
    import_simulation_results,
)


def _make_selected_candidates() -> pd.DataFrame:
    """Create a small DataFrame of already-scheduled selected candidates."""
    return pd.DataFrame({
        "candidate_id": [f"c{i}" for i in range(4)],
        "x1": np.random.uniform(0, 10, size=4),
        "x2": np.random.uniform(0, 10, size=4),
        "selected_rank": [1, 2, 3, 4],
        "simulation_window": ["window_0"] * 4,
        "constraint_eval_plan_json": [json.dumps({"plan": "default"})] * 4,
        "evidence_state": ["pending_simulation"] * 4,
        "must_resimulate": [True] * 4,
        "data_source": ["real_simulation_csv"] * 4,
        "engineering_validity": ["simulation_only"] * 4,
    })


def _make_config() -> dict:
    return {
        "parameter_columns": ["x1", "x2"],
        "simulation_executor": {
            "mode": "offline",
            "result_required_columns": [
                "candidate_id", "overall_score", "hard_constraint_passed",
            ],
        },
    }


def _make_simulation_batch() -> pd.DataFrame:
    """Create a small simulation batch DataFrame."""
    return pd.DataFrame({
        "candidate_id": ["c0", "c1", "c2", "c3"],
        "generation": [1] * 4,
        "x1": [1.0, 2.0, 3.0, 4.0],
        "x2": [5.0, 6.0, 7.0, 8.0],
        "selected_rank": [1, 2, 3, 4],
        "simulation_window": ["window_0"] * 4,
    })


# --- build_simulation_batch tests ---


def test_build_simulation_batch_preserves_selected_order() -> None:
    """Batch preserves the selected rank order from suggest_next_run."""
    selected = _make_selected_candidates()
    config = _make_config()

    batch, manifest = build_simulation_batch(
        selected=selected, config=config, generation=1,
    )

    assert len(batch) == 4
    assert list(batch["selected_rank"]) == [1, 2, 3, 4]


def test_simulation_batch_contains_constraint_plan_and_window() -> None:
    """Batch retains constraint evaluation plan and simulation window."""
    selected = _make_selected_candidates()
    config = _make_config()

    batch, manifest = build_simulation_batch(
        selected=selected, config=config, generation=1,
    )

    assert "simulation_window" in batch.columns
    assert "constraint_eval_plan_json" in batch.columns


def test_simulation_batch_marks_rows_pending_and_must_resimulate() -> None:
    """Batch rows keep pending_simulation evidence_state and must_resimulate=True."""
    selected = _make_selected_candidates()
    config = _make_config()

    batch, manifest = build_simulation_batch(
        selected=selected, config=config, generation=1,
    )

    assert all(batch["evidence_state"] == "pending_simulation")
    assert all(batch["must_resimulate"])


def test_simulation_manifest_records_boundary() -> None:
    """Manifest includes conservative evidence boundary labels."""
    selected = _make_selected_candidates()
    config = _make_config()

    batch, manifest = build_simulation_batch(
        selected=selected, config=config, generation=1,
    )

    assert manifest["generation"] == 1
    assert manifest["candidate_count"] == 4
    assert manifest["data_source"] == "real_simulation_csv"
    assert manifest["engineering_validity"] == "simulation_only"
    assert "claim_boundary" in manifest


# --- import_simulation_results tests ---


def test_import_simulation_results_requires_required_columns() -> None:
    """Result CSV without all required columns returns empty DataFrame."""
    batch = _make_simulation_batch()
    config = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        result_path = Path(tmpdir) / "results.csv"
        pd.DataFrame({
            "candidate_id": ["c0"],
            "hard_constraint_passed": [True],
        }).to_csv(result_path, index=False)

        imported = import_simulation_results(
            result_csv=str(result_path),
            simulation_batch=batch,
            config=config,
            generation=1,
        )
        assert len(imported) == 0


def test_import_simulation_results_keeps_only_selected_candidate_ids() -> None:
    """Only candidates present in the simulation batch are kept."""
    batch = _make_simulation_batch()
    config = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        result_path = Path(tmpdir) / "results.csv"
        pd.DataFrame({
            "candidate_id": ["c0", "c99"],
            "overall_score": [85.0, 90.0],
            "hard_constraint_passed": [True, True],
        }).to_csv(result_path, index=False)

        imported = import_simulation_results(
            result_csv=str(result_path),
            simulation_batch=batch,
            config=config,
            generation=1,
        )
        assert len(imported) == 1
        assert imported.iloc[0]["candidate_id"] == "c0"


def test_import_simulation_results_appends_generation_metadata() -> None:
    """Imported results include generation, source, and boundary labels."""
    batch = _make_simulation_batch()
    config = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        result_path = Path(tmpdir) / "results.csv"
        pd.DataFrame({
            "candidate_id": ["c0", "c1"],
            "overall_score": [85.0, 90.0],
            "hard_constraint_passed": [True, True],
        }).to_csv(result_path, index=False)

        imported = import_simulation_results(
            result_csv=str(result_path),
            simulation_batch=batch,
            config=config,
            generation=1,
        )

        assert all(imported["generation"] == 1)
        assert all(imported["source"] == "simulation_result")
        assert all(imported["data_source"] == "real_simulation_csv")
        assert all(imported["engineering_validity"] == "simulation_only")