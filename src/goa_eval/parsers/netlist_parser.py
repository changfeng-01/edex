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
    models: dict[str, dict] = field(default_factory=dict)
    analysis_directives: list[dict] = field(default_factory=list)


_UNIT_FACTORS = {
    "T": 1e12,
    "G": 1e9,
    "MEG": 1e6,
    "meg": 1e6,
    "K": 1e3,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
    "": 1.0,
    "F": 1.0,
    "A": 1.0,
    "V": 1.0,
    "Ohm": 1.0,
    "ohm": 1.0,
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
    key = _unit_key(unit)
    if key not in _UNIT_FACTORS:
        raise ValueError(f"Unsupported unit '{unit}' in value: {value}")
    return number * _UNIT_FACTORS[key]


def _unit_key(unit: str) -> str:
    if unit in _UNIT_FACTORS:
        return unit
    for suffix in ["Ohm", "ohm", "F", "A", "V"]:
        if unit.endswith(suffix):
            return unit[: -len(suffix)] or suffix
    return "MEG" if unit.upper() == "MEG" else unit


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
    elif directive == ".MODEL":
        model = _parse_model_directive(stripped, path, line_no)
        if model:
            result.models[str(model["name"])] = model
    elif directive in {".OP", ".TRAN", ".DC"}:
        result.analysis_directives.append(
            {
                "directive": directive,
                "args": tokens[1:],
                "raw_line": stripped,
                "source_file": str(path),
                "line_no": line_no,
            }
        )
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
    elif prefix == "r":
        device = _parse_resistor(tokens)
    elif prefix == "v":
        device = _parse_source(tokens, "voltage_source")
    elif prefix == "i":
        device = _parse_source(tokens, "current_source")
    elif prefix == "x":
        device = _parse_mos(tokens) if _looks_like_parameterized_mos(tokens) else _parse_subckt_instance(tokens, subckts)
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


def _parse_resistor(tokens: list[str]) -> Device:
    if len(tokens) < 4:
        raise ValueError("resistor line needs two nodes and value")
    raw = tokens[3]
    return Device(
        tokens[0],
        "resistor",
        tokens[1:3],
        params_raw={"R": raw},
        params_si={"R": parse_numeric_with_unit(raw)},
    )


def _parse_source(tokens: list[str], kind: str) -> Device:
    if len(tokens) < 4:
        raise ValueError(f"{kind} line needs two nodes and source spec")
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
    return Device(tokens[0], kind, tokens[1:3], params_raw=params_raw, params_si=params_si)


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


def _looks_like_parameterized_mos(tokens: list[str]) -> bool:
    params = [token for token in tokens[1:] if "=" in token]
    positional = [token for token in tokens[1:] if "=" not in token]
    if len(positional) < 5:
        return False
    if not any(token.split("=", 1)[0].upper() in {"W", "L"} for token in params):
        return False
    model = positional[-1].lower()
    return "fet" in model or "mos" in model


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


def _parse_model_directive(stripped: str, path: Path, line_no: int) -> dict | None:
    match = re.match(r"\.MODEL\s+(\S+)\s+(\S+)\s*(?:\((.*)\))?\s*$", stripped, flags=re.IGNORECASE)
    if not match:
        return None
    raw_params = {}
    params_si = {}
    body = match.group(3) or ""
    for token in body.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        raw_params[key] = value
        try:
            params_si[key] = parse_numeric_with_unit(value)
        except ValueError:
            pass
    return {
        "name": match.group(1),
        "kind": match.group(2),
        "raw_params": raw_params,
        "params_si": params_si,
        "raw_line": stripped,
        "source_file": str(path),
        "line_no": line_no,
    }
