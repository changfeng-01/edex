from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


def extract_analysis_metrics(run_dir: Path, *, topology_profile: str = "default") -> dict:
    provenance: dict[str, dict] = {}
    op_metrics, op_reason = _op_metrics(run_dir / "op_metrics.csv", provenance)
    ac_metrics, ac_reason = _ac_metrics(run_dir / "ac_metrics.csv", provenance)
    dc_metrics, dc_reason = _dc_metrics(run_dir / "dc_metrics.csv", provenance)
    tran_metrics, tran_reason = _tran_metrics(run_dir / "tran_metrics.csv", provenance)
    not_evaluable = {}
    for key, reason in {
        "op_metrics": op_reason,
        "ac_metrics": ac_reason,
        "dc_metrics": dc_reason,
        "tran_metrics": tran_reason,
    }.items():
        if reason:
            not_evaluable[key] = reason
    return {
        "topology_profile": topology_profile,
        "op_metrics": op_metrics,
        "ac_metrics": ac_metrics,
        "dc_metrics": dc_metrics,
        "tran_metrics": tran_metrics,
        "not_evaluable": not_evaluable,
        "not_evaluable_metrics": not_evaluable,
        "metric_provenance": provenance,
    }


def write_analysis_metrics(path: Path, metrics: dict) -> dict:
    from goa_eval.io_utils import write_json

    write_json(path, metrics)
    return metrics


def _op_metrics(path: Path, provenance: dict[str, dict]) -> tuple[dict, str | None]:
    if not path.exists() or path.stat().st_size == 0:
        return {}, "missing op_metrics.csv"
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return {}, f"unreadable op_metrics.csv: {exc}"
    values = _metric_value_frame(frame)
    for metric in values:
        _add_provenance(
            provenance,
            "op_metrics",
            metric,
            path,
            unit=_metric_unit(metric),
            source_column=metric if metric in frame.columns else "value",
            normalization="numeric",
        )
    voltage = _number(values.get("supply_voltage_v"))
    current = _number(values.get("supply_current_a"))
    if voltage is not None and current is not None:
        values["static_power_w"] = abs(voltage * current)
        _add_provenance(
            provenance,
            "op_metrics",
            "static_power_w",
            path,
            unit="W",
            source_column="supply_voltage_v;supply_current_a",
            normalization="abs(voltage * current)",
        )
    return values, None


def _ac_metrics(path: Path, provenance: dict[str, dict]) -> tuple[dict, str | None]:
    if not path.exists() or path.stat().st_size == 0:
        return {}, "missing ac_metrics.csv"
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return {}, f"unreadable ac_metrics.csv: {exc}"
    frequency = _series(frame, ["frequency_hz", "freq", "frequency"])
    gain = _series(frame, ["gain_db", "vdb(out)", "db"])
    if frequency is None or gain is None or len(frame) == 0:
        return {}, "ac_metrics.csv missing frequency_hz/gain_db"
    dc_gain = _number(gain.iloc[0])
    bandwidth = None
    unity = None
    if dc_gain is not None:
        target = dc_gain - 3.0
        bandwidth = _first_frequency_below(frequency, gain, target)
    unity = _first_frequency_below(frequency, gain, 0.0)
    metrics = {
        "dc_gain_db": dc_gain,
        "bandwidth_3db_hz": bandwidth,
        "unity_gain_hz": unity,
    }
    for metric, unit in {"dc_gain_db": "dB", "bandwidth_3db_hz": "Hz", "unity_gain_hz": "Hz"}.items():
        _add_provenance(
            provenance,
            "ac_metrics",
            metric,
            path,
            unit=unit,
            source_column=str(gain.name),
            normalization="derived_from_frequency_gain_curve",
        )
    return metrics, None


def _dc_metrics(path: Path, provenance: dict[str, dict]) -> tuple[dict, str | None]:
    if not path.exists() or path.stat().st_size == 0:
        return {}, "missing dc_metrics.csv"
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return {}, f"unreadable dc_metrics.csv: {exc}"
    input_v = _series(frame, ["input_v", "vin", "v(in)"])
    output_v = _series(frame, ["output_v", "vout", "v(out)"])
    if input_v is None or output_v is None or len(frame) == 0:
        return {}, "dc_metrics.csv missing input_v/output_v"
    output_values = pd.to_numeric(output_v, errors="coerce")
    input_values = pd.to_numeric(input_v, errors="coerce")
    midpoint = (float(np.nanmax(output_values)) + float(np.nanmin(output_values))) / 2.0
    index = int((output_values - midpoint).abs().idxmin())
    metrics = {
        "switching_threshold_v": _number(input_values.iloc[index]),
        "output_swing_v": float(np.nanmax(output_values) - np.nanmin(output_values)),
        "hysteresis_proxy_v": None,
    }
    for metric in metrics:
        _add_provenance(
            provenance,
            "dc_metrics",
            metric,
            path,
            unit="V",
            source_column=f"{input_v.name};{output_v.name}",
            normalization="derived_from_dc_transfer_curve",
        )
    return metrics, None


