from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from goa_eval.io_utils import write_json
from goa_eval.paper_digitization.schemas import (
    ENGINEERING_VALIDITY,
    PAPER_DIGITIZED_EVIDENCE_WEIGHT,
    PAPER_DIGITIZED_LABEL_CONFIDENCE,
    SOURCE_TYPE_PAPER_DIGITIZED_WAVEFORM,
    TRAINING_SAMPLE_COLUMNS,
)


PARAMETER_TO_FEATURE = {
    "VGH": "VGH_V",
    "VGL": "VGL_V",
    "VGLL": "VGLL_V",
    "VGL1": "VGL1_V",
    "VGL2": "VGL2_V",
    "CK_high": "CK_high_V",
    "CK_low": "CK_low_V",
    "CK_period": "CK_period_s",
    "CK_freq": "CK_freq_Hz",
    "pulse_width": "pulse_width_target_s",
    "CLOAD": "CLOAD_F",
    "RLOAD": "RLOAD_ohm",
    "scan_line_C": "scan_line_C_F",
    "scan_line_R": "scan_line_R_ohm",
    "ck_line_C": "ck_line_C_F",
    "ck_line_R": "ck_line_R_ohm",
    "Vth_shift": "Vth_shift_V",
}


def build_ml_dataset(*, paper_db: Path, eval_root: Path, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = _read_csv(paper_db / "paper_cases.csv")
    params_long = _read_csv(paper_db / "paper_params_long.csv")
    index = _read_csv(paper_db / "paper_waveform_index.csv")
    leaderboard = _read_csv(paper_db / "paper_goa_leaderboard.csv")
    source = _sample_source(cases=cases, index=index, leaderboard=leaderboard)
    rows = []
    for _, source_row in source.iterrows():
        case_id = str(source_row.get("case_id") or "").strip()
        if not case_id:
            continue
        eval_dir = eval_root / case_id
        summary = _read_json(eval_dir / "real_summary.json")
        score = _read_json(eval_dir / "score_summary.json")
        metrics = _read_metrics(eval_dir / "real_metrics.csv")
        matching_leaderboard = leaderboard[leaderboard.get("case_id", pd.Series(dtype=str)).astype(str).eq(case_id)] if not leaderboard.empty else pd.DataFrame()
        leaderboard_row = matching_leaderboard.iloc[0].to_dict() if not matching_leaderboard.empty else {}
        row = _base_training_row(source_row.to_dict(), leaderboard_row=leaderboard_row)
        row.update(_labels(summary=summary, score=score, metrics=metrics, leaderboard_row=leaderboard_row))
        row.update(_features_from_params(case_id=case_id, params_long=params_long, parameters_json=leaderboard_row.get("parameters_json")))
        row["failure_mode"] = _failure_mode(row, score)
        row["failure_reason_text"] = "; ".join(str(item) for item in score.get("failure_reasons", []) or [])
        row["split_group"] = f"{row.get('paper_id')}_{row.get('topology_id')}"
        row["do_not_train"] = bool(row.get("do_not_train") or row.get("failure_mode") == "not_evaluable")
        row["missing_feature_count"] = _missing_feature_count(row)
        rows.append(row)
    frame = pd.DataFrame(rows)
    for column in TRAINING_SAMPLE_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[TRAINING_SAMPLE_COLUMNS]
    frame.to_csv(output_dir / "goa_training_samples.csv", index=False, encoding="utf-8-sig")
    _write_parquet(frame, output_dir / "goa_training_samples.parquet")
    _write_feature_schema(output_dir / "goa_feature_schema.yaml")
    _write_label_schema(output_dir / "goa_label_schema.yaml")
    _write_missingness_report(frame, output_dir / "missingness_report.json")
    _write_feature_statistics(frame, output_dir / "feature_statistics.json")
    _write_dataset_card(frame, output_dir / "goa_dataset_card.md")
    return frame


def _sample_source(*, cases: pd.DataFrame, index: pd.DataFrame, leaderboard: pd.DataFrame) -> pd.DataFrame:
    if not cases.empty and "case_id" in cases.columns:
        return cases
    if not index.empty and "case_id" in index.columns:
        return index
    if not leaderboard.empty and "case_id" in leaderboard.columns:
        return leaderboard
    return pd.DataFrame(columns=["case_id"])


def _base_training_row(source_row: dict[str, Any], *, leaderboard_row: dict[str, Any]) -> dict[str, Any]:
    case_id = source_row.get("case_id") or leaderboard_row.get("case_id")
    paper_id = source_row.get("paper_id") or leaderboard_row.get("paper_id")
    topology_id = source_row.get("topology_id") or leaderboard_row.get("topology_id")
    return {
        "sample_id": f"sample_{case_id}",
        "case_id": case_id,
        "paper_id": paper_id,
        "figure_id": source_row.get("figure_id") or leaderboard_row.get("figure_id"),
        "table_id": source_row.get("table_id") or leaderboard_row.get("table_id"),
        "topology_id": topology_id,
        "circuit_family": "GOA",
        "device_type": source_row.get("device_type") or leaderboard_row.get("device_type"),
        "source_type": SOURCE_TYPE_PAPER_DIGITIZED_WAVEFORM,
        "weak_label": True,
        "evidence_weight": PAPER_DIGITIZED_EVIDENCE_WEIGHT,
        "engineering_validity": ENGINEERING_VALIDITY,
        "label_confidence": PAPER_DIGITIZED_LABEL_CONFIDENCE,
        "train_val_test": None,
        "notes": source_row.get("notes") or leaderboard_row.get("notes") or "",
    }


def _features_from_params(*, case_id: str, params_long: pd.DataFrame, parameters_json: Any) -> dict[str, Any]:
    features: dict[str, Any] = {}
    if not params_long.empty and "case_id" in params_long.columns:
        subset = params_long[params_long["case_id"].astype(str).eq(case_id)]
        for _, row in subset.iterrows():
            parameter_name = str(row.get("parameter_name") or "")
            normalized_value = row.get("normalized_value")
            if pd.isna(normalized_value) or normalized_value in ("", "TODO_NEEDS_MANUAL_EXTRACTION"):
                continue
            feature = PARAMETER_TO_FEATURE.get(parameter_name)
            if feature:
                features[feature] = _maybe_float(normalized_value)
            if parameter_name.startswith("W_T") and str(row.get("normalized_unit") or "") == "um":
                features[f"{parameter_name}_um"] = _maybe_float(normalized_value)
            if parameter_name.startswith("L_T") and str(row.get("normalized_unit") or "") == "um":
                features[f"{parameter_name}_um"] = _maybe_float(normalized_value)
            if parameter_name in {"C1", "C2", "Cboot"} and str(row.get("normalized_unit") or "") == "F":
                features[f"{parameter_name}_F"] = _maybe_float(normalized_value)
    parameters = _parse_parameters_json(parameters_json)
    for key, value in parameters.items():
        if key in TRAINING_SAMPLE_COLUMNS and value not in (None, "", "TODO_NEEDS_MANUAL_EXTRACTION"):
            features[key] = _maybe_float(value)
    if features.get("CK_period_s") and not features.get("CK_freq_Hz"):
        features["CK_freq_Hz"] = 1.0 / float(features["CK_period_s"])
    if features.get("CK_freq_Hz") and not features.get("CK_period_s"):
        features["CK_period_s"] = 1.0 / float(features["CK_freq_Hz"])
    width_columns = [key for key in features if key.startswith("W_T") and key.endswith("_um")]
    if width_columns:
        features["total_TFT_width_um"] = sum(float(features[key]) for key in width_columns if features.get(key) is not None)
    area_terms = []
    for index in range(1, 11):
        width = features.get(f"W_T{index}_um")
        length = features.get(f"L_T{index}_um")
        if width is not None and length is not None:
            area_terms.append(float(width) * float(length))
    if area_terms:
        features["area_proxy"] = sum(area_terms)
    return features


def _labels(*, summary: dict[str, Any], score: dict[str, Any], metrics: dict[str, Any], leaderboard_row: dict[str, Any]) -> dict[str, Any]:
    values = {**leaderboard_row, **summary, **metrics}
    values["hard_constraint_passed"] = score.get("hard_constraint_passed", values.get("hard_constraint_passed"))
    values["overall_score"] = score.get("overall_score", values.get("overall_score"))
    return {
        "PulseExist": metrics.get("PulseExist"),
        "All_pulses_exist": values.get("All_pulses_exist"),
        "Seq_pass": values.get("Seq_pass"),
        "Overall_status": values.get("Overall_status"),
        "hard_constraint_passed": values.get("hard_constraint_passed"),
        "overall_score": values.get("overall_score"),
        "VOH_min": values.get("VOH_min"),
        "VOL_max_all": values.get("VOL_max_all"),
        "Width_mean": values.get("Width_mean"),
        "Width_std": values.get("Width_std"),
        "Delay_mean": values.get("Delay_mean"),
        "Delay_std": values.get("Delay_std"),
        "Max_overlap_ratio": values.get("Max_overlap_ratio"),
        "Max_ripple": values.get("Max_ripple"),
        "Max_voltage_loss": values.get("Max_voltage_loss"),
        "Max_voltage_loss_ratio": values.get("Max_voltage_loss_ratio"),
        "RiseTime_mean": values.get("RiseTime_mean"),
        "FallTime_mean": values.get("FallTime_mean"),
        "first_failed_stage": values.get("first_failed_stage"),
        "worst_stage": values.get("worst_stage"),
    }


def _read_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    result: dict[str, Any] = {}
    if "PulseExist" in frame.columns:
        result["PulseExist"] = bool(frame["PulseExist"].astype(str).str.lower().eq("true").any())
    for source, target, reducer in [
        ("RiseTime", "RiseTime_mean", "mean"),
        ("FallTime", "FallTime_mean", "mean"),
    ]:
        if source in frame.columns:
            values = pd.to_numeric(frame[source], errors="coerce").dropna()
            if not values.empty:
                result[target] = float(values.mean() if reducer == "mean" else values.max())
    return result


def _failure_mode(row: dict[str, Any], score: dict[str, Any]) -> str:
    if str(row.get("hard_constraint_passed")).lower() == "true":
        return "pass"
    reasons = " ".join(str(item).lower() for item in score.get("failure_reasons", []) or [])
    status = str(row.get("Overall_status") or "").lower()
    if not score and status in ("", "nan", "none"):
        return "not_evaluable"
    if "pulse" in reasons or row.get("All_pulses_exist") is False:
        return "missing_pulse"
    if "false" in reasons or "trigger" in reasons:
        return "false_trigger"
    if "overlap" in reasons or _as_float(row.get("Max_overlap_ratio"), default=0.0) > 0.10:
        return "overlap"
    if "ripple" in reasons:
        return "ripple"
    if "voltage_loss" in reasons or "voltage loss" in reasons:
        return "voltage_loss"
    if "delay" in reasons:
        return "delay_dispersion"
    if "width" in reasons:
        return "width_error"
    return "unknown"


def _missing_feature_count(row: dict[str, Any]) -> int:
    feature_columns = [
        column
        for column in TRAINING_SAMPLE_COLUMNS
        if column not in {"sample_id", "case_id", "paper_id", "figure_id", "table_id", "topology_id", "notes"}
        and not column.endswith("_status")
        and column not in {"weak_label", "evidence_weight", "engineering_validity", "label_confidence", "train_val_test"}
    ]
    return sum(1 for column in feature_columns if row.get(column) in (None, "", "TODO_NEEDS_MANUAL_EXTRACTION"))


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    try:
        frame.to_parquet(path, index=False)
    except Exception as exc:
        placeholder = {"status": "parquet_unavailable", "message": f"{type(exc).__name__}: {exc}"}
        path.write_bytes(json.dumps(placeholder, ensure_ascii=False).encode("utf-8"))


def _write_feature_schema(path: Path) -> None:
    schema = {
        "schema_version": "1.0",
        "feature_groups": {
            "identity": {"columns": ["sample_id", "case_id", "paper_id", "topology_id"]},
            "topology": {
                "columns": ["TFT_count", "cap_count", "clock_count", "stage_count", "has_bootstrap", "has_dual_gate"]
            },
            "device_size": {"unit": "normalized", "columns_pattern": ["W_*_um", "L_*_um", "C*_F"]},
            "supply_timing": {
                "columns": ["VGH_V", "VGL_V", "CK_high_V", "CK_low_V", "CK_period_s", "CK_freq_Hz"]
            },
            "load": {"columns": ["CLOAD_F", "RLOAD_ohm", "scan_line_C_F", "scan_line_R_ohm"]},
            "degradation": {"columns": ["Vth_shift_V", "temperature_C", "aging_time_h"]},
        },
    }
    path.write_text(yaml.safe_dump(schema, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_label_schema(path: Path) -> None:
    schema = {
        "schema_version": "1.0",
        "label_groups": {
            "hard_labels": {"columns": ["hard_constraint_passed", "Overall_status", "failure_mode"]},
            "waveform_metrics": {
                "regression_targets": [
                    "VOH_min",
                    "VOL_max_all",
                    "Width_mean",
                    "Delay_mean",
                    "Delay_std",
                    "Max_overlap_ratio",
                    "Max_ripple",
                    "Max_voltage_loss",
                    "RiseTime_mean",
                    "FallTime_mean",
                ]
            },
            "optimization_targets": {"columns": ["overall_score", "objective_score"]},
            "weak_label_control": {"columns": ["weak_label", "evidence_weight", "label_confidence"]},
        },
    }
    path.write_text(yaml.safe_dump(schema, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_missingness_report(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty:
        report = {"row_count": 0, "columns": {}}
    else:
        report = {
            "row_count": int(len(frame)),
            "columns": {
                column: {
                    "missing_count": int(frame[column].isna().sum() + frame[column].astype(str).isin(["", "TODO_NEEDS_MANUAL_EXTRACTION"]).sum()),
                    "missing_rate": float(frame[column].isna().mean()),
                }
                for column in frame.columns
            },
        }
    write_json(path, report)


def _write_feature_statistics(frame: pd.DataFrame, path: Path) -> None:
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    stats = {}
    for column in numeric.columns:
        values = numeric[column].dropna()
        if values.empty:
            continue
        stats[column] = {
            "count": int(values.count()),
            "mean": float(values.mean()),
            "std": float(values.std()) if len(values) > 1 else 0.0,
            "min": float(values.min()),
            "max": float(values.max()),
        }
    write_json(path, stats)


def _write_dataset_card(frame: pd.DataFrame, path: Path) -> None:
    lines = [
        "# GOA Paper Digitization ML Dataset Card",
        "",
        f"- sample_count: {len(frame)}",
        "- source: paper_digitized weak labels plus future simulation CSV/rerun rows",
        "- weak_label: paper-digitized waveform rows are weak labels.",
        "- evidence_boundary: engineering_validity = simulation_only",
        "- intended_use: train surrogate, classifier, repair, active-learning, and multi-objective ranking models to reduce invalid simulation attempts.",
        "- not_intended_use: replacement for final SPICE/SmartSpice/ngspice verification or physical experiment claims.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_parameters_json(value: Any) -> dict[str, Any]:
    if value in (None, "") or pd.isna(value):
        return {}
    try:
        raw = json.loads(str(value))
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        return {}


def _maybe_float(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _as_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build ML-ready GOA training samples from paper digitization database.")
    parser.add_argument("--paper-db", type=Path, required=True)
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    frame = build_ml_dataset(paper_db=args.paper_db, eval_root=args.eval_root, output_dir=args.output_dir)
    print(args.output_dir / "goa_training_samples.csv")
    print(f"samples={len(frame)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
