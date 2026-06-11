from pathlib import Path

import pandas as pd

from goa_eval.io_utils import write_json
from goa_eval.paper_digitization.build_ml_dataset import build_ml_dataset
from goa_eval.paper_digitization.split_dataset import split_dataset
from goa_eval.paper_digitization.train_baseline import train_baseline


def test_build_ml_dataset_outputs_training_artifacts(tmp_path: Path):
    db = tmp_path / "db"
    eval_root = tmp_path / "eval"
    out = tmp_path / "ml"
    db.mkdir()
    case_id = "you2024_fig9_stage18_19"
    pd.DataFrame(
        [
            {
                "case_id": case_id,
                "paper_id": "you2024_10t2c_scan_driver",
                "figure_id": "fig9",
                "topology_id": "GOA_10T2C_MOx",
                "notes": "",
            }
        ]
    ).to_csv(db / "paper_cases.csv", index=False)
    pd.DataFrame(
        [
            {
                "paper_id": "you2024_10t2c_scan_driver",
                "case_id": case_id,
                "topology_id": "GOA_10T2C_MOx",
                "source_location": "Table 1",
                "source_type": "table",
                "parameter_name": "VGH",
                "parameter_group": "supply",
                "value": 7,
                "unit": "V",
                "normalized_value": 7,
                "normalized_unit": "V",
                "extraction_method": "manual_table",
                "weak_label": True,
                "notes": "",
            }
        ]
    ).to_csv(db / "paper_params_long.csv", index=False)
    pd.DataFrame(columns=["case_id"]).to_csv(db / "paper_waveform_index.csv", index=False)
    pd.DataFrame(
        [
            {
                "case_id": case_id,
                "paper_id": "you2024_10t2c_scan_driver",
                "figure_id": "fig9",
                "topology_id": "GOA_10T2C_MOx",
                "parameters_json": '{"CLOAD_F": 2.5e-11}',
                "overall_score": 80,
                "hard_constraint_passed": True,
                "Overall_status": "pass",
            }
        ]
    ).to_csv(db / "paper_goa_leaderboard.csv", index=False)
    run_dir = eval_root / case_id
    run_dir.mkdir(parents=True)
    write_json(run_dir / "real_summary.json", {"All_pulses_exist": True, "Seq_pass": True, "Overall_status": "pass", "VOH_min": 6.8})
    write_json(run_dir / "score_summary.json", {"overall_score": 80, "hard_constraint_passed": True, "failure_reasons": []})
    pd.DataFrame([{"PulseExist": True, "RiseTime": 1e-6, "FallTime": 1.2e-6}]).to_csv(run_dir / "real_metrics.csv", index=False)

    frame = build_ml_dataset(paper_db=db, eval_root=eval_root, output_dir=out)

    assert len(frame) == 1
    assert frame.loc[0, "sample_id"] == f"sample_{case_id}"
    assert frame.loc[0, "evidence_weight"] == 0.3
    assert frame.loc[0, "VGH_V"] == 7
    assert (out / "goa_training_samples.csv").exists()
    assert (out / "goa_training_samples.parquet").exists()
    assert len(pd.read_parquet(out / "goa_training_samples.parquet")) == 1
    assert (out / "goa_feature_schema.yaml").exists()
    assert (out / "goa_label_schema.yaml").exists()
    assert (out / "missingness_report.json").exists()
    assert (out / "feature_statistics.json").exists()
    assert (out / "goa_dataset_card.md").exists()


def test_split_dataset_small_group_warning(tmp_path: Path):
    dataset = tmp_path / "samples.csv"
    pd.DataFrame(
        [
            {"sample_id": "s1", "case_id": "c1", "paper_id": "p1", "topology_id": "t1", "figure_id": "f1"},
            {"sample_id": "s2", "case_id": "c2", "paper_id": "p1", "topology_id": "t1", "figure_id": "f1"},
        ]
    ).to_csv(dataset, index=False)

    split = split_dataset(input_path=dataset, output_path=tmp_path / "split.csv", strategy="group_by_paper_topology", seed=1)

    assert set(split["train_val_test"]) == {"train"}
    assert "small_dataset_group_split_warning" in split.loc[0, "warning"]


def test_train_baseline_insufficient_data_and_training(tmp_path: Path):
    small = tmp_path / "small.csv"
    pd.DataFrame([{"sample_id": "s1", "case_id": "c1", "overall_score": 1.0, "evidence_weight": 0.3, "VGH_V": 7}]).to_csv(
        small, index=False
    )
    split = tmp_path / "split.csv"
    pd.DataFrame([{"sample_id": "s1", "train_val_test": "train"}]).to_csv(split, index=False)

    insufficient = train_baseline(dataset_path=small, split_path=split, target="overall_score", output_dir=tmp_path / "small_out")
    assert insufficient["status"] == "insufficient_data"

    rows = []
    split_rows = []
    for index in range(12):
        rows.append(
            {
                "sample_id": f"s{index}",
                "case_id": f"c{index}",
                "overall_score": float(index),
                "evidence_weight": 0.3,
                "VGH_V": 6.0 + index,
                "CLOAD_F": 1e-12 * (index + 1),
                "do_not_train": False,
            }
        )
        split_rows.append({"sample_id": f"s{index}", "train_val_test": "train" if index < 9 else "test"})
    dataset = tmp_path / "enough.csv"
    split2 = tmp_path / "split2.csv"
    pd.DataFrame(rows).to_csv(dataset, index=False)
    pd.DataFrame(split_rows).to_csv(split2, index=False)

    trained = train_baseline(dataset_path=dataset, split_path=split2, target="overall_score", output_dir=tmp_path / "trained")

    assert trained["status"] == "trained_random_forest"
    assert (tmp_path / "trained" / "feature_importance.csv").exists()
