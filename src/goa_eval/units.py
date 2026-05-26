from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation


UNIT_FACTORS = {
    "": ("", 1.0),
    "V": ("V", 1.0),
    "mV": ("V", 1e-3),
    "A": ("A", 1.0),
    "mA": ("A", 1e-3),
    "uA": ("A", 1e-6),
    "nA": ("A", 1e-9),
    "W": ("W", 1.0),
    "mW": ("W", 1e-3),
    "uW": ("W", 1e-6),
    "Hz": ("Hz", 1.0),
    "kHz": ("Hz", 1e3),
    "MHz": ("Hz", 1e6),
    "GHz": ("Hz", 1e9),
    "deg": ("deg", 1.0),
    "s": ("s", 1.0),
    "ms": ("s", 1e-3),
    "us": ("s", 1e-6),
    "ns": ("s", 1e-9),
    "F": ("F", 1.0),
    "mF": ("F", 1e-3),
    "uF": ("F", 1e-6),
    "nF": ("F", 1e-9),
    "pF": ("F", 1e-12),
    "m": ("m", 1.0),
    "um": ("um", 1.0),
    "nm": ("um", 1e-3),
    "ohm": ("ohm", 1.0),
    "kohm": ("ohm", 1e3),
    "Mohm": ("ohm", 1e6),
    "dB": ("dB", 1.0),
}


def parse_unit_value(value, *, expected_unit: str | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return None if math.isnan(number) else number
    text = str(value).strip()
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]+)?", text)
    if not match:
        return None
    unit = match.group(2) or ""
    if unit not in UNIT_FACTORS:
        return None
    base_unit, factor = UNIT_FACTORS[unit]
    if expected_unit is not None and base_unit != expected_unit:
        return None
    try:
        return float(Decimal(match.group(1)) * Decimal(str(factor)))
    except InvalidOperation:
        return None


def normalize_numeric_fields(payload: dict, *, unit: str | None = None) -> dict:
    normalized = dict(payload)
    for key in ["minimum", "maximum", "target", "tolerance"]:
        if key in normalized:
            parsed = parse_unit_value(normalized[key], expected_unit=unit)
            if parsed is not None:
                normalized[key] = parsed
    return normalized
