from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from goa_eval.windowing import boolean_intervals, non_selected_mask as hold_non_selected_mask, ripple_in_hold_window, total_pairwise_overlap


@dataclass(frozen=True)
class RealEvalConfig:
    high_threshold: float = 5.0
    low_threshold: float = 1.0
    target_pulse_width: float = 10.0e-6
    pulse_width_tolerance: float = 1.0e-6
    max_overlap_ratio: float = 0.10
    max_ripple_v: float = 0.5
    max_voltage_loss_v: float = 0.5
    max_delay_std: float = 0.5e-6
    min_voh_margin_v: float = 1.0
    target_refresh_hz: float | None = 60.0
    stage_group_size: int = 60
    selected_center_ratio: float = 0.80
    edge_buffer_ratio: float = 0.10
    min_pulse_width: float = 2.0e-6
    false_trigger_min_duration: float = 0.0
    ripple_mode: str = "hold"


@dataclass
class RealWaveformEvaluation:
    stage_rows: list[dict]
    summary: dict
    notes: list[str]


def _detect_output_nodes(frame: pd.DataFrame) -> list[str]:
    nodes = [str(column) for column in frame.columns if str(column).startswith("o") and str(column)[1:].isdigit()]
    if not nodes:
        return [f"o{i}" for i in range(1, 9)]
    return sorted(nodes, key=lambda name: int(name[1:]))


