from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from goa_eval.goa_strategy_benchmark import (
    OUTPUT_REQUIRED_FILES,
    REQUIRED_BOUNDARY_FIELDS,
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
                "parameters_json": json.dumps(
                    {"capacitance": 1.0e-12, "drive_resistance": 1500, "transistor_width": 1.0e-6}
                ),
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
                "parameters_json": json.dumps(
                    {"capacitance": 8.0e-13, "drive_resistance": 1000, "transistor_width": 1.2e-6}
                ),
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
                "parameters_json": json.dumps(
                    {"capacitance": 1.2e-12, "drive_resistance": 2000, "transistor_width": 8.0e-7}
                ),
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _sample_param_space(tmp_path: Path) -> Path:
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


def test_goa_strategy_benchmark_writes_boundary_outputs(tmp_path: Path) -> None:
    leaderboard_path = _sample_leaderboard_csv(tmp_path)
    param_space_path = _sample_param_space(tmp_path)
    output_root = tmp_path / "benchmark"

    summary = run_goa_strategy_benchmark(
        history_path=None,
        leaderboard_path=leaderboard_path,
        param_space_path=param_space_path,
        output_root=output_root,
        strategies=["random", "adaptive", "surrogate", "repair", "hybrid_goa"],
        max_candidates=8,
        seeds=[1, 2],
        top_k=3,
    )

    for filename in OUTPUT_REQUIRED_FILES:
        assert (output_root / filename).exists(), filename
    for key, expected in REQUIRED_BOUNDARY_FIELDS.items():
        assert summary[key] == expected

    assert summary["fairness"]["random_baseline_no_replay"] is True
    assert set(summary["strategies"]) == {"random", "adaptive", "surrogate", "repair", "hybrid_goa"}

    rows = pd.read_csv(output_root / "goa_strategy_benchmark.csv")
    assert set(rows["strategy"]) == {"random", "adaptive", "surrogate", "repair", "hybrid_goa"}
    assert set(rows["engineering_validity"]) == {"simulation_only"}
    assert set(rows["simulation_backend"]) == {"no_real_ngspice_required"}

    leaderboard = pd.read_csv(output_root / "goa_strategy_leaderboard.csv")
    assert "proxy_improvement_vs_random" in leaderboard.columns
    assert "predicted_hard_constraint_pass_rate" in leaderboard.columns

    report = (output_root / "goa_strategy_benchmark_report.md").read_text(encoding="utf-8")
    assert "candidate-quality proxy only" in report
    assert "engineering_validity = simulation_only" in report


def test_goa_strategy_generators_keep_expected_sources(tmp_path: Path) -> None:
    leaderboard = pd.read_csv(_sample_leaderboard_csv(tmp_path))
    param_space = load_param_space(_sample_param_space(tmp_path))
    model_bundle = _fit_surrogate(leaderboard, list(param_space))

    random_candidates = generate_random_goa_candidates(param_space, max_candidates=4, seed=1)
    adaptive_candidates = generate_adaptive_goa_candidates(leaderboard, param_space, max_candidates=4, seed=1)
    surrogate_candidates = generate_surrogate_goa_candidates(
        leaderboard, param_space, model_bundle, max_candidates=4, seed=1
    )
    hybrid_candidates = generate_hybrid_goa_candidates(
        leaderboard, param_space, model_bundle, max_candidates=8, seed=1
    )

    assert {item["candidate_source"] for item in random_candidates} == {"random"}
    assert {item["candidate_source"] for item in adaptive_candidates} == {"adaptive"}
    assert any(item["candidate_source"] == "surrogate" for item in surrogate_candidates)
    assert {"surrogate", "repair", "exploration"}.issubset({item["candidate_source"] for item in hybrid_candidates})


def test_goa_strategy_benchmark_requires_history_or_leaderboard(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="At least one of --history or --leaderboard"):
        run_goa_strategy_benchmark(
            history_path=None,
            leaderboard_path=None,
            param_space_path=_sample_param_space(tmp_path),
            output_root=tmp_path / "out",
        )


def test_goa_strategy_benchmark_cli_smoke(tmp_path: Path) -> None:
    output_root = tmp_path / "cli_out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "goa-strategy-benchmark",
            "--leaderboard",
            str(_sample_leaderboard_csv(tmp_path)),
            "--param-space",
            str(_sample_param_space(tmp_path)),
            "--output-root",
            str(output_root),
            "--strategies",
            "random,hybrid_goa",
            "--max-candidates",
            "6",
            "--seeds",
            "1",
            "--top-k",
            "3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    summary = json.loads((output_root / "goa_strategy_benchmark_summary.json").read_text(encoding="utf-8"))
    assert set(summary["strategies"]) == {"random", "hybrid_goa"}
    assert summary["engineering_validity"] == "simulation_only"
