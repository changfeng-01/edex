from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.formal_audit import build_fairness_audit_rows, build_scenario_manifest_rows
from goa_eval.pia_ca_llso.leakage import leakage_audit_rows


def test_fairness_audit_records_shared_run_contract() -> None:
    rows = build_fairness_audit_rows(
        [
            {
                "scenario_id": "s1",
                "method": "pia_evolve_full",
                "ablation": "full",
                "budget": 20,
                "seed": 11,
                "target_score": 80,
                "history_hash": "h",
                "candidate_pool_hash": "c",
                "scoring_config_hash": "cfg",
                "result_source": "best_so_far_curve.csv",
                "leakage_check_passed": True,
                "boundary_audit_passed": True,
                "evidence_status": "evaluable",
            }
        ]
    )

    assert rows[0]["history_hash"] == "h"
    assert rows[0]["result_source"] == "best_so_far_curve.csv"
    assert rows[0]["engineering_validity"] == "simulation_only"


def test_leakage_audit_flags_result_columns() -> None:
    rows = leakage_audit_rows("s1", pd.DataFrame({"candidate_id": ["c1"], "overall_score": [90]}))

    assert rows[0]["leakage_check_passed"] is False
    assert rows[0]["leakage_columns"] == "overall_score"


def test_scenario_manifest_records_input_hashes(tmp_path) -> None:
    history = tmp_path / "history.csv"
    candidates = tmp_path / "candidates.csv"
    history.write_text("candidate_id\nh1\n", encoding="utf-8")
    candidates.write_text("candidate_id\nc1\n", encoding="utf-8")

    rows = build_scenario_manifest_rows(
        {
            "s1": {
                "history_csv": str(history),
                "candidate_csv": str(candidates),
                "config": {"target_score": 80},
                "source_type": "local_fixture",
                "claim_boundary": "CI fixture",
            }
        }
    )

    assert rows[0]["history_hash"]
    assert rows[0]["candidate_pool_hash"]
    assert rows[0]["data_source"] == "real_simulation_csv"
