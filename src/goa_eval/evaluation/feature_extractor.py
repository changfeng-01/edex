from __future__ import annotations

import numpy as np

from goa_eval.models.waveform import WaveformBundle
from goa_eval.evaluation.windowing import (
    boolean_intervals,
    first_falling_crossing,
    first_rising_crossing,
    interval_total_duration,
    non_select_mask,
    non_select_windows_mask,
    plateau_window,
    valid_high_windows,
    voltage_thresholds,
)


def extract_waveform_features(waveform_bundle: WaveformBundle, thresholds: dict) -> dict:
    vt = voltage_thresholds(thresholds)
    time_cfg = thresholds.get("time", {})
    window_cfg = thresholds.get("windows", {})
    time = waveform_bundle.time
    edge_guard = float(time_cfg.get("edge_guard_ratio_of_line", 0.05)) * float(time_cfg.get("expected_line_period", 20e-6))
    min_valid = float(time_cfg.get("min_valid_pulse_width", 2e-6))
    min_false = float(time_cfg.get("min_false_trigger_duration", 0.2e-6))
    center_ratio = float(window_cfg.get("plateau_center_ratio", 0.60))

    node_features = {}
    output_nodes = [node for node in waveform_bundle.signals if node.startswith("o")]
    output_nodes = sorted(output_nodes, key=lambda name: int(name[1:]) if name[1:].isdigit() else 999)

    for node in output_nodes:
        signal = waveform_bundle.signals[node]
        target = None
        legitimate_windows = []
        if waveform_bundle.truth_windows and node in waveform_bundle.truth_windows:
            target = waveform_bundle.truth_windows[node]
            legitimate_windows = [target]
        if target is None:
            legitimate_windows = valid_high_windows(time, signal, vt["VH"], min_valid, edge_guard)
            target = legitimate_windows[0] if legitimate_windows else None
        if target is None:
            node_features[node] = _empty_node_feature()
            continue

        rise_vh = first_rising_crossing(time, signal, vt["VH"])
        fall_vh = first_falling_crossing(time, signal, vt["VH"], rise_vh)
        tr_start = first_rising_crossing(time, signal, vt["V10"])
        tr_end = first_rising_crossing(time, signal, vt["V90"])
        tf_start = first_falling_crossing(time, signal, vt["V90"], rise_vh)
        tf_end = first_falling_crossing(time, signal, vt["V10"], rise_vh)
        plateau = plateau_window(target, center_ratio)
        plateau_mask = (time >= plateau[0]) & (time <= plateau[1])
        target_mask = (time >= target[0]) & (time <= target[1])
        if waveform_bundle.truth_windows and node in waveform_bundle.truth_windows:
            off_mask = non_select_mask(time, target, rise_vh, fall_vh, edge_guard)
        else:
            off_mask = non_select_windows_mask(time, legitimate_windows)
        off_signal = signal[off_mask]
        false_trigger_windows = [
            (start, end)
            for start, end in boolean_intervals(time, off_mask & (signal >= vt["VH"]))
            if end - start >= min_false
        ]

        voh = float(np.mean(signal[plateau_mask])) if plateau_mask.any() else float(np.max(signal[target_mask]))
        vol = float(np.mean(off_signal)) if len(off_signal) else float("nan")
        ripple = float(np.max(off_signal) - np.min(off_signal)) if len(off_signal) else float("nan")
        false_trigger = bool(false_trigger_windows)

        node_features[node] = {
            "target_window": target,
            "legitimate_windows": legitimate_windows,
            "legitimate_pulse_count": len(legitimate_windows),
            "first_scan_window": target,
            "repeated_scan_windows": legitimate_windows[1:],
            "true_false_trigger_windows": false_trigger_windows,
            "true_false_trigger_count": len(false_trigger_windows),
            "plateau_window": plateau,
            "VOH": voh,
            "VOL": vol,
            "Ripple": ripple,
            "FalseTrigger": bool(false_trigger),
            "PulseExist": bool(rise_vh is not None and fall_vh is not None and (fall_vh - rise_vh) >= min_valid),
            "trise": rise_vh,
            "tfall": fall_vh,
            "Twidth": None if rise_vh is None or fall_vh is None else fall_vh - rise_vh,
            "tr": None if tr_start is None or tr_end is None else tr_end - tr_start,
            "tf": None if tf_start is None or tf_end is None else tf_end - tf_start,
        }

    overlaps = {}
    for left, right in zip(output_nodes, output_nodes[1:]):
        both = (waveform_bundle.signals[left] >= vt["VH"]) & (waveform_bundle.signals[right] >= vt["VH"])
        overlaps[f"{left}_{right}"] = interval_total_duration(time, both)

    return {"thresholds": vt, "nodes": node_features, "overlaps": overlaps}


def _empty_node_feature() -> dict:
    return {
        "target_window": None,
        "legitimate_windows": [],
        "legitimate_pulse_count": 0,
        "first_scan_window": None,
        "repeated_scan_windows": [],
        "true_false_trigger_windows": [],
        "true_false_trigger_count": 0,
        "plateau_window": None,
        "VOH": None,
        "VOL": None,
        "Ripple": None,
        "FalseTrigger": False,
        "PulseExist": False,
        "trise": None,
        "tfall": None,
        "Twidth": None,
        "tr": None,
        "tf": None,
    }
