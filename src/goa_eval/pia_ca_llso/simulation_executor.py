"""PIA simulation executor with offline, import_results, and external_command modes."""
from __future__ import annotations

import glob
import subprocess
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from goa_eval.pia_ca_llso.simulation_contract import import_simulation_results


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

    elif mode == "import_results":
        result_glob = exec_cfg.get("result_glob", "*.csv")
        result_files = sorted(glob.glob(str(output_dir / result_glob)))
        result_files = [
            f for f in result_files
            if Path(f).name != "simulation_batch.csv"
        ]

        # Fallback: also look in configured simulation_results_dir
        results_dir = exec_cfg.get("simulation_results_dir")
        if not result_files and results_dir:
            fallback_pattern = str(Path(results_dir) / result_glob)
            result_files = sorted(glob.glob(fallback_pattern))
            result_files = [
                f for f in result_files
                if Path(f).name != "simulation_batch.csv"
            ]

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
        command_template = exec_cfg.get("external_command", "")
        if not command_template:
            return pd.DataFrame(), {
                "status": "error",
                "mode": "external_command",
                "generation": generation,
                "reason": "no_command_template",
            }

        result_glob = exec_cfg.get("result_glob", "*.csv")
        command = (
            command_template
            .replace("{candidate_csv}", str(batch_path))
            .replace("{result_csv}", str(output_dir / "simulation_results.csv"))
            .replace("{candidate_id}", "")
            .replace("{generation}", str(generation))
            .replace("{output_dir}", str(output_dir))
        )

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"external_command timed out: {command}"
            )

        if proc.returncode != 0:
            raise RuntimeError(
                f"external_command failed with exit code {proc.returncode}: "
                f"stderr={proc.stderr[:500]}"
            )

        result_files = sorted(glob.glob(str(output_dir / result_glob)))
        result_files = [
            f for f in result_files
            if Path(f).name != "simulation_batch.csv"
        ]

        if not result_files:
            raise RuntimeError(
                "external_command completed but no result files found "
                f"matching '{result_glob}' in {output_dir}"
            )

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
            raise RuntimeError(
                "external_command produced result files but none contained "
                "valid results matching the simulation batch"
            )

        combined = pd.concat(all_imported, ignore_index=True)
        return combined, {
            "status": "results_imported",
            "mode": "external_command",
            "generation": generation,
            "imported_count": len(combined),
        }

    else:
        raise ValueError(f"Unknown simulation mode: {mode}")