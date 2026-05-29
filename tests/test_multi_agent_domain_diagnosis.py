from goa_eval.multi_agent.agents.goa_agent import run_goa_agent
from goa_eval.multi_agent.agents.sky130_agent import run_sky130_agent


def _state() -> dict:
    return {
        "inputs": {},
        "metrics_summary": {
            "worst_stage": {"stage": 3, "node": "o3", "FalseTrigger": True},
            "metric_stats": {
                "OverlapRatio": {"max": 0.31},
                "Ripple": {"max": 0.15},
                "VoltageLoss": {"max": 0.12},
                "FalseTriggerCount": {"max": 1},
                "Delay": {"mean": 1.4e-9},
                "RiseTime": {"mean": 2.4e-10},
                "FallTime": {"mean": 2.7e-10},
            },
        },
        "score_summary": {
            "hard_constraint_passed": False,
            "hard_constraint_failures": ["Max_overlap_ratio above target"],
        },
        "leaderboard_summary": {
            "best_candidate": {
                "candidate_id": "sky_cand_001",
                "overall_score": 0.82,
                "load_cap": 1e-12,
                "drive_resistance": 1000,
            }
        },
        "candidate_summary": {"candidate_count": 1, "risk_summary": {"issues": []}},
        "trace_records": [],
    }


def test_goa_agent_writes_goa_specific_diagnosis():
    state = run_goa_agent(_state())

    diagnosis = state["domain_diagnosis"]

    assert diagnosis["domain"] == "GOA/8T1C"
    assert "cascade_stage_risk" in diagnosis
    assert "voltage_loss" in diagnosis
    assert "false_trigger" in diagnosis
    assert "sky130_timing" not in diagnosis


def test_goa_agent_reads_goa_benchmark_analysis_metrics(tmp_path):
    analysis_path = tmp_path / "analysis_metrics.json"
    analysis_path.write_text(
        """
{
  "topology_profile": "goa_8k_lcd_reference",
  "goa_benchmark_metrics": {
    "benchmark_scope": "literature_reference",
    "fall_time_s": 8.2e-7,
    "reference_tfall_s": 9.7e-7,
    "false_trigger_count": 0,
    "max_overlap_ratio": 0.33
  },
  "not_evaluable_metrics": {
    "area_proxy": "missing device/layout proxy source in current parameters/artifacts"
  }
}
""".strip(),
        encoding="utf-8",
    )
    state = _state()
    state["inputs"]["analysis_metrics"] = str(analysis_path)

    state = run_goa_agent(state)

    diagnosis = state["domain_diagnosis"]
    assert diagnosis["goa_benchmark"]["benchmark_scope"] == "literature_reference"
    assert diagnosis["goa_benchmark"]["fall_time_s"] == 8.2e-7
    assert diagnosis["goa_benchmark"]["reference_tfall_s"] == 9.7e-7
    assert diagnosis["analysis_metrics"]["topology_profile"] == "goa_8k_lcd_reference"


def test_sky130_agent_writes_sky130_specific_diagnosis():
    state = run_sky130_agent(_state())

    diagnosis = state["domain_diagnosis"]

    assert diagnosis["domain"] == "SKY130"
    assert "sky130_timing" in diagnosis
    assert "parameter_focus" in diagnosis
    assert "hard_constraints" in diagnosis
    assert "cascade_stage_risk" not in diagnosis
