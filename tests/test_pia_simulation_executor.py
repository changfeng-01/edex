"""Tests for PIA simulation executor (offline, import, external modes)."""
from __future__ import annotations

import json
import sys
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


def test_local_fixture_simulator_produces_result_csv() -> None:
    """local_fixture mode writes deterministic result CSV and imports it."""
    batch = _make_simulation_batch()
    config = {
        "parameter_columns": ["x1", "x2"],
        "simulation_executor": {"mode": "local_fixture"},
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        imported, status = run_simulation_step(batch, output_dir, config, generation=1)

        assert status["status"] == "results_imported"
        assert status["mode"] == "local_fixture"
        assert (output_dir / "simulation_results.csv").exists()
        assert len(imported) == 2
        assert set(imported["simulator_mode"]) == {"local_fixture"}


def test_local_fixture_results_remain_simulation_only() -> None:
    """local_fixture results preserve simulation-only evidence labels."""
    batch = _make_simulation_batch()
    config = {
        "parameter_columns": ["x1", "x2"],
        "simulation_executor": {"mode": "local_fixture"},
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        imported, _status = run_simulation_step(batch, Path(tmpdir), config, generation=1)

        assert set(imported["data_source"]) == {"real_simulation_csv"}
        assert set(imported["engineering_validity"]) == {"simulation_only"}
        assert set(imported["must_resimulate"]) == {False}


def test_external_command_records_invocation_and_output() -> None:
    """External command mode records command evidence and imports results."""
    batch = _make_simulation_batch()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        script = output_dir / "write_results.py"
        script.write_text(
            "import pandas as pd, sys\n"
            "candidate_csv, result_csv, generation, output_dir = sys.argv[1:5]\n"
            "batch = pd.read_csv(candidate_csv)\n"
            "pd.DataFrame({\n"
            "  'candidate_id': batch['candidate_id'],\n"
            "  'overall_score': [80.0 + i for i in range(len(batch))],\n"
            "  'hard_constraint_passed': [True] * len(batch),\n"
            "}).to_csv(result_csv, index=False)\n"
            "print('wrote', result_csv)\n",
            encoding="utf-8",
        )
        config = {
            "parameter_columns": ["x1", "x2"],
            "simulation_executor": {
                "mode": "external_command",
                "external_command": f'"{sys.executable}" "{script}" "{{candidate_csv}}" "{{result_csv}}" "{{generation}}" "{{output_dir}}"',
                "result_required_columns": [
                    "candidate_id", "overall_score", "hard_constraint_passed",
                ],
                "result_glob": "simulation_results.csv",
            },
        }

        imported, status = run_simulation_step(batch, output_dir, config, generation=1)

        assert len(imported) == 2
        assert status["status"] == "results_imported"
        invocation = json.loads((output_dir / "simulator_invocation.json").read_text(encoding="utf-8"))
        assert invocation["generation"] == 1
        assert invocation["exit_code"] == 0
        assert "{candidate_csv}" not in invocation["command"]
        assert "wrote" in (output_dir / "simulator_stdout.txt").read_text(encoding="utf-8")
        assert (output_dir / "simulator_stderr.txt").exists()


def test_external_command_argv_runs_without_shell_and_records_provenance() -> None:
    batch = _make_simulation_batch()

    with tempfile.TemporaryDirectory(prefix="pia argv ") as tmpdir:
        output_dir = Path(tmpdir)
        script = output_dir / "write results.py"
        script.write_text(
            "import pandas as pd, sys\n"
            "batch = pd.read_csv(sys.argv[1])\n"
            "pd.DataFrame({'candidate_id': batch['candidate_id'], 'overall_score': [88.0] * len(batch), 'hard_constraint_passed': [True] * len(batch)}).to_csv(sys.argv[2], index=False)\n",
            encoding="utf-8",
        )
        config = {
            "simulation_executor": {
                "mode": "external_command",
                "external_command_argv": [sys.executable, str(script), "{candidate_csv}", "{result_csv}"],
                "result_glob": "simulation_results.csv",
            }
        }

        imported, _status = run_simulation_step(batch, output_dir, config, generation=1)

        assert len(imported) == 2
        invocation = json.loads((output_dir / "simulator_invocation.json").read_text(encoding="utf-8"))
        assert invocation["legacy_shell_command"] is False
        assert invocation["executable"] == sys.executable
        assert invocation["working_directory"] == str(output_dir)
        assert invocation["result_validation_status"] == "passed"


def test_external_shell_command_can_be_rejected_for_formal_runs(tmp_path: Path) -> None:
    config = {
        "simulation_executor": {
            "mode": "external_command",
            "external_command": "echo unsafe",
            "allow_shell_command": False,
        }
    }

    with pytest.raises(ValueError, match="legacy shell command"):
        run_simulation_step(_make_simulation_batch(), tmp_path, config, generation=1)


def test_external_command_mismatched_candidate_ids_are_rejected() -> None:
    """External result CSV with mismatched ids fails closed."""
    batch = _make_simulation_batch()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        script = output_dir / "write_bad_results.py"
        script.write_text(
            "import pandas as pd, sys\n"
            "pd.DataFrame({'candidate_id': ['bad'], 'overall_score': [90], 'hard_constraint_passed': [True]}).to_csv(sys.argv[2], index=False)\n",
            encoding="utf-8",
        )
        config = {
            "parameter_columns": ["x1", "x2"],
            "simulation_executor": {
                "mode": "external_command",
                "external_command": f'"{sys.executable}" "{script}" "{{candidate_csv}}" "{{result_csv}}" "{{generation}}" "{{output_dir}}"',
                "result_required_columns": [
                    "candidate_id", "overall_score", "hard_constraint_passed",
                ],
                "result_glob": "simulation_results.csv",
            },
        }

        with pytest.raises(ValueError, match="candidate_id"):
            run_simulation_step(batch, output_dir, config, generation=1)
        invocation = json.loads((output_dir / "simulator_invocation.json").read_text(encoding="utf-8"))
        assert invocation["result_validation_status"] == "failed"
        assert "candidate_id" in invocation["result_validation_error"]
