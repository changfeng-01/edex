from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


class UnknownSimulatorAdapter(KeyError):
    pass


@dataclass(frozen=True)
class AdapterAvailability:
    available: bool
    reasons: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    execution_enabled: bool = True


AdapterFactory = Callable[[], Any]


class SimulatorRegistry:
    """Allow-list of trusted simulator adapter factories."""

    def __init__(self, factories: Mapping[str, AdapterFactory] | None = None) -> None:
        self._factories: dict[str, AdapterFactory] = {}
        for name, factory in (factories or {}).items():
            self.register(name, factory)

    def register(self, name: str, factory: AdapterFactory) -> None:
        key = self._normalize(name)
        if key in self._factories:
            raise ValueError(f"simulator adapter is already registered: {key}")
        if not callable(factory):
            raise TypeError("simulator adapter factory must be callable")
        self._factories[key] = factory

    def get(self, name: str) -> Any:
        key = self._normalize(name)
        factory = self._factories.get(key)
        if factory is None:
            raise UnknownSimulatorAdapter(f"unknown simulator adapter: {key}")
        return factory()

    def availability(self, name: str) -> AdapterAvailability:
        try:
            adapter = self.get(name)
        except UnknownSimulatorAdapter:
            return AdapterAvailability(
                False,
                ("adapter_unavailable",),
                (),
                execution_enabled=False,
            )
        probe = adapter.availability()
        if not isinstance(probe, AdapterAvailability):
            raise TypeError(f"adapter {name!r} returned an invalid availability result")
        return probe

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    @staticmethod
    def _normalize(name: str) -> str:
        value = str(name).strip().lower()
        if not value or not value.replace("_", "").isalnum():
            raise ValueError(f"invalid simulator adapter name: {name!r}")
        return value


def build_default_simulator_registry() -> SimulatorRegistry:
    from goa_eval.product.adapters.empyrean_offline import EmpyreanOfflineAdapter

    return SimulatorRegistry({"empyrean_offline": EmpyreanOfflineAdapter})
