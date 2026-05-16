from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd


@dataclass(frozen=True)
class ColumnMapping:
    original_name: str
    normalized_name: str


@dataclass
class RealWaveformTable:
    path: Path
    frame: pd.DataFrame
    columns: list[ColumnMapping]

    @property
    def time(self):
        return self.frame["time"].to_numpy()


def normalize_column_name(column: str) -> str:
    text = column.strip()
    if text.upper() in {"XVAL", "TIME"}:
        return "time"
    match = re.fullmatch(r"v\((.+)\)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()
    return text.lower()


def read_real_waveform(path: Path, required_nodes: list[str] | None = None) -> RealWaveformTable:
    if not path.exists():
        raise FileNotFoundError(f"Waveform file not found: {path}")
    raw = _read_flexible_table(path)
    mappings = [ColumnMapping(str(column), normalize_column_name(str(column))) for column in raw.columns]
    rename = {mapping.original_name: mapping.normalized_name for mapping in mappings}
    frame = raw.rename(columns=rename).apply(pd.to_numeric, errors="coerce")
    if "time" not in frame.columns:
        raise ValueError(f"Waveform file needs a time column named XVAL or TIME: {path}")
    frame = frame.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    if required_nodes:
        missing = [node for node in required_nodes if node not in frame.columns]
        if missing:
            available = ", ".join(str(column) for column in frame.columns)
            raise ValueError(f"Waveform file {path} is missing required columns: {', '.join(missing)}. Available columns: {available}")
    return RealWaveformTable(path=path, frame=frame, columns=mappings)


def _read_flexible_table(path: Path) -> pd.DataFrame:
    header = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
    if "," in header:
        return pd.read_csv(path, skipinitialspace=True)
    return pd.read_csv(path, sep=r"\s+", engine="python")
