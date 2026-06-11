from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from goa_eval.cli import main
from goa_eval.pia_ca_llso.training_data import build_training_data_from_db


PAPER_DB_HEADERS = {
    "paper_cases.csv": [
        "case_id",
        "paper_id",
        "figure_id",
        "table_id",
        "topology_id",
        "case_dir",
        "source_type",
        "weak_label",
        "engineering_validity",
        "notes",
    ],
    "paper_params_long.csv": [
        "paper_id",
        "case_id",
        "topology_id",
        "source_location",
        "source_type",
        "parameter_name",
        "parameter_group",
        "value",
        "unit",
        "normalized_value",
        "normalized_unit",
        "extraction_method",
        "weak_label",
        "notes",
    ],
    "paper_waveform_index.csv": [
        "case_id",
        "paper_id",
        "figure_id",
        "topology_id",
        "waveform_path",
        "internal_waveform_path",
        "stage_count",
        "output_node_pattern",
        "time_unit",
        "voltage_unit",
        "weak_label",
        "quality_status",
        "notes",
    ],
    "paper_goa_leaderboard.csv": [
        "run_id",
        "case_id",
        "paper_id",
        "figure_id",
        "topology_id",
        "parameters_json",
        "overall_score",
        "hard_constraint_passed",
        "Overall_status",
        "stage_count",
        "weak_label",
        "source_type",
        "engineering_validity",
        "data_source",
        "notes",
    ],
}


def _write_empty_paper_db(path: Path) -> None:
    path.mkdir(parents=True)
    for filename, columns in PAPER_DB_HEADERS.items():
        pd.DataFrame(columns=columns).to_csv(path / filename, index=False)


def _history_row(index: int, *, score: float, hard_pass: bool) -> dict[str, object]:
    return {
        "run_id": f"run_{index}",
        "W_PU": 420 + index,
        "W_PD": 210 + index,
        "TFT_pullup_L": 5,
        "TFT_pulldown_L": 5,
        "TFT_reset_W": 160,
        "TFT_reset_L": 5,
        "TFT_bootstrap_W": 120,
        "TFT_bootstrap_L": 5,
        "C_boot": 2.0 + index * 0.1,
        "C_load": 1.0,
        "V_CLKH": 20,
        "CLK_rise_time": 0.1,
        "CLK_fall_time": 0.1,
        "VGH": 15,
        "VGL": -5,
        "Vth_shift": 1.2,
        "overall_score": score,
        "hard_constraint_passed": hard_pass,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }


def test_pia_train_from_empty_database_marks_missing_and_parse_errors(tmp_path: Path) -> None:
    paper_db = tmp_path / "paper_database"
    history_root = tmp_path / "outputs"
    output_dir = tmp_path / "pia_training"
    _write_empty_paper_db(paper_db)
    history_root.mkdir()
    (history_root / "optimization_dataset.csv").write_text('run_id,overall_score\nbad,"unterminated\n', encoding="utf-8")

    artifacts = build_training_data_from_db(paper_db=paper_db, history_root=history_root, output_dir=output_dir)

    assert artifacts.history.empty
    assert artifacts.train_report["status"] == "insufficient_data"
    assert artifacts.train_report["parse_error_count"] == 1
    assert (output_dir / "pia_training_history.csv").exists()
    assert (output_dir / "pia_labeled_history.csv").exists()
    assert (output_dir / "pia_missing_data_report.csv").exists()
    assert (output_dir / "pia_missing_data_report.json").exists()
    assert (output_dir / "pia_training_dataset_card.md").exists()
    assert set(artifacts.missing_report["missing_reason"]) >= {"empty_paper_database", "parse_error"}


def test_pia_train_from_history_root_trains_and_labels(tmp_path: Path) -> None:
    paper_db = tmp_path / "paper_database"
    history_root = tmp_path / "outputs"
    output_dir = tmp_path / "pia_training"
    _write_empty_paper_db(paper_db)
    run_dir = history_root / "run"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            _history_row(0, score=92, hard_pass=True),
            _history_row(1, score=84, hard_pass=True),
            _history_row(2, score=58, hard_pass=False),
            _history_row(3, score=20, hard_pass=False),
        ]
    ).to_csv(run_dir / "optimization_dataset.csv", index=False)

    artifacts = build_training_data_from_db(paper_db=paper_db, history_root=history_root, output_dir=output_dir)

    assert len(artifacts.history) == 4
    assert set(artifacts.labeled_history["level_label"]) >= {"L1", "L3"}
    assert artifacts.train_report["status"] == "trained"
    assert artifacts.train_report["model_report"]["models"]["score"]["model_status"] == "ok"
    assert artifacts.history["must_resimulate"].eq(True).all()
    assert set(artifacts.history["data_source"]) == {"real_simulation_csv"}
    assert set(artifacts.history["engineering_validity"]) == {"simulation_only"}


def test_pia_missing_report_marks_ambiguous_role_mapping(tmp_path: Path) -> None:
    paper_db = tmp_path / "paper_database"
    history_root = tmp_path / "outputs"
    output_dir = tmp_path / "pia_training"
    _write_empty_paper_db(paper_db)
    history_root.mkdir()
    pd.DataFrame(
        [
            {
                "run_id": "ambiguous",
                "transistor_width": 10,
                "transistor_length": 5,
                "C_boot": 2.0,
                "C_load": 1.0,
                "overall_score": 80,
                "hard_constraint_passed": True,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        ]
    ).to_csv(history_root / "optimization_dataset.csv", index=False)

    artifacts = build_training_data_from_db(paper_db=paper_db, history_root=history_root, output_dir=output_dir)

    ambiguous = artifacts.missing_report[artifacts.missing_report["sample_id"].eq("ambiguous")]
    assert "missing_role_mapping" in set(ambiguous["missing_reason"])
    assert "TFT_pullup_W" in set(ambiguous["field"])
    assert artifacts.history.loc[0, "missing_reason"] == "missing_role_mapping"


def test_pia_train_from_db_cli_defaults_run_in_current_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_empty_paper_db(tmp_path / "data" / "paper_database")
    (tmp_path / "outputs").mkdir()

    assert main(["pia-train-from-db"]) == 0

    report_path = tmp_path / "outputs" / "pia_training_from_db" / "pia_train_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "insufficient_data"
    assert report["data_source"] == "real_simulation_csv"
    assert report["engineering_validity"] == "simulation_only"
    assert report["must_resimulate"] is True
