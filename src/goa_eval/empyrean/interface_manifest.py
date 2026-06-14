from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from goa_eval.empyrean.schemas import base_versions, evidence_boundary
from goa_eval.io_utils import write_json


COMMON_PORT_ROLES = {
    "data": "input_stimulus",
    "gate": "input_stimulus",
    "scan": "input_stimulus",
    "stv": "input_stimulus",
    "clk": "input_stimulus",
    "pixel": "output_observation",
    "cfcom": "common_electrode",
    "acom": "common_electrode",
    "vdd": "power",
    "vss": "ground",
    "gnd": "ground",
}


def write_empyrean_interface_manifest(
    path: Path,
    *,
    case_id: str,
    input_dir: Path,
    artifacts: dict[str, list[Path]],
    normalized_waveform_path: Path | None,
    waveform_column_map_path: Path | None,
    physical_summary: dict[str, Any],
    parasitic_summary: dict[str, Any],
    model_summary: dict[str, Any],
    data_source: str,
) -> dict[str, Any]:
    interface_manifest = {
        **base_versions(),
        "case_id": case_id,
        "interface_contract_version": "empyrean_fpd_offline_interface_v1",
        "execution_mode": "offline_import_only",
        "tool_invocation": False,
        "input_dir": str(input_dir),
        "port_contract": _port_contract(artifacts, waveform_column_map_path),
        "model_contract": _model_contract(model_summary, artifacts.get("schematic", [])),
        "stimulus_contract": _stimulus_contract(waveform_column_map_path, normalized_waveform_path),
        "verification_gate_contract": _verification_gate_contract(physical_summary),
        "parasitic_contract": _parasitic_contract(parasitic_summary),
        "layout_contract": _layout_contract(artifacts.get("layout", [])),
        "evidence_boundary": evidence_boundary(data_source),
        "next_step_policy": {
            "candidate_outputs_are": "next-run simulation suggestions",
            "requires_real_eda_rerun": True,
            "requires_reverification": True,
            "requires_reextraction": True,
        },
    }
    write_json(path, interface_manifest)
    return interface_manifest


def _port_contract(artifacts: dict[str, list[Path]], waveform_column_map_path: Path | None) -> dict[str, Any]:
    declared_ports = _ports_from_schematic_artifacts(artifacts.get("schematic", []))
    waveform_signals = _waveform_signals(waveform_column_map_path)
    normalized = sorted({*_normalize_port_set(declared_ports), *_normalize_port_set(waveform_signals)})
    ports = []
    for port in normalized:
        ports.append(
            {
                "name": port,
                "role": COMMON_PORT_ROLES.get(port.lower(), "unknown"),
                "present_in_schematic": port.lower() in {item.lower() for item in declared_ports},
                "present_in_waveform": port.lower() in {item.lower() for item in waveform_signals},
                "direction_policy": "inputoutput_pin_allowed",
            }
        )
    return {
        "status": "declared" if ports else "not_provided",
        "ports": ports,
        "port_name_policy": {
            "case_sensitive": False,
            "allow_aliases": False,
            "final_lvs_should_compare_top_ports": True,
            "debug_only_ignore_top_ports": True,
        },
        "manual_anchor": "Pixel-level Empyrean FPD training material uses Data, Gate, Pixel, CFCOM, and ACOM as core schematic pins.",
    }


def _model_contract(model_summary: dict[str, Any], schematic_paths: list[Path]) -> dict[str, Any]:
    model_names: set[str] = set()
    for artifact in model_summary.get("artifacts", []):
        model_names.update(str(name) for name in artifact.get("model_names", []))
    referenced = _referenced_model_names(schematic_paths)
    missing = sorted(name for name in referenced if name and name not in model_names)
    return {
        "status": "declared" if model_names or referenced else "not_provided",
        "model_names": sorted(model_names),
        "referenced_model_names": sorted(referenced),
        "missing_referenced_model_names": missing,
        "model_name_consistency": "passed" if referenced and not missing else ("not_evaluable" if not referenced else "failed"),
        "required_alignment": ["model_file_name", "model_card_name", "schematic_instance_model_reference"],
    }


def _stimulus_contract(waveform_column_map_path: Path | None, normalized_waveform_path: Path | None) -> dict[str, Any]:
    signals = _waveform_signals(waveform_column_map_path)
    return {
        "status": "declared" if signals else "not_provided",
        "normalized_waveform_path": str(normalized_waveform_path) if normalized_waveform_path else None,
        "observed_signal_names": signals,
        "recommended_parameter_fields": [
            "source_type",
            "V0",
            "V1",
            "delay",
            "rise_time",
            "fall_time",
            "pulse_width",
            "period",
            "points",
        ],
        "supported_source_types": ["vpulse", "vpwl"],
    }


