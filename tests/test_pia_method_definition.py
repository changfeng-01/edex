from __future__ import annotations

from pathlib import Path

import yaml

from goa_eval.pia_ca_llso.method_definition import (
    ACQUISITION_SCORE_COLUMN,
    HARD_CONSTRAINT_COLUMN,
    PRIMARY_OUTCOME,
    PRIMARY_SCORE_COLUMN,
    PROFILE_OBJECTIVE_COLUMN,
    build_method_definition,
)
from goa_eval.pia_ca_llso.validation_protocol import BOUNDARY


def test_method_definition_aligns_with_goa_profile_config() -> None:
    config = yaml.safe_load(Path("config/pia_ca_llso_goa_profile.yaml").read_text(encoding="utf-8"))

    definition = build_method_definition(config)

    assert definition.problem_name == "pia_ca_llso_goa_profile"
    assert definition.target_score == 80.0
    assert definition.score_column == config["labeling"]["score_col"] == PRIMARY_SCORE_COLUMN
    assert definition.hard_constraint_column == config["labeling"]["hard_pass_col"] == HARD_CONSTRAINT_COLUMN
    assert definition.parameter_columns == tuple(config["parameter_columns"])


def test_method_definition_preserves_validation_boundary_and_primary_outcome() -> None:
    definition = build_method_definition()

    assert definition.primary_outcome == PRIMARY_OUTCOME == "simulations_to_target"
    assert definition.boundary == BOUNDARY
    assert definition.boundary["data_source"] == "real_simulation_csv"
    assert definition.boundary["engineering_validity"] == "simulation_only"
    assert definition.boundary["must_resimulate"] is True
    assert definition.claim_boundary == "next-run simulation suggestions"


def test_method_definition_separates_score_objective_acquisition_and_validation_layers() -> None:
    definition = build_method_definition()
    layers = definition.objective_layers

    assert layers["simulation_score"]["column"] == PRIMARY_SCORE_COLUMN
    assert layers["profile_objective"]["column"] == PROFILE_OBJECTIVE_COLUMN
    assert layers["hard_constraint"]["column"] == HARD_CONSTRAINT_COLUMN
    assert layers["candidate_acquisition"]["column"] == ACQUISITION_SCORE_COLUMN
    assert layers["validation_outcome"]["column"] == PRIMARY_OUTCOME
    assert "not final validation evidence" in layers["candidate_acquisition"]["meaning"]


def test_method_definition_forbidden_leakage_columns_cover_result_metrics() -> None:
    definition = build_method_definition({"forbidden_leakage_columns": ["delay"]})

    for column in [
        "delay",
        "power",
        "waveform_score",
        PRIMARY_SCORE_COLUMN,
        PROFILE_OBJECTIVE_COLUMN,
        HARD_CONSTRAINT_COLUMN,
    ]:
        assert column in definition.forbidden_leakage_columns


def test_formal_method_document_contains_required_formulas_and_algorithms() -> None:
    document = Path("docs/pia_ca_llso_formal_method_zh.md").read_text(encoding="utf-8")

    required_snippets = [
        "F(x) = (m(x), S(x), H(x))",
        "tau_T = min { t | t <= B, S(x_t) >= T, H(x_t)=1 }",
        "phi: X -> R^d",
        "D_tensor(x,y)",
        "B(phi(x))",
        "D_pair(x,y)",
        "D_geodesic(x,L1)",
        "A_capm(x)",
        "A_hybrid(x)",
        "A_lit(x)",
        "Algorithm 1",
        "Algorithm 2",
        "Algorithm 3",
        "Algorithm 4",
        "data_source = real_simulation_csv",
        "engineering_validity = simulation_only",
        "must_resimulate = true",
    ]
    for snippet in required_snippets:
        assert snippet in document
