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


def attach_goa_benchmark_metrics(analysis_metrics: dict, *, summary: dict, stage_rows: list[dict], profile: dict) -> dict:
    if not _profile_uses_goa_benchmark(profile):
        return analysis_metrics
    metrics = dict(analysis_metrics)
    benchmark = build_goa_benchmark_metrics(summary=summary, stage_rows=stage_rows, profile=profile)
    metrics["goa_benchmark_metrics"] = benchmark
    not_evaluable = dict(metrics.get("not_evaluable", {}) or {})
    for metric in _missing_goa_metrics(benchmark):
        not_evaluable[metric] = _goa_missing_reason(metric)
    metrics["not_evaluable"] = not_evaluable
    metrics["not_evaluable_metrics"] = not_evaluable
    provenance = dict(metrics.get("metric_provenance", {}) or {})
    for metric, value in benchmark.items():
        if metric.startswith("reference_") or metric in {"benchmark_scope", "reference_note", "literature_baselines"}:
            normalization = "literature_reference"
        else:
            normalization = "derived_from_real_summary_or_stage_metrics"
        provenance[f"goa_benchmark_metrics.{metric}"] = {
            "source_file": "real_summary.json;real_metrics.csv",
            "source_analysis": "goa_benchmark_metrics",
            "source_column": metric,
            "unit": _metric_unit(metric),
            "parser": "attach_goa_benchmark_metrics",
            "normalization": normalization,
            "not_evaluable_reason": _goa_missing_reason(metric) if value is None else "",
        }
    metrics["metric_provenance"] = provenance
    return metrics


def build_goa_benchmark_metrics(*, summary: dict, stage_rows: list[dict], profile: dict) -> dict:
    reference = profile.get("reference", {}) or {}
    load = reference.get("load", {}) or {}
    timing = reference.get("timing", {}) or {}
    metrics = {
        "benchmark_scope": "literature_reference",
        "reference_note": str(reference.get("note", "Literature reference only; not a reproduced simulation.")),
        "fall_time_s": _safe_mean([row.get("FallTime", row.get("falling_time")) for row in stage_rows]),
        "rise_time_s": _safe_mean([row.get("RiseTime", row.get("rising_time")) for row in stage_rows]),
        "false_trigger_count": _number(summary.get("FalseTriggerCount", summary.get("False_trigger_count"))),
        "max_overlap_ratio": _number(summary.get("Max_overlap_ratio")),
        "voh_min_v": _number(summary.get("VOH_min")),
        "vol_max_v": _number(summary.get("VOL_max_all")),
        "pulse_width_mean_s": _number(summary.get("Width_mean")),
        "delay_std_s": _number(summary.get("Delay_std")),
        "reference_tfall_s": _number(timing.get("tfall_s", 0.97e-6)),
        "reference_trise_s": _number(timing.get("trise_s", 1.93e-6)),
        "reference_load_rl_ohm": _number(load.get("rl_ohm", 7200.0)),
        "reference_load_cl_f": _number(load.get("cl_f", 728e-12)),
        "literature_baselines": reference.get("baselines", {}),
        "power_total_w": None,
        "power_static_w": None,
        "power_dynamic_w": None,
        "area_proxy": None,
        "width_proxy": None,
        "delta_vth_margin_v": None,
    }
    metrics["baseline_comparisons"] = _baseline_comparisons(metrics, reference.get("baselines", {}))
    return metrics


def _profile_uses_goa_benchmark(profile: dict) -> bool:
    if str(profile.get("name", "")).startswith("goa_"):
        return True
    for rule in (profile.get("metrics", {}) or {}).values():
        if isinstance(rule, dict) and rule.get("source") == "goa_benchmark_metrics":
            return True
    return False


def _missing_goa_metrics(metrics: dict) -> list[str]:
    return [
        metric
        for metric in [
            "power_total_w",
            "power_static_w",
            "power_dynamic_w",
            "area_proxy",
            "width_proxy",
            "delta_vth_margin_v",
        ]
        if metrics.get(metric) is None
    ]


def _baseline_comparisons(metrics: dict, baselines: dict) -> dict[str, dict]:
    if not isinstance(baselines, dict):
        return {}
    mapping = {
        "fall_time_s": ("tfall_s", "smaller_better"),
        "power_total_w": ("power_total_w", "smaller_better"),
        "delta_vth_margin_v": ("delta_vth_margin_v", "larger_better"),
        "area_proxy": ("area_proxy", "smaller_better"),
    }
    comparisons: dict[str, dict] = {}
    for baseline_name, baseline in baselines.items():
        if not isinstance(baseline, dict):
            continue
        metric_rows = {}
        for current_metric, (baseline_metric, direction) in mapping.items():
            current_value = metrics.get(current_metric)
            baseline_value = baseline.get(baseline_metric)
            metric_rows[current_metric] = {
                "current_value": current_value,
                "baseline_value": baseline_value,
                "direction": direction,
                "relative_improvement": _relative_improvement(current_value, baseline_value, direction),
                "status": "evaluated" if current_value is not None and baseline_value is not None else "not_evaluable",
                "not_evaluable_reason": "" if current_value is not None and baseline_value is not None else _comparison_missing_reason(current_metric, baseline_metric, current_value, baseline_value),
            }
        comparisons[str(baseline_name)] = {
            "structure": baseline.get("structure", ""),
            "metrics": metric_rows,
        }
    return comparisons


def _relative_improvement(current_value: object, baseline_value: object, direction: str) -> float | None:
    current = _number(current_value)
    baseline = _number(baseline_value)
    if current is None or baseline in {None, 0.0}:
        return None
    if direction == "larger_better":
        return (current - baseline) / abs(baseline)
    return (baseline - current) / abs(baseline)


def _comparison_missing_reason(current_metric: str, baseline_metric: str, current_value: object, baseline_value: object) -> str:
    if current_value is None and baseline_value is None:
        return f"missing current {current_metric} and literature {baseline_metric}"
    if current_value is None:
        return f"missing current {current_metric}"
    return f"missing literature {baseline_metric}"


def _goa_missing_reason(metric: str) -> str:
    reasons = {
        "power_total_w": "missing supply power measurement in current CSV/artifacts",
        "power_static_w": "missing DC/static power measurement in current CSV/artifacts",
        "power_dynamic_w": "missing dynamic power decomposition in current CSV/artifacts",
        "area_proxy": "missing device/layout proxy source in current parameters/artifacts",
        "width_proxy": "missing GOA layout width proxy source in current parameters/artifacts",
        "delta_vth_margin_v": "missing threshold-drift or PVT sweep evidence in current artifacts",
    }
    return reasons.get(metric, f"missing {metric}")


def _safe_mean(values: list[object]) -> float | None:
    numbers = [_number(value) for value in values]
    finite = [value for value in numbers if value is not None]
    return float(np.nanmean(finite)) if finite else None


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