def evaluate_waveform_metrics(
    frame: pd.DataFrame,
    config: RealEvalConfig,
    output_nodes: list[str] | None = None,
    device_count: int | None = None,
) -> RealWaveformEvaluation:
    output_nodes = output_nodes or _detect_output_nodes(frame)
    time = frame["time"].to_numpy(dtype=float)
    stage_rows = []
    rise_edges = []
    widths = []
    voh_means = []
    vol_max_values = []
    ripples = []
    raw_ripples = []
    voltage_losses = []
    voltage_loss_ratios = []
    waveform_activity_scores = []

    for index, node in enumerate(output_nodes, start=1):
        signal = frame[node].to_numpy(dtype=float)
        metrics = compute_stage_metrics(time, signal, config)
        metrics.update({"stage": index, "node": node})
        stage_rows.append(metrics)
        rise_edges.append(metrics["rise_edge_time"])
        if metrics["PulseWidth"] is not None:
            widths.append(metrics["PulseWidth"])
        if metrics["VOH_mean"] is not None:
            voh_means.append(metrics["VOH_mean"])
        if metrics["VOL_max"] is not None:
            vol_max_values.append(metrics["VOL_max"])
        if metrics["Ripple"] is not None:
            ripples.append(metrics["Ripple"])
        if metrics.get("RippleRaw") is not None:
            raw_ripples.append(metrics["RippleRaw"])
        if metrics["VoltageLoss"] is not None:
            voltage_losses.append(metrics["VoltageLoss"])
        if metrics["VoltageLossRatio"] is not None:
            voltage_loss_ratios.append(metrics["VoltageLossRatio"])
        waveform_activity_scores.append(metrics["WaveformActivityScore"])

    delays = []
    overlaps = []
    for left, right in zip(stage_rows, stage_rows[1:]):
        if left["rise_edge_time"] is not None and right["rise_edge_time"] is not None:
            delay = right["rise_edge_time"] - left["rise_edge_time"]
            delays.append(delay)
        else:
            delay = None
        right["Delay"] = delay
        right["delay_to_next"] = delay
        overlap = _windows_overlap_duration(left["legal_windows"], right["legal_windows"], start_time=float(time[0]))
        overlaps.append(overlap)
        left["Overlap"] = overlap
        left["overlap_with_next"] = overlap
        denominator = _overlap_denominator(
            left["PulseWidth"],
            right["PulseWidth"],
            left["legal_windows"],
            right["legal_windows"],
        )
        ratio = overlap / denominator if denominator else None
        left["OverlapRatio"] = ratio
        left["overlap_ratio"] = ratio
    if stage_rows:
        stage_rows[0]["Delay"] = None
        stage_rows[0]["delay_to_next"] = None
        stage_rows[-1]["Overlap"] = None
        stage_rows[-1]["overlap_with_next"] = None
        stage_rows[-1]["OverlapRatio"] = None
        stage_rows[-1]["overlap_ratio"] = None

    seq_pass = _strictly_increasing([edge for edge in rise_edges if edge is not None]) and len([edge for edge in rise_edges if edge is not None]) == len(output_nodes)
    all_pulses_exist = all(row["PulseExist"] for row in stage_rows)
    false_trigger_count = sum(int(row["FalseTriggerCount"]) for row in stage_rows)
    overlap_ratios = [row["OverlapRatio"] for row in stage_rows if row.get("OverlapRatio") is not None]
    waveform_duration = float(time[-1] - time[0]) if len(time) >= 2 else 0.0
    frame_hold_time = _frame_hold_time(config.target_refresh_hz)
    max_voltage_loss = _safe_max(voltage_losses)
    summary = {
        "stage_count": len(output_nodes),
        "StageCount": len(output_nodes),
        "DeviceCount": device_count,
        "high_threshold": config.high_threshold,
        "low_threshold": config.low_threshold,
        "target_pulse_width": config.target_pulse_width,
        "pulse_width_tolerance": config.pulse_width_tolerance,
        "max_overlap_ratio_limit": config.max_overlap_ratio,
        "max_ripple_v_limit": config.max_ripple_v,
        "max_voltage_loss_v_limit": config.max_voltage_loss_v,
        "max_delay_std_limit": config.max_delay_std,
        "min_voh_margin_v": config.min_voh_margin_v,
        "target_refresh_hz": config.target_refresh_hz,
        "frame_hold_time": frame_hold_time,
        "waveform_duration": waveform_duration,
        "VOH_min": _safe_min(voh_means),
        "VOH_std": _safe_std(voh_means),
        "VOL_max_all": _safe_max(vol_max_values),
        "Delay_mean": _safe_mean(delays),
        "Delay_std": _safe_std(delays),
        "Width_mean": _safe_mean(widths),
        "Width_std": _safe_std(widths),
        "Max_ripple": _safe_max(ripples),
        "Max_ripple_raw": _safe_max(raw_ripples),
        "ripple_mode": config.ripple_mode,
        "Max_voltage_loss": max_voltage_loss,
        "Max_voltage_loss_ratio": _safe_max(voltage_loss_ratios),
        "Max_overlap": _safe_max(overlaps),
        "Max_overlap_ratio": _safe_max(overlap_ratios),
        "Seq_pass": bool(seq_pass),
        "All_pulses_exist": bool(all_pulses_exist),
        "FalseTriggerCount": int(false_trigger_count),
        "False_trigger_count": int(false_trigger_count),
        "WaveformActivityScore": _safe_mean(waveform_activity_scores),
        "SignalSwing_max": _safe_max([row.get("SignalSwing") for row in stage_rows]),
        "HighCrossingCount_total": int(sum(int(row.get("HighCrossingCount", 0) or 0) for row in stage_rows)),
    }
    low_freq_stable, low_freq_note = _low_frequency_stability(summary, config)
    summary["LowFreqStable"] = low_freq_stable
    summary["low_frequency_evaluation_note"] = low_freq_note
    summary.update(_large_cascade_summary(stage_rows, config))
    summary["Overall_status"] = _overall_status(summary, config)
    notes = [
        "本结果来自真实仿真 CSV，仅代表 simulation-only 基础分析。",
        "当前阈值为初步工程分析阈值，需要由电路规格进一步确认。",
    ]
    if device_count is None:
        notes.append("DeviceCount 当前未从 netlist 接入，暂记为 null。")
    return RealWaveformEvaluation(stage_rows=stage_rows, summary=summary, notes=notes)


