from __future__ import annotations

import numpy as np


def voltage_thresholds(thresholds: dict) -> dict[str, float]:
    voltage = thresholds.get("voltage", {})
    vgh = float(voltage.get("VGH", 15.0))
    vgl = float(voltage.get("VGL", -5.0))
    span = vgh - vgl
    return {
        "VGH": vgh,
        "VGL": vgl,
        "VH": vgl + float(voltage.get("VH_ratio", 0.70)) * span,
        "VL": vgl + float(voltage.get("VL_ratio", 0.20)) * span,
        "V10": vgl + float(voltage.get("edge_low_ratio", 0.10)) * span,
        "V90": vgl + float(voltage.get("edge_high_ratio", 0.90)) * span,
    }


def plateau_window(window: tuple[float, float], center_ratio: float) -> tuple[float, float]:
    start, end = window
    width = end - start
    keep = width * center_ratio
    pad = (width - keep) / 2.0
    return start + pad, end - pad


def first_rising_crossing(time: np.ndarray, signal: np.ndarray, threshold: float) -> float | None:
    mask = signal >= threshold
    indices = np.where((~mask[:-1]) & mask[1:])[0]
    if len(indices) == 0:
        return None
    return _interpolate_crossing(time, signal, indices[0], threshold)


def first_falling_crossing(time: np.ndarray, signal: np.ndarray, threshold: float, after: float | None = None) -> float | None:
    mask = signal >= threshold
    indices = np.where(mask[:-1] & (~mask[1:]))[0]
    for index in indices:
        crossing = _interpolate_crossing(time, signal, index, threshold)
        if after is None or crossing > after:
            return crossing
    return None


def first_valid_high_window(
    time: np.ndarray,
    signal: np.ndarray,
    threshold: float,
    min_width: float,
    edge_guard: float,
) -> tuple[float, float] | None:
    mask = signal >= threshold
    intervals = boolean_intervals(time, mask)
    for start, end in intervals:
        if end - start >= min_width:
            return max(float(time[0]), start - edge_guard), min(float(time[-1]), end + edge_guard)
    return None


def valid_high_windows(
    time: np.ndarray,
    signal: np.ndarray,
    threshold: float,
    min_width: float,
    edge_guard: float,
) -> list[tuple[float, float]]:
    windows = []
    for start, end in boolean_intervals(time, signal >= threshold):
        if end - start >= min_width:
            windows.append((max(float(time[0]), start - edge_guard), min(float(time[-1]), end + edge_guard)))
    return windows


def non_select_mask(
    time: np.ndarray,
    target_window: tuple[float, float],
    rise: float | None,
    fall: float | None,
    edge_guard: float,
) -> np.ndarray:
    mask = np.ones_like(time, dtype=bool)
    start, end = target_window
    mask &= ~((time >= start) & (time <= end))
    for edge in [rise, fall]:
        if edge is not None:
            mask &= ~((time >= edge - edge_guard) & (time <= edge + edge_guard))
    return mask


def non_select_windows_mask(
    time: np.ndarray,
    legitimate_windows: list[tuple[float, float]],
) -> np.ndarray:
    mask = np.ones_like(time, dtype=bool)
    for start, end in legitimate_windows:
        mask &= ~((time >= start) & (time <= end))
    return mask


def has_continuous_high(time: np.ndarray, signal: np.ndarray, threshold: float, min_duration: float) -> bool:
    intervals = boolean_intervals(time, signal >= threshold)
    return any(end - start >= min_duration for start, end in intervals)


def boolean_intervals(time: np.ndarray, mask: np.ndarray) -> list[tuple[float, float]]:
    if len(time) == 0 or not mask.any():
        return []
    changes = np.diff(mask.astype(int))
    starts = list(np.where(changes == 1)[0] + 1)
    ends = list(np.where(changes == -1)[0] + 1)
    if mask[0]:
        starts.insert(0, 0)
    if mask[-1]:
        ends.append(len(mask) - 1)
    intervals = []
    for start, end in zip(starts, ends):
        intervals.append((float(time[start]), float(time[min(end, len(time) - 1)])))
    return intervals


def interval_total_duration(time: np.ndarray, mask: np.ndarray) -> float:
    return float(sum(end - start for start, end in boolean_intervals(time, mask)))


def _interpolate_crossing(time: np.ndarray, signal: np.ndarray, index: int, threshold: float) -> float:
    t0, t1 = float(time[index]), float(time[index + 1])
    v0, v1 = float(signal[index]), float(signal[index + 1])
    if v1 == v0:
        return t1
    ratio = (threshold - v0) / (v1 - v0)
    return t0 + ratio * (t1 - t0)
