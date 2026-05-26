import json
from pathlib import Path

import pandas as pd

from goa_eval.optimizer import (
    load_param_space,
    load_parameter_semantics,
    propose_candidates,
    write_candidate_outputs,
)


def test_propose_candidates_uses_semantic_tags_before_parameter_names():
    param_space = load_param_space(Path("config/parameter_semantics.yaml"))
    semantics = load_parameter_semantics(Path("config/parameter_semantics.yaml"))
    recommendations = [
        {
            "recommendation_id": "ota_gain_review",
            "topology_profile": "ota_general",
            "trigger_metric": "dc_gain_db",
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        }
    ]

    candidates = propose_candidates(
        param_space,
        recommendations,
        profile_file=Path("config/circuit_profiles.yaml"),
        parameter_semantics=semantics,
    )

    grouped = [candidate for candidate in candidates if candidate.get("parameter_group") == "input_pair"]
    assert grouped
    assert all(candidate["must_resimulate"] is True for candidate in grouped)
    assert all(candidate["requires_user_confirmation"] is True for candidate in grouped)
    assert all("input_pair_width" in candidate["semantic_tags"] for candidate in grouped)
    assert all("m1_width" in candidate["changed_parameters"] and "m2_width" in candidate["changed_parameters"] for candidate in grouped)


def test_write_candidate_outputs_includes_semantic_audit_columns(tmp_path):
    candidates = [
        {
            "candidate_id": "cand_001",
            "priority": 92,
            "parameter": "m1_width;m2_width",
            "parameter_group": "input_pair",
            "direction": "increase",
            "candidate_value": "1.2um",
            "candidate_unit": "um",
            "source_recommendation": "ota_gain_review",
            "trigger_metric": "dc_gain_db",
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "strategy": "rule",
            "candidate_kind": "parameter_group",
            "changed_parameters": "m1_width;m2_width",
            "parameters_json": {"m1_width": "1.2um", "m2_width": "1.2um"},
            "search_score": 92,
            "rationale": "semantic candidate",
            "semantic_tags": "input_pair_width;gm_control",
            "affected_metrics": "dc_gain_db;unity_gain_hz",
            "risk_tags": "area;parasitic_capacitance;mismatch",
            "risk_level": "medium",
            "expected_tradeoff": "May improve gain but increase capacitance.",
            "requires_user_confirmation": True,
            "must_resimulate": True,
            "source_metric": "dc_gain_db",
            "source_rule": "ota_general.candidate_rules.dc_gain_db[0]",
            "ai_review_status": "not_reviewed",
            "provenance": {"profile": "ota_general"},
        }
    ]
    csv_path = tmp_path / "next_candidates.csv"
    md_path = tmp_path / "next_candidates.md"

    write_candidate_outputs(candidates, csv_path=csv_path, markdown_path=md_path)

    table = pd.read_csv(csv_path)
    assert {
        "parameter_group",
        "semantic_tags",
        "affected_metrics",
        "risk_tags",
        "risk_level",
        "expected_tradeoff",
        "requires_user_confirmation",
        "must_resimulate",
        "source_metric",
        "source_rule",
        "ai_review_status",
        "provenance",
    } <= set(table.columns)
    assert json.loads(table.loc[0, "provenance"]) == {"profile": "ota_general"}
    assert "must_resimulate" in md_path.read_text(encoding="utf-8")
