import pytest

from goa_eval.product.simulator_registry import (
    AdapterAvailability,
    SimulatorRegistry,
    UnknownSimulatorAdapter,
    build_default_simulator_registry,
)


class ProbeAdapter:
    def __init__(self):
        self.availability_calls = 0
        self.execution_calls = 0

    def availability(self):
        self.availability_calls += 1
        return AdapterAvailability(True, (), ("render", "execute"))

    def build_execution(self, *_args):
        self.execution_calls += 1
        raise AssertionError("availability must not execute")


def test_unknown_and_duplicate_adapters_fail_closed():
    registry = SimulatorRegistry()

    with pytest.raises(UnknownSimulatorAdapter, match="unknown"):
        registry.get("missing")

    registry.register("probe", ProbeAdapter)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("probe", ProbeAdapter)


def test_availability_check_does_not_render_or_execute():
    probe = ProbeAdapter()
    registry = SimulatorRegistry({"probe": lambda: probe})

    availability = registry.availability("probe")

    assert availability.available is True
    assert availability.capabilities == ("render", "execute")
    assert probe.availability_calls == 1
    assert probe.execution_calls == 0


def test_default_registry_exposes_only_supported_offline_adapters():
    registry = build_default_simulator_registry()

    assert registry.names() == ("empyrean_offline",)


def test_unknown_historical_adapter_has_stable_unavailable_probe_without_registration():
    registry = build_default_simulator_registry()

    availability = registry.availability("retired_historical_adapter")

    assert availability.available is False
    assert availability.execution_enabled is False
    assert availability.reasons == ("adapter_unavailable",)
