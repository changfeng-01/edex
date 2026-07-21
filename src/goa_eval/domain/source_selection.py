from __future__ import annotations

import math
from collections.abc import Mapping

from .contracts import CircuitDomain
from .distance import domain_distance


def source_domain_weights(
    sources: Mapping[str, CircuitDomain],
    target: CircuitDomain,
    *,
    temperature: float = 0.25,
) -> dict[str, float]:
    if not sources:
        return {}
    scale = max(float(temperature), 1.0e-9)
    raw = {name: math.exp(-domain_distance(domain, target).total / scale) for name, domain in sources.items()}
    total = sum(raw.values())
    return (
        {name: value / total for name, value in raw.items()} if total > 0.0 else {name: 1.0 / len(raw) for name in raw}
    )
