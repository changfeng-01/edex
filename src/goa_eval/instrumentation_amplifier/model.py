from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class InstrumentationAmplifierComponents:
    R: float
    RG: float
    RD: float
    KD_plus: float
    KD_minus: float
    CF: float
    R1: float
    R2: float
    R3: float
    R4: float
    R5: float
    R6: float
    C5: float
    C6: float

    def as_dict(self) -> dict[str, float]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class AmplifierSolveResult:
    output_v: complex
    status: str
    matrix_condition_number: float


@dataclass(frozen=True)
class TransferMetrics:
    differential_gain: float
    common_mode_gain: float
    cmrr_db: float
    common_mode_gain_status: str
    bandwidth_hz: float | None
    bandwidth_status: str
    model_status: str
    matrix_condition_number: float


def derive_components(
    design: Mapping[str, Any],
    variations: Mapping[str, Any] | None = None,
    *,
    reference_uncompensated: bool = False,
) -> InstrumentationAmplifierComponents:
    required = ("R", "RG", "RD", "KD_plus", "KD_minus", "CF")
    missing = [name for name in required if name not in design]
    if missing:
        raise ValueError("missing instrumentation parameters: " + ", ".join(missing))
    values = {name: float(design[name]) for name in required}
    for name in ("R", "RG", "RD", "KD_plus", "KD_minus"):
        if not math.isfinite(values[name]) or values[name] <= 0.0:
            raise ValueError(f"{name} must be finite and positive")
    if not math.isfinite(values["CF"]) or (
        values["CF"] <= 0.0 and not (reference_uncompensated and values["CF"] == 0.0)
    ):
        raise ValueError("CF must be finite and positive outside reference_uncompensated")
    deltas = []
    for index in range(1, 7):
        delta = float((variations or {}).get(f"delta{index}", 0.0))
        if not math.isfinite(delta) or delta <= -1.0:
            raise ValueError(f"delta{index} must be finite and greater than -1")
        deltas.append(delta)
    r5_nominal = values["KD_plus"] * values["RD"]
    r6_nominal = values["KD_minus"] * values["RD"]
    return InstrumentationAmplifierComponents(
        **values,
        R1=values["R"] * (1.0 + deltas[0]),
        R2=values["R"] * (1.0 + deltas[1]),
        R3=values["RD"] * (1.0 + deltas[2]),
        R4=values["RD"] * (1.0 + deltas[3]),
        R5=r5_nominal * (1.0 + deltas[4]),
        R6=r6_nominal * (1.0 + deltas[5]),
        C5=values["CF"] / values["KD_plus"] if values["CF"] else 0.0,
        C6=values["CF"] / values["KD_minus"] if values["CF"] else 0.0,
    )


