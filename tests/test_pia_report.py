"""Tests for PIA report rendering."""
from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.report import render_candidate_report, render_evolution_report


def test_candidate_report_boundary() -> None:
    """Candidate report includes simulation_only and must_resimulate boundary."""
    selected = pd.DataFrame([
        {
            "candidate_id": "c1",
            "selected_rank": 1,
            "candidate_role": "exploit",
            "acquisition_score": 0.85,
            "selection_reason": "top",
        },
    ])
    report_text = render_candidate_report(selected, {"strategy": "test"})
    assert "simulation_only" in report_text
    assert "must_resimulate = true" in report_text


def test_evolution_report_includes_stop_reason_and_boundary() -> None:
    """Evolution report includes stop reason and evidence boundary."""
    summary = {
        "stop_reason": "target_score_reached",
        "best_score": 95.0,
        "generations_run": 3,
        "simulations_used": 12,
        "target_reached": True,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "claim_boundary": "simulation-only evidence, not physical validation",
    }

    report = render_evolution_report(summary)
    assert "target_score_reached" in report
    assert "real_simulation_csv" in report
    assert "simulation_only" in report


def test_evolution_report_lists_generation_artifacts() -> None:
    """Evolution report lists replayable generation artifacts."""
    summary = {
        "stop_reason": "pending_simulation_results",
        "best_score": 81.0,
        "generations_run": 1,
        "simulations_used": 0,
        "target_reached": False,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "claim_boundary": "candidate suggestions require simulation before claims",
        "latest_simulation_batch": "generation_000/simulation_batch.csv",
        "generation_artifacts": [
            "generation_000/offspring_candidates.csv",
            "generation_000/pia_selected_candidates.csv",
            "generation_000/imported_results.csv",
        ],
    }

    report = render_evolution_report(summary)

    assert "generation_000/simulation_batch.csv" in report
    assert "offspring_candidates.csv" in report
    assert "pia_selected_candidates.csv" in report
    assert "imported_results.csv" in report
    assert "must_resimulate = true" in report
