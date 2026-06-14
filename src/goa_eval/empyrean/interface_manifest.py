from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

import yaml

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
    node_mapping_path: Path | None,
    physical_summary: dict[str, Any],
    parasitic_summary: dict[str, Any],
    model_summary: dict[str, Any],
    data_source: str,
) -> dict[str, Any]:
    declared_ports = _ports_from_schematic_artifacts(artifacts.get("schematic", []))
    waveform_signals = _waveform_signals(waveform_column_map_path)
    node_mapping_contract = _node_mapping_contract(
        node_mapping_path,
        declared_ports=declared_ports,
        waveform_signals=waveform_signals,
        parasitic_summary=parasitic_summary,
    )
    node_mapping_records = node_mapping_contract.get("records", [])
    interface_manifest = {
        **base_versions(),
        "case_id": case_id,
        "interface_contract_version": "empyrean_fpd_offline_interface_v1",
        "execution_mode": "offline_import_only",
        "tool_invocation": False,
        "input_dir": str(input_dir),
        "node_mapping_contract": node_mapping_contract,
        "port_contract": _port_contract(declared_ports, waveform_signals, node_mapping_records),
        "model_contract": _model_contract(model_summary, artifacts.get("schematic", [])),
        "stimulus_contract": _stimulus_contract(waveform_signals, normalized_waveform_path, node_mapping_records),
        "verification_gate_contract": _verification_gate_contract(physical_summary),
        "parasitic_contract": _parasitic_contract(parasitic_summary, node_mapping_records),
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


def _port_contract(declared_ports: list[str], waveform_signals: list[str], node_mapping_records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = sorted({*_normalize_port_set(declared_ports), *_normalize_port_set(waveform_signals)})
    ports = []
    for port in normalized:
        matches = _mapping_matches(port, node_mapping_records, fields=["schematic_net", "waveform_signal", "rc_net", "layout_label"])
        first_match = matches[0] if matches else {}
        ports.append(
            {
                "name": port,
                "role": COMMON_PORT_ROLES.get(port.lower(), "unknown"),
                "present_in_schematic": port.lower() in {item.lower() for item in declared_ports},
                "present_in_waveform": port.lower() in {item.lower() for item in waveform_signals},
                "direction_policy": "inputoutput_pin_allowed",
                "engineering_name": first_match.get("engineering_name"),
                "mapping_role": first_match.get("role"),
                "mapped_sources": _mapped_sources(port, matches),
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


def _node_mapping_contract(
    path: Path | None,
    *,
    declared_ports: list[str],
    waveform_signals: list[str],
    parasitic_summary: dict[str, Any],
) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "status": "not_provided",
            "mapping_file_path": str(path) if path else None,
            "records": [],
            "coverage": {"schematic": 0, "waveform": 0, "rc": 0},
            "unmatched": {"schematic": [], "waveform": [], "rc": []},
            "message": "net_mapping.yaml was not provided.",
        }
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = raw.get("mappings", raw if isinstance(raw, list) else [])
        if not isinstance(rows, list):
            raise ValueError("net_mapping.yaml must contain a mappings list.")
        records = [_normalize_mapping_record(row, index) for index, row in enumerate(rows, start=1)]
        records = [record for record in records if record]
        if not records:
            raise ValueError("net_mapping.yaml did not contain any valid mapping records.")
        unmatched = _unmatched_mapping_references(
            records,
            declared_ports=declared_ports,
            waveform_signals=waveform_signals,
            rc_nets=_rc_nets(parasitic_summary),
        )
        coverage = {
            "schematic": sum(1 for record in records if record.get("schematic_net") and not _is_unmatched(record["schematic_net"], unmatched["schematic"])),
            "waveform": sum(1 for record in records if record.get("waveform_signal") and not _is_unmatched(record["waveform_signal"], unmatched["waveform"])),
            "rc": sum(1 for record in records if record.get("rc_net") and not _is_unmatched(record["rc_net"], unmatched["rc"])),
        }
        return {
            "status": "declared",
            "mapping_file_path": str(path),
            "records": records,
            "coverage": coverage,
            "unmatched": unmatched,
            "message": "",
        }
    except Exception as exc:
        return {
            "status": "invalid",
            "mapping_file_path": str(path),
            "records": [],
            "coverage": {"schematic": 0, "waveform": 0, "rc": 0},
            "unmatched": {"schematic": [], "waveform": [], "rc": []},
            "message": f"{type(exc).__name__}: {exc}",
        }


def _normalize_mapping_record(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    allowed = [
        "engineering_name",
        "role",
        "schematic_net",
        "layout_label",
        "waveform_signal",
        "rc_net",
        "instance",
        "description",
    ]
    record = {key: str(row.get(key)).strip() for key in allowed if row.get(key) is not None and str(row.get(key)).strip()}
    if not any(record.get(key) for key in ["engineering_name", "schematic_net", "waveform_signal", "rc_net"]):
        return {}
    record["mapping_index"] = index
    return record


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


def _stimulus_contract(
    signals: list[str],
    normalized_waveform_path: Path | None,
    node_mapping_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "declared" if signals else "not_provided",
        "normalized_waveform_path": str(normalized_waveform_path) if normalized_waveform_path else None,
        "observed_signal_names": signals,
        "signal_mappings": _signal_mappings(signals, node_mapping_records),
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


def _parasitic_contract(parasitic_summary: dict[str, Any], node_mapping_records: list[dict[str, Any]]) -> dict[str, Any]:
    nets = []
    for row in parasitic_summary.get("grouped_by_net", []):
        net = str(row.get("net", ""))
        if not net:
            continue
        matches = _mapping_matches(net, node_mapping_records, fields=["rc_net"])
        first_match = matches[0] if matches else {}
        nets.append(
            {
                "net_name": net,
                "role": COMMON_PORT_ROLES.get(net.lower(), "unknown"),
                "total_resistance": row.get("resistance"),
                "total_capacitance": row.get("capacitance"),
                "criticality": _criticality_for_net(net),
                "engineering_name": first_match.get("engineering_name"),
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


def _unmatched_mapping_references(
    records: list[dict[str, Any]],
    *,
    declared_ports: list[str],
    waveform_signals: list[str],
    rc_nets: list[str],
) -> dict[str, list[str]]:
    schematic = _lower_set(declared_ports)
    waveform = _lower_set(waveform_signals)
    rc = _lower_set(rc_nets)
    unmatched = {"schematic": [], "waveform": [], "rc": []}
    for record in records:
        schematic_net = record.get("schematic_net")
        if schematic_net and schematic_net.lower() not in schematic:
            unmatched["schematic"].append(schematic_net)
        waveform_signal = record.get("waveform_signal")
        if waveform_signal and waveform_signal.lower() not in waveform:
            unmatched["waveform"].append(waveform_signal)
        rc_net = record.get("rc_net")
        if rc_net and rc_net.lower() not in rc:
            unmatched["rc"].append(rc_net)
    return {key: sorted(set(value)) for key, value in unmatched.items()}


def _rc_nets(parasitic_summary: dict[str, Any]) -> list[str]:
    return [str(row.get("net")) for row in parasitic_summary.get("grouped_by_net", []) if row.get("net")]


def _mapping_matches(value: str, records: list[dict[str, Any]], *, fields: list[str]) -> list[dict[str, Any]]:
    lower = value.lower()
    return [record for record in records if any(str(record.get(field, "")).lower() == lower for field in fields)]


def _mapped_sources(value: str, matches: list[dict[str, Any]]) -> list[str]:
    lower = value.lower()
    sources = []
    for field in ["schematic_net", "layout_label", "waveform_signal", "rc_net"]:
        if any(str(record.get(field, "")).lower() == lower for record in matches):
            sources.append(field)
    return sources


def _signal_mappings(signals: list[str], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mappings = []
    for signal in signals:
        matches = _mapping_matches(signal, records, fields=["waveform_signal"])
        if not matches:
            continue
        for record in matches:
            mappings.append(
                {
                    "signal_name": signal,
                    "engineering_name": record.get("engineering_name"),
                    "role": record.get("role"),
                    "schematic_net": record.get("schematic_net"),
                    "rc_net": record.get("rc_net"),
                }
            )
    return mappings


def _is_unmatched(value: str, unmatched_values: list[str]) -> bool:
    return value.lower() in {item.lower() for item in unmatched_values}


def _lower_set(values: list[str]) -> set[str]:
    return {str(value).lower() for value in values}


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