def compute_stage_metrics(time: np.ndarray, signal: np.ndarray, config: RealEvalConfig) -> dict:
    legal_windows = detect_legal_pulse_windows(time, signal, config)
    window = legal_windows[0] if legal_windows else None
    pulse_exist = window is not None
    diagnostics = _signal_diagnostics(time, signal, config)
    if not pulse_exist:
        return {
            "PulseExist": False,
            "pulse_exist": False,
            "LegalPulseCount": 0,
            "legal_windows": [],
            "primary_window": None,
            "repeated_windows": [],
            "false_trigger_windows": [],
            "rise_edge_time": None,
            "fall_edge_time": None,
            "PulseWidth": None,
            "pulse_width": None,
            "VOH_mean": None,
            "VOH_max": None,
            "VOL_max": None,
            "Delay": None,
            "delay_to_next": None,
            "RiseTime": None,
            "FallTime": None,
            "rising_time": None,
            "falling_time": None,
            "Ripple": None,
            "RippleRaw": None,
            "ripple": None,
            "ripple_mode": config.ripple_mode,
            "VHoldEnd": None,
            "VoltageLoss": None,
            "VoltageLossRatio": None,
            "FalseTrigger": False,
            "FalseTriggerCount": 0,
            "false_trigger": False,
            "Overlap": None,
            "OverlapRatio": None,
            "overlap_with_next": None,
            "overlap_ratio": None,
            **diagnostics,
        }

    start, end = window
    selected = selected_window(window, config.selected_center_ratio)
    selected_mask = (time >= selected[0]) & (time <= selected[1])
    non_selected = non_selected_mask(time, legal_windows, config.edge_buffer_ratio)
    non_selected_signal = signal[non_selected]
    high_level = float(np.nanmax(signal[selected_mask])) if selected_mask.any() else float(np.nanmax(signal))
    low_level = float(np.nanmin(signal))
    v10 = low_level + 0.1 * (high_level - low_level)
    v90 = low_level + 0.9 * (high_level - low_level)
    edge_search_start = start - max(config.min_pulse_width, 10.0 * _sample_step(time))
    rise_edge = _first_crossing(time, signal, config.high_threshold, "rising", after=edge_search_start)
    if rise_edge is None and len(time) and start <= float(time[0]) and float(signal[0]) > config.high_threshold:
        rise_edge = float(time[0])
    fall_edge = _first_crossing(time, signal, config.high_threshold, "falling", after=rise_edge)
    if fall_edge is None and len(time) and end >= float(time[-1]) and float(signal[-1]) > config.high_threshold:
        fall_edge = float(time[-1])
    false_mask = non_selected & (signal > config.high_threshold)
    false_windows = [
        pulse
        for pulse in boolean_intervals(time, false_mask)
        if pulse[1] - pulse[0] >= config.false_trigger_min_duration
    ]
    rise_time = _edge_duration(time, signal, v10, v90, "rising", after=edge_search_start)
    fall_time = _edge_duration(time, signal, v90, v10, "falling", after=rise_edge)
    raw_ripple, vol_max = ripple_in_hold_window(time, signal, legal_windows, config.edge_buffer_ratio)
    ripple = _evaluated_ripple(raw_ripple, config)
    selected_signal = signal[selected_mask]
    voh_max = float(np.nanmax(selected_signal)) if selected_mask.any() else None
    v_hold_end = _last_finite(selected_signal) if selected_mask.any() else None
    voltage_loss = _voltage_loss(voh_max, v_hold_end)
    voltage_loss_ratio = voltage_loss / voh_max if voltage_loss is not None and voh_max not in (None, 0.0) else None
    row = {
        "PulseExist": True,
        "pulse_exist": True,
        "LegalPulseCount": len(legal_windows),
        "legal_windows": legal_windows,
        "primary_window": window,
        "repeated_windows": legal_windows[1:],
        "false_trigger_windows": false_windows,
        "rise_edge_time": rise_edge,
        "fall_edge_time": fall_edge,
        "PulseWidth": end - start,
        "pulse_width": end - start,
        "VOH_mean": float(np.nanmean(signal[selected_mask])) if selected_mask.any() else None,
        "VOH_max": voh_max,
        "VOL_max": vol_max,
        "Delay": None,
        "delay_to_next": None,
        "RiseTime": rise_time,
        "FallTime": fall_time,
        "rising_time": rise_time,
        "falling_time": fall_time,
        "Ripple": ripple,
        "RippleRaw": raw_ripple,
        "ripple": ripple,
        "ripple_mode": config.ripple_mode,
        "VHoldEnd": v_hold_end,
        "VoltageLoss": voltage_loss,
        "VoltageLossRatio": voltage_loss_ratio,
        "FalseTrigger": bool(false_windows),
        "FalseTriggerCount": len(false_windows),
        "false_trigger": bool(false_windows),
        "Overlap": None,
        "OverlapRatio": None,
        "overlap_with_next": None,
        "overlap_ratio": None,
        **diagnostics,
    }
    return row


