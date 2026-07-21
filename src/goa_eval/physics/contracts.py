from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class FidelityLevel(IntEnum):
    """Evidence fidelity, from analytic heuristic to silicon observation."""

    F0_HEURISTIC = 0
    F1_ANALYTIC = 1
    F2_MODEL = 2
    F3_CIRCUIT_SIMULATION = 3
    F4_MEASUREMENT = 4


@dataclass(frozen=True)
class DeviceSpec:
    role: str
    polarity: str
    width_m: float
    length_m: float
    mobility_m2_v_s: float
    cox_f_m2: float
    threshold_v: float
    channel_length_modulation_per_v: float = 0.0
    series_resistance_ohm: float = 0.0
    subthreshold_slope_v: float = 0.08
    subthreshold_current_scale_a: float = 1.0e-12


@dataclass(frozen=True)
class DeviceBias:
    vgs_v: float
    vds_v: float
    temperature_c: float = 25.0


@dataclass(frozen=True)
class DeviceEvaluation:
    role: str
    polarity: str
    region: str
    overdrive_v: float
    drain_current_a: float
    large_signal_resistance_ohm: float
    small_signal_resistance_ohm: float
    trajectory_resistance_ohm: float
    fidelity: FidelityLevel
    source_drain_swapped: bool


@dataclass(frozen=True)
class BootstrapNetwork:
    boot_capacitance_f: float
    target_gate_capacitance_f: float
    output_load_capacitance_f: float
    parasitic_loss_capacitance_f: float
    clock_step_v: float
    initial_gate_v: float
    leakage_charge_c: float = 0.0


@dataclass(frozen=True)
class BootstrapEvaluation:
    coupling_factor: float
    gate_boost_v: float
    boosted_gate_v: float
    target_headroom_v: float
    charge_residual_c: float
    fidelity: FidelityLevel


@dataclass(frozen=True)
class ParasiticComponent:
    value: float
    unit: str
    source: str


@dataclass(frozen=True)
class ResolvedParasitic:
    value_si: float
    source: str
    status: str
