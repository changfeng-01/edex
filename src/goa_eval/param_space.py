from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


PARAMETER_FIELDS = [
    "capacitance",
    "drive_resistance",
    "transistor_width",
    "transistor_length",
    "vdd",
    "load_cap",
    "temp",
    "corner",
]


@dataclass(frozen=True)
class ParameterSpace:
    parameters: dict[str, object]

    def normalized(self) -> dict[str, object]:
        return {field: self.parameters.get(field) for field in PARAMETER_FIELDS}


def load_parameter_space(path: Path) -> ParameterSpace:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parameters = raw.get("parameters", raw)
    return ParameterSpace(parameters={field: parameters.get(field) for field in PARAMETER_FIELDS})


@dataclass(frozen=True)
class RunParameters:
    run_id: str
    circuit_version: str | None
    parameters: dict[str, object]
    conditions: dict[str, object]
    numeric_parameters: dict[str, float | None]

    def flat_record(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "circuit_version": self.circuit_version,
            **self.parameters,
            **self.conditions,
        }


def load_run_params(path: Path) -> RunParameters:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parameters = dict(raw.get("parameters", {}) or {})
    conditions = dict(raw.get("conditions", {}) or {})
    run_id = str(raw.get("run_id") or path.parent.name)
    return RunParameters(
        run_id=run_id,
        circuit_version=raw.get("circuit_version"),
        parameters=parameters,
        conditions=conditions,
        numeric_parameters={key: parse_engineering_value(value) for key, value in {**parameters, **conditions}.items()},
    )


def parse_engineering_value(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value).strip()
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]+)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or ""
    factors = {
        "": 1.0,
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9,
        "F": 1.0,
        "pF": 1e-12,
        "nF": 1e-9,
        "uF": 1e-6,
        "mF": 1e-3,
    }
    if unit not in factors:
        return None
    return number * factors[unit]
