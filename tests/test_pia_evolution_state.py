"""Tests for PIA evolution state schema."""
from __future__ import annotations


def test_generation_state_serializes_boundary_fields() -> None:
    """GenerationState serializes with conservative evidence labels."""
    from goa_eval.pia_ca_llso.evolution_state import GenerationState

    state = GenerationState(
        generation=1,
        history_rows=10,
        offspring_rows=24,
        selected_rows=4,
        imported_result_rows=4,
        best_score=82.5,
        stop_reason=None,
    )

    payload = state.to_dict()

    assert payload["generation"] == 1
    assert payload["history_rows"] == 10
    assert payload["best_score"] == 82.5
    assert payload["data_source"] == "real_simulation_csv"
    assert payload["engineering_validity"] == "simulation_only"


def test_generation_state_with_stop_reason() -> None:
    """GenerationState includes stop reason when provided."""
    from goa_eval.pia_ca_llso.evolution_state import GenerationState

    state = GenerationState(
        generation=3,
        history_rows=30,
        offspring_rows=24,
        selected_rows=4,
        imported_result_rows=4,
        best_score=95.0,
        stop_reason="target_score_reached",
    )

    payload = state.to_dict()
    assert payload["stop_reason"] == "target_score_reached"