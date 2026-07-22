from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.multi_agent.availability import check_langgraph_availability


def _write_case(case_dir: Path) -> None:
    artifacts = case_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "real_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "result_version": "1.0",
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "Max_overlap_ratio": 0.0,
                "FalseTriggerCount": 0,
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "score_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "result_version": "1.0",
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "hard_constraint_passed": True,
                "overall_score": 0.9,
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame([{"schema_version": "1.0", "result_version": "1.0", "stage": 1, "OverlapRatio": 0.0}]).to_csv(
        artifacts / "real_metrics.csv", index=False
    )
    pd.DataFrame([{"candidate_id": "cand_001", "overall_score": 0.9}]).to_csv(
        artifacts / "optimization_leaderboard.csv", index=False
    )
    pd.DataFrame([{"candidate_id": "next_001", "parameter": "load_cap", "candidate_values": "[1p]"}]).to_csv(
        artifacts / "best_next_candidates.csv", index=False
    )
    (artifacts / "optimization_history.json").write_text(
        json.dumps({"rounds": [{"round_index": 1, "best_score": 0.9, "best_run_dir": "round_1"}], "stop_reason": "target_met"}),
        encoding="utf-8",
    )
    pd.DataFrame([{"target.status": "passed"}]).to_csv(artifacts / "validation_summary.csv", index=False)

    (case_dir / "task.yaml").write_text(
        f"""
task_name: benchmark_goa
task_type: goa_eda_optimization
profile: goa_8t1c_720
inputs:
  artifact_dir: {artifacts.as_posix()}
  param_space: examples/sample_params.yaml
validity:
  data_source: real_simulation_csv
  engineering_validity: simulation_only
""".strip(),
        encoding="utf-8",
    )
    (case_dir / "expected.json").write_text(
        json.dumps(
            {
                "selected_domain_agent": "GOAAgent",
                "required_artifacts": ["real_summary", "score_summary", "real_metrics", "optimization_leaderboard", "best_next_candidates"],
                "expected_risk_types": [],
                "optimization_loop_status": "awaiting_rerun_results",
                "forbidden_claims": [
                    "silicon validation",
                    "physical validation",
                    "tape-out proof",
                    "real chip verification",
                    "industrial-grade full automation",
                ],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "README.md").write_text("# benchmark case\n", encoding="utf-8")


@pytest.mark.skipif(not check_langgraph_availability()["available"], reason="LangGraph not installed")
def test_benchmark_run_cli_writes_summary_results_and_report(tmp_path: Path):
    suite = tmp_path / "suite"
    case_dir = suite / "goa_case"
    case_dir.mkdir(parents=True)
    _write_case(case_dir)
    output = tmp_path / "benchmark"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "benchmark-run",
            "--suite",
            str(suite),
            "--output-dir",
            str(output),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((output / "benchmark_summary.json").read_text(encoding="utf-8"))
    assert summary["case_count"] == 1
    assert summary["hard_constraint_pass_rate"] == 1.0
    assert summary["status_counts"] == {"passed": 1}
    assert summary["not_evaluable_count"] == 0
    for metric in [
        "route_accuracy",
        "artifact_discovery_score",
        "diagnosis_match_score",
        "critic_risk_detection_score",
        "boundary_safety_score",
        "optimization_loop_status_score",
        "report_forbidden_claim_score",
    ]:
        assert metric in summary["metrics"]
    assert summary["metrics"]["route_accuracy"] == 1.0
    assert summary["metrics"]["boundary_safety_score"] == 1.0
    assert summary["metrics"]["optimization_loop_status_score"] == 1.0
    results = (output / "case_results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    case_result = json.loads(results[0])
    assert case_result["case_status"] == "passed"
    assert case_result["hard_constraint_passed"] is True
    assert case_result["hard_constraints"]["required_artifacts_present"] is True
    report = (output / "benchmark_report.md").read_text(encoding="utf-8")
    assert "Hard constraint pass rate" in report
    assert "| case | status | hard_constraints |" in report


def test_repository_benchmark_suite_has_required_case_format():
    suite = Path("benchmarks/multi_agent")

    assert (suite / "README.md").exists()
    cases = [path for path in suite.iterdir() if path.is_dir()]
    assert cases
    for case in cases:
        assert (case / "task.yaml").exists()
        assert (case / "expected.json").exists()
        assert (case / "README.md").exists()
