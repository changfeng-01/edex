from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


TIME_FACTORS = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "ms": 1.0e-3,
    "us": 1.0e-6,
    "µs": 1.0e-6,
    "ns": 1.0e-9,
    "ps": 1.0e-12,
}

VOLTAGE_FACTORS = {
    "v": 1.0,
    "volt": 1.0,
    "volts": 1.0,
    "mv": 1.0e-3,
}


@dataclass(frozen=True)
class NormalizedWaveform:
    frame: pd.DataFrame
    quality: dict[str, Any]


def normalize_wpd_frame(
    raw: pd.DataFrame,
    *,
    time_unit: str = "s",
    voltage_unit: str = "V",
    curve_map: dict[str, str] | None = None,
    resample_step: float | None = None,
) -> NormalizedWaveform:
    curve_map = curve_map or {}
    raw = raw.copy()
    raw.columns = [str(column).strip() for column in raw.columns]
    kind = _detect_input_kind(raw)
    quality: dict[str, Any] = {
        "input_format": kind,
        "time_unit_input": time_unit,
        "voltage_unit_input": voltage_unit,
        "time_unit_output": "s",
        "voltage_unit_output": "V",
        "duplicate_time_points_merged": 0,
        "interpolated": False,
        "resample_step_s": resample_step,
        "curve_map": curve_map,
        "warnings": [],
    }

    if kind == "multi_curve":
        long_frame = _multi_curve_long_frame(raw, time_unit=time_unit, voltage_unit=voltage_unit)
    else:
        long_frame = _single_curve_long_frame(raw, time_unit=time_unit, voltage_unit=voltage_unit)

    normalized_curves = _normalize_curve_names(long_frame["curve"].dropna().astype(str).unique().tolist(), curve_map)
    long_frame["curve"] = long_frame["curve"].map(normalized_curves)
    frames: dict[str, pd.DataFrame] = {}
    for curve, curve_frame in long_frame.groupby("curve", sort=False):
        cleaned, duplicate_count = _dedupe_curve(curve_frame[["time", "voltage"]])
        quality["duplicate_time_points_merged"] += duplicate_count
        frames[str(curve)] = cleaned

    if not frames:
        raise ValueError("No waveform samples were found in WPD CSV.")

    output = _wide_frame(frames, resample_step=resample_step)
    quality["output_columns"] = list(output.columns)
    quality["sample_count"] = int(len(output))
    quality["curve_count"] = int(len(frames))
    quality["interpolated"] = bool(len(frames) > 1 or resample_step is not None)
    if output["time"].duplicated().any():
        quality["warnings"].append("duplicate_time_points_remain_after_normalization")
    if not output["time"].is_monotonic_increasing:
        quality["warnings"].append("time_not_monotonic_after_normalization")
    return NormalizedWaveform(frame=output, quality=quality)


def load_curve_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "curve_map" in raw and isinstance(raw["curve_map"], dict):
        raw = raw["curve_map"]
    if "curves" in raw and isinstance(raw["curves"], dict):
        raw = raw["curves"]
    if not isinstance(raw, dict):
        raise ValueError(f"Curve map must be a YAML mapping: {path}")
    return {str(key): str(value) for key, value in raw.items()}


def parse_duration(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?)([a-zA-Zµ]*)", text)
    if not match:
        raise ValueError(f"Invalid duration: {value}")
    amount = float(match.group(1))
    unit = (match.group(2) or "s").lower()
    if unit not in TIME_FACTORS:
        raise ValueError(f"Unsupported time unit in duration {value!r}")
    return amount * TIME_FACTORS[unit]


def time_factor(unit: str) -> float:
    normalized = str(unit).strip().lower()
    if normalized not in TIME_FACTORS:
        raise ValueError(f"Unsupported time unit: {unit}")
    return TIME_FACTORS[normalized]


def voltage_factor(unit: str) -> float:
    normalized = str(unit).strip().lower()
    if normalized not in VOLTAGE_FACTORS:
        raise ValueError(f"Unsupported voltage unit: {unit}")
    return VOLTAGE_FACTORS[normalized]


def _detect_input_kind(raw: pd.DataFrame) -> str:
    lower = {column.lower(): column for column in raw.columns}
    if "curve" in lower:
        return "multi_curve"
    if {"x", "y"} <= set(lower):
        return "wpd_xy"
    return "two_column"


