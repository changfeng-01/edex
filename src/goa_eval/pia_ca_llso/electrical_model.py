from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd


V3_CANONICAL_FEATURES = (
    "pullup_overdrive_v",
    "pulldown_overdrive_v",
    "pullup_effective_resistance_ohm",
    "pulldown_effective_resistance_ohm",
    "effective_load_capacitance_f",
    "pullup_rc_delay_s",
    "pulldown_rc_delay_s",
    "critical_rc_delay_s",
    "bootstrap_coupling_factor_v3",
    "bootstrap_headroom_v",
    "drive_balance_log_ratio",
    "clock_slew_over_rc_ratio",
)

_CAPACITANCE_FACTORS = {"f": 1.0, "pf": 1e-12, "ff": 1e-15, "nf": 1e-9, "uf": 1e-6}
_RESISTANCE_FACTORS = {"ohm": 1.0, "kohm": 1e3, "mohm": 1e6}
_TIME_FACTORS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12}
_REGION_CODES = {"unknown": -1.0, "off": 0.0, "linear": 1.0, "saturation": 2.0}


def attach_v3_electrical_features(
    features: pd.DataFrame,
    frame: pd.DataFrame,
    profile_config: Mapping[str, Any],
) -> dict[str, Any]:
    model_config = profile_config.get("electrical_model", {})
    if not isinstance(model_config, Mapping):
        return {"electrical_model_version": "disabled"}
    observations = _load_observations(profile_config.get("pvt", {}))
    rows: list[dict[str, Any]] = []
    for _, source_row in frame.iterrows():
        try:
            nominal, electrical = _compute_electrical_row(source_row.to_dict(), profile_config)
            pvt_features, pvt_status, pvt_diagnostics = _compute_pvt_features(
                source_row.to_dict(),
                profile_config,
                observations,
            )
        except ValueError as exc:
            nominal = {feature: 0.0 for feature in V3_CANONICAL_FEATURES}
            nominal.update({"pullup_region_code": -1.0, "pulldown_region_code": -1.0, "bootstrap_region_code": -1.0})
            electrical = {
                "model": str(model_config.get("model", "tft_square_law_v1")),
                "status": "missing",
                "reason": str(exc),
                "features": {feature: "missing" for feature in V3_CANONICAL_FEATURES},
                "devices": {},
                "parasitics": {"source": "unavailable", "status": "missing"},
            }
            pvt_features = {}
            pvt_status = "missing"
            pvt_diagnostics = {"status": "missing", "reason": str(exc), "scenarios": {}}
        status_map = dict(electrical["features"])
        rows.append(
            {
                **nominal,
                "physics_feature_status_json": json.dumps(status_map, ensure_ascii=True, sort_keys=True),
                "capm_electrical_status_json": json.dumps(electrical, ensure_ascii=True, sort_keys=True),
                "capm_pvt_features_json": json.dumps(pvt_features, ensure_ascii=True, sort_keys=True),
                "capm_pvt_status": pvt_status,
                "capm_pvt_diagnostics_json": json.dumps(pvt_diagnostics, ensure_ascii=True, sort_keys=True),
            }
        )
    attached = pd.DataFrame(rows, index=frame.index)
    for column in attached.columns:
        features[column] = attached[column]
    return {
        "electrical_model_version": "v3",
        "canonical_feature_names": list(V3_CANONICAL_FEATURES),
        "pvt_enabled": bool(_pvt_config(profile_config).get("scenarios")),
    }


