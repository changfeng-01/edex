from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import pandas as pd


def load_history(run_dir: Path) -> pd.DataFrame:
    history_json = run_dir / "optimization_history.json"
    leaderboard_csv = run_dir / "optimization_leaderboard.csv"
    rows: list[dict[str, Any]] = []
    if history_json.exists():
        try:
            payload = json.loads(history_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        raw_rows = payload.get("history", payload if isinstance(payload, list) else [])
        if isinstance(raw_rows, list):
            rows = [row for row in raw_rows if isinstance(row, dict)]
    if not rows and leaderboard_csv.exists():
        return pd.read_csv(leaderboard_csv)
    return pd.DataFrame(rows)


def load_optional_csv(run_dir: Path, filename: str) -> pd.DataFrame:
    path = run_dir / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_optional_json(run_dir: Path, filename: str) -> dict[str, Any]:
    path = run_dir / filename
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def iter_offline_run_dirs(runs_root: Path) -> list[tuple[str, str, Path]]:
    if not runs_root.exists():
        return []
    runs: list[tuple[str, str, Path]] = []
    for algorithm_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        for seed_dir in sorted(path for path in algorithm_dir.iterdir() if path.is_dir()):
            runs.append((algorithm_dir.name, seed_dir.name, seed_dir))
    return runs
