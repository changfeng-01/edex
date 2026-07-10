from __future__ import annotations

import math
from typing import Any

import pandas as pd


TRUE_VALUES = {"true", "1", "yes"}
FALSE_VALUES = {"false", "0", "no"}


def strict_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        raise ValueError(f"{field} must be a boolean value")
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise ValueError(f"{field} must be one of true/false/1/0/yes/no")
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"{field} must be one of true/false/1/0/yes/no")


def finite_float(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result