def detect_main_pulse_window(time: np.ndarray, signal: np.ndarray, config: RealEvalConfig) -> tuple[float, float] | None:
    intervals = detect_legal_pulse_windows(time, signal, config)
    if not intervals:
        return None
    return intervals[0]


def detect_legal_pulse_windows(time: np.ndarray, signal: np.ndarray, config: RealEvalConfig) -> list[tuple[float, float]]:
    return [
        pulse
        for pulse in _high_intervals(time, signal, config.high_threshold)
        if pulse[1] - pulse[0] >= config.min_pulse_width
    ]


def selected_window(window: tuple[float, float], center_ratio: float) -> tuple[float, float]:
    start, end = window
    width = end - start
    pad = width * (1.0 - center_ratio) / 2.0
    return start + pad, end - pad


def non_selected_mask(time: np.ndarray, windows: list[tuple[float, float]], edge_buffer_ratio: float) -> np.ndarray:
    return hold_non_selected_mask(time, windows, edge_buffer_ratio)


def _high_intervals(time: np.ndarray, signal: np.ndarray, high_threshold: float) -> list[tuple[float, float]]:
    return boolean_intervals(time, signal > high_threshold)


def _first_crossing(time: np.ndarray, signal: np.ndarray, threshold: float, direction: str, after: float | None) -> float | None:
    if direction == "rising":
        indices = np.where((signal[:-1] <= threshold) & (signal[1:] > threshold))[0]
    else:
        indices = np.where((signal[:-1] >= threshold) & (signal[1:] < threshold))[0]
    for index in indices:
        crossing = _interpolate(time, signal, index, threshold)
        if after is None or crossing > after:
            return crossing
    return None


def _edge_duration(time: np.ndarray, signal: np.ndarray, start_threshold: float, end_threshold: float, direction: str, after: float | None) -> float | None:
    start = _first_crossing(time, signal, start_threshold, direction, after)
    end = _first_crossing(time, signal, end_threshold, direction, start)
    if start is None or end is None:
        return None
    return end - start


def _interpolate(time: np.ndarray, signal: np.ndarray, index: int, threshold: float) -> float:
    t0, t1 = float(time[index]), float(time[index + 1])
    v0, v1 = float(signal[index]), float(signal[index + 1])
    if v1 == v0:
        return t1
    return t0 + (threshold - v0) / (v1 - v0) * (t1 - t0)


def _strictly_increasing(values: list[float]) -> bool:
    return all(left < right for left, right in zip(values, values[1:]))


def _safe_mean(values: list[float]) -> float | None:
    values = _finite_values(values)
    return float(np.mean(values)) if values else None


def _safe_std(values: list[float]) -> float | None:
    values = _finite_values(values)
    return float(np.std(values)) if values else None


def _safe_min(values: list[float]) -> float | None:
    values = _finite_values(values)
    return float(min(values)) if values else None


def _safe_max(values: list[float]) -> float | None:
    values = _finite_values(values)
    return float(max(values)) if values else None


