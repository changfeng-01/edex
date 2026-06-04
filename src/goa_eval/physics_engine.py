from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

import pandas as pd

from goa_eval.param_space import parse_engineering_value


@dataclass(frozen=True)
class PhysicsEvaluation:
    """Lightweight circuit-physics prior for candidate ranking.

    This is not a SPICE replacement.  It only computes conservative proxy
    quantities that are useful before the next simulation run: RC delay,
    drive/load balance, storage-capacitance margin, timing spacing, and
    voltage margin.
    """

    physics_score: float
    physical_hard_passed: bool
    proxy_metrics: dict[str, float | str | None]
    violations: list[str]
    rationale: str
    model_status: str = "physics_prior_engine_v1"

    def metadata(self) -> dict[str, Any]:
        return {
            "physics_score": round(float(self.physics_score), 6),
            "physical_hard_passed": bool(self.physical_hard_passed),
            "physics_proxy_json": json.dumps(self.proxy_metrics, ensure_ascii=False, sort_keys=True),
            "physics_violations": ";".join(self.violations),
            "source_candidate_rationale": self.rationale,
            "model_status": self.model_status,
        }


def evaluate_candidate_physics(
    parameters: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> PhysicsEvaluation:
    """Evaluate a candidate point with explicit circuit-physics proxies.

    The score is intentionally conservative.  It rewards candidates that move
    toward smaller RC delay, stronger drive/load ratio, larger hold/storage
    margin, safer timing separation, and positive voltage headroom.  All values
    remain proxy-level evidence and still require SPICE re-simulation.
    """

    state = _physics_state(parameters)
    baseline_state = _physics_state(baseline or {}) if baseline else {}
    proxy = _proxy_metrics(state)
    baseline_proxy = _proxy_metrics(baseline_state) if baseline_state else {}

    score = 70.0
    violations: list[str] = []
    rationale_parts: list[str] = []

    rc_delay = _as_float(proxy.get("rc_delay_s"))
    baseline_rc_delay = _as_float(baseline_proxy.get("rc_delay_s"))
    if rc_delay is not None:
        score += 8.0
        if baseline_rc_delay is not None and baseline_rc_delay > 0:
            ratio = rc_delay / baseline_rc_delay
            if ratio < 0.85:
                score += min(12.0, 12.0 * (1.0 - ratio))
                rationale_parts.append("RC delay proxy improves versus baseline")
            elif ratio > 1.15:
                penalty = min(18.0, 18.0 * (ratio - 1.0))
                score -= penalty
                violations.append("rc_delay_proxy_degraded_vs_baseline")
                rationale_parts.append("mask penalty: RC delay degraded versus baseline")
        elif rc_delay > 0:
            score += _bounded_log_reward(1.0 / rc_delay, scale=5.0)

    drive_load = _as_float(proxy.get("drive_to_load_ratio"))
    baseline_drive_load = _as_float(baseline_proxy.get("drive_to_load_ratio"))
    if drive_load is not None and drive_load > 0:
        score += min(8.0, _bounded_log_reward(drive_load, scale=2.0))
        if baseline_drive_load is not None and baseline_drive_load > 0:
            ratio = drive_load / baseline_drive_load
            if ratio > 1.1:
                score += min(10.0, 5.0 * math.log10(max(ratio, 1.0)))
                rationale_parts.append("drive/load proxy improves versus baseline")
            elif ratio < 0.8:
                score -= min(12.0, 12.0 * (1.0 - ratio))
                violations.append("drive_load_proxy_weaker_than_baseline")
                rationale_parts.append("mask penalty: drive/load ratio weakened versus baseline")

    storage_ratio = _as_float(proxy.get("storage_to_load_cap_ratio"))
    if storage_ratio is not None:
        if storage_ratio >= 1.0:
            score += min(8.0, 4.0 * storage_ratio)
            rationale_parts.append("storage capacitance margin is acceptable")
        else:
            score -= 18.0 * (1.0 - storage_ratio)
            violations.append("storage_cap_margin_below_load_cap")
            rationale_parts.append("mask penalty: storage capacitance margin is below load capacitance")

    timing_margin = _as_float(proxy.get("timing_spacing_over_rc"))
    if timing_margin is not None:
        if timing_margin >= 2.0:
            score += min(10.0, 2.5 * timing_margin)
            rationale_parts.append("timing spacing is safely above RC proxy")
        else:
            score -= 28.0 * (2.0 - timing_margin) / 2.0
            violations.append("timing_spacing_below_2x_rc_delay")
            rationale_parts.append("mask penalty: timing spacing is below 2x RC delay")

    pulse_margin = _as_float(proxy.get("pulse_width_over_rc"))
    if pulse_margin is not None:
        if pulse_margin >= 3.0:
            score += min(8.0, 1.5 * pulse_margin)
        else:
            score -= 18.0 * (3.0 - pulse_margin) / 3.0
            violations.append("pulse_width_below_3x_rc_delay")
            rationale_parts.append("mask penalty: pulse width is below 3x RC delay")

    voltage_margin = _as_float(proxy.get("voltage_margin_v"))
    if voltage_margin is not None:
        if voltage_margin <= 0:
            score -= 35.0
            violations.append("non_positive_voltage_margin")
            rationale_parts.append("mask penalty: voltage margin is non-positive")
        elif voltage_margin < 0.2:
            score -= 12.0 * (0.2 - voltage_margin) / 0.2
            violations.append("low_voltage_margin")
            rationale_parts.append("mask penalty: voltage margin is low")
        else:
            score += min(6.0, 3.0 * voltage_margin)

    score = max(0.0, min(100.0, score))
    hard_violations = {
        "non_positive_voltage_margin",
        "timing_spacing_below_2x_rc_delay",
        "pulse_width_below_3x_rc_delay",
    }
    hard_passed = not hard_violations.intersection(violations)
    rationale = "; ".join(rationale_parts) if rationale_parts else "physics-prior candidate ranked by RC, drive/load, storage, timing, and voltage proxies"
    return PhysicsEvaluation(score, hard_passed, proxy, violations, rationale)


def rank_physics_guided_points(
    points: list[dict[str, Any]],
    *,
    history: pd.DataFrame | None = None,
    max_points: int | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Rank sweep points using the physical prior engine.

    Returns ``(point, metadata)`` pairs that can be fed into the existing
    multi-round optimizer metadata path.  The function does not run ngspice and
    does not upgrade evidence level.
    """

    baseline = _best_baseline(history) if history is not None else {}
    ranked: list[tuple[dict[str, Any], dict[str, Any], PhysicsEvaluation]] = []
    for point in points:
        evaluation = evaluate_candidate_physics(point, baseline=baseline)
        metadata = {
            "candidate_source": "physics_prior_engine",
            "optimizer_strategy": "physics_guided_hybrid",
            "objective_score": round(float(evaluation.physics_score), 6),
            "model_prediction": "",
            **evaluation.metadata(),
        }
        ranked.append((point, metadata, evaluation))
    ranked.sort(
        key=lambda item: (
            not item[2].physical_hard_passed,
            -float(item[2].physics_score),
            json.dumps(item[0], ensure_ascii=False, sort_keys=True),
        )
    )
    selected = ranked[: max_points if max_points is not None else len(ranked)]
    return [(point, metadata) for point, metadata, _ in selected]


def _physics_state(parameters: dict[str, Any]) -> dict[str, float]:
    state: dict[str, float] = {}
    numeric = {str(name): parse_engineering_value(value) for name, value in parameters.items()}
    for name, value in numeric.items():
        if value is None:
            continue
        lower = name.lower()
        if _is_width_name(lower):
            state["total_width_m"] = state.get("total_width_m", 0.0) + value
        if _is_resistance_name(lower):
            state["drive_resistance_ohm"] = min(value, state.get("drive_resistance_ohm", value))
        if _is_capacitance_name(lower):
            state["total_cap_f"] = state.get("total_cap_f", 0.0) + value
            if "load" in lower:
                state["load_cap_f"] = state.get("load_cap_f", 0.0) + value
            if any(token in lower for token in ["store", "storage", "hold"]):
                state["storage_cap_f"] = state.get("storage_cap_f", 0.0) + value
        if _is_delay_name(lower):
            state[f"delay::{name}"] = value
        if _is_pulse_width_name(lower):
            state[f"pulse_width::{name}"] = value
        if lower in {"vdd", "v_supply", "supply_v"} or "vdd" in lower:
            state["vdd_v"] = value
        if "vth" in lower or "threshold" in lower:
            state["threshold_v"] = value
    return state


def _proxy_metrics(state: dict[str, float]) -> dict[str, float | str | None]:
    total_width = _positive(state.get("total_width_m"))
    drive_resistance = _positive(state.get("drive_resistance_ohm"))
    total_cap = _positive(state.get("total_cap_f"))
    load_cap = _positive(state.get("load_cap_f")) or total_cap
    storage_cap = _positive(state.get("storage_cap_f"))

    effective_resistance = drive_resistance
    if effective_resistance is None and total_width is not None:
        effective_resistance = 1.0 / max(total_width, 1e-30)
    rc_delay = effective_resistance * total_cap if effective_resistance is not None and total_cap is not None else None

    drive_to_load = None
    if total_width is not None and load_cap is not None:
        drive_to_load = total_width / max(load_cap, 1e-30)
    elif drive_resistance is not None and load_cap is not None:
        drive_to_load = 1.0 / max(drive_resistance * load_cap, 1e-30)

    delays = sorted(value for key, value in state.items() if key.startswith("delay::") and value >= 0)
    spacing = _min_positive_gap(delays)
    pulse_widths = [value for key, value in state.items() if key.startswith("pulse_width::") and value > 0]
    min_pulse_width = min(pulse_widths) if pulse_widths else None

    voltage_margin = None
    if "vdd_v" in state:
        voltage_margin = state["vdd_v"] - state.get("threshold_v", 0.0)

    return {
        "rc_delay_s": rc_delay,
        "drive_to_load_ratio": drive_to_load,
        "storage_to_load_cap_ratio": storage_cap / load_cap if storage_cap is not None and load_cap is not None else None,
        "min_timing_spacing_s": spacing,
        "timing_spacing_over_rc": spacing / rc_delay if spacing is not None and rc_delay not in {None, 0.0} else None,
        "min_pulse_width_s": min_pulse_width,
        "pulse_width_over_rc": min_pulse_width / rc_delay if min_pulse_width is not None and rc_delay not in {None, 0.0} else None,
        "voltage_margin_v": voltage_margin,
    }


def _best_baseline(history: pd.DataFrame | None) -> dict[str, Any]:
    if history is None or history.empty:
        return {}
    frame = history.copy()
    if "overall_score" in frame:
        frame["_score"] = pd.to_numeric(frame["overall_score"], errors="coerce")
        frame = frame.sort_values("_score", ascending=False, kind="mergesort")
    row = frame.iloc[0].drop(labels=["_score"], errors="ignore")
    payload: dict[str, Any] = {}
    if isinstance(row.get("parameters_json"), str):
        try:
            parsed = json.loads(row.get("parameters_json"))
            if isinstance(parsed, dict):
                payload.update(parsed)
        except json.JSONDecodeError:
            pass
    for key, value in row.items():
        if key not in payload and parse_engineering_value(value) is not None:
            payload[str(key)] = value
    return payload


def _is_width_name(name: str) -> bool:
    if "pulse" in name or "period" in name or "time" in name:
        return False
    return "width" in name or name.startswith("w_") or name.endswith("_w") or name in {"wn", "wp"}


def _is_resistance_name(name: str) -> bool:
    return "resistance" in name or name.startswith("r_") or name.endswith("_r") or "rdriver" in name or "r_driver" in name


def _is_capacitance_name(name: str) -> bool:
    return "cap" in name or name.startswith("c_") or name.endswith("_c")


def _is_delay_name(name: str) -> bool:
    return "delay" in name or "phase" in name


def _is_pulse_width_name(name: str) -> bool:
    return "pulse_width" in name or name.endswith("_pw") or name == "pw"


def _positive(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return value


def _min_positive_gap(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    gaps = [right - left for left, right in zip(values, values[1:]) if right > left]
    return min(gaps) if gaps else None


def _bounded_log_reward(value: float, *, scale: float) -> float:
    if value <= 0:
        return 0.0
    return max(0.0, min(scale, math.log10(value + 1.0)))


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
