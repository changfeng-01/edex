import numpy as np

from goa_eval.models.waveform import WaveformBundle


def generate_mock_waveform(version_name: str, thresholds: dict) -> WaveformBundle:
    mock_cfg = thresholds.get("mock", {})
    voltage = thresholds.get("voltage", {})
    time_cfg = thresholds.get("time", {})
    dt = float(mock_cfg.get("sample_interval", 20e-9))
    total = float(mock_cfg.get("total_time", 180e-6))
    nodes = list(mock_cfg.get("output_nodes", [f"o{i}" for i in range(1, 9)]))
    vgh = float(voltage.get("VGH", 15.0))
    vgl = float(voltage.get("VGL", -5.0))
    line_period = float(time_cfg.get("expected_line_period", 20e-6))
    width = float(time_cfg.get("expected_pulse_width", 10e-6))
    rise = 100e-9

    time = np.arange(0.0, total, dt)
    signals = {
        "clk": _pulse_train(time, vgl, vgh, 5.25e-6, rise, rise, width, line_period),
        "clkb": _pulse_train(time, vgh, vgl, 4.75e-6, rise, rise, width, line_period),
        "stv": _pulse_train(time, vgl, vgh, 0.0, rise, rise, width, 100e-6),
    }
    truth_windows = {}
    for index, node in enumerate(nodes, start=1):
        start = (index - 1) * line_period + 2e-6
        end = start + width
        truth_windows[node] = (start, end)
        signals[node] = _single_pulse(time, vgl, vgh - 0.05 * (index - 1), start, end, rise)

    return WaveformBundle(
        version_name=version_name,
        time=time,
        signals=signals,
        data_source="mock",
        engineering_validity="workflow_test_only",
        truth_windows=truth_windows,
        metadata={"workflow_warning": "mock waveform only validates software flow"},
    )


def _pulse_train(time, low, high, delay, rise, fall, width, period):
    signal = np.full_like(time, low, dtype=float)
    start = delay
    while start < float(time[-1]):
        pulse = _single_pulse(time, low, high, start, start + width, rise, fall)
        signal = np.maximum(signal, pulse) if high >= low else np.minimum(signal, pulse)
        start += period
    return signal


def _single_pulse(time, low, high, start, end, rise=100e-9, fall=100e-9):
    signal = np.full_like(time, low, dtype=float)
    rise_end = start + rise
    fall_start = end - fall
    high_mask = (time >= rise_end) & (time <= fall_start)
    signal[high_mask] = high
    rise_mask = (time >= start) & (time < rise_end)
    fall_mask = (time > fall_start) & (time <= end)
    if rise > 0:
        signal[rise_mask] = low + (high - low) * ((time[rise_mask] - start) / rise)
    if fall > 0:
        signal[fall_mask] = high - (high - low) * ((time[fall_mask] - fall_start) / fall)
    return signal
