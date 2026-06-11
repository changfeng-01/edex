from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from goa_eval.io_utils import write_json
from goa_eval.metrics import RealEvalConfig, evaluate_waveform_metrics
from goa_eval.paper_digitization.schemas import (
    ENGINEERING_VALIDITY,
    PAPER_CLAIM_BOUNDARY,
    SOURCE_TYPE_PAPER_DIGITIZED,
)
from goa_eval.waveform_io import read_real_waveform


def run_quality_check(
    *,
    waveform_path: Path,
    case_id: str | None = None,
    high_threshold: float = 5.0,
    low_threshold: float = 1.0,
    supply_min_v: float | None = None,
    supply_max_v: float | None = None,
    reported_metrics_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    raw = pd.read_csv(waveform_path)
    normalized_columns = [str(column).strip().lower() for column in raw.columns]
    time_column = raw.columns[normalized_columns.index("time")] if "time" in normalized_columns else raw.columns[0]
    time = pd.to_numeric(raw[time_column], errors="coerce")
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    checks["time_monotonic"] = bool(time.dropna().is_monotonic_increasing and not time.dropna().duplicated().any())
    if not checks["time_monotonic"]:
        warnings.append("time_not_strictly_increasing_or_duplicate")

    waveform = read_real_waveform(waveform_path)
    signal_columns = [column for column in waveform.frame.columns if column != "time"]
    voltage_values = waveform.frame[signal_columns].stack() if signal_columns else pd.Series(dtype=float)
    checks["voltage_range_ok"] = True
    if supply_min_v is not None and supply_max_v is not None and not voltage_values.empty:
        margin = max(1.0, 0.10 * abs(float(supply_max_v) - float(supply_min_v)))
        low_ok = voltage_values.min() >= float(supply_min_v) - margin
        high_ok = voltage_values.max() <= float(supply_max_v) + margin
        checks["voltage_range_ok"] = bool(low_ok and high_ok)
        if not checks["voltage_range_ok"]:
            warnings.append("warning_voltage_out_of_range")

    checks["pulse_detected"] = False
    try:
        config = RealEvalConfig(high_threshold=high_threshold, low_threshold=low_threshold)
        evaluation = evaluate_waveform_metrics(waveform.frame, config, output_nodes=signal_columns)
        checks["pulse_detected"] = bool(evaluation.summary.get("All_pulses_exist"))
        if not checks["pulse_detected"]:
            warnings.append("warning_no_legal_pulse_detected")
    except Exception as exc:
        warnings.append(f"warning_pulse_check_failed:{type(exc).__name__}:{exc}")

    checks["reported_metric_consistency"] = _reported_metric_consistency(
        reported_metrics_path=reported_metrics_path,
        waveform_path=waveform_path,
    )
    if checks["reported_metric_consistency"] == "warning":
        warnings.append("warning_reported_metric_diff_over_30_percent")

    warnings.append("weak_label_digitized_from_published_figure_not_original_simulation")
    status = "pass"
    if warnings:
        status = "warning"
    if "warning_voltage_out_of_range" in warnings:
        status = "warning_voltage_out_of_range"
    result = {
        "case_id": case_id or waveform_path.parent.name,
        "quality_status": status,
        "warnings": warnings,
        "checks": checks,
        "source_type": SOURCE_TYPE_PAPER_DIGITIZED,
        "weak_label": True,
        "engineering_validity": ENGINEERING_VALIDITY,
        "claim_boundary": PAPER_CLAIM_BOUNDARY,
    }
    if output_path:
        write_json(output_path, result)
    return result


def _reported_metric_consistency(*, reported_metrics_path: Path | None, waveform_path: Path) -> str:
    if reported_metrics_path is None or not reported_metrics_path.exists():
        return "not_available"
    raw = yaml.safe_load(reported_metrics_path.read_text(encoding="utf-8")) or {}
    reported = raw.get("reported_metrics") or raw.get("metrics") or raw
    if not isinstance(reported, dict):
        return "not_available"
    metric_keys = {"reported_rise_time", "reported_fall_time", "reported_pulse_width"}
    if not any(key in reported for key in metric_keys):
        return "not_available"
    try:
        waveform = read_real_waveform(waveform_path)
        output_nodes = [column for column in waveform.frame.columns if column != "time"]
        evaluation = evaluate_waveform_metrics(waveform.frame, RealEvalConfig(), output_nodes=output_nodes)
    except Exception:
        return "warning"
    observed = {
        "reported_rise_time": _mean_metric(evaluation.stage_rows, "RiseTime"),
        "reported_fall_time": _mean_metric(evaluation.stage_rows, "FallTime"),
        "reported_pulse_width": _mean_metric(evaluation.stage_rows, "PulseWidth"),
    }
    compared = False
    for key in metric_keys:
        if reported.get(key) in (None, "", "TODO_NEEDS_MANUAL_EXTRACTION"):
            continue
        expected = _as_float(reported.get(key))
        current = observed.get(key)
        if expected is None or current in (None, 0):
            continue
        compared = True
        if abs(float(current) - expected) / max(abs(expected), 1.0e-30) > 0.30:
            return "warning"
    return "pass" if compared else "not_available"


def _mean_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = pd.to_numeric(pd.Series([row.get(key) for row in rows]), errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run quality checks for a paper-digitized waveform.")
    parser.add_argument("--waveform", type=Path, required=True)
    parser.add_argument("--case-id")
    parser.add_argument("--high-threshold", type=float, default=5.0)
    parser.add_argument("--low-threshold", type=float, default=1.0)
    parser.add_argument("--supply-min-v", type=float)
    parser.add_argument("--supply-max-v", type=float)
    parser.add_argument("--reported-metrics", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_quality_check(
        waveform_path=args.waveform,
        case_id=args.case_id,
        high_threshold=args.high_threshold,
        low_threshold=args.low_threshold,
        supply_min_v=args.supply_min_v,
        supply_max_v=args.supply_max_v,
        reported_metrics_path=args.reported_metrics,
        output_path=args.output,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
