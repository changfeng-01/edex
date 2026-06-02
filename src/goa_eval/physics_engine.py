from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any

import pandas as pd


MODEL_STATUS = "physics_prior_engine_v1"


@dataclass(frozen=True)
class PhysicsEvaluation:
    physics_score: float
    physical_hard_passed: bool
    proxy_metrics: dict[str, float | str | None]
    violations: list[str]
    rationale: str
    model_status: str = MODEL_STATUS


def evaluate_candidate_physics(
    parameters: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> PhysicsEvaluation:
    values = _extract_physical_values(parameters)
    baseline_values = _extract_physical_values(baseline or {}) if baseline else {}

    tau = _tau_proxy(values)
    baseline_tau = _tau_proxy(baseline_values)
    drive_to_load = _drive_to_load_ratio(values, tau)
    baseline_drive = _drive_to_load_ratio(baseline_values, baseline_tau)
    storage_to_load = _ratio(values.get("c_store"), values.get("c_load"))
    timing_over_rc = _ratio(values.get("timing_spacing"), tau)
    pulse_over_rc = _ratio(values.get("pulse_width"), tau)
    voltage_margin = _voltage_margin(values)

    proxy_metrics: dict[str, float | str | None] = {
        "rc_delay_proxy": tau,
        "drive_to_load_ratio": drive_to_load,
        "storage_to_load_cap_ratio": storage_to_load,
        "timing_spacing_over_rc": timing_over_rc,
        "pulse_width_over_rc": pulse_over_rc,
        "voltage_margin": voltage_margin,
        "effective_width": values.get("w_eff"),
        "load_capacitance": values.get("c_load"),
        "driver_resistance": values.get("r_driver"),
    }
    if baseline_tau is not None:
        proxy_metrics["baseline_rc_delay_proxy"] = baseline_tau
    if baseline_drive is not None:
        proxy_metrics["baseline_drive_to_load_ratio"] = baseline_drive

    violations: list[str] = []
    if voltage_margin is not None and voltage_margin <= 0:
        violations.append("voltage_margin <= 0")
    if timing_over_rc is not None and timing_over_rc < 2:
        violations.append("timing_spacing_over_rc < 2")
    if pulse_over_rc is not None and pulse_over_rc < 3:
        violations.append("pulse_width_over_rc < 3")

    component_scores = [
        _tau_score(tau, baseline_tau),
        _drive_score(drive_to_load, baseline_drive),
        _storage_score(storage_to_load),
        _margin_score(timing_over_rc, hard=2.0, preferred=3.0),
        _margin_score(pulse_over_rc, hard=3.0, preferred=4.0),
        _voltage_score(voltage_margin),
    ]
    available_scores = [score for score in component_scores if score is not None]
    if available_scores:
        physics_score = sum(available_scores) / len(available_scores)
    else:
        physics_score = 50.0
    if violations:
        physics_score = min(physics_score, 35.0)

    rationale = _rationale(proxy_metrics, violations)
    return PhysicsEvaluation(
        physics_score=round(max(0.0, min(100.0, physics_score)), 6),
        physical_hard_passed=not violations,
        proxy_metrics=proxy_metrics,
        violations=violations,
        rationale=rationale,
    )


def rank_physics_guided_points(
    points: list[dict[str, Any]],
    *,
    history: pd.DataFrame | None = None,
    max_points: int | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    baseline = _baseline_from_history(history)
    ranked: list[tuple[dict[str, Any], dict[str, Any], PhysicsEvaluation]] = []
    for point in points:
        evaluation = evaluate_candidate_physics(point, baseline=baseline)
        metadata = {
            "candidate_source": "physics_prior_engine",
            "source_run_dir": "",
            "source_candidate_id": "",
            "source_candidate_trigger_metric": "",
            "source_candidate_kind": "physics_prior",
            "source_candidate_score": evaluation.physics_score,
            "source_candidate_parameters_json": _json_text(point),
            "source_candidate_rationale": evaluation.rationale,
            "optimizer_strategy": "physics_guided_hybrid",
            "objective_score": evaluation.physics_score,
            "model_status": evaluation.model_status,
            "model_prediction": "",
            "physics_score": evaluation.physics_score,
            "physical_hard_passed": evaluation.physical_hard_passed,
            "physics_proxy_json": _json_text(evaluation.proxy_metrics),
            "physics_violations": ";".join(evaluation.violations),
            "physics_rationale": evaluation.rationale,
        }
        ranked.append((dict(point), metadata, evaluation))

    ranked.sort(
        key=lambda item: (
            item[2].physical_hard_passed,
            item[2].physics_score,
            _json_text(item[0]),
        ),
        reverse=True,
    )
    selected = ranked if max_points is None else ranked[: max(0, int(max_points))]
    return [(point, metadata) for point, metadata, _ in selected]


def _extract_physical_values(parameters: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    widths: list[float] = []
    for key, raw in parameters.items():
        name = str(key).lower()
        value = _parse_physical_number(raw)
        if value is None or value <= 0 and not _is_voltage_name(name):
            continue
        if _is_load_cap_name(name):
            values["c_load"] = value
        elif _is_storage_cap_name(name):
            values["c_store"] = value
        elif _is_driver_resistance_name(name):
            values["r_driver"] = value
        elif _is_width_name(name):
            widths.append(value)
        elif _is_timing_spacing_name(name):
            values["timing_spacing"] = _min_positive(values.get("timing_spacing"), value)
        elif _is_pulse_width_name(name):
            values["pulse_width"] = _min_positive(values.get("pulse_width"), value)
        elif _is_vdd_name(name):
            values["vdd"] = value
        elif _is_vth_name(name):
            values["vth"] = value
        elif "capacitance" in name and "c_load" not in values:
            values["c_load"] = value
    if widths:
        values["w_eff"] = sum(widths)
    return values


def _tau_proxy(values: dict[str, float]) -> float | None:
    c_load = values.get("c_load")
    if c_load is None or c_load <= 0:
        return None
    r_driver = values.get("r_driver")
    if r_driver is not None and r_driver > 0:
        return r_driver * c_load
    w_eff = values.get("w_eff")
    if w_eff is not None and w_eff > 0:
        return c_load / w_eff
    return None


def _drive_to_load_ratio(values: dict[str, float], tau: float | None) -> float | None:
    c_load = values.get("c_load")
    w_eff = values.get("w_eff")
    if c_load is not None and c_load > 0 and w_eff is not None and w_eff > 0:
        return w_eff / c_load
    if tau is not None and tau > 0:
        return 1.0 / tau
    return None


def _voltage_margin(values: dict[str, float]) -> float | None:
    vdd = values.get("vdd")
    vth = values.get("vth")
    if vdd is None or vth is None:
        return None
    return vdd - vth


def _tau_score(tau: float | None, baseline_tau: float | None) -> float | None:
    if tau is None or tau <= 0:
        return None
    if baseline_tau is not None and baseline_tau > 0:
        return _clamp(50.0 + 25.0 * math.log10(baseline_tau / tau), 0.0, 100.0)
    return 70.0


def _drive_score(drive: float | None, baseline_drive: float | None) -> float | None:
    if drive is None or drive <= 0:
        return None
    if baseline_drive is not None and baseline_drive > 0:
        return _clamp(50.0 + 25.0 * math.log10(drive / baseline_drive), 0.0, 100.0)
    return 70.0


def _storage_score(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0:
        return 0.0
    if value >= 2.0:
        return 100.0
    if value >= 1.0:
        return 75.0 + 25.0 * (value - 1.0)
    return 75.0 * value


def _margin_score(value: float | None, *, hard: float, preferred: float) -> float | None:
    if value is None:
        return None
    if value <= 0:
        return 0.0
    if value < hard:
        return 50.0 * value / hard
    if value >= preferred:
        return 100.0
    return 75.0 + 25.0 * ((value - hard) / (preferred - hard))


def _voltage_score(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0:
        return 0.0
    if value < 0.2:
        return 40.0 + 150.0 * value
    return min(100.0, 70.0 + 20.0 * value)


def _baseline_from_history(history: pd.DataFrame | None) -> dict[str, Any]:
    if history is None or history.empty:
        return {}
    frame = history.copy()
    if "status" in frame:
        evaluated = frame[frame["status"].astype(str).str.lower().eq("evaluated")]
        if not evaluated.empty:
            frame = evaluated
    if "overall_score" in frame:
        scores = pd.to_numeric(frame["overall_score"], errors="coerce")
        if scores.notna().any():
            return frame.loc[scores.idxmax()].to_dict()
    return frame.iloc[0].to_dict()


def _parse_physical_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return None if math.isnan(number) else number
    text = str(value).strip()
    if not text:
        return None
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]+)?", text)
    if not match:
        return None
    unit = (match.group(2) or "").lower()
    factor = {
        "": 1.0,
        "f": 1e-15,
        "pf": 1e-12,
        "nf": 1e-9,
        "uf": 1e-6,
        "mf": 1e-3,
        "s": 1.0,
        "ms": 1e-3,
        "us": 1e-6,
        "ns": 1e-9,
        "ps": 1e-12,
        "ohm": 1.0,
        "kohm": 1e3,
        "k": 1e3,
        "mohm": 1e6,
        "v": 1.0,
        "mv": 1e-3,
        "m": 1.0,
        "u": 1e-6,
        "um": 1e-6,
        "n": 1e-9,
        "nm": 1e-9,
    }.get(unit)
    if factor is None:
        return None
    return float(match.group(1)) * factor


def _is_load_cap_name(name: str) -> bool:
    compact = name.replace("_", "").replace("-", "")
    return compact in {"cload", "loadcap", "loadcapacitance"} or ("load" in name and ("cap" in name or name.endswith("_c")))


def _is_storage_cap_name(name: str) -> bool:
    return ("store" in name or "storage" in name or "hold" in name) and ("cap" in name or name.endswith("_c"))


def _is_driver_resistance_name(name: str) -> bool:
    return ("driver" in name or "drive" in name or name.startswith("r_")) and ("resistance" in name or name.endswith("_r") or name.startswith("r_"))


def _is_width_name(name: str) -> bool:
    return ("width" in name or name.endswith(".w") or name.endswith("_w")) and "pulse" not in name


def _is_timing_spacing_name(name: str) -> bool:
    return "spacing" in name or "pulse_delay" in name or name in {"delay", "timing_delay"}


def _is_pulse_width_name(name: str) -> bool:
    return "pulse" in name and "width" in name


def _is_vdd_name(name: str) -> bool:
    return name in {"vdd", "v_dd", "supply_voltage", "v_supply"} or name.endswith("_vdd")


def _is_vth_name(name: str) -> bool:
    return name in {"vth", "v_th", "threshold_voltage"} or "threshold" in name


def _is_voltage_name(name: str) -> bool:
    return _is_vdd_name(name) or _is_vth_name(name)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _min_positive(current: float | None, value: float) -> float:
    if value <= 0:
        return current if current is not None else value
    if current is None or current <= 0:
        return value
    return min(current, value)


def _rationale(proxy_metrics: dict[str, float | str | None], violations: list[str]) -> str:
    if violations:
        return "hard physics prior violation: " + "; ".join(violations)
    available = [key for key, value in proxy_metrics.items() if value is not None]
    if not available:
        return "no physics proxies were computable; neutral prior score"
    return "physics prior passed using " + ", ".join(available[:6])


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
