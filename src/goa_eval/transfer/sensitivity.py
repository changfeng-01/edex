from __future__ import annotations

import math
from collections.abc import Callable, Mapping


def estimate_local_elasticities(
    response: Callable[[dict[str, float]], float],
    point: Mapping[str, float],
    *,
    relative_step: float = 1.0e-3,
) -> dict[str, float]:
    """Estimate d(log y)/d(log x) with a symmetric multiplicative step."""

    step = max(float(relative_step), 1.0e-8)
    output: dict[str, float] = {}
    for name, value in point.items():
        if value <= 0.0:
            output[name] = float("nan")
            continue
        plus = dict(point)
        minus = dict(point)
        plus[name] = value * math.exp(step)
        minus[name] = value * math.exp(-step)
        upper = float(response(plus))
        lower = float(response(minus))
        if upper <= 0.0 or lower <= 0.0:
            output[name] = float("nan")
        else:
            output[name] = (math.log(upper) - math.log(lower)) / (2.0 * step)
    return output
