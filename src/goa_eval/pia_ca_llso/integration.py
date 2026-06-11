from __future__ import annotations

from pathlib import Path

import pandas as pd


class HistoryAdapter:
    """CSV-first adapter for existing EDA optimization outputs."""

    def load(self, path: str | Path) -> pd.DataFrame:
        return pd.read_csv(path)


class CandidateAdapter:
    """CSV-first adapter for candidate tables emitted by current or future pipelines."""

    def load(self, path: str | Path) -> pd.DataFrame:
        frame = pd.read_csv(path)
        if "candidate_id" not in frame.columns:
            frame.insert(0, "candidate_id", [f"candidate_{idx}" for idx in range(len(frame))])
        return frame
