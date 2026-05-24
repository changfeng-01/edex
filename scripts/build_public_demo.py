from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_RUN_ID = "public_demo_run"
DEMO_TIMESTAMP = "2026-05-22T00:00:00"
DEMO_CODE_VERSION = "public_demo_snapshot"
DEMO_OUTPUT_LABEL = "examples/demo_run"
DEMO_MOCK_RESPONSE = (
    "固定公开 demo：当前样例波形的主要风险是相邻输出阶段存在重叠，"
    "建议优先复核 cand_001 到 cand_003 的 drive_resistance 时序候选，"
    "再观察 Max_overlap_ratio、Delay_mean 和 Max_ripple 是否改善。"
    "本结论仅用于下一轮仿真设计，必须保留 simulation_only 边界。"
)

DASHBOARD_FILES = [
    "real_summary.json",
    "score_summary.json",
    "real_metrics.csv",
    "optimization_dataset.csv",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = resolve_path(args.output_dir)
    frontend_data_dir = resolve_path(args.frontend_data_dir)

    recreate_output_dir(output_dir)
    run_demo_pipeline(output_dir)
    normalize_demo_outputs(output_dir)
    sync_frontend_data(output_dir, frontend_data_dir)
    print(f"Public demo run written to {display_path(output_dir)}")
    print(f"Dashboard data synced to {display_path(frontend_data_dir)}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the public CircuitPilot demo run.")
    parser.add_argument("--output-dir", default="examples/demo_run")
    parser.add_argument("--frontend-data-dir", default="frontend/public/data")
    return parser.parse_args(argv)


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def recreate_output_dir(output_dir: Path) -> None:
    protected = {REPO_ROOT.resolve(), (REPO_ROOT / "examples").resolve(), (REPO_ROOT / "frontend").resolve()}
    if output_dir in protected:
        raise SystemExit(f"Refusing to delete protected directory: {display_path(output_dir)}")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def run_demo_pipeline(output_dir: Path) -> None:
    paths = {
        "summary": output_dir / "real_summary.json",
        "score": output_dir / "score_summary.json",
        "metrics": output_dir / "real_metrics.csv",
        "recommendations": output_dir / "recommendations.md",
        "candidates_csv": output_dir / "next_candidates.csv",
        "candidates_md": output_dir / "next_candidates.md",
        "analysis_md": output_dir / "llm_parameter_analysis.md",
        "analysis_json": output_dir / "llm_parameter_analysis.json",
    }
    run_cli(
        "evaluate-real",
        "--waveform",
        "examples/sample_waveform.csv",
        "--output-dir",
        str(output_dir),
    )
    run_cli(
        "recommend",
        "--summary",
        str(paths["summary"]),
        "--score",
        str(paths["score"]),
        "--metrics",
        str(paths["metrics"]),
        "--output",
        str(paths["recommendations"]),
    )
    run_cli(
        "propose-candidates",
        "--summary",
        str(paths["summary"]),
        "--score",
        str(paths["score"]),
        "--metrics",
        str(paths["metrics"]),
        "--param-space",
        "examples/sample_params.yaml",
        "--strategy",
        "constrained-random",
        "--max-candidates",
        "10",
        "--seed",
        "42",
        "--output-csv",
        str(paths["candidates_csv"]),
        "--output-md",
        str(paths["candidates_md"]),
    )
    run_cli(
        "analyze-params",
        "--summary",
        str(paths["summary"]),
        "--score",
        str(paths["score"]),
        "--metrics",
        str(paths["metrics"]),
        "--candidates",
        str(paths["candidates_csv"]),
        "--params",
        "examples/sample_params.yaml",
        "--mock-response",
        DEMO_MOCK_RESPONSE,
        "--output-md",
        str(paths["analysis_md"]),
        "--output-json",
        str(paths["analysis_json"]),
    )


def run_cli(*args: str) -> None:
    command = [sys.executable, "-m", "goa_eval.cli", *args]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"Command failed: {' '.join(command)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def normalize_demo_outputs(output_dir: Path) -> None:
    normalize_json_file(output_dir / "real_summary.json", normalize_summary)
    normalize_json_file(output_dir / "run_manifest_real.json", normalize_manifest)
    normalize_json_file(output_dir / "llm_parameter_analysis.json", normalize_analysis)
    normalize_optimization_dataset(output_dir / "optimization_dataset.csv")


def normalize_json_file(path: Path, normalizer) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    normalizer(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_summary(data: dict[str, Any]) -> None:
    data["run_id"] = DEMO_RUN_ID
    data["run_timestamp"] = DEMO_TIMESTAMP
    data["input_file"] = "examples/sample_waveform.csv"


def normalize_manifest(data: dict[str, Any]) -> None:
    data["run_id"] = DEMO_RUN_ID
    data["run_time"] = DEMO_TIMESTAMP
    data["command"] = (
        "python -m goa_eval.cli evaluate-real "
        "--waveform examples/sample_waveform.csv "
        "--output-dir examples/demo_run"
    )
    data["input_files"] = ["examples/sample_waveform.csv"]
    hashes = data.get("input_file_hashes", {})
    if hashes:
        first_hash = next(iter(hashes.values()))
        data["input_file_hashes"] = {"examples/sample_waveform.csv": first_hash}
    data["code_version_or_git_commit"] = DEMO_CODE_VERSION


def normalize_analysis(data: dict[str, Any]) -> None:
    data["input_files"] = {
        "summary": f"{DEMO_OUTPUT_LABEL}/real_summary.json",
        "score": f"{DEMO_OUTPUT_LABEL}/score_summary.json",
        "metrics": f"{DEMO_OUTPUT_LABEL}/real_metrics.csv",
        "candidates": f"{DEMO_OUTPUT_LABEL}/next_candidates.csv",
        "params": "examples/sample_params.yaml",
    }


def normalize_optimization_dataset(path: Path) -> None:
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


def sync_frontend_data(output_dir: Path, frontend_data_dir: Path) -> None:
    frontend_data_dir.mkdir(parents=True, exist_ok=True)
    for name in DASHBOARD_FILES:
        shutil.copy2(output_dir / name, frontend_data_dir / name)
    source_figures = output_dir / "figures"
    target_figures = frontend_data_dir / "figures"
    if target_figures.exists():
        shutil.rmtree(target_figures)
    shutil.copytree(source_figures, target_figures)


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
