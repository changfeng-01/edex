from __future__ import annotations

import json

import pandas as pd

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


def test_pia_evolve_cli_offline_smoke(tmp_path) -> None:
    """pia-evolve --mode offline writes a generation batch."""
    output_dir = tmp_path / "evolve_out"

    assert main([
        "pia-evolve",
        "--history-csv", "examples/pia_ca_llso/sample_history.csv",
        "--candidate-csv", "examples/pia_ca_llso/sample_candidates.csv",
        "--config", "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir", str(output_dir),
        "--strategy", "classifier_level_hybrid",
        "--generations", "2",
        "--offspring-per-generation", "8",
        "--top-k", "4",
        "--mode", "offline",
        "--target-score", "100",
        "--seed", "42",
    ]) == 0

    assert (output_dir / "generation_000" / "simulation_batch.csv").exists()
    assert (output_dir / "evolution_summary.json").exists()


def test_pia_evolve_cli_resume_imports_pending_generation_results(tmp_path) -> None:
    """pia-evolve can resume a pending generation after result CSV arrives."""
    output_dir = tmp_path / "evolve_resume"

    assert main([
        "pia-evolve",
        "--history-csv", "examples/pia_ca_llso/sample_history.csv",
        "--candidate-csv", "examples/pia_ca_llso/sample_candidates.csv",
        "--config", "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir", str(output_dir),
        "--strategy", "classifier_level_hybrid",
        "--generations", "2",
        "--offspring-per-generation", "8",
        "--top-k", "4",
        "--mode", "offline",
        "--target-score", "100",
        "--seed", "42",
    ]) == 0

    batch = pd.read_csv(output_dir / "generation_000" / "simulation_batch.csv")
    pd.DataFrame({
        "candidate_id": batch["candidate_id"].head(1),
        "overall_score": [92.0],
        "hard_constraint_passed": [True],
    }).to_csv(output_dir / "generation_000" / "simulation_results.csv", index=False)

    assert main([
        "pia-evolve",
        "--history-csv", "examples/pia_ca_llso/sample_history.csv",
        "--candidate-csv", "examples/pia_ca_llso/sample_candidates.csv",
        "--config", "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir", str(output_dir),
        "--strategy", "classifier_level_hybrid",
        "--generations", "2",
        "--offspring-per-generation", "8",
        "--top-k", "4",
        "--mode", "import_results",
        "--target-score", "100",
        "--resume-from", str(output_dir),
        "--resume-generation", "0",
        "--seed", "42",
    ]) == 0

    history = pd.read_csv(output_dir / "evolution_history.csv")
    assert "92.0" in history.to_csv(index=False)
    assert (output_dir / "generation_001" / "simulation_batch.csv").exists()


def test_pia_benchmark_cli_closed_loop(tmp_path) -> None:
    evolve_dir = tmp_path / "evolve_local"
    bench_dir = tmp_path / "bench_closed_loop"

    assert main([
        "pia-evolve",
        "--history-csv", "examples/pia_ca_llso/sample_history.csv",
        "--candidate-csv", "examples/pia_ca_llso/sample_candidates.csv",
        "--config", "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir", str(evolve_dir),
        "--strategy", "classifier_level_hybrid",
        "--generations", "1",
        "--offspring-per-generation", "8",
        "--top-k", "4",
        "--mode", "local_fixture",
        "--target-score", "100",
    ]) == 0

    assert main([
        "pia-benchmark",
        "--closed-loop",
        "--evolution-dir", str(evolve_dir),
        "--output-dir", str(bench_dir),
        "--target-score", "90",
    ]) == 0

    assert (bench_dir / "pia_closed_loop_benchmark.json").exists()


def test_pia_evolve_cli_writes_boundary_audit(tmp_path) -> None:
    output_dir = tmp_path / "evolve_audit"

    assert main([
        "pia-evolve",
        "--history-csv", "examples/pia_ca_llso/sample_history.csv",
        "--candidate-csv", "examples/pia_ca_llso/sample_candidates.csv",
        "--config", "config/pia_ca_llso_goa_profile.yaml",
        "--output-dir", str(output_dir),
        "--strategy", "classifier_level_hybrid",
        "--generations", "1",
        "--offspring-per-generation", "8",
        "--top-k", "4",
        "--mode", "offline",
        "--target-score", "100",
        "--audit-boundary",
    ]) == 0

    audit = json.loads((output_dir / "boundary_audit.json").read_text(encoding="utf-8"))
    assert audit["passed"] is True


def test_pia_validate_cli_smoke_runs_protocol(tmp_path) -> None:
    output_dir = tmp_path / "validate_smoke"

    assert main([
        "pia-validate",
        "--protocol", "config/pia_ca_llso_validation_protocol.yaml",
        "--output-dir", str(output_dir),
        "--smoke",
        "--max-runs", "2",
    ]) == 0

    assert (output_dir / "validation_runs.csv").exists()


def test_pia_validate_cli_writes_aggregate_csv_and_report(tmp_path) -> None:
    output_dir = tmp_path / "validate_report"

    assert main([
        "pia-validate",
        "--protocol", "config/pia_ca_llso_validation_protocol.yaml",
        "--output-dir", str(output_dir),
        "--smoke",
        "--max-runs", "2",
    ]) == 0

    assert (output_dir / "validation_summary.csv").exists()
    assert (output_dir / "pairwise_win_rates.csv").exists()
    assert (output_dir / "validation_summary.json").exists()