def _compute_electrical_row(
    row: Mapping[str, Any],
    profile_config: Mapping[str, Any],
) -> tuple[dict[str, float], dict[str, Any]]:
    model_config = profile_config.get("electrical_model", {})
    units = model_config.get("units", {}) if isinstance(model_config, Mapping) else {}
    cap_factor = _unit_factor(units.get("capacitance", "F"), _CAPACITANCE_FACTORS)
    time_factor = _unit_factor(units.get("time", "s"), _TIME_FACTORS)
    parasitics, parasitic_status = _resolve_parasitics(row, profile_config.get("parasitics", {}))
    c_load = max((_number(row.get("C_load")) or 0.0) * cap_factor, 0.0)
    c_boot = max((_number(row.get("C_boot")) or 0.0) * cap_factor, 0.0)
    effective_load = c_load + parasitics["output_capacitance_f"]

    devices = model_config.get("devices", {}) if isinstance(model_config, Mapping) else {}
    device_results: dict[str, dict[str, Any]] = {}
    for role in ("pullup", "pulldown", "bootstrap", "reset"):
        role_config = devices.get(role)
        if isinstance(role_config, Mapping):
            device_results[role] = _evaluate_device(row, role_config, role)

    pullup = device_results.get("pullup", _missing_device())
    pulldown = device_results.get("pulldown", _missing_device())
    bootstrap = device_results.get("bootstrap", _missing_device())
    pullup_r = max(float(pullup["resistance_ohm"]) + parasitics["pullup_resistance_ohm"], 0.0)
    pulldown_r = max(float(pulldown["resistance_ohm"]) + parasitics["pulldown_resistance_ohm"], 0.0)
    pullup_tau = pullup_r * effective_load
    pulldown_tau = pulldown_r * effective_load
    critical_tau = max(pullup_tau, pulldown_tau)
    denominator = c_boot + effective_load + parasitics["bootstrap_loss_capacitance_f"]
    coupling = c_boot / denominator if denominator > 0 else 0.0
    clk_amp = max(_number(row.get("CLK_amp")) or 0.0, 0.0)
    bootstrap_headroom = float(bootstrap["overdrive_v"]) + coupling * clk_amp
    resistance_floor = 1e-30
    drive_balance = math.log(max(pullup_r, resistance_floor) / max(pulldown_r, resistance_floor))
    slew = max((_number(row.get("CLK_rise_time")) or 0.0) + (_number(row.get("CLK_fall_time")) or 0.0), 0.0) * time_factor
    slew_ratio = slew / max(critical_tau, 1e-30)

    canonical = {
        "pullup_overdrive_v": float(pullup["overdrive_v"]),
        "pulldown_overdrive_v": float(pulldown["overdrive_v"]),
        "pullup_effective_resistance_ohm": pullup_r,
        "pulldown_effective_resistance_ohm": pulldown_r,
        "effective_load_capacitance_f": effective_load,
        "pullup_rc_delay_s": pullup_tau,
        "pulldown_rc_delay_s": pulldown_tau,
        "critical_rc_delay_s": critical_tau,
        "bootstrap_coupling_factor_v3": coupling,
        "bootstrap_headroom_v": bootstrap_headroom,
        "drive_balance_log_ratio": drive_balance,
        "clock_slew_over_rc_ratio": slew_ratio,
        "pullup_region_code": _REGION_CODES[str(pullup["region"])],
        "pulldown_region_code": _REGION_CODES[str(pulldown["region"])],
        "bootstrap_region_code": _REGION_CODES[str(bootstrap["region"])],
    }
    feature_status = {
        "pullup_overdrive_v": str(pullup["status"]),
        "pulldown_overdrive_v": str(pulldown["status"]),
        "pullup_effective_resistance_ohm": str(pullup["status"]),
        "pulldown_effective_resistance_ohm": str(pulldown["status"]),
        "effective_load_capacitance_f": str(parasitic_status["status"]),
        "pullup_rc_delay_s": _combine_status(str(pullup["status"]), str(parasitic_status["status"])),
        "pulldown_rc_delay_s": _combine_status(str(pulldown["status"]), str(parasitic_status["status"])),
        "critical_rc_delay_s": _combine_status(str(pullup["status"]), str(pulldown["status"])),
        "bootstrap_coupling_factor_v3": str(parasitic_status["status"]),
        "bootstrap_headroom_v": _combine_status(str(bootstrap["status"]), str(parasitic_status["status"])),
        "drive_balance_log_ratio": _combine_status(str(pullup["status"]), str(pulldown["status"])),
        "clock_slew_over_rc_ratio": _combine_status(str(pullup["status"]), str(pulldown["status"])),
    }
    electrical_status = {
        "model": str(model_config.get("model", "tft_square_law_v1")),
        "status": _combine_status(*feature_status.values()),
        "features": feature_status,
        "devices": {
            role: {key: value for key, value in result.items() if key != "resistance_ohm"}
            for role, result in device_results.items()
        },
        "parasitics": parasitic_status,
    }
    return canonical, electrical_status


