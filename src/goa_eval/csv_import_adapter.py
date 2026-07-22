from __future__ import annotations

from pathlib import Path
import json
import shutil
from typing import Any

import pandas as pd
import yaml

from goa_eval.io_utils import read_json as _read_json, write_json
from goa_eval.optimizer import constrained_random_candidates, load_param_space, write_candidate_outputs
from goa_eval.parameter_semantics import load_parameter_semantics
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown


OPTIONAL_INPUT_FILES = [
    "op_metrics.csv",
    "ac_metrics.csv",
    "dc_metrics.csv",
    "tran_metrics.csv",
    "source_netlist.spice",
]


def run_csv_import(
    *,
    input_dir: Path,
    output_dir: Path,
    spec_path: Path = Path("config/evaluation_spec_low_voltage.yaml"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    circuit_profile: str | None = None,
    profile_file: Path | None = None,
    params_file: Path | None = None,
    max_candidates: int = 10,
    seed: int = 42,
) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"csv-import input directory not found: {input_dir}")
    waveform = input_dir / "waveform.csv"
    if not waveform.exists():
        raise FileNotFoundError(f"csv-import requires waveform.csv in {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = _copy_inputs(input_dir, output_dir)
    metadata = _simulation_metadata(input_dir)
    metadata.update(
        {
            "adapter": "csv-import",
            "input_dir": str(input_dir),
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        }
    )
    write_json(output_dir / "simulation_metadata.json", metadata)
    write_json(
        output_dir / "adapter_status.json",
        {
            "adapter": "csv-import",
            "status": "imported",
            "message": "",
            "input_dir": str(input_dir),
            "copied_files": copied,
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        },
    )
    summary = run_real_waveform_evaluation(
        waveform_path=output_dir / "waveform.csv",
        internal_waveform_path=None,
        output_dir=output_dir,
        spec_path=spec_path,
        topology=circuit_profile,
        circuit_profile=circuit_profile,
        profile_file=profile_file,
    )
    score = json.loads((output_dir / "score_summary.json").read_text(encoding="utf-8"))
    metrics = pd.read_csv(output_dir / "real_metrics.csv")
    recommendations = write_recommendations_markdown(
        summary_path=output_dir / "real_summary.json",
        score_path=output_dir / "score_summary.json",
        metrics_path=output_dir / "real_metrics.csv",
        output_path=output_dir / "recommendations.md",
    )
    param_space = load_param_space(param_space_path)
    semantics = load_parameter_semantics(params_file) if params_file else None
    candidates = constrained_random_candidates(
        param_space,
        recommendations or build_recommendations(summary, score, metrics),
        max_candidates=max_candidates,
        seed=seed,
        profile_file=profile_file,
        parameter_semantics=semantics,
    )
    write_candidate_outputs(candidates, csv_path=output_dir / "next_candidates.csv", markdown_path=output_dir / "next_candidates.md")
    return _run_row(output_dir, adapter="csv-import")


def run_csv_import_sweep(
    *,
    input_root: Path,
    output_root: Path,
    spec_path: Path = Path("config/evaluation_spec_low_voltage.yaml"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    circuit_profile: str | None = None,
    profile_file: Path | None = None,
    params_file: Path | None = None,
    max_candidates: int = 10,
    seed: int = 42,
) -> list[dict[str, Any]]:
    input_dirs = [path for path in sorted(input_root.iterdir()) if path.is_dir()]
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for index, input_dir in enumerate(input_dirs, start=1):
        run_dir = output_root / f"{index:04d}_{_safe_name(input_dir.name)}"
        try:
            row = run_csv_import(
                input_dir=input_dir,
                output_dir=run_dir,
                spec_path=spec_path,
                param_space_path=param_space_path,
                circuit_profile=circuit_profile,
                profile_file=profile_file,
                params_file=params_file,
                max_candidates=max_candidates,
                seed=seed + index - 1,
            )
            row["input_dir"] = str(input_dir)
        except Exception as exc:
            run_dir.mkdir(parents=True, exist_ok=True)
            row = {
                "status": "failed",
                "message": f"{type(exc).__name__}: {exc}",
                "adapter": "csv-import",
                "run_dir": run_dir.name,
                "input_dir": str(input_dir),
                "overall_score": None,
                "objective_score": None,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
            write_json(run_dir / "adapter_status.json", row)
        rows.append(row)
    _write_sweep_outputs(output_root, rows)
    return rows


def _copy_inputs(input_dir: Path, output_dir: Path) -> list[str]:
    copied = []
    for name in ["waveform.csv", *OPTIONAL_INPUT_FILES]:
        source = input_dir / name
        if not source.exists():
            continue
        shutil.copy2(source, output_dir / name)
        copied.append(name)
    return copied


def _simulation_metadata(input_dir: Path) -> dict[str, Any]:
    for name in ["simulation_metadata.json", "metadata.json"]:
        path = input_dir / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    for name in ["simulation_metadata.yaml", "metadata.yaml", "metadata.yml"]:
        path = input_dir / name
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def _run_row(run_dir: Path, *, adapter: str) -> dict[str, Any]:
    status = _read_json(run_dir / "adapter_status.json")
    score = _read_json(run_dir / "score_summary.json")
    summary = _read_json(run_dir / "real_summary.json")
    analysis = _read_json(run_dir / "analysis_metrics.json")
    return {
        "status": "evaluated",
        "message": status.get("message", ""),
        "adapter": adapter,
        "run_dir": run_dir.name,
        "overall_score": score.get("overall_score"),
        "objective_score": score.get("objective_score"),
        "hard_constraint_passed": score.get("hard_constraint_passed"),
        "circuit_profile": score.get("circuit_profile"),
        "not_evaluable_metric_count": len(score.get("not_evaluable_metrics", {}) or {}),
        "stage_count": summary.get("stage_count"),
        "Max_overlap_ratio": summary.get("Max_overlap_ratio"),
        "dc_gain_db": (analysis.get("ac_metrics") or {}).get("dc_gain_db"),
        "static_power_w": (analysis.get("op_metrics") or {}).get("static_power_w"),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }


def _write_sweep_outputs(output_root: Path, rows: list[dict[str, Any]]) -> None:
    frame = pd.DataFrame(rows)
    frame.to_csv(output_root / "simulate_sweep_runs.csv", index=False, encoding="utf-8-sig")
    if frame.empty:
        frame.to_csv(output_root / "simulate_sweep_leaderboard.csv", index=False, encoding="utf-8-sig")
        return
    ranked = frame.copy()
    ranked["_evaluated"] = ranked["status"].eq("evaluated").astype(int)
    ranked["_score"] = pd.to_numeric(ranked.get("objective_score"), errors="coerce").fillna(
        pd.to_numeric(ranked.get("overall_score"), errors="coerce")
    )
    ranked["_score"] = ranked["_score"].fillna(float("-inf"))
    ranked.sort_values(["_evaluated", "_score", "run_dir"], ascending=[False, False, True]).drop(
        columns=["_evaluated", "_score"]
    ).to_csv(output_root / "simulate_sweep_leaderboard.csv", index=False, encoding="utf-8-sig")


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("_") or "run"
