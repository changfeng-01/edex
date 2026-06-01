from __future__ import annotations

from pathlib import Path
import csv
import json
import shutil
from typing import Any

import pandas as pd

from goa_eval.io_utils import write_json
from goa_eval.llm_analysis import run_llm_parameter_analysis
from goa_eval.optimizer import constrained_random_candidates, load_param_space, write_candidate_outputs
from goa_eval.product_demo.schemas import DIRECTORIES
from goa_eval.product_demo.workflow import run_product_demo
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown


DATA_SOURCE = "real_simulation_csv"
ENGINEERING_VALIDITY = "simulation_only"
DEFAULT_CASE_ID = "public_demo"
DEMO_RUN_ID = "public_demo_run"
DEMO_TIMESTAMP = "2026-05-22T00:00:00"
DEMO_CODE_VERSION = "public_demo_snapshot"
DEFAULT_MOCK_RESPONSE = (
    "CircuitPilot public demo mock analysis. The current evidence is simulation_only, "
    "derived from real_simulation_csv artifacts. Prioritize candidate review and rerun "
    "simulation before making any physical validation claim."
)


def run_demo_mainline(
    *,
    case_id: str = DEFAULT_CASE_ID,
    waveform_path: Path = Path("examples/sample_waveform.csv"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    demo_run_dir: Path | None = None,
    product_demo_root: Path = Path("outputs/product_demo"),
    frontend_data_root: Path = Path("frontend/public/demo_data"),
    spec_path: Path = Path("config/spec.yaml"),
    seed: int = 42,
    max_candidates: int = 10,
    mock_response: str = DEFAULT_MOCK_RESPONSE,
) -> dict[str, Any]:
    repo_root = Path.cwd()
    demo_run_dir = demo_run_dir or Path("outputs/demo_mainline") / case_id
    demo_run_dir = _resolve(demo_run_dir)
    product_demo_root = _resolve(product_demo_root)
    frontend_data_root = _resolve(frontend_data_root)
    mock_response = mock_response or DEFAULT_MOCK_RESPONSE

    _recreate_dir(demo_run_dir, repo_root=repo_root)
    summary = run_real_waveform_evaluation(
        waveform_path=waveform_path,
        internal_waveform_path=None,
        output_dir=demo_run_dir,
        spec_path=spec_path,
    )

    paths = _pipeline_paths(demo_run_dir)
    write_recommendations_markdown(
        summary_path=paths["summary"],
        score_path=paths["score"],
        metrics_path=paths["metrics"],
        output_path=paths["recommendations"],
    )

    score = json.loads(paths["score"].read_text(encoding="utf-8")) if paths["score"].exists() else {}
    metrics = pd.read_csv(paths["metrics"]) if paths["metrics"].exists() else pd.DataFrame()
    recommendations = build_recommendations(summary, score, metrics)
    candidates = constrained_random_candidates(
        load_param_space(param_space_path),
        recommendations,
        max_candidates=max_candidates,
        seed=seed,
    )
    write_candidate_outputs(candidates, csv_path=paths["candidates_csv"], markdown_path=paths["candidates_md"])

    run_llm_parameter_analysis(
        summary_path=paths["summary"],
        score_path=paths["score"],
        metrics_path=paths["metrics"],
        candidates_path=paths["candidates_csv"],
        params_path=param_space_path,
        mock_response=mock_response,
        output_md=paths["analysis_md"],
        output_json=paths["analysis_json"],
    )
    normalize_demo_outputs(demo_run_dir, waveform_path=waveform_path, param_space_path=param_space_path)

    case_dir = run_product_demo(input_dir=demo_run_dir, output_dir=product_demo_root, case_id=case_id)
    frontend_case_dir = sync_dashboard_package(case_dir, frontend_data_root / case_id)
    manifest = write_demo_mainline_manifest(
        case_dir=case_dir,
        case_id=case_id,
        waveform_path=waveform_path,
        param_space_path=param_space_path,
        spec_path=spec_path,
        demo_run_dir=demo_run_dir,
        product_demo_root=product_demo_root,
        frontend_case_dir=frontend_case_dir,
        seed=seed,
        max_candidates=max_candidates,
    )
    return manifest


def sync_dashboard_package(case_dir: Path, frontend_case_dir: Path) -> Path:
    dashboard_dir = case_dir / DIRECTORIES["dashboard"]
    figure_dir = case_dir / DIRECTORIES["figures"]
    report_dir = case_dir / DIRECTORIES["report"]
    frontend_case_dir.mkdir(parents=True, exist_ok=True)
    for path in dashboard_dir.glob("*.json"):
        shutil.copy2(path, frontend_case_dir / path.name)
    _sync_tree(figure_dir, frontend_case_dir / "figures")
    _sync_tree(report_dir, frontend_case_dir / "reports")
    return frontend_case_dir


def write_demo_mainline_manifest(
    *,
    case_dir: Path,
    case_id: str,
    waveform_path: Path,
    param_space_path: Path,
    spec_path: Path,
    demo_run_dir: Path,
    product_demo_root: Path,
    frontend_case_dir: Path,
    seed: int,
    max_candidates: int,
) -> dict[str, Any]:
    dashboard_summary_path = case_dir / DIRECTORIES["dashboard"] / "dashboard_summary.json"
    dashboard_summary = json.loads(dashboard_summary_path.read_text(encoding="utf-8"))
    evidence = dashboard_summary.get("evidence", {})
    manifest = {
        "case_id": case_id,
        "command": {
            "module": "python -m goa_eval.cli demo",
            "console_script": "circuitpilot demo",
            "seed": seed,
            "max_candidates": max_candidates,
        },
        "input_files": {
            "waveform": _display_path(waveform_path),
            "param_space": _display_path(param_space_path),
            "spec": _display_path(spec_path),
        },
        "output_directories": {
            "demo_run_dir": demo_run_dir.as_posix(),
            "product_demo_root": product_demo_root.as_posix(),
            "product_demo_case_dir": case_dir.as_posix(),
            "frontend_demo_data_dir": frontend_case_dir.as_posix(),
        },
        "evidence_boundary": {
            "data_source": evidence.get("data_source", DATA_SOURCE),
            "engineering_validity": evidence.get("engineering_validity", ENGINEERING_VALIDITY),
        },
    }
    write_json(case_dir / "demo_mainline_manifest.json", manifest)
    return manifest


def normalize_demo_outputs(output_dir: Path, *, waveform_path: Path, param_space_path: Path) -> None:
    _normalize_json_file(output_dir / "real_summary.json", lambda data: _normalize_summary(data, waveform_path))
    _normalize_json_file(output_dir / "run_manifest_real.json", lambda data: _normalize_real_manifest(data, waveform_path))
    _normalize_json_file(output_dir / "llm_parameter_analysis.json", lambda data: _normalize_analysis(data, output_dir, param_space_path))
    _normalize_optimization_dataset(output_dir / "optimization_dataset.csv")


def _normalize_json_file(path: Path, normalizer) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    normalizer(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_summary(data: dict[str, Any], waveform_path: Path) -> None:
    data["run_id"] = DEMO_RUN_ID
    data["run_timestamp"] = DEMO_TIMESTAMP
    data["input_file"] = _display_path(waveform_path)


def _normalize_real_manifest(data: dict[str, Any], waveform_path: Path) -> None:
    input_file = _display_path(waveform_path)
    data["run_id"] = DEMO_RUN_ID
    data["run_time"] = DEMO_TIMESTAMP
    data["command"] = "python -m goa_eval.cli demo"
    data["input_files"] = [input_file]
    hashes = data.get("input_file_hashes", {})
    if hashes:
        first_hash = next(iter(hashes.values()))
        data["input_file_hashes"] = {input_file: first_hash}
    data["code_version_or_git_commit"] = DEMO_CODE_VERSION


def _normalize_analysis(data: dict[str, Any], output_dir: Path, param_space_path: Path) -> None:
    label = _display_path(output_dir)
    data["input_files"] = {
        "summary": f"{label}/real_summary.json",
        "score": f"{label}/score_summary.json",
        "metrics": f"{label}/real_metrics.csv",
        "candidates": f"{label}/next_candidates.csv",
        "params": _display_path(param_space_path),
    }


def _normalize_optimization_dataset(path: Path) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    for row in rows:
        row["run_id"] = DEMO_RUN_ID
        row["run_timestamp"] = DEMO_TIMESTAMP
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _pipeline_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "summary": output_dir / "real_summary.json",
        "score": output_dir / "score_summary.json",
        "metrics": output_dir / "real_metrics.csv",
        "recommendations": output_dir / "recommendations.md",
        "candidates_csv": output_dir / "next_candidates.csv",
        "candidates_md": output_dir / "next_candidates.md",
        "analysis_md": output_dir / "llm_parameter_analysis.md",
        "analysis_json": output_dir / "llm_parameter_analysis.json",
    }


def _sync_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _recreate_dir(path: Path, *, repo_root: Path) -> None:
    resolved = path.resolve()
    protected = {
        repo_root.resolve(),
        (repo_root / "examples").resolve(),
        (repo_root / "frontend").resolve(),
        (repo_root / "src").resolve(),
        (repo_root / "tests").resolve(),
    }
    if resolved in protected:
        raise ValueError(f"Refusing to recreate protected directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