def _tran_metrics(path: Path, provenance: dict[str, dict]) -> tuple[dict, str | None]:
    if not path.exists() or path.stat().st_size == 0:
        fallback = path.with_name("waveform.csv")
        if fallback.exists() and fallback.stat().st_size > 0:
            path = fallback
        else:
            return {}, "missing tran_metrics.csv"
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return {}, f"unreadable {path.name}: {exc}"
    time = _series(frame, ["TIME", "time", "xval"])
    output = _first_output_series(frame)
    if time is None or output is None or len(frame) == 0:
        return {}, f"{path.name} missing time/output"
    t = pd.to_numeric(time, errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(output, errors="coerce").to_numpy(dtype=float)
    swing = float(np.nanmax(y) - np.nanmin(y))
    frequency = _frequency_from_crossings(t, y)
    slew = _slew_rate(t, y)
    metrics = {
        "output_swing_v": swing,
        "frequency_hz": frequency,
        "period_std_s": _period_std(t, y),
        "slew_rate_v_per_s": slew,
        "startup_time_s": _startup_time(t, y),
    }
    for metric in metrics:
        _add_provenance(
            provenance,
            "tran_metrics",
            metric,
            path,
            unit=_metric_unit(metric),
            source_column=str(output.name),
            normalization="derived_from_time_domain_waveform",
        )
    return metrics, None


def _metric_value_frame(frame: pd.DataFrame) -> dict:
    if {"metric", "value"} <= set(frame.columns):
        return {str(row["metric"]): _number(row["value"]) for _, row in frame.iterrows()}
    if len(frame) == 1:
        return {str(column): _number(frame.iloc[0][column]) for column in frame.columns}
    return {}


def _series(frame: pd.DataFrame, names: list[str]) -> pd.Series | None:
    lookup = {str(column).strip().lower(): column for column in frame.columns}
    for name in names:
        column = lookup.get(name.lower())
        if column is not None:
            return frame[column]
    return None


def _first_output_series(frame: pd.DataFrame) -> pd.Series | None:
    for column in frame.columns:
        lowered = str(column).strip().lower()
        if lowered in {"time", "xval", "frequency_hz", "freq", "frequency"}:
            continue
        return frame[column]
    return None


def _first_frequency_below(frequency: pd.Series, gain: pd.Series, target: float) -> float | None:
    freq = pd.to_numeric(frequency, errors="coerce")
    values = pd.to_numeric(gain, errors="coerce")
    mask = values <= target
    if not mask.any():
        return None
    return _number(freq[mask].iloc[0])


def _frequency_from_crossings(time: np.ndarray, signal: np.ndarray) -> float | None:
    crossings = _rising_crossings(time, signal)
    if len(crossings) < 2:
        return None
    periods = np.diff(crossings)
    mean = float(np.nanmean(periods))
    return None if mean <= 0 else 1.0 / mean


def _period_std(time: np.ndarray, signal: np.ndarray) -> float | None:
    crossings = _rising_crossings(time, signal)
    if len(crossings) < 3:
        return None
    return float(np.nanstd(np.diff(crossings)))


def _rising_crossings(time: np.ndarray, signal: np.ndarray) -> list[float]:
    threshold = (float(np.nanmax(signal)) + float(np.nanmin(signal))) / 2.0
    crossings = []
    for index in np.where((signal[:-1] <= threshold) & (signal[1:] > threshold))[0]:
        t0, t1 = float(time[index]), float(time[index + 1])
        y0, y1 = float(signal[index]), float(signal[index + 1])
        if y1 == y0:
            crossings.append(t1)
        else:
            crossings.append(t0 + (threshold - y0) / (y1 - y0) * (t1 - t0))
    return crossings


def _slew_rate(time: np.ndarray, signal: np.ndarray) -> float | None:
    if len(time) < 2:
        return None
    dt = np.diff(time)
    dy = np.diff(signal)
    valid = dt > 0
    if not valid.any():
        return None
    return float(np.nanmax(np.abs(dy[valid] / dt[valid])))


def _startup_time(time: np.ndarray, signal: np.ndarray) -> float | None:
    swing = float(np.nanmax(signal) - np.nanmin(signal))
    if swing <= 0:
        return None
    low = float(np.nanmin(signal)) + 0.9 * swing
    indices = np.where(signal >= low)[0]
    if len(indices) == 0:
        return None
    return float(time[int(indices[0])])


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _add_provenance(
    provenance: dict[str, dict],
    source_analysis: str,
    metric: str,
    path: Path,
    *,
    unit: str,
    source_column: str,
    normalization: str,
    not_evaluable_reason: str = "",
) -> None:
    provenance[f"{source_analysis}.{metric}"] = {
        "unit": unit,
        "source_file": path.name,
        "source_analysis": source_analysis.replace("_metrics", ""),
        "source_column": source_column,
        "parser": "analysis_metrics",
        "normalization": normalization,
        "not_evaluable_reason": not_evaluable_reason,
    }


def _metric_unit(metric: str) -> str:
    if metric == "slew_rate_v_per_s":
        return "V/s"
    if metric.endswith("_hz"):
        return "Hz"
    if metric.endswith("_db"):
        return "dB"
    if metric.endswith("_w"):
        return "W"
    if metric.endswith("_a"):
        return "A"
    if metric.endswith("_s"):
        return "s"
    if metric.endswith("_v"):
        return "V"
    if metric.endswith("_deg"):
        return "deg"
    return ""
