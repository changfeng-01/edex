from pathlib import Path

from goa_eval.multi_agent.report_writer import write_decision_report


def test_decision_report_contains_required_evidence_sections(tmp_path):
    state = {
        "task_name": "sky130_multi_agent_mvp",
        "task_type": "sky130_eda_optimization",
        "profile": "sky130_inverter_chain",
        "objectives": {"primary": "pass_hard_constraints"},
        "selected_domain_agent": "SKY130Agent",
        "routing_reason": "profile or task_type indicates SKY130 evaluation",
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "leaderboard_summary": {"best_candidate": {"candidate_id": "sky_cand_001", "overall_score": 0.82}},
        "candidate_summary": {
            "candidate_count": 1,
            "candidate_summary": [{"candidate_id": "next_001", "source_recommendation": "ripple_hold_window_review"}],
        },
        "domain_diagnosis": {"domain": "SKY130", "sky130_timing": {"Delay": {"mean": 1.2e-9}}},
        "netlist_summary": {"not_implemented_yet": False, "device_count": 4, "integrity_issues": ["netlist missing .END directive"]},
        "warnings": ["bad metric cell count 1 in inspected metrics"],
        "failures": ["hard_constraint_failed: Max_overlap_ratio above target"],
    }
    trace = [
        {"agent_name": "RouterAgent", "tool_name": "inspect_task_inputs", "status": "pass"},
        {"agent_name": "SKY130Agent", "tool_name": "inspect_leaderboard", "status": "pass"},
    ]
    handoff_trace = [
        {"from_agent": "RouterAgent", "to_agent": "SKY130Agent", "reason": "profile match"},
    ]
    critic_report = {
        "verdicts": [
            {"verdict": "reject", "reason": "critic checks completed", "issues": ["hard_constraint_failed"]},
        ],
        "warnings": state["warnings"],
        "failures": state["failures"],
    }
    memory = {"suggested_next_actions": ["replay next_candidates through the existing deterministic simulation flow"]}

    path = write_decision_report(tmp_path, state, memory, trace, handoff_trace, critic_report)
    text = Path(path).read_text(encoding="utf-8")

    for required in [
        "Task Objective",
        "Agent Routing",
        "Tool Calls",
        "best_candidate",
        "Candidate Generation Rationale",
        "Domain Diagnosis",
        "Critic Review",
        "Warnings And Failures",
        "Netlist Review",
        "simulation_only",
    ]:
        assert required in text
