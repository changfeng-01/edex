"""PIA simulation batch contract and result import.

build_simulation_batch() wraps already-scheduled selected_candidates
(from suggest_next_run()) with generation metadata and a manifest.
It does NOT re-schedule -- scheduling is handled by suggest_next_run().

import_simulation_results() imports and validates simulation results
for a generation, enforcing required columns and boundary labels.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd


def build_simulation_batch(
    selected: pd.DataFrame,
    config: Mapping[str, Any],
    generation: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a simulation batch from already-scheduled selected candidates.

    The input `selected` DataFrame is expected to come from
    suggest_next_run(), which already attaches evaluation_schedule
    metadata.  This function wraps it with generation-level metadata
    and produces a manifest.
    """
    batch = selected.copy()
    batch["generation"] = generation

    manifest: dict[str, Any] = {
        "generation": generation,
        "candidate_count": len(batch),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "claim_boundary": (
            "candidate suggestions require simulation before claims"
        ),
    }

    return batch, manifest


def import_simulation_results(
    result_csv: str | Path,
    simulation_batch: pd.DataFrame,
    config: Mapping[str, Any],
    generation: int,
) -> pd.DataFrame:
    """Import and validate simulation results for a generation.

    Rules:
    - Require configured result columns; return empty if missing.
    - Keep only rows whose candidate_id is in the simulation batch.
    - Merge missing parameter columns from the simulation batch.
    - Set generation, source, and boundary labels.
    """
    result_path = Path(result_csv)
    if not result_path.exists():
        return pd.DataFrame()

    try:
        results = pd.read_csv(result_path)
    except Exception:
        return pd.DataFrame()

    required_cols = config.get("simulation_executor", {}).get(
        "result_required_columns",
        ["candidate_id", "overall_score", "hard_constraint_passed"],
    )

    # Check required columns
    missing = [c for c in required_cols if c not in results.columns]
    if missing:
        return pd.DataFrame()

    # Keep only candidates in the simulation batch
    batch_ids = set(simulation_batch["candidate_id"])
    results = results[results["candidate_id"].isin(batch_ids)].copy()

    if len(results) == 0:
        return results

    # Merge missing parameter columns from batch
    for col in simulation_batch.columns:
        if col not in results.columns and col != "candidate_id":
            mapping = dict(zip(simulation_batch["candidate_id"], simulation_batch[col]))
            results[col] = results["candidate_id"].map(mapping)

    # Set metadata
    results["generation"] = generation
    results["source"] = "simulation_result"
    results["data_source"] = "real_simulation_csv"
    results["engineering_validity"] = "simulation_only"

    return results.reset_index(drop=True)