def _evaluate_device(row: Mapping[str, Any], config: Mapping[str, Any], role: str) -> dict[str, Any]:
    polarity = str(config.get("polarity", "n")).strip().lower()
    sign = -1.0 if polarity.startswith("p") else 1.0
    width = _column_number(row, config.get("width_column"))
    length = _column_number(row, config.get("length_column"))
    mobility = _column_number(row, config.get("mobility_column"))
    cox = _column_number(row, config.get("cox_column"))
    threshold = _column_number(row, config.get("threshold_column"))
    vgs_raw = _column_number(row, config.get("vgs_column"))
    vds_raw = _column_number(row, config.get("vds_column"))
    observed_r = _column_number(row, config.get("observed_resistance_column"))
    channel_lambda = max(_number(config.get("channel_length_modulation_per_v")) or 0.0, 0.0)
    if threshold is None:
        threshold = _number(row.get("Vth_shift"))
    threshold_magnitude = abs(threshold) if threshold is not None else 0.0
    bias_available = vgs_raw is not None and vds_raw is not None and threshold is not None
    if bias_available:
        vgs = sign * float(vgs_raw)
        vds = max(sign * float(vds_raw), 0.0)
        overdrive = vgs - threshold_magnitude
        if overdrive <= 0.0:
            region = "off"
        elif vds < overdrive:
            region = "linear"
        else:
            region = "saturation"
    else:
        vds = 0.0
        overdrive = 0.0
        region = "unknown"

    if observed_r is not None and observed_r >= 0.0:
        resistance = float(observed_r)
        status = "observed"
    elif None not in {width, length, mobility, cox} and float(length) > 0.0 and bias_available:
        beta = max(float(mobility) * float(cox) * float(width) / float(length), 0.0)
        if region == "off":
            current = 0.0
        elif region == "linear":
            current = beta * (overdrive * vds - 0.5 * vds**2)
        else:
            current = 0.5 * beta * overdrive**2 * (1.0 + channel_lambda * vds)
        resistance = vds / max(current, 1e-30) if vds > 0.0 else 1.0 / max(beta * max(overdrive, 0.0), 1e-30)
        status = "physical"
    else:
        ratio = max((float(width) / float(length)) if width is not None and length not in {None, 0.0} else 1.0, 1e-12)
        fallback_margin = max(abs(_number(row.get("VGH")) or 0.0) - threshold_magnitude, 1e-12)
        resistance = 1.0 / (ratio * fallback_margin)
        status = "proxy_fallback"
    return {
        "role": role,
        "polarity": "p" if sign < 0 else "n",
        "region": region,
        "overdrive_v": float(overdrive),
        "resistance_ohm": float(max(resistance, 0.0)),
        "status": status,
    }


def _resolve_parasitics(row: Mapping[str, Any], config: Any) -> tuple[dict[str, float], dict[str, Any]]:
    config = config if isinstance(config, Mapping) else {}
    values = {
        "output_capacitance_f": 0.0,
        "bootstrap_loss_capacitance_f": 0.0,
        "pullup_resistance_ohm": 0.0,
        "pulldown_resistance_ohm": 0.0,
    }
    found: set[str] = set()
    direct = config.get("direct_columns", {})
    semantic_map = {
        "output_capacitance": ("output_capacitance_f", _CAPACITANCE_FACTORS),
        "bootstrap_loss_capacitance": ("bootstrap_loss_capacitance_f", _CAPACITANCE_FACTORS),
        "pullup_resistance": ("pullup_resistance_ohm", _RESISTANCE_FACTORS),
        "pulldown_resistance": ("pulldown_resistance_ohm", _RESISTANCE_FACTORS),
    }
    if isinstance(direct, Mapping):
        for semantic, (target, factors) in semantic_map.items():
            spec = direct.get(semantic)
            if not isinstance(spec, Mapping):
                continue
            raw = _column_number(row, spec.get("column"))
            if raw is None:
                continue
            values[target] = max(raw * _unit_factor(spec.get("unit", "F" if "capacitance" in semantic else "ohm"), factors), 0.0)
            found.add(target)
    source = "direct" if found else "zero_fallback"
    summary_column = config.get("summary_path_column")
    summary_path = row.get(summary_column) if isinstance(summary_column, str) else None
    if summary_path:
        try:
            payload = json.loads(Path(str(summary_path)).read_text(encoding="utf-8"))
            r_factor = _unit_factor(payload.get("resistance_unit", "ohm"), _RESISTANCE_FACTORS)
            c_factor = _unit_factor(payload.get("capacitance_unit", "F"), _CAPACITANCE_FACTORS)
            role_map = config.get("net_role_map", {})
            for entry in payload.get("grouped_by_net", []):
                role = role_map.get(str(entry.get("net"))) if isinstance(role_map, Mapping) else None
                target_r = {"pullup_path": "pullup_resistance_ohm", "pulldown_path": "pulldown_resistance_ohm"}.get(role)
                target_c = {"output": "output_capacitance_f", "bootstrap_loss": "bootstrap_loss_capacitance_f"}.get(role)
                if target_r and target_r not in found and _number(entry.get("resistance")) is not None:
                    values[target_r] += max(float(entry["resistance"]) * r_factor, 0.0)
                if target_c and target_c not in found and _number(entry.get("capacitance")) is not None:
                    values[target_c] += max(float(entry["capacitance"]) * c_factor, 0.0)
            source = "direct" if found else "summary"
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            source = "invalid_summary" if not found else source
    if values["output_capacitance_f"] == 0.0 and _number(row.get("C_parasitic")) is not None:
        legacy_unit = config.get("legacy_capacitance_unit", "F")
        values["output_capacitance_f"] = max(float(row["C_parasitic"]) * _unit_factor(legacy_unit, _CAPACITANCE_FACTORS), 0.0)
        source = "legacy" if not found else source
    resistance_multiplier = max(_number(row.get("__pvt_resistance_multiplier")) or 1.0, 0.0)
    capacitance_multiplier = max(_number(row.get("__pvt_capacitance_multiplier")) or 1.0, 0.0)
    values["pullup_resistance_ohm"] *= resistance_multiplier
    values["pulldown_resistance_ohm"] *= resistance_multiplier
    values["output_capacitance_f"] *= capacitance_multiplier
    values["bootstrap_loss_capacitance_f"] *= capacitance_multiplier
    status = "physical" if source in {"direct", "summary"} else "proxy_fallback"
    return values, {"source": source, "status": status, **values}


