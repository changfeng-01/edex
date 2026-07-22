from goa_eval.multi_agent.router import route_task


def test_router_selects_goa_agent():
    decision = route_task("goa_eda_optimization", "goa_8t1c_720", {})
    assert decision["selected_domain_agent"] == "GOAAgent"


def test_router_rejects_retired_sky130_profile():
    decision = route_task("sky130_eda_optimization", "sky130_inverter_chain", {})
    assert decision["selected_domain_agent"] == "unsupported"
    assert decision["handoff_to"] == "CriticAgent"


def test_router_selects_generic_waveform_agent_from_inputs():
    decision = route_task("evaluation", "", {"real_metrics": "metrics.csv"})
    assert decision["selected_domain_agent"] == "GenericWaveformAgent"


def test_router_selects_netlist_agent():
    decision = route_task("netlist_inspection", "generic_netlist", {"netlist": "a.sp"})
    assert decision["selected_domain_agent"] == "NetlistAgent"


def test_router_returns_unsupported_for_insufficient_inputs():
    decision = route_task("unknown", "", {})
    assert decision["selected_domain_agent"] == "unsupported"
    assert decision["handoff_to"] == "CriticAgent"
