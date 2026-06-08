from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from goa_eval.eclipse_benchmark.reports import build_markdown_report


def test_report_declares_evidence_boundaries_and_diagnostic_scores() -> None:
    report = build_markdown_report(
        summary={
            "benchmark_type": "eclipse_model_benchmark",
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "score_threshold": 80,
        },
        leaderboard=pd.DataFrame([{"algorithm": "eclipse_opt", "best_feasible_score_mean": 82.0}]),
    )

    assert "simulation_only" in report
    assert "predicted scores are not final benchmark evidence" in report
    assert "physics_score is not a final optimization result" in report
    assert "attention_score is diagnostic only" in report
    assert "summary index, not a replacement for primary metrics" in report
    assert "Sorting rule" in report


def test_eclipse_benchmark_cli_smoke(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "random" / "seed_1"
    run_dir.mkdir(parents=True)
    rows = [
        {
            "candidate_id": "c1",
            "overall_score": 82,
            "hard_constraint_passed": True,
            "target_passed": True,
            "rank_status": "evaluated",
        }
    ]
    (run_dir / "optimization_history.json").write_text(json.dumps({"history": rows}), encoding="utf-8")
    pd.DataFrame(rows).to_csv(run_dir / "optimization_leaderboard.csv", index=False)
    output_root = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "eclipse-benchmark",
            "--runs-root",
            str(tmp_path / "runs"),
            "--output-root",
            str(output_root),
            "--score-threshold",
            "80",
            "--baseline",
            "random",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_root / "eclipse_benchmark_report.md").exists()