def _compute_pvt_features(
    row: Mapping[str, Any],
    profile_config: Mapping[str, Any],
    observations: pd.DataFrame,
) -> tuple[dict[str, dict[str, float]], str, dict[str, Any]]:
    pvt = _pvt_config(profile_config)
    scenarios = pvt.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        return {}, "nominal_only", {"status": "nominal_only", "scenarios": {}}
    scenario_features: dict[str, dict[str, float]] = {}
    diagnostics: dict[str, Any] = {"scenarios": {}}
    statuses: list[str] = []
    sample_column = str(pvt.get("sample_id_column", "sample_id"))
    sample_value = row.get(sample_column)
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            continue
        key = _scenario_key(scenario)
        corner = str(scenario.get("corner", "tt"))
        observed = _matching_observation(observations, sample_column, sample_value, scenario)
        corner_models = pvt.get("corner_models", {})
        corner_model = corner_models.get(corner) if isinstance(corner_models, Mapping) else None
        if observed is None and not isinstance(corner_model, Mapping):
            diagnostics["scenarios"][key] = {"status": "missing", "reason": "corner_model_and_observation_missing"}
            statuses.append("missing")
            continue
        projected = dict(row)
        if isinstance(corner_model, Mapping):
            projected = _project_pvt_row(projected, profile_config, pvt, scenario, corner_model)
        if observed is not None:
            projected.update({name: value for name, value in observed.items() if pd.notna(value)})
        canonical, _ = _compute_electrical_row(projected, profile_config)
        scenario_features[key] = canonical
        if observed is not None and isinstance(corner_model, Mapping):
            status = "mixed_observed_projected"
        elif observed is not None:
            status = "observed"
        else:
            status = "proxy_projected"
        diagnostics["scenarios"][key] = {"status": status, "corner": corner}
        statuses.append(status)
    overall = _aggregate_pvt_status(statuses)
    diagnostics["status"] = overall
    diagnostics["scenario_count"] = len(scenario_features)
    return scenario_features, overall, diagnostics


