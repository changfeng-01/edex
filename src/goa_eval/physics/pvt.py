from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PVTScenario:
    corner: str
    temperature_c: float
    supply_v: float
    kind: str = "deterministic_corner"
    probability: float | None = None


@dataclass(frozen=True)
class PVTScenarioCatalog:
    deterministic: tuple[PVTScenario, ...]
    statistical: tuple[PVTScenario, ...]
    deterministic_probability: None = None


def classify_pvt_scenarios(scenarios: Iterable[PVTScenario]) -> PVTScenarioCatalog:
    deterministic: list[PVTScenario] = []
    statistical: list[PVTScenario] = []
    seen: set[tuple[str, float, float, str]] = set()
    for scenario in scenarios:
        key = (scenario.corner, float(scenario.temperature_c), float(scenario.supply_v), scenario.kind)
        if key in seen:
            continue
        seen.add(key)
        if scenario.kind == "statistical_sample":
            if scenario.probability is None or not 0.0 <= scenario.probability <= 1.0:
                raise ValueError("statistical PVT samples require probability in [0, 1]")
            statistical.append(scenario)
        elif scenario.kind == "deterministic_corner":
            if scenario.probability is not None:
                raise ValueError("deterministic corners cannot carry probability")
            deterministic.append(scenario)
        else:
            raise ValueError(f"unsupported PVT scenario kind: {scenario.kind}")
    return PVTScenarioCatalog(tuple(deterministic), tuple(statistical))
