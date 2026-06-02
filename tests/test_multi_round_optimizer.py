import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from goa_eval.multi_round_optimizer import (
    build_adaptive_sweep_config,
    build_strategy_sweep_config,
    composite_objective,
    encode_parameter_points,
    enrich_history_row,
    stable_leaderboard,
    target_metric_status,
    should_stop_optimization,
)


def _base_config() -> dict:
    return {
        "parameters": {
            "m1_width": {"target": "M1.W", "values": ["1u", "2u", "3u"]},
            "load_cap": {"target": "CLOAD.C", "values": ["0.5pF", "1pF", "2pF"]},
        }
    }


def test_build_adaptive_sweep_config_prefers_high_scores_candidates_and_skips_seen(tmp_path: Path):
    history = pd.DataFrame(
        [
            {"status": "evaluated", "overall_score": 60.0, "m1_width": "1u", "load_cap": "0.5pF", "run_dir": "run_a"},
            {"status": "evaluated", "overall_score": 80.0, "m1_width": "2u", "load_cap": "1pF", "run_dir": "run_b"},
            {"status": "failed", "overall_score": None, "m1_width": "3u", "load_cap": "2pF", "run_dir": "run_c"},
        ]
    )
    best_run = tmp_path / "run_b"
    best_run.mkdir()
    pd.DataFrame(
        [
            {
                "candidate_id": "cand_007",
                "parameter": "m1_width",
                "candidate_value": "3u",
                "search_score": 95,
                "trigger_metric": "dc_gain_db",
                "candidate_kind": "single_parameter",
                "parameters_json": json.dumps({"m1_width": "3u"}),
            }
        ]
    ).to_csv(best_run / "next_candidates.csv", index=False)

    result = build_adaptive_sweep_config(
        base_config=_base_config(),
        history=history,
        best_run_dir=best_run,
        max_runs=4,
        seed=11,
        exploration_ratio=0.25,
    )

    points = result["points"]
    assert {"m1_width": "3u", "load_cap": "1pF"} in points
    assert {"m1_width": "2u", "load_cap": "1pF"} not in points
    assert len(points) <= 4
    assert result["stop_reason"] == ""
    assert result["config"]["parameters"]["m1_width"]["target"] == "M1.W"
    metadata = result["config"]["point_metadata"][0]
    assert metadata["candidate_source"] == "next_candidates"
    assert metadata["source_candidate_id"] == "cand_007"
    assert metadata["source_candidate_trigger_metric"] == "dc_gain_db"
    assert metadata["source_candidate_parameters_json"] == json.dumps({"m1_width": "3u"})


def test_stable_leaderboard_adds_rank_status_and_sorts_failures_last():
    history = pd.DataFrame(
        [
            {"status": "failed", "overall_score": None, "run_dir": "run_failed"},
            {"status": "evaluated", "overall_score": None, "run_dir": "run_unknown"},
            {"status": "evaluated", "overall_score": 70.0, "run_dir": "run_low"},
            {"status": "evaluated", "overall_score": 90.0, "run_dir": "run_high"},
        ]
    )

    leaderboard = stable_leaderboard(history)

    assert list(leaderboard["run_dir"]) == ["run_high", "run_low", "run_unknown", "run_failed"]
    assert list(leaderboard["rank_status"]) == ["evaluated", "evaluated", "not_evaluable", "failed"]


def test_stable_leaderboard_prefers_target_overlap_before_overall_score():
    history = pd.DataFrame(
        [
            {
                "status": "evaluated",
                "overall_score": 90.0,
                "target_metric": "Max_overlap_ratio",
                "target_value": 0.22,
                "target_passed": False,
                "run_dir": "high_score_bad_overlap",
            },
            {
                "status": "evaluated",
                "overall_score": 70.0,
                "target_metric": "Max_overlap_ratio",
                "target_value": 0.08,
                "target_passed": True,
                "run_dir": "lower_score_target_pass",
            },
        ]
    )

    leaderboard = stable_leaderboard(history)

    assert list(leaderboard["run_dir"]) == ["lower_score_target_pass", "high_score_bad_overlap"]


