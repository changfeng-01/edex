from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from goa_eval.parsers.netlist_parser import parse_netlist
from goa_eval.waveform_io import normalize_column_name
from goa_eval.web.schemas import UploadedCaseConfig


TIME_COLUMN_ALIASES = {"xval", "time", "t", "time(s)", "time_s", "time_ns", "time_us", "time_µs", "time_μs", "time_ms"}
NETLIST_FILENAMES = ("source_netlist.sp", "source_netlist.spice", "source_netlist.netlist")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def inspect_uploaded_case_input(case_dir: Path, config: UploadedCaseConfig | None = None) -> dict[str, Any]:
    input_dir = case_dir / "input"
    warnings: list[str] = []
    errors: list[str] = []
    suggestions: list[str] = []

    preview: dict[str, Any] = {
        "row_count": 0,
        "column_count": 0,
        "original_columns": [],
        "normalized_columns": [],
        "time_column_original": None,
        "time_column_normalized": None,
        "time_min": None,
        "time_max": None,
        "time_span": None,
        "guessed_time_unit": None,
        "voltage_min": None,
        "voltage_max": None,
        "detected_output_nodes": [],
        "detected_output_node_count": 0,
        "sample_output_nodes": [],
        "missing_configured_nodes": [],
        "expected_stage_count": None,
        "observed_stage_count": 0,
        "output_coverage_ratio": None,
        "coverage_status": "unknown",
        "warnings": warnings,
        "errors": errors,
        "suggestions": suggestions,
        "params_summary": _inspect_params(input_dir / "params.yaml", warnings, errors, suggestions),
        "netlist_summary": _inspect_netlist(input_dir, warnings),
        "attachments_summary": _inspect_attachments(input_dir),
        "image_analysis_enabled": False,
        "ready_for_analysis": False,
    }

    waveform_path = input_dir / "waveform.csv"
    if not waveform_path.exists():
        errors.append("waveform.csv is required")
        suggestions.append("Upload a CSV waveform file named waveform.csv before running analysis.")
        return preview

    try:
        frame = _read_waveform_frame(waveform_path)
    except Exception as exc:
        errors.append(f"waveform.csv could not be read: {exc}")
        suggestions.append("Check that waveform.csv is UTF-8 text with a header row and numeric samples.")
        return preview

    original_columns = [str(column) for column in frame.columns]
    normalized_columns = [_normalize_preview_column(column) for column in original_columns]
    time_index = _find_time_column(original_columns, normalized_columns)
    output_pairs = _detect_output_nodes(original_columns, normalized_columns)

    preview["row_count"] = int(len(frame))
    preview["column_count"] = int(len(original_columns))
    preview["original_columns"] = original_columns
    preview["normalized_columns"] = normalized_columns
    preview["detected_output_nodes"] = [node for _, node in output_pairs]
    preview["detected_output_node_count"] = len(output_pairs)
    preview["observed_stage_count"] = len(output_pairs)
    preview["sample_output_nodes"] = [node for _, node in output_pairs[:8]]

    if time_index is None:
        errors.append("No supported time column found in waveform.csv")
        suggestions.append("Use a time column named XVAL, TIME, time, Time, t, Time(s), time_s, time_ns, or time_us.")
    else:
        time_original = original_columns[time_index]
        time_values = pd.to_numeric(frame.iloc[:, time_index], errors="coerce").dropna()
        preview["time_column_original"] = time_original
        preview["time_column_normalized"] = "time"
        if time_values.empty:
            errors.append("The detected time column does not contain numeric values.")
        else:
            time_min = float(time_values.min())
            time_max = float(time_values.max())
            preview["time_min"] = time_min
            preview["time_max"] = time_max
            preview["time_span"] = float(time_max - time_min)
            preview["guessed_time_unit"] = _guess_time_unit(time_original, time_values)

    if not output_pairs:
        warnings.append("No output node columns were detected.")
        suggestions.append("Use output columns such as v(o1), o1, OUT1, out1, gate1, or gout1.")
    else:
        voltage_values = pd.concat(
            [pd.to_numeric(frame.iloc[:, index], errors="coerce") for index, _ in output_pairs],
            ignore_index=True,
        ).dropna()
        if not voltage_values.empty:
            preview["voltage_min"] = float(voltage_values.min())
            preview["voltage_max"] = float(voltage_values.max())

    missing_configured_nodes = _missing_configured_nodes(config, [node for _, node in output_pairs])
    preview["missing_configured_nodes"] = missing_configured_nodes
    if config is not None and config.stage_count:
        preview["expected_stage_count"] = int(config.stage_count)
        preview["output_coverage_ratio"] = len(output_pairs) / int(config.stage_count)
        preview["coverage_status"] = "complete" if not missing_configured_nodes else "partial"
    if missing_configured_nodes:
        warnings.append("Some configured output nodes were not found in waveform.csv.")

    if preview["params_summary"]["exists"] is False:
        warnings.append("params.yaml was not uploaded; candidate generation will use defaults or be limited by downstream configuration.")
    if preview["attachments_summary"]["image_count"] > 0:
        warnings.append("Image attachments are stored for display only and are not used for curve recognition.")
    suggestions.append("Preview checks input readability only; run analysis still requires simulation evidence review.")

    preview["ready_for_analysis"] = not errors
    return preview


def _read_waveform_frame(path: Path) -> pd.DataFrame:
    header = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
    if "," in header:
        return pd.read_csv(path, skipinitialspace=True)
    return pd.read_csv(path, sep=r"\s+", engine="python")