def parse_electrical_value(value: Any, unit: str, *, quantity: str) -> float:
    units = {
        "resistance": {"ohm": 1.0, "kohm": 1.0e3, "mohm": 1.0e6},
        "capacitance": {"f": 1.0, "nf": 1.0e-9, "pf": 1.0e-12},
        "frequency": {"hz": 1.0, "khz": 1.0e3, "mhz": 1.0e6},
        "voltage": {"v": 1.0, "mv": 1.0e-3},
        "current": {"a": 1.0, "ma": 1.0e-3, "ua": 1.0e-6},
    }
    normalized = str(unit).strip().lower().replace("ω", "ohm")
    try:
        scale = units[quantity][normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported unit {unit!r} for {quantity}") from exc
    parsed = float(value) * scale
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite {quantity} value")
    return parsed


class InstrumentationAmplifierModel:
    def __init__(
        self,
        design: Mapping[str, Any],
        *,
        variations: Mapping[str, Any] | None = None,
        opamp_model: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
        reference_uncompensated: bool = False,
    ) -> None:
        self.components = derive_components(
            design, variations, reference_uncompensated=reference_uncompensated
        )
        self.opamp_model = dict(opamp_model or {})
        self.environment = dict(environment or {})
        self.model_status = (
            "physical_model"
            if _positive(self.opamp_model.get("A0"))
            and _positive(self.opamp_model.get("GBW"))
            else "proxy"
        )

    def solve(self, u1: float, u2: float, *, frequency_hz: float = 0.0) -> AmplifierSolveResult:
        if frequency_hz < 0.0 or not math.isfinite(float(frequency_hz)):
            return AmplifierSolveResult(complex("nan"), "invalid_frequency", float("inf"))
        if self.model_status == "proxy":
            return self._solve_ideal(float(u1), float(u2), float(frequency_hz))
        return self._solve_finite(float(u1), float(u2), float(frequency_hz))

    def _solve_ideal(self, u1: float, u2: float, frequency_hz: float) -> AmplifierSolveResult:
        component = self.components
        s = 1j * 2.0 * math.pi * frequency_hz
        g5 = 1.0 / component.R5 + s * component.C5
        g6 = 1.0 / component.R6 + s * component.C6
        o1 = u1 + component.R1 / component.RG * (u1 - u2)
        o2 = u2 + component.R2 / component.RG * (u2 - u1)
        p3 = (o2 / component.R4) / (1.0 / component.R4 + g6)
        output = p3 + (p3 - o1) / (component.R3 * g5)
        return AmplifierSolveResult(output, "ok", 1.0)

    def _solve_finite(self, u1: float, u2: float, frequency_hz: float) -> AmplifierSolveResult:
        c = self.components
        s = 1j * 2.0 * math.pi * frequency_hz
        a0 = float(self.opamp_model["A0"])
        gbw = float(self.opamp_model["GBW"])
        pole = 2.0 * math.pi * gbw / a0
        gain = a0 / (1.0 + s / pole)
        rout = max(float(self.opamp_model.get("Rout", 0.0)), 0.0)
        rl = float(self.environment.get("RL", float("inf")))
        if not math.isinf(rl) and rl <= 0.0:
            return AmplifierSolveResult(complex("nan"), "invalid_load", float("inf"))
        gload = 0.0 if math.isinf(rl) else 1.0 / rl
        g5 = 1.0 / c.R5 + s * c.C5
        g6 = 1.0 / c.R6 + s * c.C6
        matrix = np.zeros((10, 10), dtype=complex)
        rhs = np.zeros(10, dtype=complex)
        n1, n2, e1, o1, e2, o2, p3, n3, e3, output = range(10)

        matrix[0, n1], matrix[0, e1], rhs[0] = gain, 1.0, gain * u1
        matrix[1, n2], matrix[1, e2], rhs[1] = gain, 1.0, gain * u2
        matrix[2, p3], matrix[2, n3], matrix[2, e3] = -gain, gain, 1.0
        matrix[3, n1] = 1.0 / c.R1 + 1.0 / c.RG
        matrix[3, n2], matrix[3, o1] = -1.0 / c.RG, -1.0 / c.R1
        matrix[4, n2] = 1.0 / c.R2 + 1.0 / c.RG
        matrix[4, n1], matrix[4, o2] = -1.0 / c.RG, -1.0 / c.R2
        matrix[5, p3], matrix[5, o2] = 1.0 / c.R4 + g6, -1.0 / c.R4
        matrix[6, n3] = 1.0 / c.R3 + g5
        matrix[6, o1], matrix[6, output] = -1.0 / c.R3, -g5
        if rout > 0.0:
            gr = 1.0 / rout
            matrix[7, o1] = gr + 1.0 / c.R1 + 1.0 / c.R3
            matrix[7, e1], matrix[7, n1], matrix[7, n3] = -gr, -1.0 / c.R1, -1.0 / c.R3
            matrix[8, o2] = gr + 1.0 / c.R2 + 1.0 / c.R4
            matrix[8, e2], matrix[8, n2], matrix[8, p3] = -gr, -1.0 / c.R2, -1.0 / c.R4
            matrix[9, output] = gr + g5 + gload
            matrix[9, e3], matrix[9, n3] = -gr, -g5
        else:
            matrix[7, o1], matrix[7, e1] = 1.0, -1.0
            matrix[8, o2], matrix[8, e2] = 1.0, -1.0
            matrix[9, output], matrix[9, e3] = 1.0, -1.0
        try:
            condition = float(np.linalg.cond(matrix))
            solution = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError:
            return AmplifierSolveResult(complex("nan"), "singular_mna", float("inf"))
        if not np.isfinite(solution).all():
            return AmplifierSolveResult(complex("nan"), "non_finite_mna", condition)
        return AmplifierSolveResult(complex(solution[output]), "ok", condition)

    def transfer_metrics(self) -> TransferMetrics:
        differential = self.solve(-0.5, 0.5, frequency_hz=0.0)
        common = self.solve(1.0, 1.0, frequency_hz=0.0)
        differential_gain = abs(differential.output_v)
        common_gain = abs(common.output_v)
        resolution = (
            np.finfo(float).eps
            * max(differential.matrix_condition_number, common.matrix_condition_number, 1.0)
            * max(differential_gain, 1.0)
            * 10.0
        )
        if common_gain <= resolution:
            cmrr = float("inf")
            common_status = "ideal_infinite"
        else:
            cmrr = 20.0 * math.log10(differential_gain / common_gain)
            common_status = "resolved"
        bandwidth, bandwidth_status = self._find_bandwidth(differential_gain)
        return TransferMetrics(
            differential_gain=differential_gain,
            common_mode_gain=common_gain,
            cmrr_db=cmrr,
            common_mode_gain_status=common_status,
            bandwidth_hz=bandwidth,
            bandwidth_status=bandwidth_status,
            model_status=self.model_status,
            matrix_condition_number=max(
                differential.matrix_condition_number, common.matrix_condition_number
            ),
        )

    def _find_bandwidth(self, dc_gain: float) -> tuple[float | None, str]:
        if not math.isfinite(dc_gain) or dc_gain <= 0.0:
            return None, "invalid_dc_gain"
        target = dc_gain / math.sqrt(2.0)
        upper = max(float(self.opamp_model.get("GBW", 1.0e6)) * 100.0, 1.0e9)
        frequencies = np.geomspace(1.0e-3, upper, 240)
        previous_frequency = 0.0
        previous_gain = dc_gain
        bracket: tuple[float, float] | None = None
        for frequency in frequencies:
            solved = self.solve(-0.5, 0.5, frequency_hz=float(frequency))
            if solved.status != "ok":
                return None, solved.status
            gain = abs(solved.output_v)
            if previous_gain >= target and gain < target:
                bracket = (previous_frequency, float(frequency))
                break
            previous_frequency, previous_gain = float(frequency), gain
        if bracket is None:
            return None, "no_crossing"
        low, high = bracket
        for _ in range(80):
            middle = 0.5 * (low + high)
            gain = abs(self.solve(-0.5, 0.5, frequency_hz=middle).output_v)
            if gain >= target:
                low = middle
            else:
                high = middle
        return 0.5 * (low + high), "resolved"

    def evaluate(self) -> dict[str, Any]:
        metrics = self.transfer_metrics()
        frequency = float(self.environment.get("f", 0.0))
        differential = float(self.environment.get("Vd", 1.0))
        common = float(self.environment.get("V_CM", 0.0))
        actual = self.solve(
            common - 0.5 * differential,
            common + 0.5 * differential,
            frequency_hz=frequency,
        )
        output_peak = abs(actual.output_v)
        slew_rate = self.opamp_model.get("SR")
        slew_utilization = (
            2.0 * math.pi * frequency * output_peak / float(slew_rate)
            if _positive(slew_rate)
            else None
        )
        vcc = float(self.environment.get("VCC", 5.0))
        vee = float(self.environment.get("VEE", -5.0))
        output_high = float(self.opamp_model.get("output_high_v", vcc))
        output_low = float(self.opamp_model.get("output_low_v", vee))
        output_headroom = min(output_high - output_peak, output_peak - output_low)
        input_low = self.opamp_model.get("input_common_min_v")
        input_high = self.opamp_model.get("input_common_max_v")
        if input_low is not None and input_high is not None:
            input_values = (common - 0.5 * differential, common + 0.5 * differential)
            input_margin = min(
                min(input_values) - float(input_low),
                float(input_high) - max(input_values),
            )
            common_status = "physical_model"
        else:
            input_margin = None
            common_status = "proxy"
        observed_power = self.environment.get("power_w")
        supply_current = self.opamp_model.get("supply_current_a")
        if observed_power is not None:
            power = float(observed_power)
            power_status = "observed"
        elif _positive(supply_current):
            power = abs(vcc - vee) * float(supply_current)
            power_status = "physical_model"
        else:
            power = None
            power_status = "missing"
        return {
            "differential_gain": metrics.differential_gain,
            "common_mode_gain": metrics.common_mode_gain,
            "cmrr_db": metrics.cmrr_db,
            "common_mode_gain_status": metrics.common_mode_gain_status,
            "bandwidth_hz": metrics.bandwidth_hz,
            "bandwidth_status": metrics.bandwidth_status,
            "model_status": metrics.model_status,
            "matrix_condition_number": metrics.matrix_condition_number,
            "output_peak_v": output_peak,
            "output_headroom_v": output_headroom,
            "slew_utilization": slew_utilization,
            "input_common_mode_margin_v": input_margin,
            "input_common_mode_status": common_status,
            "power_w": power,
            "power_status": power_status,
            "solve_status": actual.status,
        }


def _positive(value: object) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0.0
    except (TypeError, ValueError):
        return False
