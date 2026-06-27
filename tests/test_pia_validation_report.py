from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.validation_report import render_validation_report


def _protocol() -> dict:
    return {
        "name": "pia_ca_llso_phase3_validation",
        "primary_outcome": "simulations_to_target",
        "target_score": 80,
        "methods": ["random", "pia_evolve_full"],
        "ablations": ["full", "capm_only"],
        "scenarios": [{"scenario_id": "sample_goa"}],
        "boundary": {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        },
    }


def _run_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "sample_goa",
                "method": "pia_evolve_full",
                "ablation": "full",
                "seed": 11,
                "budget": 8,
                "target_hit": True,
                "best_score_final": 88.0,
            }
        ]
    )


def _summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "sample_goa",
                "method": "pia_evolve_full",
                "ablation": "full",
                "budget": 8,
                "target_hit_rate": 1.0,
                "best_score_mean": 88.0,
                "simulations_to_target_mean": 4.0,
                "boundary_audit_pass_rate": 1.0,
            }
        ]
    )


def test_validation_report_includes_primary_outcome() -> None:
    report = render_validation_report(_protocol(), _run_frame(), _summary_frame(), pd.DataFrame())

    assert "Primary outcome" in report
    assert "simulations_to_target" in report


def test_validation_report_includes_ablation_table() -> None:
    report = render_validation_report(_protocol(), _run_frame(), _summary_frame(), pd.DataFrame())

    assert "Ablations" in report
    assert "capm_only" in report


def test_validation_report_includes_boundary_statement() -> None:
    report = render_validation_report(_protocol(), _run_frame(), _summary_frame(), pd.DataFrame())

    assert "engineering_validity = simulation_only" in report
    assert "These results are simulation-only evidence, not physical validation." in report


def test_validation_report_does_not_overclaim_physical_validation() -> None:
    report = render_validation_report(_protocol(), _run_frame(), _summary_frame(), pd.DataFrame())
    lower = report.lower()

    assert "validated in silicon" not in lower
    assert "validated on hardware" not in lower
    assert "physical validation complete" not in lower
