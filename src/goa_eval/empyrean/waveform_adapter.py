from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

from goa_eval.empyrean.schemas import STATUS_PASSED, WaveformConversionResult, base_versions
from goa_eval.io_utils import write_json


TIME_COLUMN_NAMES = {"time", "xval"}


def convert_empyrean_waveform_csv(input_path: Path, output_dir: Path) -> WaveformConversionResult:
    if not input_path.exists():
        raise FileNotFoundError(f"Empyrean waveform file not found: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(input_path, skipinitialspace=True)
    time_column = _find_time_column(list(raw.columns))
    if time_column is None:
        available = ", ".join(str(column) for column in raw.columns)
        raise ValueError(f"Empyrean waveform CSV needs a TIME/time/XVAL/xval column. Available columns: {available}")

    rows: dict[str, Any] = {"time": pd.to_numeric(raw[time_column], errors="coerce")}
    column_map: list[dict[str, Any]] = [
        {"original_name": str(time_column), "normalized_name": "time", "role": "time"}
    ]
    used = {"time"}
    for column in raw.columns:
        if column == time_column:
            continue
        normalized = normalize_empyrean_signal_column(str(column))
        normalized = _deduplicate(normalized, used)
        used.add(normalized)
        rows[normalized] = pd.to_numeric(raw[column], errors="coerce")
        column_map.append(
            {
                "original_name": str(column),
                "normalized_name": normalized,
                "role": "signal",
            }
        )

    normalized_frame = pd.DataFrame(rows).dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    waveform_path = output_dir / "normalized_waveform.csv"
    map_path = output_dir / "waveform_column_map.json"
    normalized_frame.to_csv(waveform_path, index=False, encoding="utf-8-sig")
    write_json(
        map_path,
        {
            **base_versions(),
            "input_path": str(input_path),
            "normalized_waveform_path": str(waveform_path),
            "columns": column_map,
        },
    )
    return WaveformConversionResult(
        **base_versions(),
        status=STATUS_PASSED,
        input_path=str(input_path),
        normalized_waveform_path=str(waveform_path),
        column_map_path=str(map_path),
        time_column=str(time_column),
        signal_count=len(column_map) - 1,
    )


def normalize_empyrean_signal_column(column: str) -> str:
    text = column.strip()
    match = re.fullmatch(r"v\((.+)\)", text, flags=re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    text = text.replace("\\", ".").replace("/", ".")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", text)
    return text.strip("_").lower() or "signal"


def _find_time_column(columns: list[Any]) -> Any | None:
    for column in columns:
        if str(column).strip().lower() in TIME_COLUMN_NAMES:
            return column
    return None


def _deduplicate(name: str, used: set[str]) -> str:
    if name not in used:
        return name
    index = 2
    while f"{name}_{index}" in used:
        index += 1
    return f"{name}_{index}"
