from __future__ import annotations

from pathlib import Path

import pytest

from goa_eval.pia_ca_llso.validation_protocol import (
    expand_validation_grid,
    load_validation_protocol,
    validate_protocol,
)


def test_validation_protocol_loads_required_methods_and_ablation_settings() -> None:
    protocol = load_validation_protocol("config/pia_ca_llso_validation_protocol.yaml")

    assert protocol["primary_outcome"] == "simulations_to_target"
    assert "pia_evolve_full" in protocol["methods"]
    assert "active_uncertainty_diversity" in protocol["methods"]
    assert "no_llso_offspring" in protocol["ablations"]


def test_validation_protocol_rejects_missing_primary_outcome() -> None:
    protocol = load_validation_protocol("config/pia_ca_llso_validation_protocol.yaml")
    protocol.pop("primary_outcome")

    with pytest.raises(ValueError, match="primary_outcome"):
        validate_protocol(protocol)


def test_validation_protocol_expands_budget_seed_scenario_grid() -> None:
    protocol = {
        "primary_outcome": "simulations_to_target",
        "target_score": 80,
        "budgets": [8, 20],
        "seeds": [11, 23],
        "methods": [
            "random",
            "ca_llso_raw_distance",
            "pia_capm_distance",
            "adaptive_pia_capm",
            "classifier_level_hybrid",
            "active_uncertainty_diversity",
            "pia_evolve_full",
        ],
        "ablations": [
            "full",
            "no_classifier",
            "no_adaptive_capm",
            "no_constraint_repair",
            "no_llso_offspring",
            "no_evaluation_scheduler",
            "capm_only",
        ],
        "scenarios": [{"scenario_id": "sample_goa"}],
        "boundary": {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        },
    }

    specs = expand_validation_grid(protocol)

    assert len(specs) == 196
    assert specs[0].scenario_id == "sample_goa"
    assert specs[0].target_score == 80


def test_validation_protocol_preserves_boundary_labels() -> None:
    protocol = load_validation_protocol(Path("config/pia_ca_llso_validation_protocol.yaml"))

    assert protocol["boundary"]["data_source"] == "real_simulation_csv"
    assert protocol["boundary"]["engineering_validity"] == "simulation_only"
    assert protocol["boundary"]["must_resimulate"] is True
