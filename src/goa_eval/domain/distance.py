from __future__ import annotations

import math

from .contracts import CircuitDomain, DomainDistance


def domain_distance(source: CircuitDomain, target: CircuitDomain) -> DomainDistance:
    topology = _categorical_distance(source.topology_family, target.topology_family)
    technology = 0.5 * (
        _categorical_distance(source.technology_family, target.technology_family)
        + _categorical_distance(source.process_family, target.process_family)
    )
    continuous: list[float] = []
    missing = 0
    for left, right in (
        (source.supply_v, target.supply_v),
        (source.clock_period_s, target.clock_period_s),
        (source.load_capacitance_f, target.load_capacitance_f),
    ):
        if left is None or right is None or left <= 0.0 or right <= 0.0:
            missing += 1
            continue
        continuous.append(min(abs(math.log(left / right)) / math.log(10.0), 1.0))
    operating = sum(continuous) / len(continuous) if continuous else 0.0
    source_roles = set(source.role_signature)
    target_roles = set(target.role_signature)
    union = source_roles | target_roles
    role_mismatch = 1.0 - len(source_roles & target_roles) / len(union) if union else 0.0
    missing_fraction = missing / 3.0
    components = (topology, technology, operating, role_mismatch, missing_fraction)
    weights = (0.30, 0.25, 0.25, 0.15, 0.05)
    total = math.sqrt(sum(weight * component**2 for weight, component in zip(weights, components)))
    return DomainDistance(float(total), topology, technology, operating, role_mismatch, missing_fraction)


def _categorical_distance(left: str, right: str) -> float:
    if left == right:
        return 0.0
    if "unknown" in {left.lower(), right.lower()}:
        return 0.5
    return 1.0
