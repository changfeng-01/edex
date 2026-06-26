"""Tests for PIA simulation executor (offline, import, external modes)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.pia_ca_llso.simulation_executor import run_simulation_step


def _make_simulation_batch() -> pd.DataFrame:
    """Create a small simulation batch."""
    return pd.DataFrame({
        "candidate_id": ["c0", "c1"],
        "generation": [1, 1],
        "x1": [1.0, 2.0],
        "x2": [5.0, 6.0],
        "selected_rank": [1, 2],
        "simulation_window": ["window_0", "window_0"],
        "evidence_state": ["pending_simulation", "pending_simulation"],
        "must_resimulate": [True, True],
        "data_source": ["real_simulation_csv", "real_simulation_csv"],
        "engineering_validity": ["simulation_only", "simulation_only"],
    })


def _make_config_offline() -> dict:
    return {"simulation_executor": {"mode": "offline"}}


def _make_config_import() -> dict:
    return {
        "simulation_executor": {
            "mode": "import_results",
            "result_required_columns": [
                "candidate_id", "overall_score", "hard_constraint_passed",
            ],
            "result_glob": "*.csv",
        },
    }


def test_offline_executor_returns_pending_status() -> None:
    """Offline mode writes batch and returns empty imported results."""
    batch = _make_simulation_batch()
    config = _make_config_offline()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        imported, status = run_simulation_step(
            simulation_batch=batch,
            output_dir=output_dir,
            config=config,
            generation=1,
        )

        assert len(imported) == 0
        assert status["status"] == "pending_simulation"
        assert status["mode"] == "offline"
        batch_path = output_dir / "simulation_batch.csv"
        assert batch_path.exists()


def test_result_import_executor_loads_generation_result_csv() -> None:
    """Import mode reads result CSV from generation directory."""
    batch = _make_simulation_batch()
    config = _make_config_import()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        pd.DataFrame({
            "candidate_id": ["c0", "c1"],
            "overall_score": [85.0, 90.0],
            "hard_constraint_passed": [True, True],
        }).to_csv(output_dir / "simulation_results.csv", index=False)

        imported, status = run_simulation_step(
            simulation_batch=batch,
            output_dir=output_dir,
            config=config,
            generation=1,
        )

        assert len(imported) == 2
        assert status["status"] == "results_imported"
        assert status["imported_count"] == 2


def test_external_command_executor_fails_closed_on_missing_result() -> None:
    """External command mode raises RuntimeError when result file is missing."""
    batch = _make_simulation_batch()
    config = {
        "simulation_executor": {
            "mode": "external_command",
            "external_command": "echo test",
            "result_required_columns": [
                "candidate_id", "overall_score", "hard_constraint_passed",
            ],
            "result_glob": "*.csv",
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        with pytest.raises(RuntimeError, match="external_command"):
            run_simulation_step(
                simulation_batch=batch,
                output_dir=output_dir,
                config=config,
                generation=1,
            )