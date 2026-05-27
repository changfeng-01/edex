from pathlib import Path

import pandas as pd

from goa_eval.multi_agent.critic import run_critic_checks


def test_critic_detects_missing_files_and_boundary_mismatch(tmp_path):
    bad_summary = tmp_path / "bad_summary.json"
    bad_summary.write_text(
        '{"data_source":"mock","engineering_validity":"silicon_validated"}',
        encoding="utf-8",
    )
    state = {
        "profile": "unknown",
        "selected_domain_agent": "unsupported",
        "generated_files": {"missing": str(tmp_path / "missing.json"), "bad": str(bad_summary)},
        "tool_results": {},
        "handoff_records": [],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    verdicts = run_critic_checks(state)
    issues = [issue for verdict in verdicts for issue in verdict.issues]

    assert any("missing output file" in issue for issue in issues)
    assert any("data_source" in issue for issue in issues)
    assert any("unsupported profile" in issue for issue in issues)
    assert any("handoff record missing" in issue for issue in issues)


def test_critic_detects_metric_bad_cells_and_candidate_risk(tmp_path):
    metrics = tmp_path / "metrics.csv"
    pd.DataFrame(
        [
            {"schema_version": "1.0", "result_version": "1.0", "stage": 1, "Ripple": None},
            {"schema_version": "1.0", "result_version": "1.0", "stage": 2, "Ripple": "not_evaluable"},
        ]
    ).to_csv(metrics, index=False)
    candidates = tmp_path / "next_candidates.csv"
    pd.DataFrame(
        [
            {
                "candidate_id": "cand_001",
                "parameter": "drive_resistance",
                "candidate_values": "[999999]",
                "parameter_change_count": 3,
            }
        ]
    ).to_csv(candidates, index=False)
    param_space = tmp_path / "params.yaml"
    param_space.write_text("parameters:\n  drive_resistance:\n    values: [1000, 1500]\n", encoding="utf-8")
    state = {
        "generated_files": {"metrics": str(metrics), "next_candidates": str(candidates)},
        "inputs": {"param_space": str(param_space)},
        "candidate_summary": {"candidate_count": 1},
        "tool_results": {
            "RouterAgent": [{"tool_name": "generate_candidates"}],
        },
        "handoff_records": [{"from_agent": "RouterAgent", "to_agent": "CriticAgent"}],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    verdicts = run_critic_checks(state)
    issues = [issue for verdict in verdicts for issue in verdict.issues]

    assert any("bad metric cell" in issue for issue in issues)
    assert any("parameter change count" in issue for issue in issues)
    assert any("unauthorized tool" in issue for issue in issues)
