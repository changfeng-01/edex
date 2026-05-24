from __future__ import annotations

from collections import Counter
from pathlib import Path

from goa_eval.io_utils import write_json
from goa_eval.parsers.netlist_parser import NetlistParseResult, parse_netlist


def summarize_netlist_file(path: Path) -> dict:
    return summarize_netlist_structure(parse_netlist(path))


def write_netlist_structure(path: Path, parsed: NetlistParseResult) -> dict:
    summary = summarize_netlist_structure(parsed)
    write_json(path, summary)
    return summary


def summarize_netlist_structure(parsed: NetlistParseResult) -> dict:
    devices = parsed.devices
    device_counts = dict(Counter(device.kind for device in devices))
    model_counts = dict(Counter(str(model.get("kind", "")) for model in parsed.models.values()))
    node_degrees = _node_degrees(devices)
    mos = [device for device in devices if device.kind == "mos"]
    caps = [device for device in devices if device.kind == "capacitor"]
    resistors = [device for device in devices if device.kind == "resistor"]
    voltage_sources = [device for device in devices if device.kind == "voltage_source"]
    current_sources = [device for device in devices if device.kind == "current_source"]
    scalar_features = {
        "mos_count": len(mos),
        "cap_count": len(caps),
        "resistor_count": len(resistors),
        "current_source_count": len(current_sources),
        "voltage_source_count": len(voltage_sources),
        "model_count": len(parsed.models),
        "node_count": len(node_degrees),
        "max_node_degree": max(node_degrees.values(), default=0),
        "transistor_width_sum": sum(device.params_si.get("W", 0.0) for device in mos),
        "capacitance_sum": sum(device.params_si.get("C", 0.0) for device in caps),
    }
    return {
        "device_counts": device_counts,
        "model_counts": model_counts,
        "node_count": len(node_degrees),
        "node_degrees": node_degrees,
        "mos_summary": {
            "count": len(mos),
            "models": sorted({str(device.model) for device in mos if device.model}),
            "transistor_width_sum": scalar_features["transistor_width_sum"],
        },
        "passive_summary": {
            "capacitor_count": len(caps),
            "resistor_count": len(resistors),
            "capacitance_sum": scalar_features["capacitance_sum"],
            "resistance_sum": sum(device.params_si.get("R", 0.0) for device in resistors),
        },
        "source_summary": {
            "voltage_source_count": len(voltage_sources),
            "current_source_count": len(current_sources),
        },
        "subckt_summary": {
            "subckt_count": len(parsed.subckts),
            "subckts": sorted(parsed.subckts),
        },
        "analysis_directives": parsed.analysis_directives,
        "models": parsed.models,
        "scalar_features": scalar_features,
        "warnings": parsed.warnings,
    }


def _node_degrees(devices) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for device in devices:
        for node in device.nodes:
            counts[str(node)] += 1
    return dict(sorted(counts.items()))
