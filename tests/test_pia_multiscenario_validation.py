from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from goa_eval.cli import main
from goa_eval.pia_ca_llso.case_pack import case_pack_to_protocol, load_case_pack
from goa_eval.pia_ca_llso.multi_scenario_validation import (
    _multi_scenario_win_rates,
    materialize_validation_scenario,
    run_multi_scenario_validation,
)


def _write_direct_scenario(tmp_path):
    history = pd.DataFrame(
        [
            {"sample_id": "h1", "candidate_id": "c1", "level_label": "L1", "overall_score": 92.0, "hard_constraint_passed": True, "C_boot": 2.2, "C_load": 1.0, "VGH": 15.0, "VGL": -5.0, "Vth_shift": 1.2},
            {"sample_id": "h2", "candidate_id": "c2", "level_label": "L2", "overall_score": 84.0, "hard_constraint_passed": True, "C_boot": 1.7, "C_load": 1.1, "VGH": 15.0, "VGL": -5.0, "Vth_shift": 1.5},
            {"sample_id": "h3", "candidate_id": "c3", "level_label": "L4", "overall_score": 25.0, "hard_constraint_passed": False, "C_boot": 0.8, "C_load": 1.8, "VGH": 13.0, "VGL": -4.0, "Vth_shift": 3.0},
            {"sample_id": "h4", "candidate_id": "c4", "level_label": "L3", "overall_score": 55.0, "hard_constraint_passed": False, "C_boot": 1.1, "C_load": 1.5, "VGH": 14.0, "VGL": -5.0, "Vth_shift": 2.0},
        ]
    )
    candidates = pd.DataFrame(
        [
            {"candidate_id": "c1", "C_boot": 2.2, "C_load": 1.0, "VGH": 15.0, "VGL": -5.0, "Vth_shift": 1.2},
            {"candidate_id": "c2", "C_boot": 1.7, "C_load": 1.1, "VGH": 15.0, "VGL": -5.0, "Vth_shift": 1.5},
            {"candidate_id": "c3", "C_boot": 0.8, "C_load": 1.8, "VGH": 13.0, "VGL": -4.0, "Vth_shift": 3.0},
            {"candidate_id": "c4", "C_boot": 1.1, "C_load": 1.5, "VGH": 14.0, "VGL": -5.0, "Vth_shift": 2.0},
        ]
    )
    history_path = tmp_path / "direct_history.csv"
    candidate_path = tmp_path / "direct_candidates.csv"
    history.to_csv(history_path, index=False)
    candidates.to_csv(candidate_path, index=False)
    return history_path, candidate_path


def _write_720_action_scenario(tmp_path):
    history = pd.DataFrame(
        [
            {
                "run_id": "real_1",
                "overall_score": 53.0,
                "hard_constraint_passed": False,
                "capacitance": 8e-13,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "cand_001",
                "parameter": "capacitance",
                "candidate_value": 1.2e-12,
                "parameters_json": json.dumps({"capacitance": 1.2e-12}),
                "must_resimulate": True,
            },
            {
                "candidate_id": "cand_002",
                "parameter": "capacitance",
                "candidate_value": 1.0e-12,
                "parameters_json": json.dumps({"capacitance": 1.0e-12}),
                "must_resimulate": True,
            },
        ]
    )
    history_path = tmp_path / "action_history.csv"
    candidate_path = tmp_path / "action_candidates.csv"
    history.to_csv(history_path, index=False)
    candidates.to_csv(candidate_path, index=False)
    return history_path, candidate_path


def _protocol(tmp_path, direct_history, direct_candidates, action_history, action_candidates):
    return {
        "target_score": 80,
        "top_k": 2,
        "seeds": [1, 2],
        "methods": ["pia_full", "pia_no_repair", "paper_adaptive_constraint_eval"],
        "scenarios": [
            {
                "scenario_id": "direct_evidence",
                "history_csv": str(direct_history),
                "candidate_csv": str(direct_candidates),
                "candidate_evidence_source": "history_by_candidate_id",
            },
            {
                "scenario_id": "action_missing",
                "history_csv": str(action_history),
                "candidate_csv": str(action_candidates),
                "candidate_format": "action_recommendations",
            },
        ],
    }


def test_materializes_720_action_candidate_pool_without_claiming_evidence(tmp_path) -> None:
    history_path, candidate_path = _write_720_action_scenario(tmp_path)

    scenario = materialize_validation_scenario(
        {"scenario_id": "action_missing", "history_csv": str(history_path), "candidate_csv": str(candidate_path), "candidate_format": "action_recommendations"}
    )

    assert scenario.scenario_id == "action_missing"
    assert scenario.evidence_available is False
    assert scenario.sparse_history is True
    assert "sample_id" in scenario.history.columns
    assert "capacitance" in scenario.candidates.columns
    assert scenario.candidates["must_resimulate"].eq(True).all()


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