def _normalize_preview_column(column: str) -> str:
    normalized = normalize_column_name(column)
    if _is_time_alias(column) or _is_time_alias(normalized):
        return "time"
    return normalized


def _find_time_column(original_columns: list[str], normalized_columns: list[str]) -> int | None:
    for index, (original, normalized) in enumerate(zip(original_columns, normalized_columns)):
        if normalized == "time" or _is_time_alias(original):
            return index
    return None


def _is_time_alias(column: str) -> bool:
    text = column.strip().lower()
    return text in TIME_COLUMN_ALIASES


def _guess_time_unit(column: str, values: pd.Series) -> str:
    text = column.strip().lower()
    if "ns" in text:
        return "ns"
    if "us" in text or "µs" in text or "μs" in text:
        return "us"
    if "ms" in text:
        return "ms"
    if text.endswith("_s") or text == "time(s)" or text.endswith("(s)"):
        return "s"
    max_abs = float(values.abs().max()) if not values.empty else 0.0
    if max_abs > 1_000:
        return "ns"
    if max_abs > 1:
        return "us"
    return "s"


def _detect_output_nodes(original_columns: list[str], normalized_columns: list[str]) -> list[tuple[int, str]]:
    nodes: list[tuple[int, str]] = []
    seen: set[str] = set()
    for index, (original, normalized) in enumerate(zip(original_columns, normalized_columns)):
        if normalized == "time":
            continue
        node = _output_node_name(original, normalized)
        if node and node not in seen:
            seen.add(node)
            nodes.append((index, node))
    return nodes


def _output_node_name(original: str, normalized: str) -> str | None:
    candidates = [normalized.strip().lower(), original.strip().lower()]
    for candidate in candidates:
        if re.fullmatch(r"(?:o|out|gate|gout)\d+", candidate):
            return candidate
    return None


def _missing_configured_nodes(config: UploadedCaseConfig | None, detected_nodes: list[str]) -> list[str]:
    if config is None or not config.stage_count:
        return []
    detected = {node.lower() for node in detected_nodes}
    missing: list[str] = []
    for index in range(1, config.stage_count + 1):
        try:
            expected = config.output_node_pattern.format(index=index).lower()
        except Exception:
            return []
        if expected not in detected:
            missing.append(expected)
    return missing


def _inspect_params(path: Path, warnings: list[str], errors: list[str], suggestions: list[str]) -> dict[str, Any]:
    summary = {
        "exists": path.exists(),
        "parseable": False,
        "parameter_count": 0,
        "parameter_names": [],
        "has_param_space": False,
    }
    if not path.exists():
        return summary
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        errors.append(f"params.yaml could not be parsed: {exc}")
        suggestions.append("Check params.yaml syntax before generating candidate parameters.")
        return summary

    summary["parseable"] = True
    if isinstance(payload, dict):
        parameters = payload.get("parameters")
        if isinstance(parameters, dict):
            names = sorted(str(name) for name in parameters)
            summary["has_param_space"] = True
        elif _looks_like_param_space(payload):
            names = sorted(str(name) for name in payload)
            summary["has_param_space"] = True
        else:
            names = []
            warnings.append("params.yaml is parseable but no parameter space was detected.")
        summary["parameter_names"] = names
        summary["parameter_count"] = len(names)
    else:
        warnings.append("params.yaml is parseable but does not contain a mapping.")
    return summary


def _looks_like_param_space(payload: dict[Any, Any]) -> bool:
    if not payload:
        return False
    return all(isinstance(value, (dict, list, tuple, int, float, str, bool)) for value in payload.values())


def _inspect_netlist(input_dir: Path, warnings: list[str]) -> dict[str, Any]:
    path = next((input_dir / name for name in NETLIST_FILENAMES if (input_dir / name).exists()), None)
    summary = {
        "netlist_available": path is not None,
        "filename": path.name if path else None,
        "line_count": 0,
        "mos_like_device_count": 0,
        "capacitor_like_count": 0,
        "resistor_like_count": 0,
        "subckt_count": 0,
        "parser_warnings": [],
    }
    if path is None:
        return summary

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    meaningful = [line.strip() for line in lines if line.strip() and not line.strip().startswith("*")]
    summary["line_count"] = len(lines)
    summary["mos_like_device_count"] = sum(1 for line in meaningful if re.match(r"^(?:m|xm)\S*", line, flags=re.IGNORECASE))
    summary["capacitor_like_count"] = sum(1 for line in meaningful if re.match(r"^c\S*", line, flags=re.IGNORECASE))
    summary["resistor_like_count"] = sum(1 for line in meaningful if re.match(r"^r\S*", line, flags=re.IGNORECASE))
    summary["subckt_count"] = sum(1 for line in meaningful if line.upper().startswith(".SUBCKT"))

    try:
        parsed = parse_netlist(path)
        summary["parser_warnings"] = parsed.warnings[:8]
        summary["subckt_count"] = max(int(summary["subckt_count"]), len(parsed.subckts))
    except Exception as exc:
        warnings.append(f"Netlist parser could not fully parse the uploaded netlist: {exc}")
    return summary


def _inspect_attachments(input_dir: Path) -> dict[str, Any]:
    attachments_dir = input_dir / "attachments"
    files = []
    if attachments_dir.exists():
        for path in sorted(attachments_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                files.append({"filename": path.name, "size_bytes": path.stat().st_size, "extension": path.suffix.lower()})
    return {
        "image_count": len(files),
        "images": files,
        "image_analysis_enabled": False,
    }