def test_target_metric_status_requires_evaluable_overlap_and_threshold():
    passing = {"status": "evaluated", "stage_count": 3, "Max_overlap_ratio": 0.08}
    failing = {"status": "evaluated", "stage_count": 3, "Max_overlap_ratio": 0.18}
    single_node = {"status": "evaluated", "stage_count": 1, "Max_overlap_ratio": 0.0}

    assert target_metric_status(passing, metric="Max_overlap_ratio", threshold=0.1)["target_passed"] is True
    assert target_metric_status(failing, metric="Max_overlap_ratio", threshold=0.1)["target_passed"] is False
    assert target_metric_status(single_node, metric="Max_overlap_ratio", threshold=0.1)["target_status"] == "not_evaluable"


def test_enrich_history_row_reads_score_and_analysis_artifacts(tmp_path: Path):
    run_dir = tmp_path / "run_001"
    run_dir.mkdir()
    (run_dir / "score_summary.json").write_text(
        json.dumps(
            {
                "hard_constraint_failures": ["All_pulses_exist is false", "Seq_pass is false"],
                "profile_score": 72.5,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "analysis_metrics.json").write_text(
        json.dumps(
            {
                "not_evaluable_metrics": {"dc_gain_db": "missing ac file", "static_power_w": "missing op file"},
                "profile_metric_scores": {"frequency_hz": {"score": 91.0}},
            }
        ),
        encoding="utf-8",
    )

    enriched = enrich_history_row({"run_dir": str(run_dir), "overall_score": 88.0})

    assert enriched["hard_constraint_failure_count"] == 2
    assert enriched["not_evaluable_metric_count"] == 2
    assert enriched["profile_score"] == 72.5
    assert enriched["profile_metric_score_mean"] == 91.0


def test_composite_objective_prefers_fewer_hard_failures_before_score():
    weaker_score_but_functional = {
        "overall_score": 70.0,
        "hard_constraint_failure_count": 0,
        "not_evaluable_metric_count": 1,
        "profile_score": 50.0,
    }
    higher_score_with_failures = {
        "overall_score": 88.0,
        "hard_constraint_failure_count": 2,
        "not_evaluable_metric_count": 0,
        "profile_score": 100.0,
    }

    assert composite_objective(weaker_score_but_functional) > composite_objective(higher_score_with_failures)


def test_encode_parameter_points_uses_discrete_value_indices():
    parameters = _base_config()["parameters"]
    points = [
        {"m1_width": "1u", "load_cap": "0.5pF"},
        {"m1_width": "3u", "load_cap": "2pF"},
    ]

    encoded = encode_parameter_points(points, parameters)

    assert encoded.tolist() == [[0.0, 0.0], [2.0, 2.0]]


def test_bayesian_strategy_falls_back_to_diverse_points_for_zero_variance():
    history = pd.DataFrame(
        [
            {"status": "evaluated", "overall_score": 88.0, "m1_width": "1u", "load_cap": "0.5pF", "run_dir": "run_a"},
            {"status": "evaluated", "overall_score": 88.0, "m1_width": "2u", "load_cap": "1pF", "run_dir": "run_b"},
            {"status": "evaluated", "overall_score": 88.0, "m1_width": "3u", "load_cap": "2pF", "run_dir": "run_c"},
        ]
    )

    result = build_strategy_sweep_config(
        base_config=_base_config(),
        history=history,
        best_run_dir=None,
        max_runs=2,
        seed=3,
        exploration_ratio=0.25,
        strategy="bayesian",
    )

    assert len(result["points"]) == 2
    assert result["config"]["optimizer_strategy"] == "bayesian"
    assert {item["candidate_source"] for item in result["config"]["point_metadata"]} == {"diversity_fallback"}
    assert {item["model_status"] for item in result["config"]["point_metadata"]} == {"fallback_zero_variance"}


def test_genetic_strategy_generates_unseen_legal_points():
    history = pd.DataFrame(
        [
            {"status": "evaluated", "overall_score": 60.0, "m1_width": "1u", "load_cap": "0.5pF", "run_dir": "run_a"},
            {"status": "evaluated", "overall_score": 90.0, "m1_width": "2u", "load_cap": "1pF", "run_dir": "run_b"},
        ]
    )

    result = build_strategy_sweep_config(
        base_config=_base_config(),
        history=history,
        best_run_dir=None,
        max_runs=3,
        seed=9,
        exploration_ratio=0.25,
        strategy="genetic",
    )

    legal_values = {name: set(spec["values"]) for name, spec in _base_config()["parameters"].items()}
    seen = {("1u", "0.5pF"), ("2u", "1pF")}
    assert result["points"]
    for point in result["points"]:
        assert tuple(point[name] for name in ["m1_width", "load_cap"]) not in seen
        assert all(point[name] in legal_values[name] for name in legal_values)
    assert {item["optimizer_strategy"] for item in result["config"]["point_metadata"]} == {"genetic"}


def test_surrogate_strategy_prefers_predicted_high_score_region():
    history = pd.DataFrame(
        [
            {"status": "evaluated", "overall_score": 10.0, "m1_width": "1u", "load_cap": "0.5pF", "run_dir": "run_a"},
            {"status": "evaluated", "overall_score": 30.0, "m1_width": "1u", "load_cap": "1pF", "run_dir": "run_b"},
            {"status": "evaluated", "overall_score": 70.0, "m1_width": "2u", "load_cap": "1pF", "run_dir": "run_c"},
            {"status": "evaluated", "overall_score": 90.0, "m1_width": "3u", "load_cap": "1pF", "run_dir": "run_d"},
        ]
    )

    result = build_strategy_sweep_config(
        base_config=_base_config(),
        history=history,
        best_run_dir=None,
        max_runs=1,
        seed=2,
        exploration_ratio=0.25,
        strategy="surrogate",
    )

    assert result["points"][0]["m1_width"] == "3u"
    assert result["config"]["point_metadata"][0]["candidate_source"] == "surrogate_model"


def test_physics_guided_hybrid_uses_physics_prior_candidates_before_fallback():
    history = pd.DataFrame(
        [
            {"status": "evaluated", "overall_score": 70.0, "m1_width": "1u", "load_cap": "1pF", "run_dir": "run_a"},
        ]
    )

    result = build_strategy_sweep_config(
        base_config=_base_config(),
        history=history,
        best_run_dir=None,
        max_runs=2,
        seed=5,
        exploration_ratio=0.25,
        strategy="physics_guided_hybrid",
    )

    metadata = result["config"]["point_metadata"]
    assert result["points"]
    assert {item["candidate_source"] for item in metadata} == {"physics_prior_engine"}
    assert {item["optimizer_strategy"] for item in metadata} == {"physics_guided_hybrid"}
    assert all(item["model_status"] == "physics_prior_engine_v1" for item in metadata)
    assert {"physics_score", "physical_hard_passed", "physics_proxy_json", "physics_violations", "physics_rationale"} <= set(metadata[0])


def test_should_stop_optimization_uses_patience_and_min_improvement():
    rounds = [
        {"round_index": 1, "best_score": 80.0},
        {"round_index": 2, "best_score": 80.1},
    ]

    assert should_stop_optimization(rounds, patience=1, min_improvement=0.5) == "no improvement for 1 round(s)"
    assert should_stop_optimization(rounds, patience=1, min_improvement=0.05) == ""


def test_optimize_rounds_cli_mock_writes_multi_round_outputs(tmp_path: Path):
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")
    sweep_path = tmp_path / "sweep.yaml"
    sweep_path.write_text(
        """
parameters:
  m1_width:
    target: M1.W
    values: ["1u", "2u"]
  load_cap:
    target: CLOAD.C
    values: ["1pF", "2pF"]
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "multi_round"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "optimize-rounds",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--sweep",
            str(sweep_path),
            "--rounds",
            "2",
            "--max-runs-per-round",
            "2",
            "--output-root",
            str(output_root),
            "--strategy",
            "hybrid",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_root / "round_001" / "sky130_sweep_runs.csv").exists()
    assert (output_root / "round_002" / "sky130_sweep_runs.csv").exists()
    assert (output_root / "optimization_history.json").exists()
    assert (output_root / "optimization_leaderboard.csv").exists()
    assert (output_root / "round_summary.csv").exists()
    assert (output_root / "final_param_space.yaml").exists()
    assert (output_root / "best_next_candidates.csv").exists()

    summary = pd.read_csv(output_root / "round_summary.csv")
    leaderboard = pd.read_csv(output_root / "optimization_leaderboard.csv")
    final_space = yaml.safe_load((output_root / "final_param_space.yaml").read_text(encoding="utf-8"))
    assert len(summary) == 2
    assert {"round_index", "best_score", "stop_reason"} <= set(summary.columns)
    assert {
        "round_index",
        "overall_score",
        "run_dir",
        "rank_status",
        "candidate_source",
        "source_candidate_id",
        "source_candidate_trigger_metric",
        "source_candidate_parameters_json",
    } <= set(leaderboard.columns)
    assert leaderboard["candidate_source"].notna().all()
    assert "initial_grid" in set(leaderboard["candidate_source"])
    assert leaderboard["rank_status"].isin(["evaluated", "not_evaluable", "skipped", "failed"]).all()
    assert {"optimizer_strategy", "objective_score", "model_status"} <= set(leaderboard.columns)
    assert "optimizer_strategy" in final_space
    assert "parameters" in final_space


def test_optimize_rounds_cli_mock_records_top_candidate_round_and_target_fields(tmp_path: Path):
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")
    sweep_path = tmp_path / "sweep.yaml"
    sweep_path.write_text(
        """
parameters:
  m1_width:
    target: M1.W
    values: ["1u", "2u", "3u"]
  load_cap:
    target: CLOAD.C
    values: ["1pF", "2pF", "3pF"]
""",
        encoding="utf-8",
    )
    validation_path = tmp_path / "validation.yaml"
    validation_path.write_text(
        """
target:
  metric: Max_overlap_ratio
  threshold: 0.1
candidate_replay:
  top_n: 3
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "candidate_rounds"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "optimize-rounds",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--sweep",
            str(sweep_path),
            "--validation-config",
            str(validation_path),
            "--rounds",
            "2",
            "--max-runs-per-round",
            "3",
            "--output-root",
            str(output_root),
            "--strategy",
            "adaptive",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    leaderboard = pd.read_csv(output_root / "optimization_leaderboard.csv")
    assert {"target_metric", "target_threshold", "target_passed", "target_status"} <= set(leaderboard.columns)
    second_round = leaderboard[leaderboard["round_index"].eq(2)]
    assert not second_round.empty
    assert "next_candidates" in set(second_round["candidate_source"])
    assert len(second_round[second_round["candidate_source"].eq("next_candidates")]) == 3
    assert second_round["source_candidate_id"].notna().any()
    assert set(second_round["target_metric"]) == {"Max_overlap_ratio"}
    assert set(pd.to_numeric(second_round["target_threshold"])) == {0.1}


def _row() -> dict:
    testbench = "\n".join(
        [
            ".title multi-round fixture",
            "VDD vdd 0 DC 1.8",
            "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
            "CLOAD vout 0 1pF",
            "V1 vin 0 pulse(0 1.8 1n 1n 1n 5n 20n)",
            ".tran 1n 40n",
            ".end",
        ]
    )
    return {
        "circuit_id": "multi_round_amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": testbench,
        "testbench_spice": testbench,
        "netlist_json": {
            "ports": [
                {"name": "vout", "role": "output_v"},
                {"name": "vaux", "role": "output_v"},
                {"name": "vthird", "role": "output_v"},
            ]
        },
    }
