from __future__ import annotations


def test_selector_reexports_extracted_weight_constants() -> None:
    from goa_eval.pia_ca_llso import selector, selector_weights

    assert selector.CAPM_ACQUISITION_WEIGHTS is selector_weights.CAPM_ACQUISITION_WEIGHTS
    assert selector.LITERATURE_ENSEMBLE_WEIGHTS is selector_weights.LITERATURE_ENSEMBLE_WEIGHTS


def test_multi_round_facade_reexports_decision_functions() -> None:
    from goa_eval import multi_round_decisions, multi_round_optimizer

    assert multi_round_optimizer.target_metric_status is multi_round_decisions.target_metric_status
    assert multi_round_optimizer.should_stop_optimization is multi_round_decisions.should_stop_optimization


def test_goa_hybrid_facade_reexports_candidate_allocation() -> None:
    from goa_eval import goa_hybrid_candidates, goa_hybrid_optimizer

    assert goa_hybrid_optimizer.goa_candidate_counts is goa_hybrid_candidates.candidate_counts
    assert goa_hybrid_optimizer.goa_candidate_counts(5, {"surrogate": 0.5, "repair": 0.3, "exploration": 0.2}) == {
        "surrogate": 3,
        "repair": 1,
        "exploration": 1,
    }