def test_multi_scenario_validate_runs_all_scenarios_and_seeds(tmp_path) -> None:
    direct_history, direct_candidates = _write_direct_scenario(tmp_path)
    action_history, action_candidates = _write_720_action_scenario(tmp_path)

    result = run_multi_scenario_validation(_protocol(tmp_path, direct_history, direct_candidates, action_history, action_candidates), tmp_path / "out")
    runs = pd.read_csv(tmp_path / "out" / "multi_scenario_runs.csv")

    assert result["scenario_count"] == 2
    assert set(runs["scenario_id"]) == {"direct_evidence", "action_missing"}
    assert set(runs["seed"]) == {1, 2}
    assert {"pia_full", "pia_no_repair", "paper_adaptive_constraint_eval"} == set(runs["method"])
    assert runs["data_source"].eq("real_simulation_csv").all()
    assert runs["engineering_validity"].eq("simulation_only").all()
    assert runs["must_resimulate"].eq(True).all()


def test_pia_no_repair_disables_constraint_ledger_repair_candidates(tmp_path) -> None:
    direct_history, direct_candidates = _write_direct_scenario(tmp_path)
    action_history, action_candidates = _write_720_action_scenario(tmp_path)

    run_multi_scenario_validation(_protocol(tmp_path, direct_history, direct_candidates, action_history, action_candidates), tmp_path / "out")
    runs = pd.read_csv(tmp_path / "out" / "multi_scenario_runs.csv")
    no_repair = runs[runs["method"] == "pia_no_repair"]

    assert not no_repair.get("source", pd.Series(dtype=str)).fillna("").eq("constraint_ledger_repair").any()


def test_same_budget_is_enforced_for_all_methods(tmp_path) -> None:
    direct_history, direct_candidates = _write_direct_scenario(tmp_path)
    action_history, action_candidates = _write_720_action_scenario(tmp_path)

    run_multi_scenario_validation(_protocol(tmp_path, direct_history, direct_candidates, action_history, action_candidates), tmp_path / "out")
    summary = pd.read_csv(tmp_path / "out" / "multi_scenario_summary.csv")

    assert summary["budget"].nunique() == 1
    assert summary["budget"].iloc[0] == 2


def test_evidence_missing_scenarios_are_excluded_from_statistical_claims(tmp_path) -> None:
    direct_history, direct_candidates = _write_direct_scenario(tmp_path)
    action_history, action_candidates = _write_720_action_scenario(tmp_path)

    run_multi_scenario_validation(_protocol(tmp_path, direct_history, direct_candidates, action_history, action_candidates), tmp_path / "out")
    summary = pd.read_csv(tmp_path / "out" / "multi_scenario_summary.csv")
    action_rows = summary[summary["scenario_id"] == "action_missing"]
    claim_rows = summary[summary["included_in_statistical_claim"] == True]

    assert action_rows["included_in_statistical_claim"].eq(False).all()
    assert set(claim_rows["scenario_id"]) == {"direct_evidence"}


def test_multi_scenario_summary_reports_mean_std_win_rate_and_majority(tmp_path) -> None:
    direct_history, direct_candidates = _write_direct_scenario(tmp_path)
    action_history, action_candidates = _write_720_action_scenario(tmp_path)

    run_multi_scenario_validation(_protocol(tmp_path, direct_history, direct_candidates, action_history, action_candidates), tmp_path / "out")

    summary = pd.read_csv(tmp_path / "out" / "multi_scenario_summary.csv")
    win_rates = pd.read_csv(tmp_path / "out" / "multi_scenario_win_rates.csv")
    majority = pd.read_csv(tmp_path / "out" / "majority_vote_summary.csv")
    ablation = pd.read_csv(tmp_path / "out" / "no_repair_ablation_summary.csv")

    for column in ["target_hit_rate_mean", "target_hit_rate_std", "convergence_auc_mean", "convergence_auc_std"]:
        assert column in summary.columns
    assert set(win_rates["method"]) == {"pia_full", "pia_no_repair", "paper_adaptive_constraint_eval"}
    assert "majority_scenario_win_rate" in majority.columns
    assert set(ablation["comparison"]) == {"pia_full_vs_pia_no_repair"}


def test_cli_pia_validate_multiscenario_smoke(tmp_path) -> None:
    direct_history, direct_candidates = _write_direct_scenario(tmp_path)
    action_history, action_candidates = _write_720_action_scenario(tmp_path)
    protocol_path = tmp_path / "protocol.yaml"
    protocol_path.write_text(yaml.safe_dump(_protocol(tmp_path, direct_history, direct_candidates, action_history, action_candidates)), encoding="utf-8")
    output_dir = tmp_path / "cli_out"

    assert main(
        [
            "pia-validate",
            "--protocol",
            str(protocol_path),
            "--output-dir",
            str(output_dir),
            "--seeds",
            "1,2",
            "--multi-scenario",
        ]
    ) == 0

    assert (output_dir / "multi_scenario_validation_report.md").exists()


def test_multi_scenario_win_rates_do_not_award_exact_ties() -> None:
    per_seed = pd.DataFrame(
        [
            {"scenario_id": "s1", "seed": 1, "method": "pia_full", "target_hit_rate": 0.0, "convergence_auc": 0.0, "included_in_statistical_claim": True},
            {"scenario_id": "s1", "seed": 1, "method": "pia_no_repair", "target_hit_rate": 0.0, "convergence_auc": 0.0, "included_in_statistical_claim": True},
            {"scenario_id": "s1", "seed": 1, "method": "paper_adaptive_constraint_eval", "target_hit_rate": 0.0, "convergence_auc": 0.0, "included_in_statistical_claim": True},
        ]
    )

    win_rates = _multi_scenario_win_rates(per_seed)

    assert win_rates["scenario_wins"].sum() == 0
