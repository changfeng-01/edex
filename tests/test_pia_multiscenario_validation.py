from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from goa_eval.pia_ca_llso.case_pack import case_pack_to_protocol, load_case_pack


def test_case_pack_protocol_preserves_multiscenario_boundary(tmp_path: Path) -> None:
    pack = tmp_path / "case"
    pack.mkdir()
    pd.DataFrame(
        [{"sample_id": "h1", "candidate_id": "hist_1", "overall_score": 70.0, "hard_constraint_passed": True}]
    ).to_csv(pack / "history.csv", index=False)
    pd.DataFrame([{"candidate_id": "c1", "C_boot": 2.0}]).to_csv(pack / "candidate_pool.csv", index=False)
    pd.DataFrame([{"candidate_id": "c1", "method": "pia_full", "seed": 1, "overall_score": 88.0, "hard_constraint_passed": True}]).to_csv(
        pack / "simulation_results.csv",
        index=False,
    )
    (pack / "scoring_config.yaml").write_text("target_score: 80\n", encoding="utf-8")
    (pack / "provenance.json").write_text(json.dumps({"source": "test"}), encoding="utf-8")
    (pack / "scenario.yaml").write_text(
        yaml.safe_dump(
            {
                "scenario_id": "case",
                "history_csv": "history.csv",
                "candidate_csv": "candidate_pool.csv",
                "result_csv": "simulation_results.csv",
                "methods": ["pia_full"],
                "seeds": [1],
                "top_k": 1,
                "target_score": 80,
                "evidence_boundary": {
                    "data_source": "real_simulation_csv",
                    "engineering_validity": "simulation_only",
                    "must_resimulate": True,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    protocol = case_pack_to_protocol([load_case_pack(pack)])

    assert protocol["scenarios"][0]["scenario_id"] == "case"
    assert protocol["boundary"]["data_source"] == "real_simulation_csv"
    assert protocol["boundary"]["engineering_validity"] == "simulation_only"
    assert protocol["boundary"]["must_resimulate"] is True
