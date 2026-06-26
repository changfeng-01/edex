from __future__ import annotations

import json

from goa_eval.cli import main


def test_pia_label_suggest_and_benchmark_cli_run_on_sample_data(tmp_path) -> None:
    label_dir = tmp_path / "label"
    suggest_dir = tmp_path / "suggest"
    bench_dir = tmp_path / "bench"

    assert main([
        "pia-label",
        "--history-csv",
        "examples/pia_ca_llso/sample_history.csv",
        "--config",
        "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir",
        str(label_dir),
    ]) == 0
    assert (label_dir / "labeled_history.csv").exists()

    assert main([
        "pia-suggest",
        "--history-csv",
        str(label_dir / "labeled_history.csv"),
        "--candidate-csv",
        "examples/pia_ca_llso/sample_candidates.csv",
        "--config",
        "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir",
        str(suggest_dir),
        "--top-k",
        "4",
    ]) == 0
    assert (suggest_dir / "pia_selected_candidates.csv").exists()
    assert json.loads((suggest_dir / "pia_candidate_explanations.json").read_text(encoding="utf-8"))

    assert main([
        "pia-benchmark",
        "--history-csv",
        "examples/pia_ca_llso/sample_history.csv",
        "--candidate-csv",
        "examples/pia_ca_llso/sample_candidates.csv",
        "--config",
        "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir",
        str(bench_dir),
    ]) == 0
    assert (bench_dir / "pia_ablation_report.md").exists()


def test_classifier_level_hybrid_cli_smoke_runs_on_sample_data(tmp_path) -> None:
    output_dir = tmp_path / "classifier_suggest"

    assert main([
        "pia-suggest",
        "--history-csv",
        "examples/pia_ca_llso/sample_history.csv",
        "--candidate-csv",
        "examples/pia_ca_llso/sample_candidates.csv",
        "--config",
        "config/pia_ca_llso_goa_profile.yaml",
        "--strategy",
        "classifier_level_hybrid",
        "--top-k",
        "4",
        "--output-dir",
        str(output_dir),
    ]) == 0

    selected = (output_dir / "pia_selected_candidates.csv").read_text(encoding="utf-8")
    assert "classifier_hybrid_score" in selected
    assert "simulation_window" in selected
    assert "constraint_eval_plan_json" in selected
