import json
from pathlib import Path

import pandas as pd

from goa_eval.multi_agent.optimization_loop import build_optimization_loop_record, write_optimization_artifacts


def _state(tmp_path: Path) -> dict:
    next_candidates = tmp_path / "next_candidates.csv"
    pd.DataFrame(
        [
            {
                "candidate_id": "next_001",
                "parameter": "load_cap",
                "candidate_values": "[1e-12]",
                "source_recommendation": "ripple_hold_window_review",
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        ]
    ).to_csv(next_candidates, index=False)
    return {
        "task_name": "sky130_multi_agent_mvp",
        "task_type": "sky130_eda_optimization",
        "profile": "sky130_inverter_chain",
        "output_dir": str(tmp_path),
        "objectives": {"primary": "pass_hard_constraints"},
        "inputs": {"leaderboard": "baseline.csv", "param_space": "params.yaml"},
        "leaderboard_summary": {"best_candidate": {"candidate_id": "base_001", "overall_score": 0.72}},
        "candidate_summary": {
            "next_candidates_path": str(next_candidates),
            "candidate_count": 1,
            "candidate_summary": [{"candidate_id": "next_001", "source_recommendation": "ripple_hold_window_review"}],
        },
        "critic_verdicts": [{"verdict": "warning", "risk_type": "rerun_missing", "severity": "warning", "issues": ["rerun missing"]}],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }


def test_loop_record_waits_for_rerun_results(tmp_path):
    record = build_optimization_loop_record(_state(tmp_path))

    assert record["status"] == "awaiting_rerun_results"
    assert record["decision"]["decision"] == "await_rerun_results"
    assert "multi-agent-run" in record["rerun_instruction"]["command"]
    assert record["baseline"]["best_candidate"]["candidate_id"] == "base_001"
    assert record["next_candidates"]["candidate_count"] == 1


def test_loop_record_compares_better_rerun_result(tmp_path):
    rerun_leaderboard = tmp_path / "rerun_leaderboard.csv"
    pd.DataFrame([{"candidate_id": "next_001", "overall_score": 0.91}]).to_csv(rerun_leaderboard, index=False)
    state = _state(tmp_path)
    state["inputs"]["rerun_leaderboard"] = str(rerun_leaderboard)

    record = build_optimization_loop_record(state)

    assert record["status"] == "decision_ready"
    assert record["comparison"]["score_delta"] == 0.19
    assert record["decision"]["decision"] == "accept_rerun_candidate"


def test_loop_record_compares_worse_rerun_result(tmp_path):
    rerun_leaderboard = tmp_path / "rerun_leaderboard.csv"
    pd.DataFrame([{"candidate_id": "next_001", "overall_score": 0.55}]).to_csv(rerun_leaderboard, index=False)
    state = _state(tmp_path)
    state["inputs"]["rerun_leaderboard"] = str(rerun_leaderboard)

    record = build_optimization_loop_record(state)

    assert record["status"] == "decision_ready"
    assert record["comparison"]["score_delta"] == -0.17
    assert record["decision"]["decision"] == "reject_rerun_candidate"


def test_optimization_artifacts_write_loop_record_and_decision_card(tmp_path):
    state = _state(tmp_path)

    paths = write_optimization_artifacts(tmp_path, state, {"top_risks": [{"risk_type": "rerun_missing", "severity": "warning"}]})

    record = json.loads(Path(paths["optimization_loop_record"]).read_text(encoding="utf-8"))
    card = Path(paths["optimization_decision_card"]).read_text(encoding="utf-8")
    assert record["status"] == "awaiting_rerun_results"
    for text in ["Decision Evidence Card", "baseline", "candidate", "rerun status", "comparison", "top risks", "simulation_only"]:
        assert text in card
