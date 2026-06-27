"""Deterministic local simulator fixture for PIA closed-loop tests."""
from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd


def run_local_fixture_simulator(
    simulation_batch: pd.DataFrame,
    config: Mapping[str, Any],
    generation: int,
) -> pd.DataFrame:
    """Produce deterministic simulation-like result rows.

    This is a CI fixture, not a physical simulator.  It intentionally emits
    simulation-only result rows through the same CSV import contract used by
    real external simulators.
    """
    parameter_columns = [
        col for col in config.get("parameter_columns", [])
        if col in simulation_batch.columns
    ]
    rows: list[dict[str, Any]] = []
    for idx, row in simulation_batch.reset_index(drop=True).iterrows():
        if parameter_columns:
            numeric = pd.to_numeric(row[parameter_columns], errors="coerce").fillna(0.0)
            param_signal = float(numeric.sum())
        else:
            param_signal = float(idx)
        score = 82.0 + 8.0 * math.sin(param_signal + generation * 0.37 + idx * 0.11)
        score = max(0.0, min(100.0, score))
        rows.append({
            "candidate_id": row["candidate_id"],
            "overall_score": round(score, 6),
            "hard_constraint_passed": bool(score >= 75.0),
            "simulator_mode": "local_fixture",
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        })
    return pd.DataFrame(rows)
