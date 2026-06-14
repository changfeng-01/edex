from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from goa_eval.io_utils import read_yaml as _read_yaml, read_json as _read_json, write_json
from goa_eval.paper_digitization.schemas import (
    ENGINEERING_VALIDITY,
    PAPER_LEADERBOARD_COLUMNS,
    SOURCE_TYPE_PAPER_DIGITIZED,
)


def build_paper_leaderboard(
    *,
    cases_root: Path,
    eval_root: Path,
    output_path: Path,
    params_long_path: Path | None = None,
) -> pd.DataFrame:
    params_long_path = params_long_path or output_path.parent / "paper_params_long.csv"
    params_long = pd.read_csv(params_long_path) if params_long_path.exists() else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for case_dir in sorted(path for path in cases_root.iterdir() if path.is_dir()):
        case_id = case_dir.name
        eval_dir = eval_root / case_id
        metadata = _read_yaml(case_dir / "simulation_metadata.yaml")
        paper_metadata = _read_yaml(case_dir / "paper_metadata.yaml")
        paper_params = _read_yaml(case_dir / "paper_params.yaml")
        summary = _read_json(eval_dir / "real_summary.json")
        score = _read_json(eval_dir / "score_summary.json")
        metrics = _read_metrics(eval_dir / "real_metrics.csv")
        parameters = _parameters_json(case_id=case_id, params=paper_params, params_long=params_long)
        row = {
            "run_id": summary.get("run_id") or case_id,
            "case_id": case_id,
            "paper_id": metadata.get("paper_id") or paper_metadata.get("paper_id"),
            "figure_id": metadata.get("figure_id"),
            "topology_id": paper_metadata.get("topology_id") or metadata.get("topology_id"),
            "parameters_json": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
            "overall_score": score.get("overall_score"),
            "hard_constraint_passed": score.get("hard_constraint_passed"),
            "Overall_status": summary.get("Overall_status"),
            "stage_count": summary.get("stage_count"),
            "VOH_min": summary.get("VOH_min"),
            "VOL_max_all": summary.get("VOL_max_all"),
            "Width_mean": summary.get("Width_mean"),
            "Width_std": summary.get("Width_std"),
            "Delay_mean": summary.get("Delay_mean"),
            "Delay_std": summary.get("Delay_std"),
            "Max_overlap_ratio": summary.get("Max_overlap_ratio"),
            "Max_ripple": summary.get("Max_ripple"),
            "Max_voltage_loss": summary.get("Max_voltage_loss"),
            "first_failed_stage": summary.get("first_failed_stage"),
            "worst_stage": summary.get("worst_stage"),
            "weak_label": True,
            "source_type": SOURCE_TYPE_PAPER_DIGITIZED,
            "engineering_validity": ENGINEERING_VALIDITY,
            "notes": metadata.get("notes", ""),
        }
        row.update(metrics)
        rows.append(row)
    frame = pd.DataFrame(rows)
    for column in PAPER_LEADERBOARD_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[PAPER_LEADERBOARD_COLUMNS]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False, encoding="utf-8-sig")
    write_json(
        output_path.parent / "paper_database_summary.json",
        {
            "leaderboard_path": str(output_path),
            "case_count": int(len(frame)),
            "source_type": SOURCE_TYPE_PAPER_DIGITIZED,
            "engineering_validity": ENGINEERING_VALIDITY,
        },
    )
    return frame


def _parameters_json(*, case_id: str, params: dict[str, Any], params_long: pd.DataFrame) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    raw_parameters = params.get("parameters", params) if isinstance(params, dict) else {}
    if isinstance(raw_parameters, dict):
        for key, value in _flatten(raw_parameters).items():
            if value not in (None, "", "TODO_NEEDS_MANUAL_EXTRACTION"):
                parameters[str(key)] = value
    if not params_long.empty and "case_id" in params_long.columns:
        subset = params_long[params_long["case_id"].astype(str).eq(case_id)]
        for _, row in subset.iterrows():
            name = row.get("parameter_name")
            value = row.get("normalized_value")
            if pd.isna(name) or pd.isna(value) or value in ("", "TODO_NEEDS_MANUAL_EXTRACTION"):
                continue
            parameters[str(name)] = _maybe_float(value)
    return parameters


def _read_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    result: dict[str, Any] = {}
    for source, target in [
        ("RiseTime", "RiseTime_mean"),
        ("FallTime", "FallTime_mean"),
        ("VoltageLoss", "Max_voltage_loss"),
        ("Ripple", "Max_ripple"),
    ]:
        if source in frame.columns and target not in result:
            values = pd.to_numeric(frame[source], errors="coerce").dropna()
            if not values.empty:
                result[target] = float(values.mean() if target.endswith("_mean") else values.max())
    return result


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            flattened.update(_flatten(item, name))
        else:
            flattened[name] = item
    return flattened


def _maybe_float(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build paper GOA leaderboard from evaluated paper cases.")
    parser.add_argument("--cases-root", type=Path, required=True)
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--output", dest="output_path", type=Path, required=True)
    parser.add_argument("--params-long", dest="params_long_path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    frame = build_paper_leaderboard(
        cases_root=args.cases_root,
        eval_root=args.eval_root,
        output_path=args.output_path,
        params_long_path=args.params_long_path,
    )
    print(args.output_path)
    print(f"cases={len(frame)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
