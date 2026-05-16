from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from goa_eval.models.design import SubcktDef
from goa_eval.models.device import Device


@dataclass
class NetlistParseResult:
    devices: list[Device] = field(default_factory=list)
    subckts: dict[str, SubcktDef] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


_UNIT_FACTORS = {
    "T": 1e12,
    "G": 1e9,
    "MEG": 1e6,
    "K": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


def parse_numeric_with_unit(value: str) -> float:
    text = value.strip()
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]+)?", text)
    if not match:
        raise ValueError(f"Cannot parse numeric value: {value}")
    number = float(match.group(1))
    unit = match.group(2)
    if not unit:
        return number
    key = "MEG" if unit.upper() == "MEG" else unit
    if key not in _UNIT_FACTORS:
        raise ValueError(f"Unsupported unit '{unit}' in value: {value}")
    return number * _UNIT_FACTORS[key]


def parse_netlist(path: Path) -> NetlistParseResult:
    result = NetlistParseResult()
    current: SubcktDef | None = None

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+"):
            result.warnings.append(f"{path}:{line_no}: continuation line skipped")
            continue
        if stripped.startswith("."):
            _parse_directive(stripped, path, line_no, result, current_ref=[current])
            current = result.subckts.get("__current__")
            result.subckts.pop("__current__", None)
            continue

        try:
            device = _parse_device_line(stripped, raw_line, path, line_no, current, result.subckts)
        except Exception as exc:
            result.warnings.append(f"{path}:{line_no}: {exc}")
            device = Device(
                name=stripped.split()[0],
                kind="unknown",
                nodes=[],
                raw_line=raw_line,
                source_file=str(path),
                line_no=line_no,
                parent_subckt=current.name if current else None,
            )
        result.devices.append(device)
        if current is not None:
            current.devices.append(device)

    return result


def _parse_directive(
    stripped: str,
    path: Path,
    line_no: int,
    result: NetlistParseResult,
    current_ref: list[SubcktDef | None],
) -> None:
    tokens = stripped.split()
    directive = tokens[0].upper()
    current = current_ref[0]
    if directive == ".SUBCKT":
        if len(tokens) < 2:
            result.warnings.append(f"{path}:{line_no}: malformed .SUBCKT")
            return
        current = SubcktDef(tokens[1], tokens[2:], source_file=str(path), line_no=line_no)
        result.subckts[current.name] = current
    elif directive == ".ENDS":
        end_name = tokens[1] if len(tokens) > 1 else None
        if current and end_name and end_name != current.name:
            result.warnings.append(f"{path}:{line_no}: .ENDS {end_name} does not match {current.name}")
        current = None
    result.subckts["__current__"] = current


def _parse_device_line(
    stripped: str,
    raw_line: str,
    path: Path,
    line_no: int,
    current: SubcktDef | None,
    subckts: dict[str, SubcktDef],
) -> Device:
    tokens = stripped.split()
    name = tokens[0]
    prefix = name[0].lower()
    if prefix == "m":
        device = _parse_mos(tokens)
    elif prefix == "c":
        device = _parse_capacitor(tokens)
    elif prefix == "v":
        device = _parse_voltage_source(tokens)
    elif prefix == "x":
        device = _parse_subckt_instance(tokens, subckts)
    else:
        device = Device(name=name, kind="unknown", nodes=tokens[1:])
    device.raw_line = raw_line
    device.source_file = str(path)
    device.line_no = line_no
    device.parent_subckt = current.name if current else None
    return device


def _parse_mos(tokens: list[str]) -> Device:
    params_tokens = [tok for tok in tokens[1:] if "=" in tok]
    positional = [tok for tok in tokens[1:] if "=" not in tok]
    if len(positional) < 4:
        raise ValueError("MOS line needs at least 3 nodes and model")
    model = positional[-1]
    nodes = positional[:-1]
    params_raw, params_si = _parse_params(params_tokens)
    return Device(tokens[0], "mos", nodes, model=model, params_raw=params_raw, params_si=params_si)


def _parse_capacitor(tokens: list[str]) -> Device:
    if len(tokens) < 4:
        raise ValueError("capacitor line needs two nodes and value")
    raw = tokens[3]
    return Device(
        tokens[0],
        "capacitor",
        tokens[1:3],
        params_raw={"C": raw},
        params_si={"C": parse_numeric_with_unit(raw)},
    )


def _parse_voltage_source(tokens: list[str]) -> Device:
    if len(tokens) < 4:
        raise ValueError("voltage source line needs two nodes and source spec")
    spec = " ".join(tokens[3:])
    params_raw = {"source_spec": spec}
    params_si = {}
    if spec.upper().startswith("DC"):
        pieces = spec.split()
        if len(pieces) >= 2:
            params_raw["dc_value"] = pieces[1]
            params_si["dc_value"] = parse_numeric_with_unit(pieces[1])
    pulse_match = re.search(r"PULSE\(([^)]*)\)", spec, flags=re.IGNORECASE)
    if pulse_match:
        names = ["v1", "v2", "delay", "rise", "fall", "width", "period"]
        values = pulse_match.group(1).split()
        for key, value in zip(names, values):
            params_raw[f"pulse_{key}"] = value
            try:
                params_si[f"pulse_{key}"] = parse_numeric_with_unit(value)
            except ValueError:
                pass
    return Device(tokens[0], "voltage_source", tokens[1:3], params_raw=params_raw, params_si=params_si)


def _parse_subckt_instance(tokens: list[str], subckts: dict[str, SubcktDef]) -> Device:
    if len(tokens) < 3:
        raise ValueError("subckt instance line needs nodes and model")
    model = tokens[-1]
    nodes = tokens[1:-1]
    port_map = {}
    subckt = subckts.get(model)
    if subckt:
        port_map = {port: node for port, node in zip(subckt.ports, nodes)}
    return Device(tokens[0], "subckt_instance", nodes, model=model, port_map=port_map)


def _parse_params(tokens: list[str]) -> tuple[dict[str, str], dict[str, float]]:
    raw: dict[str, str] = {}
    si: dict[str, float] = {}
    for token in tokens:
        key, value = token.split("=", 1)
        raw[key] = value
        try:
            si[key] = parse_numeric_with_unit(value)
        except ValueError:
            pass
    return raw, si