def _verification_gate_contract(physical_summary: dict[str, Any]) -> dict[str, Any]:
    checks = {}
    blocking = []
    for name in ["drc", "lvs", "erc"]:
        status = str((physical_summary.get(name) or {}).get("status", "not_provided"))
        checks[name] = {
            "status": status,
            "final_gate_required": True,
            "blocks_claim_if_not_passed": True,
        }
        if status != "passed":
            blocking.append(name)
    return {
        "status": "passed" if not blocking else "incomplete",
        "checks": checks,
        "blocking_checks": blocking,
        "lvs_top_port_policy": {
            "ignore_layout_and_source_top_ports": "debug_only",
            "final_export_requires_top_port_compare": True,
        },
    }


def _parasitic_contract(parasitic_summary: dict[str, Any]) -> dict[str, Any]:
    nets = []
    for row in parasitic_summary.get("grouped_by_net", []):
        net = str(row.get("net", ""))
        if not net:
            continue
        nets.append(
            {
                "net_name": net,
                "role": COMMON_PORT_ROLES.get(net.lower(), "unknown"),
                "total_resistance": row.get("resistance"),
                "total_capacitance": row.get("capacitance"),
                "criticality": _criticality_for_net(net),
            }
        )
    return {
        "status": "declared" if nets else str(parasitic_summary.get("status", "not_provided")),
        "resistance_unit": parasitic_summary.get("resistance_unit"),
        "capacitance_unit": parasitic_summary.get("capacitance_unit"),
        "critical_nets": nets,
        "feeds_optimizer_context": bool(nets),
        "rerun_requirement": "parasitics must be re-extracted after layout or candidate parameter changes",
    }


def _layout_contract(layout_paths: list[Path]) -> dict[str, Any]:
    records = []
    for path in layout_paths:
        records.append({"path": str(path), "file_name": path.name, "artifact_type": _layout_artifact_type(path)})
    return {
        "status": "declared" if records else "not_provided",
        "artifacts": records,
        "expected_rule_inputs": ["technology_file", "layer_map", "drc_rule", "lvs_rule", "erc_connect_rule"],
    }


def _ports_from_schematic_artifacts(paths: list[Path]) -> list[str]:
    ports: set[str] = set()
    for path in paths:
        if not path.exists() or path.suffix.lower() not in {".sp", ".spi", ".spice", ".cdl", ".txt", ".v"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for match in re.finditer(r"(?im)^\s*\.subckt\s+\S+\s+(.+)$", text):
            for token in re.split(r"\s+", match.group(1).strip()):
                if token and not token.startswith("+"):
                    ports.add(token)
        for match in re.finditer(r"(?im)^\s*X\S+\s+(.+)$", text):
            tokens = re.split(r"\s+", match.group(1).strip())
            for token in tokens[:-1]:
                if token and not token.startswith("+"):
                    ports.add(token)
    return sorted(ports)


def _referenced_model_names(paths: list[Path]) -> set[str]:
    references: set[str] = set()
    for path in paths:
        if not path.exists() or path.suffix.lower() not in {".sp", ".spi", ".spice", ".cdl", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for match in re.finditer(r"(?im)^\s*[A-Za-z]\S*\s+(.+)$", text):
            tokens = re.split(r"\s+", match.group(1).strip())
            if tokens and tokens[0].lower() not in {".include", ".model", ".subckt", ".ends"}:
                references.add(tokens[-1])
    return {item for item in references if item and not item.startswith('"')}


def _waveform_signals(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        columns = payload.get("columns")
        if isinstance(columns, list):
            return sorted(
                str(item.get("normalized_name"))
                for item in columns
                if isinstance(item, dict) and item.get("role") == "signal" and item.get("normalized_name")
            )
        signals = payload.get("signal_columns") or payload.get("column_map") or payload.get("signals")
        if isinstance(signals, dict):
            return sorted(str(value) for value in signals.values())
        if isinstance(signals, list):
            return sorted(str(item) for item in signals)
    return []


def _normalize_port_set(values: list[str]) -> set[str]:
    return {str(value).strip() for value in values if str(value).strip()}


def _criticality_for_net(net: str) -> str:
    lower = net.lower()
    if lower in {"pixel", "gate", "data", "scan", "stv"} or re.match(r"o\d+$", lower):
        return "high"
    if lower in {"cfcom", "acom", "vdd", "vss", "gnd"}:
        return "medium"
    return "review"


def _layout_artifact_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".gds":
        return "gds_layout"
    if suffix == ".tf":
        return "technology_file"
    if suffix == ".map":
        return "layer_map"
    if "layer" in path.name.lower():
        return "layer_summary"
    return "layout_metadata"