def _project_pvt_row(
    row: dict[str, Any],
    profile_config: Mapping[str, Any],
    pvt: Mapping[str, Any],
    scenario: Mapping[str, Any],
    corner: Mapping[str, Any],
) -> dict[str, Any]:
    reference_temperature = float(pvt.get("reference_temperature_c", 25.0))
    temperature = float(scenario.get("temperature_c", reference_temperature))
    reference_supply = max(float(pvt.get("reference_supply_v", scenario.get("supply_v", 1.0))), 1e-30)
    supply = float(scenario.get("supply_v", reference_supply))
    temperature_ratio = (temperature + 273.15) / (reference_temperature + 273.15)
    exponent = float(pvt.get("mobility_temperature_exponent", 0.0))
    mobility_scale = float(corner.get("mu_multiplier", 1.0)) * temperature_ratio ** (-exponent)
    threshold_shift = float(corner.get("vth_shift_v", 0.0)) + float(
        pvt.get("vth_temperature_coefficient_v_per_c", 0.0)
    ) * (temperature - reference_temperature)
    supply_scale = supply / reference_supply
    model = profile_config.get("electrical_model", {})
    devices = model.get("devices", {}) if isinstance(model, Mapping) else {}
    for device in devices.values() if isinstance(devices, Mapping) else []:
        if not isinstance(device, Mapping):
            continue
        mobility_column = device.get("mobility_column")
        threshold_column = device.get("threshold_column")
        if isinstance(mobility_column, str) and _number(row.get(mobility_column)) is not None:
            row[mobility_column] = float(row[mobility_column]) * mobility_scale
        if isinstance(threshold_column, str) and _number(row.get(threshold_column)) is not None:
            row[threshold_column] = max(abs(float(row[threshold_column])) + threshold_shift, 0.0)
        for bias_key in ("vgs_column", "vds_column"):
            column = device.get(bias_key)
            if isinstance(column, str) and _number(row.get(column)) is not None:
                row[column] = float(row[column]) * supply_scale
    if _number(row.get("CLK_amp")) is not None:
        row["CLK_amp"] = float(row["CLK_amp"]) * supply_scale
    row["__pvt_resistance_multiplier"] = float(corner.get("resistance_multiplier", 1.0))
    row["__pvt_capacitance_multiplier"] = float(corner.get("capacitance_multiplier", 1.0))
    return row


def _load_observations(config: Any) -> pd.DataFrame:
    config = config if isinstance(config, Mapping) else {}
    path = config.get("observations_csv")
    if not path:
        return pd.DataFrame()
    try:
        return pd.read_csv(Path(str(path)))
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()


def _matching_observation(
    observations: pd.DataFrame,
    sample_column: str,
    sample_value: Any,
    scenario: Mapping[str, Any],
) -> dict[str, Any] | None:
    if observations.empty or sample_column not in observations.columns:
        return None
    mask = observations[sample_column].astype(str) == str(sample_value)
    for column in ("corner", "temperature_c", "supply_v"):
        if column not in observations.columns:
            return None
        if column == "corner":
            mask &= observations[column].astype(str) == str(scenario.get(column))
        else:
            mask &= pd.to_numeric(observations[column], errors="coerce") == float(scenario.get(column))
    matches = observations.loc[mask]
    return None if matches.empty else matches.iloc[0].to_dict()


def _pvt_config(profile_config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = profile_config.get("pvt", {})
    return value if isinstance(value, Mapping) else {}


def _scenario_key(scenario: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(scenario.get("corner", "tt")),
            _format_number(scenario.get("temperature_c", 25.0)),
            _format_number(scenario.get("supply_v", 0.0)),
        ]
    )


def _format_number(value: Any) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else format(number, ".12g")


def _aggregate_pvt_status(statuses: list[str]) -> str:
    if not statuses or "missing" in statuses:
        return "missing"
    if "mixed_observed_projected" in statuses or ("observed" in statuses and "proxy_projected" in statuses):
        return "mixed_observed_projected"
    if all(status == "observed" for status in statuses):
        return "observed"
    return "proxy_projected"


def _combine_status(*statuses: str) -> str:
    values = set(statuses)
    if "missing" in values:
        return "missing"
    if "proxy_fallback" in values or "unknown" in values:
        return "proxy_fallback"
    if "observed" in values:
        return "observed" if values == {"observed"} else "physical"
    return "physical"


def _unit_factor(unit: Any, factors: Mapping[str, float]) -> float:
    normalized = str(unit).strip().lower().replace("Ω", "ohm")
    if normalized not in factors:
        raise ValueError(f"Unsupported electrical unit: {unit}")
    return float(factors[normalized])


def _column_number(row: Mapping[str, Any], column: Any) -> float | None:
    return _number(row.get(column)) if isinstance(column, str) else None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _missing_device() -> dict[str, Any]:
    return {
        "role": "missing",
        "polarity": "unknown",
        "region": "unknown",
        "overdrive_v": 0.0,
        "resistance_ohm": 0.0,
        "status": "missing",
    }
