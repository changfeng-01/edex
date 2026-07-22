from __future__ import annotations

import math
from typing import Any, Mapping

from .physics_protocol import PhysicalEffect, PhysicalEffectPacket


def build_goa_effect_packet(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    source_profile: str = "goa_8t1c_720",
    scenario_key: str = "nominal",
) -> PhysicalEffectPacket:
    effects = {
        "critical_time_log_delta": _log_ratio(
            _first(baseline, "critical_rc_delay_s", "delay_s", "fall_time_s"),
            _first(current, "critical_rc_delay_s", "delay_s", "fall_time_s"),
            sign=-1.0,
        ),
        "output_headroom_normalized_delta": _linear(
            _first(baseline, "output_headroom_v", "bootstrap_headroom_v", "voh_min_v"),
            _first(current, "output_headroom_v", "bootstrap_headroom_v", "voh_min_v"),
            scale=float(current.get("headroom_scale_v", baseline.get("headroom_scale_v", 1.0))),
        ),
        "power_log_delta": _log_ratio(
            _first(baseline, "power_w", "power_total_w"),
            _first(current, "power_w", "power_total_w"),
            sign=-1.0,
        ),
        "mismatch_sensitivity_log_delta": _log_ratio(
            baseline.get("mismatch_sensitivity"), current.get("mismatch_sensitivity"), sign=-1.0
        ),
        "task_gain_margin_delta": PhysicalEffect("not_applicable"),
        "bootstrap_coupling_delta": _linear(
            baseline.get("bootstrap_coupling_factor_v3"),
            current.get("bootstrap_coupling_factor_v3"),
            scale=1.0,
        ),
        "tft_region_margin_delta": _linear(
            baseline.get("tft_region_margin_v"),
            current.get("tft_region_margin_v"),
            scale=float(current.get("tft_margin_scale_v", 1.0)),
        ),
    }
    return PhysicalEffectPacket(
        source_agent="GOAAgent",
        source_profile=source_profile,
        model_version="goa_existing_physics_v4",
        scenario_key=scenario_key,
        effects=effects,
        raw_si={str(name): value for name, value in current.items() if _finite(value) is not None},
        applicability={"circuit_family": "GOA/TFT"},
        evidence={
            "data_source": str(current.get("data_source", "real_simulation_csv")),
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        },
    )


def _first(values: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if values.get(name) is not None:
            return values[name]
    return None


def _log_ratio(baseline: Any, current: Any, *, sign: float) -> PhysicalEffect:
    base = _finite(baseline)
    value = _finite(current)
    if base is None or value is None or base <= 0.0 or value <= 0.0:
        return PhysicalEffect("missing")
    return PhysicalEffect("supported", sign * math.log(value / base), 0.25)


def _linear(baseline: Any, current: Any, *, scale: float) -> PhysicalEffect:
    base = _finite(baseline)
    value = _finite(current)
    if base is None or value is None or not math.isfinite(scale) or scale <= 0.0:
        return PhysicalEffect("missing")
    return PhysicalEffect("supported", (value - base) / scale, 0.25)


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
