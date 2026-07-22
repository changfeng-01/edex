from goa_eval.multi_agent.agent_contracts import get_agent_contracts
from goa_eval.multi_agent.domain_registry import default_domain_agent_registry
from goa_eval.multi_agent.graph_app import _after_evaluation, _domain_route_map
from goa_eval.multi_agent.router import route_task


def test_default_registry_exposes_instrumentation_agent_template() -> None:
    registry = default_domain_agent_registry()

    spec = registry.get("InstrumentationAmplifierAgent")

    assert spec.node_name == "instrumentation_amplifier"
    assert spec.physics_adapter_name == "instrumentation_amplifier_three_opamp_v1"
    assert "instrumentation_amplifier_three_opamp_compensated_v1" in spec.profiles
    assert {"three_opamp_7r", "instrumentation_amplifier", "three_opamp_lm324"} <= set(
        spec.aliases
    )


def test_registry_router_uses_profile_alias_before_input_fallback() -> None:
    decision = route_task("evaluation", "three_opamp_7r", {"real_metrics": "metrics.csv"})

    assert decision["selected_domain_agent"] == "InstrumentationAmplifierAgent"
    assert "profile" in decision["reason"]


def test_registry_preserves_existing_non_retired_routes() -> None:
    assert route_task("goa_eda_optimization", "goa_8t1c_720", {})[
        "selected_domain_agent"
    ] == "GOAAgent"
    assert route_task("evaluation", "", {"real_metrics": "metrics.csv"})[
        "selected_domain_agent"
    ] == "GenericWaveformAgent"
    assert route_task("netlist_inspection", "generic_netlist", {"netlist": "a.sp"})[
        "selected_domain_agent"
    ] == "NetlistAgent"


def test_agent_contracts_are_merged_from_domain_registry() -> None:
    contracts = get_agent_contracts()

    contract = contracts["InstrumentationAmplifierAgent"]
    assert "instrumentation_agent_diagnosis" in contract.output_schema
    assert "TransferCoordinatorAgent" in contract.handoff_policy["next"]


def test_graph_domain_route_map_is_derived_from_registry() -> None:
    route_map = _domain_route_map(default_domain_agent_registry())

    assert route_map["InstrumentationAmplifierAgent"] == "instrumentation_amplifier"
    assert route_map["GOAAgent"] == "goa"
    assert route_map["unsupported"] == "critic_after_domain"


def test_graph_inserts_transfer_coordinator_only_when_source_packet_exists() -> None:
    assert _after_evaluation({"inputs": {}}) == "optimization"
    assert (
        _after_evaluation({"inputs": {"source_effect_packet": {"schema_version": "v1"}}})
        == "transfer_coordinator"
    )
