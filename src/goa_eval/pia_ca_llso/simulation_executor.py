"""PIA simulation executor with offline, import_results, and external_command modes."""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from goa_eval.pia_ca_llso.local_simulator import run_local_fixture_simulator
from goa_eval.pia_ca_llso.simulation_contract import import_simulation_results
from goa_eval.pia_ca_llso.simulator_adapter import run_external_simulator_command


NON_RESULT_CSV_ARTIFACTS = {
    "simulation_batch.csv",
    "offspring_candidates.csv",
    "pia_selected_candidates.csv",
    "imported_results.csv",
}


def _filter_result_files(files: list[str]) -> list[str]:
    return [
        f for f in files
        if Path(f).name not in NON_RESULT_CSV_ARTIFACTS
    ]


def run_simulation_step(
    simulation_batch: pd.DataFrame,
    output_dir: Path,
    config: Mapping[str, Any],
    generation: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Execute the simulation step for a generation.

    Returns (imported_results, status_dict).

    Modes:
    - offline: write batch and return pending status
    - import_results: read result CSV from generation directory
    - external_command: call configured command, parse results
    """
    exec_cfg = config.get("simulation_executor", {})
    mode = exec_cfg.get("mode", "offline")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Always write the batch
    batch_path = output_dir / "simulation_batch.csv"
    simulation_batch.to_csv(batch_path, index=False)

    if mode == "offline":
        return pd.DataFrame(), {
            "status": "pending_simulation",
            "mode": "offline",
            "generation": generation,
            "batch_path": str(batch_path),
        }

    elif mode == "local_fixture":
        result_path = output_dir / "simulation_results.csv"
        fixture_results = run_local_fixture_simulator(
            simulation_batch=simulation_batch,
            config=config,
            generation=generation,
        )
        fixture_results.to_csv(result_path, index=False)
        imported = import_simulation_results(
            result_csv=result_path,
            simulation_batch=simulation_batch,
            config=config,
            generation=generation,
        )
        return imported, {
            "status": "results_imported",
            "mode": "local_fixture",
            "generation": generation,
            "imported_count": len(imported),
            "result_path": str(result_path),
        }

    elif mode == "import_results":
        result_glob = exec_cfg.get("result_glob", "*.csv")
        result_files = sorted(glob.glob(str(output_dir / result_glob)))
        result_files = _filter_result_files(result_files)

        # Fallback: also look in configured simulation_results_dir
        results_dir = exec_cfg.get("simulation_results_dir")
        if not result_files and results_dir:
            fallback_pattern = str(Path(results_dir) / result_glob)
            result_files = sorted(glob.glob(fallback_pattern))
            result_files = _filter_result_files(result_files)

        if not result_files:
            return pd.DataFrame(), {
                "status": "pending_simulation",
                "mode": "import_results",
                "generation": generation,
                "reason": "no_result_files_found",
            }

        all_imported = []
        for rf in result_files:
            imported = import_simulation_results(
                result_csv=rf,
                simulation_batch=simulation_batch,
                config=config,
                generation=generation,
            )
            if len(imported) > 0:
                all_imported.append(imported)

        if not all_imported:
            return pd.DataFrame(), {
                "status": "pending_simulation",
                "mode": "import_results",
                "generation": generation,
                "reason": "no_valid_results",
            }

        combined = pd.concat(all_imported, ignore_index=True)
        return combined, {
            "status": "results_imported",
            "mode": "import_results",
            "generation": generation,
            "imported_count": len(combined),
        }

    elif mode == "external_command":
        command_template = exec_cfg.get("external_command")
        command_argv = exec_cfg.get("external_command_argv")
        if not command_template and not command_argv:
            return pd.DataFrame(), {
                "status": "error",
                "mode": "external_command",
                "generation": generation,
                "reason": "no_command_template",
            }
        if command_template and not bool(exec_cfg.get("allow_shell_command", True)):
            raise ValueError("legacy shell command is disabled; use external_command_argv")

        result_glob = exec_cfg.get("result_glob", "*.csv")
        result_path = output_dir / "simulation_results.csv"
        invocation = run_external_simulator_command(
            command_template,
            command_argv=command_argv,
            candidate_csv=batch_path,
            result_csv=result_path,
            generation=generation,
            output_dir=output_dir,
            timeout_seconds=int(exec_cfg.get("timeout_seconds", 300)),
        )

        result_files = sorted(glob.glob(str(output_dir / result_glob)))
        result_files = _filter_result_files(result_files)

        if not result_files:
            raise RuntimeError(
                "external_command completed but no result files found "
                f"matching '{result_glob}' in {output_dir}"
            )

        all_imported = []
        try:
            for rf in result_files:
                imported = import_simulation_results(
                    result_csv=rf,
                    simulation_batch=simulation_batch,
                    config=config,
                    generation=generation,
                )
                if len(imported) > 0:
                    all_imported.append(imported)
        except Exception as exc:
            invocation["result_validation_status"] = "failed"
            invocation["result_validation_error"] = str(exc)
            (output_dir / "simulator_invocation.json").write_text(
                json.dumps(invocation, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            raise

        if not all_imported:
            raise RuntimeError(
                "external_command produced result files but none contained "
                "valid results matching the simulation batch"
            )

        combined = pd.concat(all_imported, ignore_index=True)
        invocation["result_validation_status"] = "passed"
        (output_dir / "simulator_invocation.json").write_text(
            json.dumps(invocation, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return combined, {
            "status": "results_imported",
            "mode": "external_command",
            "generation": generation,
            "imported_count": len(combined),
            "invocation": invocation,
        }

    else:
        raise ValueError(f"Unknown simulation mode: {mode}")