def _single_curve_long_frame(raw: pd.DataFrame, *, time_unit: str, voltage_unit: str) -> pd.DataFrame:
    lower = {column.lower(): column for column in raw.columns}
    if {"x", "y"} <= set(lower):
        time_column = lower["x"]
        voltage_column = lower["y"]
    else:
        time_column = _find_column(raw.columns, ["time", "x"])
        voltage_column = _find_column(raw.columns, ["voltage", "v", "y"])
    resolved_time_unit = _unit_from_column(time_column, fallback=time_unit)
    resolved_voltage_unit = _unit_from_column(voltage_column, fallback=voltage_unit)
    frame = pd.DataFrame(
        {
            "curve": "o1",
            "time": pd.to_numeric(raw[time_column], errors="coerce") * time_factor(resolved_time_unit),
            "voltage": pd.to_numeric(raw[voltage_column], errors="coerce") * voltage_factor(resolved_voltage_unit),
        }
    )
    return frame.dropna(subset=["time", "voltage"])


def _multi_curve_long_frame(raw: pd.DataFrame, *, time_unit: str, voltage_unit: str) -> pd.DataFrame:
    curve_column = _find_column(raw.columns, ["curve", "series", "trace"])
    time_column = _find_column(raw.columns, ["time", "x"])
    voltage_column = _find_column(raw.columns, ["voltage", "v", "y"])
    resolved_time_unit = _unit_from_column(time_column, fallback=time_unit)
    resolved_voltage_unit = _unit_from_column(voltage_column, fallback=voltage_unit)
    frame = pd.DataFrame(
        {
            "curve": raw[curve_column].astype(str).str.strip(),
            "time": pd.to_numeric(raw[time_column], errors="coerce") * time_factor(resolved_time_unit),
            "voltage": pd.to_numeric(raw[voltage_column], errors="coerce") * voltage_factor(resolved_voltage_unit),
        }
    )
    return frame.dropna(subset=["curve", "time", "voltage"])


def _find_column(columns: pd.Index, candidates: list[str]) -> str:
    lower = {str(column).strip().lower(): str(column) for column in columns}
    for candidate in candidates:
        for key, original in lower.items():
            if key == candidate or key.startswith(candidate + "_"):
                return original
    if len(columns) >= 2 and "time" in candidates:
        return str(columns[0])
    if len(columns) >= 2:
        return str(columns[1])
    raise ValueError(f"Could not find any of columns: {', '.join(candidates)}")


def _unit_from_column(column: str, *, fallback: str) -> str:
    lower = column.strip().lower()
    for suffix in ["_us", "_ns", "_ms", "_s", "_v", "_mv"]:
        if lower.endswith(suffix):
            return suffix[1:]
    return fallback


def _normalize_curve_names(curves: list[str], curve_map: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    next_output = 1
    for curve in curves:
        mapped = curve_map.get(curve)
        if mapped:
            normalized[curve] = mapped
            continue
        if re.fullmatch(r"o[1-9][0-9]*", curve.lower()) and curve.lower() not in normalized.values():
            normalized[curve] = f"o{next_output}"
        else:
            normalized[curve] = f"o{next_output}"
        next_output += 1
    return normalized


def _dedupe_curve(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    sorted_frame = frame.dropna().sort_values("time")
    duplicate_count = int(sorted_frame["time"].duplicated().sum())
    deduped = sorted_frame.groupby("time", as_index=False, sort=True)["voltage"].mean()
    return deduped, duplicate_count


def _wide_frame(frames: dict[str, pd.DataFrame], *, resample_step: float | None) -> pd.DataFrame:
    starts = [frame["time"].min() for frame in frames.values()]
    ends = [frame["time"].max() for frame in frames.values()]
    if resample_step is not None:
        start = min(starts)
        end = max(ends)
        times = np.arange(start, end + resample_step * 0.5, resample_step)
    elif len(frames) == 1:
        times = next(iter(frames.values()))["time"].to_numpy(dtype=float)
    else:
        times = np.array(sorted(set(np.concatenate([frame["time"].to_numpy(dtype=float) for frame in frames.values()]))))

    output = pd.DataFrame({"time": times})
    for curve, frame in frames.items():
        output[curve] = np.interp(times, frame["time"].to_numpy(dtype=float), frame["voltage"].to_numpy(dtype=float))
    columns = ["time", *sorted([column for column in output.columns if column != "time"], key=_node_sort_key)]
    return output[columns]


def _node_sort_key(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"o([0-9]+)", value)
    if match:
        return int(match.group(1)), value
    return 10_000, value
