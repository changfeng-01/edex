from __future__ import annotations

from goa_eval.pia_ca_llso.external_score import compute_real_score, is_external_evaluable
from goa_eval.pia_ca_llso.schema import SimulationRecord


def test_real_score_layers_and_blocks_predicted_only() -> None:
    feasible = SimulationRecord("s1", {}, {"overall_score": 0.85}, "evaluated_feasible", True, 0, 85, "L1", "imported")
    soft_fail = SimulationRecord("s2", {}, {"overall_score": 0.85}, "evaluated_soft_fail", False, 0.25, 85, "L3", "imported")
    sim_failed = SimulationRecord("s3", {}, {}, "sim_failed", False, 1, None, "L4", "imported")
    predicted = SimulationRecord("s4", {}, {}, "predicted_only", False, 0, None, None, "llso")

    assert compute_real_score(feasible, None) == 85
    assert compute_real_score(soft_fail, None) == 15
    assert compute_real_score(sim_failed, None) == 5
    assert not is_external_evaluable(predicted)