def _finite_values(values: list[float]) -> list[float]:
    return [float(value) for value in values if value is not None and not math.isnan(float(value))]


def _overall_status(summary: dict, config: RealEvalConfig) -> str:
    if not summary["Seq_pass"]:
        return "FAIL_SEQUENCE"
    if not summary["All_pulses_exist"]:
        return "FAIL_MISSING_PULSE"
    if summary["FalseTriggerCount"] > 0:
        return "FAIL_FALSE_TRIGGER"
    if summary["Max_overlap_ratio"] is not None and summary["Max_overlap_ratio"] > config.max_overlap_ratio:
        return "FAIL_OVERLAP"
    if summary["Max_ripple"] is not None and summary["Max_ripple"] > config.max_ripple_v:
        return "FAIL_RIPPLE"
    if summary["Max_voltage_loss"] is not None and summary["Max_voltage_loss"] > config.max_voltage_loss_v:
        return "FAIL_VOLTAGE_LOSS"
    if summary["Width_mean"] is not None and abs(summary["Width_mean"] - config.target_pulse_width) > config.pulse_width_tolerance:
        return "FAIL_WIDTH"
    if summary["VOH_min"] is not None and summary["VOH_min"] - config.high_threshold < config.min_voh_margin_v:
        return "FAIL_LOW_VOH"
    return "PASS_BASIC_SIMULATION_CHECK"


def _evaluated_ripple(raw_ripple: float | None, config: RealEvalConfig) -> float | None:
    mode = str(config.ripple_mode or "hold").lower()
    if mode in {"diagnostic_only", "diagnostic-only", "diagnostic"}:
        return None
    return raw_ripple


def _large_cascade_summary(stage_rows: list[dict], config: RealEvalConfig) -> dict:
    failed_rows = [row for row in stage_rows if _stage_failed(row, config)]
    first_failed = min((int(row["stage"]) for row in failed_rows), default=None)
    worst = _worst_stage(stage_rows, config)
    return {
        "worst_stage": worst,
        "first_failed_stage": first_failed,
        "VOH_p1": _percentile([row.get("VOH_mean") for row in stage_rows], 1),
        "VOH_p5": _percentile([row.get("VOH_mean") for row in stage_rows], 5),
        "VOH_p50": _percentile([row.get("VOH_mean") for row in stage_rows], 50),
        "VoltageLoss_p95": _percentile([row.get("VoltageLoss") for row in stage_rows], 95),
        "Delay_p95": _percentile([row.get("Delay") for row in stage_rows], 95),
        "Ripple_p95": _percentile([row.get("Ripple") for row in stage_rows], 95),
        "VOH_slope": _metric_slope(stage_rows, "VOH_mean"),
        "VoltageLoss_slope": _metric_slope(stage_rows, "VoltageLoss"),
        "Delay_slope": _metric_slope(stage_rows, "Delay"),
        "block_summary": _block_summary(stage_rows, config),
    }


def _block_summary(stage_rows: list[dict], config: RealEvalConfig) -> list[dict]:
    group_size = max(1, int(config.stage_group_size or 1))
    blocks = []
    for start in range(0, len(stage_rows), group_size):
        rows = stage_rows[start : start + group_size]
        if not rows:
            continue
        blocks.append(
            {
                "block_index": len(blocks) + 1,
                "stage_start": int(rows[0]["stage"]),
                "stage_end": int(rows[-1]["stage"]),
                "VOH_min": _safe_min([row.get("VOH_mean") for row in rows]),
                "Max_voltage_loss": _safe_max([row.get("VoltageLoss") for row in rows]),
                "Max_ripple": _safe_max([row.get("Ripple") for row in rows]),
                "Delay_mean": _safe_mean([row.get("Delay") for row in rows]),
                "failed_stage_count": sum(1 for row in rows if _stage_failed(row, config)),
            }
        )
    return blocks


