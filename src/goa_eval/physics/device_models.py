from __future__ import annotations

import math

from .contracts import DeviceBias, DeviceEvaluation, DeviceSpec, FidelityLevel


def evaluate_tft_phase_charge(spec: DeviceSpec, bias: DeviceBias) -> DeviceEvaluation:
    """Evaluate a signed TFT using one continuous phase-aware charge model.

    Threshold voltage remains signed. Multiplication by the polarity sign maps
    N- and P-type devices to the same normalized coordinate system and keeps
    depletion-mode devices (negative normalized threshold) physically valid.
    """

    polarity_sign = -1.0 if spec.polarity.lower().startswith("p") else 1.0
    normalized_vgs = polarity_sign * float(bias.vgs_v)
    normalized_threshold = polarity_sign * float(spec.threshold_v)
    normalized_vds = polarity_sign * float(bias.vds_v)
    direction = -1.0 if normalized_vds < 0.0 else 1.0
    vds = abs(normalized_vds)
    overdrive = normalized_vgs - normalized_threshold

    width = max(float(spec.width_m), 1.0e-30)
    length = max(float(spec.length_m), 1.0e-30)
    beta = max(float(spec.mobility_m2_v_s), 0.0) * max(float(spec.cox_f_m2), 0.0) * width / length
    channel_lambda = max(float(spec.channel_length_modulation_per_v), 0.0)
    slope = max(float(spec.subthreshold_slope_v), 1.0e-6)

    if overdrive <= -slope:
        region = "cutoff"
        magnitude = 0.0
        conductance = 0.0
    elif overdrive <= 0.0:
        region = "subthreshold"
        thermal_voltage = 8.617333262e-5 * (float(bias.temperature_c) + 273.15)
        drain_factor = 1.0 - math.exp(-vds / max(thermal_voltage, 1.0e-9))
        magnitude = max(float(spec.subthreshold_current_scale_a), 0.0) * math.exp(overdrive / slope) * drain_factor
        conductance = magnitude / max(thermal_voltage, 1.0e-9)
    elif vds < overdrive:
        region = "linear"
        base = beta * (overdrive * vds - 0.5 * vds**2)
        magnitude = max(base * (1.0 + channel_lambda * vds), 0.0)
        conductance = max(beta * (overdrive - vds) * (1.0 + channel_lambda * vds) + base * channel_lambda, 0.0)
    else:
        region = "saturation"
        base = 0.5 * beta * overdrive**2
        magnitude = max(base * (1.0 + channel_lambda * vds), 0.0)
        conductance = max(base * channel_lambda, 0.0)

    current_sign = polarity_sign * direction
    current = current_sign * magnitude
    series = max(float(spec.series_resistance_ohm), 0.0)
    large_signal = (
        vds / max(magnitude, 1.0e-30) + series if vds > 0.0 else 1.0 / max(beta * max(overdrive, 0.0), 1.0e-30) + series
    )
    small_signal = 1.0 / max(conductance, 1.0e-30) + series
    trajectory = math.sqrt(max(large_signal, 0.0) * max(small_signal, 0.0))
    return DeviceEvaluation(
        role=spec.role,
        polarity="p" if polarity_sign < 0.0 else "n",
        region=region,
        overdrive_v=float(overdrive),
        drain_current_a=float(current),
        large_signal_resistance_ohm=float(large_signal),
        small_signal_resistance_ohm=float(small_signal),
        trajectory_resistance_ohm=float(trajectory),
        fidelity=FidelityLevel.F2_MODEL,
        source_drain_swapped=bool(direction < 0.0),
    )
