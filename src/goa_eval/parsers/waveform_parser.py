from pathlib import Path
import re

import pandas as pd

from goa_eval.models.waveform import WaveformBundle


def read_waveform_csv(path: Path, version_name: str) -> WaveformBundle:
    df = _read_flexible_csv(path)
    original_columns = list(df.columns)
    renamed = {_column: _normalize_column(_column) for _column in df.columns}
    df = df.rename(columns=renamed)
    if "time" not in df.columns:
        raise ValueError(f"Waveform CSV needs a time or XVAL column: {path}")
    df = df.apply(pd.to_numeric, errors="coerce")
    time = df["time"].to_numpy()

    internal_nodes = []
    signals = {}
    for col in df.columns:
        if col == "time":
            continue
        if col.startswith("xs"):
            internal_nodes.append(col)
            continue
        signals[col] = df[col].to_numpy()

    metadata = {
        "waveform_csv": str(path),
        "original_columns": original_columns,
        "normalized_columns": renamed,
        "internal_nodes": internal_nodes,
        "sample_count": int(len(time)),
        "time_start": float(time[0]) if len(time) else None,
        "time_end": float(time[-1]) if len(time) else None,
    }
    return WaveformBundle(version_name, time, signals, "simulation", "simulation_result", metadata=metadata)


def _read_flexible_csv(path: Path) -> pd.DataFrame:
    header = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
    if "," in header:
        return pd.read_csv(path, skipinitialspace=True)
    return pd.read_csv(path, sep=r"\s+", engine="python")


def _normalize_column(column: str) -> str:
    text = column.strip()
    if text.upper() in {"XVAL", "TIME"}:
        return "time"
    match = re.fullmatch(r"v\((.+)\)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text
