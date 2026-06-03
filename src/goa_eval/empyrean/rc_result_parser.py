from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

from goa_eval.empyrean.schemas import STATUS_NOT_EVALUABLE, STATUS_NOT_PROVIDED, STATUS_PASSED, base_versions
from goa_eval.io_utils import write_json


def parse_rc_result(path: Path | None, output_path: Path) -> dict[str, Any]:
    if path is None or not path.exists():
        summary = {
            **base_versions(),
            "status": STATUS_NOT_PROVIDED,
            "has_rc_data": False,
            "resistance_unit": None,
            "capacitance_unit": None,
            "total_resistance": None,
            "total_capacitance": None,
            "max_resistance": None,
            "max_capacitance": None,
            "net_count": 0,
            "raw_file_path": str(path) if path else None,
            "grouped_by_net": [],
            "message": "RC result file was not provided.",
        }
        write_json(output_path, summary)
        return summary
    try:
        frame = _read_rc_table(path)
        result = summarize_rc_frame(frame, path)
    except Exception as exc:
        result = {
            **base_versions(),
            "status": STATUS_NOT_EVALUABLE,
            "has_rc_data": False,
            "resistance_unit": None,
            "capacitance_unit": None,
            "total_resistance": None,
            "total_capacitance": None,
            "max_resistance": None,
            "max_capacitance": None,
            "net_count": 0,
            "raw_file_path": str(path),
            "grouped_by_net": [],
            "message": f"{type(exc).__name__}: {exc}",
        }
    write_json(output_path, result)
    return result


def summarize_rc_frame(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    resistance_column = _find_column(frame, ["resistance", "res", "r_ohm", "r", "ohm"])
    capacitance_column = _find_column(frame, ["capacitance", "cap", "c_ff", "c_pf", "c", "ff", "pf"])
    net_column = _find_column(frame, ["net", "signal", "label", "node"])
    if resistance_column is None and capacitance_column is None:
        raise ValueError("No resistance or capacitance columns were recognized.")
    resistance = _numeric_series(frame[resistance_column]) if resistance_column else pd.Series(dtype=float)
    capacitance = _numeric_series(frame[capacitance_column]) if capacitance_column else pd.Series(dtype=float)
    grouped = []
    if net_column:
        work = pd.DataFrame({"net": frame[net_column].astype(str)})
        if resistance_column:
            work["resistance"] = resistance
        if capacitance_column:
            work["capacitance"] = capacitance
        grouped_frame = work.groupby("net", dropna=False).sum(numeric_only=True).reset_index()
        grouped = grouped_frame.to_dict(orient="records")
    return {
        **base_versions(),
        "status": STATUS_PASSED,
        "has_rc_data": True,
        "resistance_unit": _unit_from_column(str(resistance_column), "ohm") if resistance_column else None,
        "capacitance_unit": _unit_from_column(str(capacitance_column), "F") if capacitance_column else None,
        "total_resistance": _sum_or_none(resistance),
        "total_capacitance": _sum_or_none(capacitance),
        "max_resistance": _max_or_none(resistance),
        "max_capacitance": _max_or_none(capacitance),
        "net_count": int(frame[net_column].nunique()) if net_column else int(len(frame)),
        "raw_file_path": str(path),
        "grouped_by_net": grouped,
        "message": "",
    }


def _read_rc_table(path: Path) -> pd.DataFrame:
    first = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
    if "," in first:
        return pd.read_csv(path, skipinitialspace=True)
    return pd.read_csv(path, sep=r"\s+", engine="python")


def _find_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {_normalize_name(column): str(column) for column in frame.columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for key, original in normalized.items():
        if any(len(candidate) > 1 and candidate in key for candidate in candidates):
            return original
    return None


def _normalize_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").dropna()


def _sum_or_none(series: pd.Series) -> float | None:
    if series.empty:
        return None
    return float(series.sum())


def _max_or_none(series: pd.Series) -> float | None:
    if series.empty:
        return None
    return float(series.max())


def _unit_from_column(column: str, fallback: str) -> str:
    lower = column.lower()
    if "pf" in lower:
        return "pF"
    if "ff" in lower:
        return "fF"
    if "kohm" in lower:
        return "kOhm"
    if "ohm" in lower:
        return "ohm"
    return fallback