def _stage_failed(row: dict, config: RealEvalConfig) -> bool:
    if not row.get("PulseExist", False):
        return True
    if int(row.get("FalseTriggerCount", 0) or 0) > 0:
        return True
    if _gt(row.get("OverlapRatio"), config.max_overlap_ratio):
        return True
    if _gt(row.get("Ripple"), config.max_ripple_v):
        return True
    if _gt(row.get("VoltageLoss"), config.max_voltage_loss_v):
        return True
    voh = row.get("VOH_mean")
    if voh is not None and float(voh) - config.high_threshold < config.min_voh_margin_v:
        return True
    return False


def _worst_stage(stage_rows: list[dict], config: RealEvalConfig) -> int | None:
    if not stage_rows:
        return None
    return int(max(stage_rows, key=lambda row: _stage_risk_score(row, config))["stage"])


def _stage_risk_score(row: dict, config: RealEvalConfig) -> float:
    if not row.get("PulseExist", False):
        return 1_000_000.0 + float(row.get("stage", 0))
    score = 0.0
    score += 10_000.0 * int(row.get("FalseTriggerCount", 0) or 0)
    score += _ratio(row.get("OverlapRatio"), config.max_overlap_ratio) * 100.0
    score += _ratio(row.get("Ripple"), config.max_ripple_v) * 100.0
    score += _ratio(row.get("VoltageLoss"), config.max_voltage_loss_v) * 100.0
    voh = row.get("VOH_mean")
    if voh is not None:
        margin = float(voh) - config.high_threshold
        if config.min_voh_margin_v:
            score += max(0.0, 1.0 - margin / config.min_voh_margin_v) * 100.0
    return float(score)


def _ratio(value: float | None, limit: float | None) -> float:
    if value is None or limit in (None, 0):
        return 0.0
    return max(0.0, float(value) / float(limit))


def _percentile(values: list[float | None], percentile: float) -> float | None:
    finite = _finite_values(values)
    if not finite:
        return None
    return float(np.percentile(finite, percentile))


