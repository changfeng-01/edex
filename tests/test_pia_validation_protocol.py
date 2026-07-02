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
    assert protocol["validation_profile"] == "formal"
    assert protocol["budgets"] == [10, 20, 50, 100, 200]
    assert len(protocol["seeds"]) == 20
    assert "pia_physics_distance" in protocol["methods"]
    assert "literature_ensemble_hybrid" in protocol["methods"]
    assert "sklearn_surrogate_baseline" in protocol["methods"]
    assert "paper_ca_llso" in protocol["methods"]
    assert "pia_evolve_full" in protocol["methods"]
    assert "active_uncertainty_diversity" in protocol["methods"]
    assert "active_influence_on_demand" in protocol["methods"]
    assert "no_capm_barrier" in protocol["ablations"]
    assert "no_influence_graph" in protocol["ablations"]
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
            "pia_physics_distance",
            "pia_capm_distance",
            "adaptive_pia_capm",
            "classifier_level_hybrid",
            "active_uncertainty_diversity",
            "active_influence_on_demand",
            "literature_ensemble_hybrid",
            "sklearn_surrogate_baseline",
            "pia_evolve_full",
        ],
        "ablations": [
            "full",
            "no_classifier",
            "no_adaptive_capm",
            "no_constraint_repair",
            "no_llso_offspring",
            "no_evaluation_scheduler",
            "no_influence_graph",
            "no_on_demand_constraint",
            "no_transfer_trust",
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

    assert len(specs) == 440
    assert specs[0].scenario_id == "sample_goa"
    assert specs[0].target_score == 80


def test_validation_protocol_preserves_boundary_labels() -> None:
    protocol = load_validation_protocol(Path("config/pia_ca_llso_validation_protocol.yaml"))

    assert protocol["boundary"]["data_source"] == "real_simulation_csv"
    assert protocol["boundary"]["engineering_validity"] == "simulation_only"
    assert protocol["boundary"]["must_resimulate"] is True
