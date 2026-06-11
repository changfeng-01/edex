from __future__ import annotations

from goa_eval.pia_ca_llso.schema import Candidate, ParameterSpec, ProblemSpec, SimulationRecord


def test_schema_round_trips_between_dicts() -> None:
    spec = ProblemSpec(
        problem_name="goa_demo",
        parameter_specs=[ParameterSpec(name="TFT_pullup_W", lower=10, upper=1000, unit="um", group="pullup")],
        objective_names=["overall_score"],
        constraint_specs={"min_score": 80},
        physics_feature_config={"profile": "goa"},
        score_config={"score_col": "overall_score"},
        target_score=80,
        metadata={"data_source": "real_simulation_csv", "engineering_validity": "simulation_only"},
    )
    record = SimulationRecord(
        sample_id="s1",
        params={"TFT_pullup_W": 200},
        metrics={"overall_score": 92},
        status="evaluated_feasible",
        hard_pass=True,
        constraint_violation=0,
        score=92,
        level_label="L1",
        source="imported",
    )
    candidate = Candidate(candidate_id="c1", params={"TFT_pullup_W": 240}, source="imported", p_l1=0.8)

    assert ProblemSpec.from_dict(spec.to_dict()).metadata["data_source"] == "real_simulation_csv"
    assert SimulationRecord.from_dict(record.to_dict()).level_label == "L1"
    assert Candidate.from_dict(candidate.to_dict()).p_l1 == 0.8
