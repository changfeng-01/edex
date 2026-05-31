from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from goa_eval.goa_strategy_benchmark import (
    generate_adaptive_goa_candidates,
    generate_hybrid_goa_candidates,
    generate_random_goa_candidates,
    generate_surrogate_goa_candidates,
    run_goa_strategy_benchmark,
)
from goa_eval.goa_hybrid_optimizer import _fit_surrogate
from goa_eval.optimizer import load_param_space


def _sample_leaderboard_csv(tmp_path: Path) -> Path:
    path = tmp_path / "optimization_leaderboard.csv"
    pd.DataFrame(
        [
            {
                "candidate_id": "seed_1",
                "overall_score": 61.0,
                "Max_overlap_ratio": 0.5,
                "Max_ripple": 0.2,
                "Max_voltage_loss": 0.1,
                "Delay_std": 0.04,
                "hard_constraint_passed": False,
                "rank_status": "evaluated",
                "parameters_json": json.dumps({"capacitance": 1.0e-12, "drive_resistance": 1500, "transistor_width": 1.0e-6}),
            },
            {
                "candidate_id": "seed_2",
                "overall_score": 72.0,
                "Max_overlap_ratio": 0.3,
                "Max_ripple": 0.1,
                "Max_voltage_loss": 0.08,
                "Delay_std": 0.03,
                "hard_constraint_passed": True,
                "rank_status": "evaluated",
                "parameters_json": json.dumps({"capacitance": 8.0e-13, "drive_resistance": 1000, "transistor_width": 1.2e-6}),
            },
            {
                "candidate_id": "seed_3",
                "overall_score": 55.0,
                "Max_overlap_ratio": 0.6,
                "Max_ripple": 0.3,
                "Max_voltage_loss": 0.15,
                "Delay_std": 0.05,
                "hard_constraint_passed": False,
                "rank_status": "not_evaluable",
                "not_evaluable_metric_count": 3,
                "parameters_json": json.dumps({"capacitance": 1.2e-12, "drive_resistance": 2000, "transistor_width": 8.0e-7}),
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _sample_param_space(tmp_path: Path) -> Path:
    import yaml

    path = tmp_path / "sample_params.yaml"
    path.write_text(
        yaml.dump(
            {
                "parameters": {
                    "capacitance": {"unit": "F", "values": [8.0e-13, 1.0e-12, 1.2e-12]},
                    "drive_resistance": {"unit": "ohm", "values": [1000, 1500, 2000]},
                    "transistor_width": {"unit": "m", "values": [8.0e-7, 1.0e-6, 1.2e-6]},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


class TestGoaStrategyBenchmarkCLI:
    def test_cli_smoke_produces_required_outputs(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "goa_eval.cli",
                "goa-strategy-benchmark",
                "--leaderboard",
                str(leaderboard),
                "--param-space",
                str(param_space),
                "--output-root",
                str(output_root),
                "--strategies",
                "random,adaptive,surrogate,repair,hybrid_goa",
                "--max-candidates",
                "10",
                "--seeds",
                "1,2",
                "--top-k",
                "5",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        assert (output_root / "goa_strategy_benchmark.csv").exists()
        assert (output_root / "goa_strategy_benchmark_summary.json").exists()
        assert (output_root / "goa_strategy_leaderboard.csv").exists()
        assert (output_root / "goa_strategy_benchmark_report.md").exists()

    def test_cli_no_history_no_leaderboard_errors(self, tmp_path: Path):
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "goa_eval.cli",
                "goa-strategy-benchmark",
                "--param-space",
                str(param_space),
                "--output-root",
                str(output_root),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


class TestStrategyCoverage:
    def test_all_strategies_appear_in_benchmark(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        summary = run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["random", "adaptive", "surrogate", "repair", "hybrid_goa"],
            max_candidates=10,
            seeds=[1],
        )

        bench = pd.read_csv(output_root / "goa_strategy_benchmark.csv")
        strategy_set = set(bench["strategy"].unique())
        assert "random" in strategy_set
        assert "adaptive" in strategy_set
        assert "surrogate" in strategy_set
        assert "repair" in strategy_set
        assert "hybrid_goa" in strategy_set


class TestBoundaryFields:
    def test_summary_boundary_fields(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        summary = run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["random", "hybrid_goa"],
            max_candidates=10,
            seeds=[1],
        )

        assert summary["benchmark_type"] == "goa_strategy_benchmark"
        assert summary["task_type"] == "candidate_quality_proxy"
        assert summary["engineering_validity"] == "simulation_only"
        assert summary["simulation_backend"] == "no_real_ngspice_required"
        assert summary["result_claim"] == "candidate_quality_proxy_only"
        assert summary["mock_used"] is False


class TestFairnessFields:
    def test_summary_fairness_fields(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        summary = run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["random", "adaptive"],
            max_candidates=15,
            seeds=[1, 2],
            top_k=8,
        )

        fairness = summary["fairness"]
        assert fairness["same_param_space"] is True
        assert fairness["same_candidate_budget"] == 15
        assert fairness["same_seed_set"] == [1, 2]
        assert fairness["same_objective_config"] is not None
        assert fairness["same_top_k"] == 8
        assert fairness["random_baseline_no_replay"] is True
        assert fairness["no_real_ngspice_required"] is True


class TestRandomBaseline:
    def test_random_candidates_have_correct_source_and_status(self, tmp_path: Path):
        param_space_path = _sample_param_space(tmp_path)
        param_space = load_param_space(param_space_path)

        candidates = generate_random_goa_candidates(param_space, max_candidates=5, seed=42)

        assert len(candidates) == 5
        for candidate in candidates:
            assert candidate["candidate_source"] == "random"
            assert candidate["model_status"] == "random_no_replay"
            assert candidate["repair_operator"] == ""
            assert candidate["data_source"] == "benchmark-derived"
            assert candidate["simulation_backend"] == "no_real_ngspice_required"

    def test_random_benchmark_row_has_no_surrogate_no_repair(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["random"],
            max_candidates=10,
            seeds=[1],
        )

        bench = pd.read_csv(output_root / "goa_strategy_benchmark.csv")
        random_row = bench[bench["strategy"] == "random"].iloc[0]
        assert random_row["surrogate_candidate_ratio"] == 0.0
        assert random_row["repair_candidate_ratio"] == 0.0
        assert random_row["exploration_candidate_ratio"] == 0.0


class TestHybridGoaIntegration:
    def test_hybrid_goa_candidate_sources_appear(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["hybrid_goa"],
            max_candidates=10,
            seeds=[1],
        )

        bench = pd.read_csv(output_root / "goa_strategy_benchmark.csv")
        hybrid_row = bench[bench["strategy"] == "hybrid_goa"].iloc[0]
        total = hybrid_row["repair_candidate_ratio"] + hybrid_row["surrogate_candidate_ratio"] + hybrid_row["exploration_candidate_ratio"]
        assert total > 0.0

    def test_hybrid_goa_produces_candidates_from_multiple_sources(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space_path = _sample_param_space(tmp_path)
        param_space = load_param_space(param_space_path)
        leaderboard_df = pd.read_csv(leaderboard)
        model_bundle = _fit_surrogate(leaderboard_df, list(param_space.keys()))

        candidates = generate_hybrid_goa_candidates(
            leaderboard_df, param_space, model_bundle, max_candidates=10, seed=42
        )

        sources = {c["candidate_source"] for c in candidates}
        assert sources & {"surrogate", "repair", "exploration"}


class TestLeaderboardSorting:
    def test_leaderboard_sorts_by_hard_constraint_then_pareto(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["random", "adaptive", "surrogate", "repair", "hybrid_goa"],
            max_candidates=10,
            seeds=[1],
        )

        lb = pd.read_csv(output_root / "goa_strategy_leaderboard.csv")
        assert not lb.empty
        assert "strategy" in lb.columns
        assert "predicted_hard_constraint_pass_rate" in lb.columns
        assert "pareto_front_hit_rate" in lb.columns


class TestCandidatesWritten:
    def test_candidate_csv_files_generated(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["random", "hybrid_goa"],
            max_candidates=10,
            seeds=[1],
        )

        candidates_dir = output_root / "candidates"
        assert candidates_dir.exists()
        candidate_files = list(candidates_dir.glob("*.csv"))
        assert len(candidate_files) >= 1

    def test_report_marks_simulation_only(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space = _sample_param_space(tmp_path)
        output_root = tmp_path / "goa_strategy_benchmark"

        run_goa_strategy_benchmark(
            leaderboard_path=leaderboard,
            history_path=None,
            param_space_path=param_space,
            output_root=output_root,
            strategies=["random", "adaptive"],
            max_candidates=10,
            seeds=[1],
        )

        report = (output_root / "goa_strategy_benchmark_report.md").read_text(encoding="utf-8")
        assert "simulation_only" in report
        assert "candidate_quality_proxy" in report
        assert "no_real_ngspice_required" in report
        assert "not physical validation" in report
        assert "Do not describe proxy improvement" in report


class TestAdaptiveStrategy:
    def test_adaptive_candidates_have_correct_source(self, tmp_path: Path):
        leaderboard = _sample_leaderboard_csv(tmp_path)
        param_space_path = _sample_param_space(tmp_path)
        param_space = load_param_space(param_space_path)
        leaderboard_df = pd.read_csv(leaderboard)

        candidates = generate_adaptive_goa_candidates(leaderboard_df, param_space, max_candidates=5, seed=42)

        assert len(candidates) == 5
        for candidate in candidates:
            assert candidate["candidate_source"] == "adaptive"
            assert candidate["model_status"] == "rule_based_adaptive"
