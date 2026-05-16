from __future__ import annotations

import numpy as np


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


def interval_overlap_duration(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_start, left_end = left
    right_start, right_end = right
    return float(max(0.0, min(left_end, right_end) - max(left_start, right_start)))


def total_pairwise_overlap(left_windows: list[tuple[float, float]], right_windows: list[tuple[float, float]]) -> float:
    total = 0.0
    for left in left_windows:
        for right in right_windows:
            total += interval_overlap_duration(left, right)
    return float(total)


def selected_window(window: tuple[float, float], center_ratio: float) -> tuple[float, float]:
    start, end = window
    width = end - start
    pad = width * (1.0 - center_ratio) / 2.0
    return start + pad, end - pad


def excluded_window_mask(time: np.ndarray, windows: list[tuple[float, float]], edge_buffer_ratio: float) -> np.ndarray:
    mask = np.zeros_like(time, dtype=bool)
    for start, end in windows:
        width = end - start
        edge_buffer = max(edge_buffer_ratio * width, 0.0)
        mask |= (time >= start - edge_buffer) & (time <= end + edge_buffer)
    return mask


def non_selected_mask(time: np.ndarray, windows: list[tuple[float, float]], edge_buffer_ratio: float) -> np.ndarray:
    return ~excluded_window_mask(time, windows, edge_buffer_ratio)


def ripple_in_hold_window(
    time: np.ndarray,
    signal: np.ndarray,
    legal_windows: list[tuple[float, float]],
    edge_buffer_ratio: float,
) -> tuple[float | None, float | None]:
    mask = non_selected_mask(time, legal_windows, edge_buffer_ratio)
    values = signal[mask]
    if len(values) == 0:
        return None, None
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return None, None
    return float(np.nanmax(finite) - np.nanmin(finite)), float(np.nanmax(finite))
