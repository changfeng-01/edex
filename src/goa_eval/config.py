from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_configs(config_path: Path, thresholds_path: Path) -> tuple[dict, dict]:
    return load_yaml(config_path), load_yaml(thresholds_path)


def load_real_spec(spec_path: Path | None, *, high_threshold: float | None = None, low_threshold: float | None = None) -> dict:
    raw = load_yaml(spec_path) if spec_path else {}
    thresholds = raw.get("thresholds", {})
    cascade = raw.get("cascade", {})
    weights = raw.get("weights", {})
    spec = {
        "high_threshold": _float(thresholds.get("high_threshold", 5.0)),
        "low_threshold": _float(thresholds.get("low_threshold", 1.0)),
        "target_pulse_width": _us_to_s(thresholds.get("target_pulse_width_us", 10.0)),
        "pulse_width_tolerance": _us_to_s(thresholds.get("pulse_width_tolerance_us", 1.0)),
        "max_overlap_ratio": _float(thresholds.get("max_overlap_ratio", 0.10)),
        "max_ripple_v": _float(thresholds.get("max_ripple_v", 0.5)),
        "max_voltage_loss_v": _float(thresholds.get("max_voltage_loss_v", 0.5)),
        "max_delay_std": _us_to_s(thresholds.get("max_delay_std_us", 0.5)),
        "min_voh_margin_v": _float(thresholds.get("min_voh_margin_v", 1.0)),
        "target_refresh_hz": _float(thresholds.get("target_refresh_hz", 60.0)),
        "min_pulse_width": _us_to_s(thresholds.get("min_pulse_width_us", 2.0)),
        "false_trigger_min_duration": _us_to_s(thresholds.get("false_trigger_min_duration_us", 0.0)),
        "ripple_mode": str(thresholds.get("ripple_mode", "hold")),
        "cascade": {
            "stage_count": _int(cascade.get("stage_count", 720)),
            "output_node_pattern": str(cascade.get("output_node_pattern", "o{index}")),
            "stage_group_size": _int(cascade.get("stage_group_size", 60)),
            "sample_nodes": _int_list(cascade.get("sample_nodes", [1, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720])),
        },
        "weights": {
            "function_score": _float(weights.get("function_score", 0.35)),
            "quality_score": _float(weights.get("quality_score", 0.25)),
            "stability_score": _float(weights.get("stability_score", 0.15)),
            "consistency_score": _float(weights.get("consistency_score", 0.15)),
            "cost_score": _float(weights.get("cost_score", 0.10)),
        },
        "source_path": str(spec_path) if spec_path else None,
    }
    if high_threshold is not None:
        spec["high_threshold"] = float(high_threshold)
    if low_threshold is not None:
        spec["low_threshold"] = float(low_threshold)
    return spec


def _float(value) -> float:
    return float(value)


def _int(value) -> int:
    return int(value)


def _int_list(value) -> list[int]:
    if value is None:
        return []
    return [int(item) for item in value]


def _us_to_s(value) -> float:
    return float(value) * 1.0e-6
