from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .contracts import CanonicalAction, DecodedAction


def decode_action(
    action: CanonicalAction,
    domain_config: Mapping[str, Any],
    row: Mapping[str, Any],
) -> DecodedAction:
    key = f"{action.role}.{action.parameter}"
    role_map = domain_config.get("role_parameter_map", {})
    column = role_map.get(key) if isinstance(role_map, Mapping) else None
    if not isinstance(column, str) or column not in row:
        return DecodedAction(str(column or ""), float("nan"), float("nan"), False, "missing_mapping")
    current = float(row[column])
    if action.operation == "log_scale":
        proposed = current * math.exp(float(action.magnitude))
    elif action.operation == "add":
        proposed = current + float(action.magnitude)
    elif action.operation == "set":
        proposed = float(action.magnitude)
    else:
        return DecodedAction(column, current, current, False, "unsupported_operation")
    bounds = domain_config.get("bounds", {})
    limits = bounds.get(column) if isinstance(bounds, Mapping) else None
    value = proposed
    if isinstance(limits, (list, tuple)) and len(limits) == 2:
        value = min(max(proposed, float(limits[0])), float(limits[1]))
    return DecodedAction(column, float(value), float(proposed), not math.isclose(value, proposed), "ok")