def _metric_slope(stage_rows: list[dict], metric: str) -> float | None:
    points = [(float(row["stage"]), float(row[metric])) for row in stage_rows if row.get(metric) is not None and not math.isnan(float(row[metric]))]
    if len(points) < 2:
        return None
    x = np.array([point[0] for point in points], dtype=float)
    y = np.array([point[1] for point in points], dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def _frame_hold_time(target_refresh_hz: float | None) -> float | None:
    if target_refresh_hz is None:
        return None
    try:
        hz = float(target_refresh_hz)
    except (TypeError, ValueError):
        return None
    if hz <= 0.0 or math.isnan(hz):
        return None
    return 1.0 / hz


def _low_frequency_stability(summary: dict, config: RealEvalConfig) -> tuple[bool | str, str]:
    frame_hold_time = summary.get("frame_hold_time")
    waveform_duration = summary.get("waveform_duration")
    if frame_hold_time is None:
        return "not_configured", "未配置 target_refresh_hz，因此不评价低频保持稳定性。"
    if waveform_duration is None or float(waveform_duration) < float(frame_hold_time):
        return (
            "not_evaluable_with_current_waveform",
            "当前波形时长短于目标刷新周期，只能计算扫描脉冲内电压损失，不能证明低 Hz 保持稳定性。",
        )
    stable = (
        bool(summary.get("All_pulses_exist"))
        and int(summary.get("FalseTriggerCount", 0) or 0) == 0
        and not _gt(summary.get("Max_ripple"), config.max_ripple_v)
        and not _gt(summary.get("Max_voltage_loss"), config.max_voltage_loss_v)
    )
    return bool(stable), "当前波形覆盖目标刷新周期，已按电压损失、纹波和误触发进行低频稳定性初判。"


def _windows_overlap_duration(
    left_windows: list[tuple[float, float]],
    right_windows: list[tuple[float, float]],
    *,
    start_time: float | None = None,
) -> float:
    if start_time is None:
        return total_pairwise_overlap(left_windows, right_windows)
    total = 0.0
    for left in left_windows:
        for right in right_windows:
            if _starts_at_boundary(left, start_time) and _starts_at_boundary(right, start_time):
                continue
            total += total_pairwise_overlap([left], [right])
    return float(total)


def _starts_at_boundary(window: tuple[float, float], start_time: float) -> bool:
    return abs(float(window[0]) - float(start_time)) <= 1e-15


def _overlap_denominator(
    left_width: float | None,
    right_width: float | None,
    left_windows: list[tuple[float, float]] | None = None,
    right_windows: list[tuple[float, float]] | None = None,
) -> float | None:
    left_total = _windows_total_duration(left_windows or [])
    right_total = _windows_total_duration(right_windows or [])
    if left_total > 0 and right_total > 0:
        values = [left_total, right_total]
    else:
        values = [width for width in [left_width, right_width] if width is not None and width > 0]
    return min(values) if len(values) == 2 else None


def _windows_total_duration(windows: list[tuple[float, float]]) -> float:
    return float(sum(max(0.0, end - start) for start, end in windows))


def _last_finite(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return None
    return float(finite[-1])


def _voltage_loss(voh_max: float | None, v_hold_end: float | None) -> float | None:
    if voh_max is None or v_hold_end is None:
        return None
    return float(max(0.0, voh_max - v_hold_end))


def _gt(value: float | None, limit: float | None) -> bool:
    if value is None or limit is None:
        return False
    return float(value) > float(limit)


def _sample_step(time: np.ndarray) -> float:
    if len(time) < 2:
        return 0.0
    return float(np.nanmedian(np.diff(time)))


def _signal_diagnostics(time: np.ndarray, signal: np.ndarray, config: RealEvalConfig) -> dict:
    finite = signal[np.isfinite(signal)]
    if len(finite) == 0:
        return {
            "SignalMin": None,
            "SignalMax": None,
            "SignalSwing": None,
            "HighCrossingCount": 0,
            "LowCrossingCount": 0,
            "TimeAboveHighRatio": None,
            "TimeBelowLowRatio": None,
            "WaveformActivityScore": 0.0,
        }
    signal_min = float(np.nanmin(finite))
    signal_max = float(np.nanmax(finite))
    swing = signal_max - signal_min
    high_crossings = _crossing_count(signal, config.high_threshold)
    low_crossings = _crossing_count(signal, config.low_threshold)
    duration = float(time[-1] - time[0]) if len(time) >= 2 else 0.0
    above_ratio = _duration_ratio(time, signal > config.high_threshold, duration)
    below_ratio = _duration_ratio(time, signal < config.low_threshold, duration)
    swing_score = min(100.0, max(0.0, 100.0 * swing / config.high_threshold)) if config.high_threshold else 0.0
    edge_score = min(100.0, 50.0 * max(high_crossings, low_crossings))
    occupancy = max(above_ratio or 0.0, below_ratio or 0.0)
    occupancy_score = min(100.0, max(0.0, 100.0 * occupancy))
    activity_score = 0.45 * swing_score + 0.40 * edge_score + 0.15 * occupancy_score
    return {
        "SignalMin": signal_min,
        "SignalMax": signal_max,
        "SignalSwing": swing,
        "HighCrossingCount": int(high_crossings),
        "LowCrossingCount": int(low_crossings),
        "TimeAboveHighRatio": above_ratio,
        "TimeBelowLowRatio": below_ratio,
        "WaveformActivityScore": float(_clamp_score(activity_score)),
    }


def _crossing_count(signal: np.ndarray, threshold: float) -> int:
    above = signal > threshold
    return int(np.count_nonzero(np.diff(above.astype(int))))


def _duration_ratio(time: np.ndarray, mask: np.ndarray, duration: float) -> float | None:
    if duration <= 0.0:
        return None
    return float(sum(end - start for start, end in boolean_intervals(time, mask)) / duration)


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))
