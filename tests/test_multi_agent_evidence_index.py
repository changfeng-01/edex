from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from goa_eval.multi_agent.evidence_index import build_evidence_index, write_evidence_index
from goa_eval.multi_agent.agents.optimization_agent import run_optimization_agent
from goa_eval.multi_agent.graph_app import run_multi_agent_task


def _write_artifact_bundle(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "real_summary.json").write_text(
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
    (root / "score_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "result_version": "1.0",
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "hard_constraint_passed": True,
                "overall_score": 0.91,
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame([{"schema_version": "1.0", "result_version": "1.0", "stage": 1, "OverlapRatio": 0.0}]).to_csv(
        root / "real_metrics.csv", index=False
    )
    pd.DataFrame([{"candidate_id": "best_001", "overall_score": 0.91, "target.status": "passed"}]).to_csv(
        root / "optimization_leaderboard.csv", index=False
    )
    pd.DataFrame([{"candidate_id": "cand_001", "parameter": "load_cap", "candidate_values": "[1p]"}]).to_csv(
        root / "best_next_candidates.csv", index=False
    )
    (root / "optimization_history.json").write_text(
        json.dumps(
            {
                "rounds": [
                    {"round_index": 1, "best_score": 0.88, "best_run_dir": "round_1/best"},
                    {"round_index": 2, "best_score": 0.91, "best_run_dir": "round_2/best", "target_status": "passed"},
                ],
                "stop_reason": "target_met",
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame([{"target.status": "passed"}]).to_csv(root / "validation_summary.csv", index=False)
    (root / "run_manifest_real.json").write_text(
        json.dumps({"data_source": "real_simulation_csv", "engineering_validity": "simulation_only"}),
        encoding="utf-8",
    )
    (root / "diagnosis_report.md").write_text("simulation_only diagnosis", encoding="utf-8")
    (root / "real_waveform_report.md").write_text("real_simulation_csv report", encoding="utf-8")
    (root / "sky130_mainline_report.md").write_text("simulation_only mainline report", encoding="utf-8")


def test_build_evidence_index_discovers_artifact_dir_bundle(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    _write_artifact_bundle(artifacts)
    output = tmp_path / "out"

    index = build_evidence_index({"artifact_dir": str(artifacts)}, output)
    written = write_evidence_index(index, output)

    assert index["artifacts"]["real_summary"]["exists"] is True
    assert index["artifacts"]["real_metrics"]["exists"] is True
    assert index["artifacts"]["best_next_candidates"]["exists"] is True
    assert index["aliases"]["leaderboard"].endswith("optimization_leaderboard.csv")
    assert index["aliases"]["next_candidates"].endswith("best_next_candidates.csv")
    assert index["artifact_discovery_score"] > 0.75
    assert written.name == "evidence_index.json"
    assert json.loads(written.read_text(encoding="utf-8"))["schema_version"] == "1.0"


def test_multi_agent_run_accepts_artifact_dir_only_task(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    _write_artifact_bundle(artifacts)
    task = tmp_path / "task.yaml"
    task.write_text(
        f"""
task_name: artifact_dir_only
task_type: sky130_eda_optimization
profile: sky130_inverter_chain
inputs:
  artifact_dir: {artifacts.as_posix()}
  param_space: examples/sample_params.yaml
validity:
  data_source: real_simulation_csv
  engineering_validity: simulation_only
""".strip(),
        encoding="utf-8",
    )
    output = tmp_path / "multi_agent"

    state = run_multi_agent_task(task, output)

    assert (output / "evidence_index.json").exists()
    assert state["evidence_index"]["artifacts"]["score_summary"]["exists"] is True
    assert state["inputs"]["real_summary"].endswith("real_summary.json")
    assert state["candidate_summary"]["source"] == "existing_artifact"
    assert state["candidate_summary"]["status"] == "awaiting_rerun_results"
    assert state["optimization_history_summary"]["round_count"] == 2
    assert state["optimization_history_summary"]["best_score"] == 0.91


def test_optimization_agent_reuses_best_next_candidates_and_summarizes_history(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    _write_artifact_bundle(artifacts)
    state = {
        "inputs": {
            "best_next_candidates": str(artifacts / "best_next_candidates.csv"),
            "optimization_history": str(artifacts / "optimization_history.json"),
            "leaderboard": str(artifacts / "optimization_leaderboard.csv"),
            "param_space": "examples/sample_params.yaml",
        },
        "limits": {},
        "output_dir": str(tmp_path / "out"),
        "agent_messages": [],
        "handoff_records": [],
        "tool_results": {},
        "generated_files": {},
    }

    updated = run_optimization_agent(state)

    assert updated["candidate_summary"]["source"] == "existing_artifact"
    assert updated["candidate_summary"]["next_candidates_path"].endswith("best_next_candidates.csv")
    assert updated["candidate_summary"]["status"] == "awaiting_rerun_results"
    assert updated["optimization_history_summary"]["round_count"] == 2
    assert updated["optimization_history_summary"]["best_score"] == 0.91
    assert "next_candidates" not in updated["generated_files"]
