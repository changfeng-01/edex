import json
from pathlib import Path

import pandas as pd
import yaml

from goa_eval.io_utils import write_json
from goa_eval.paper_digitization.build_leaderboard import build_paper_leaderboard


def test_build_paper_leaderboard(tmp_path: Path):
    case_dir = tmp_path / "cases" / "you2024_fig9_stage18_19"
    eval_dir = tmp_path / "eval" / "you2024_fig9_stage18_19"
    db_dir = tmp_path / "db"
    case_dir.mkdir(parents=True)
    eval_dir.mkdir(parents=True)
    db_dir.mkdir()

    (case_dir / "simulation_metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "case_id": "you2024_fig9_stage18_19",
                "paper_id": "you2024_10t2c_scan_driver",
                "figure_id": "fig9",
                "source_type": "paper_digitized",
                "engineering_validity": "simulation_only",
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "paper_metadata.yaml").write_text(
        yaml.safe_dump({"paper_id": "you2024_10t2c_scan_driver", "topology_id": "GOA_10T2C_MOx"}),
        encoding="utf-8",
    )
    (case_dir / "paper_params.yaml").write_text(
        yaml.safe_dump({"parameters": {"VGH_V": 7, "CLOAD_F": 25e-12}}),
        encoding="utf-8",
    )
    write_json(eval_dir / "real_summary.json", {"run_id": "real_1", "Overall_status": "pass", "stage_count": 2, "Max_ripple": 0.1})
    write_json(eval_dir / "score_summary.json", {"overall_score": 88.0, "hard_constraint_passed": True})
    pd.DataFrame(
        [
            {"stage": 1, "Delay": 1e-6, "Ripple": 0.1, "VoltageLoss": 0.2},
            {"stage": 2, "Delay": 2e-6, "Ripple": 0.2, "VoltageLoss": 0.3},
        ]
    ).to_csv(eval_dir / "real_metrics.csv", index=False)

    output = db_dir / "paper_goa_leaderboard.csv"
    frame = build_paper_leaderboard(cases_root=tmp_path / "cases", eval_root=tmp_path / "eval", output_path=output)

    assert output.exists()
    assert {"parameters_json", "overall_score", "Max_ripple", "Max_voltage_loss", "Delay_std"} <= set(frame.columns)
    params = json.loads(frame.loc[0, "parameters_json"])
    assert params["VGH_V"] == 7
    assert frame.loc[0, "engineering_validity"] == "simulation_only"
