from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import shutil
import subprocess
from typing import Any, Iterable

import numpy as np
import pandas as pd

from goa_eval.io_utils import write_json
from goa_eval.netlist_structure import write_netlist_structure
from goa_eval.optimizer import constrained_random_candidates, load_param_space, write_candidate_outputs
from goa_eval.parsers.netlist_parser import parse_netlist
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown


DEFAULT_DATASET = "pphilip/analog-circuits-sky130"
DEFAULT_CONFIG = "with_testbench"


class Sky130DependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedSky130Run:
    run_dir: Path
    testbench_path: Path
    raw_waveform_path: Path
    waveform_path: Path
    node_map: dict[str, str]


def run_sky130_transient(
    *,
    output_root: Path,
    split: str = "train",
    max_rows: int = 5,
    topology: str | None = None,
    source_dataset: str | None = None,
    dataset_name: str = DEFAULT_DATASET,
    mock_dataset_json: Path | None = None,
    mock_ngspice: bool = False,
    ngspice_cmd: str = "ngspice",
    spec_path: Path = Path("config/sky130_transient_spec.yaml"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    max_candidates: int = 10,
    seed: int = 42,
    skip_netlist_structure: bool = False,
) -> list[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    if not mock_ngspice and shutil.which(ngspice_cmd) is None:
        raise Sky130DependencyError(f'ngspice executable not found: "{ngspice_cmd}". Install ngspice or use --mock-ngspice for tests.')
    rows = load_sky130_rows(
        split=split,
        max_rows=max_rows,
        topology=topology,
        source_dataset=source_dataset,
        dataset_name=dataset_name,
        mock_dataset_json=mock_dataset_json,
    )
    summaries: list[dict] = []
    for index, row in enumerate(rows, start=1):
        run_dir = output_root / _run_dir_name(index, row)
        result = process_sky130_row(
            row=row,
            run_dir=run_dir,
            split=split,
            index=index,
            mock_ngspice=mock_ngspice,
            ngspice_cmd=ngspice_cmd,
            spec_path=spec_path,
            param_space_path=param_space_path,
            max_candidates=max_candidates,
            seed=seed,
            skip_netlist_structure=skip_netlist_structure,
        )
        summaries.append(result)
    _write_runs_summary(output_root / "sky130_runs.csv", summaries)
    return summaries


def load_sky130_rows(
    *,
    split: str,
    max_rows: int,
    topology: str | None,
    source_dataset: str | None,
    dataset_name: str,
    mock_dataset_json: Path | None,
) -> list[dict]:
    if mock_dataset_json is not None:
        raw = json.loads(mock_dataset_json.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else [raw]
    else:
        try:
            from datasets import load_dataset
        except ModuleNotFoundError as exc:
            raise Sky130DependencyError(
                'Missing optional dependency "datasets". Install with: python -m pip install -e ".[sky130]"'
            ) from exc
        rows = list(load_dataset(dataset_name, DEFAULT_CONFIG, split=split))

    selected: list[dict] = []
    for row in rows:
        row = dict(row)
        if topology and str(row.get("topology", "")) != topology:
            continue
        if source_dataset and str(row.get("source_dataset", "")) != source_dataset:
            continue
        selected.append(row)
        if len(selected) >= max(0, int(max_rows)):
            break
    return selected


def process_sky130_row(
    *,
    row: dict,
    run_dir: Path,
    split: str,
    index: int,
    mock_ngspice: bool,
    ngspice_cmd: str,
    spec_path: Path,
    param_space_path: Path,
    max_candidates: int,
    seed: int,
    skip_netlist_structure: bool = False,
) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    provenance = _provenance(row, split, index, run_dir)
    structure = write_netlist_structure_artifacts(row, run_dir, skip=skip_netlist_structure)
    try:
        node_map = build_output_node_map(row)
        if not node_map:
            return _status(run_dir, provenance, "skipped", "no output_v nodes found", structure=structure)
        if not str(row.get("testbench_spice", "")).strip():
            return _status(run_dir, provenance, "skipped", "missing testbench_spice", structure=structure)
        prepared = prepare_testbench(row, run_dir, node_map)
        if mock_ngspice:
            write_mock_waveform(prepared.waveform_path, node_map)
            (run_dir / "ngspice.log").write_text("mock ngspice run\n", encoding="utf-8")
        else:
            run_ngspice(prepared, ngspice_cmd=ngspice_cmd)
            convert_ngspice_waveform(prepared.raw_waveform_path, prepared.waveform_path, node_map)
        summary = run_real_waveform_evaluation(
            waveform_path=prepared.waveform_path,
            internal_waveform_path=None,
            output_dir=run_dir,
            spec_path=spec_path,
            output_nodes=list(node_map),
            topology=row.get("topology"),
        )
        _write_sky130_metadata(run_dir, provenance, node_map, structure)
        _write_recommendations_and_candidates(run_dir, param_space_path, max_candidates=max_candidates, seed=seed)
        score = json.loads((run_dir / "score_summary.json").read_text(encoding="utf-8"))
        analysis = json.loads((run_dir / "analysis_metrics.json").read_text(encoding="utf-8")) if (run_dir / "analysis_metrics.json").exists() else {}
        return _status(
            run_dir,
            provenance,
            "evaluated",
            "",
            overall_score=score.get("overall_score"),
            failure_reasons=score.get("failure_reasons", []),
            structure=structure,
            score=score,
            analysis=analysis,
        )
    except Sky130DependencyError as exc:
        return _status(run_dir, provenance, "failed", str(exc), structure=structure)
    except Exception as exc:
        return _status(run_dir, provenance, "failed", f"{type(exc).__name__}: {exc}", structure=structure)


def build_output_node_map(row: dict) -> dict[str, str]:
    netlist = row.get("netlist_json")
    if isinstance(netlist, str):
        try:
            netlist = json.loads(netlist)
        except json.JSONDecodeError:
            netlist = {}
    outputs: list[str] = []
    for item in _walk_json(netlist):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", item.get("port_role", ""))).lower()
        if role != "output_v":
            continue
        name = item.get("name") or item.get("node") or item.get("net") or item.get("node_name")
        if name is not None and str(name) not in outputs:
            outputs.append(str(name))
    return {f"o{index}": node for index, node in enumerate(outputs, start=1)}


def prepare_testbench(row: dict, run_dir: Path, node_map: dict[str, str]) -> PreparedSky130Run:
    run_dir.mkdir(parents=True, exist_ok=True)
    testbench_path = run_dir / "testbench.spice"
    raw_waveform_path = run_dir / "waveform_raw.txt"
    waveform_path = run_dir / "waveform.csv"
    write_json(run_dir / "dataset_row.json", row)
    write_json(run_dir / "node_map.json", node_map)
    testbench = ensure_waveform_control(str(row.get("testbench_spice", "")), node_map, raw_waveform_path.name)
    testbench_path.write_text(testbench, encoding="utf-8")
    return PreparedSky130Run(
        run_dir=run_dir,
        testbench_path=testbench_path,
        raw_waveform_path=raw_waveform_path,
        waveform_path=waveform_path,
        node_map=node_map,
    )


def write_netlist_structure_artifacts(row: dict, run_dir: Path, *, skip: bool = False) -> dict:
    if skip:
        return {"structure_status": "skipped", "structure_message": "netlist structure parsing disabled"}
    selected = _select_source_netlist(row)
    if selected is None:
        return {"structure_status": "skipped", "structure_message": "missing netlist text"}
    field_name, netlist_text = selected
    source_path = run_dir / "source_netlist.spice"
    structure_path = run_dir / "netlist_structure.json"
    source_path.write_text(_strip_control_blocks(netlist_text).rstrip() + "\n", encoding="utf-8")
    try:
        summary = write_netlist_structure(structure_path, parse_netlist(source_path))
    except Exception as exc:
        return {
            "structure_status": "failed",
            "structure_message": f"{type(exc).__name__}: {exc}",
            "source_netlist_path": source_path.name,
        }
    return {
        "structure_status": "generated",
        "structure_message": "",
        "source_netlist_field": field_name,
        "source_netlist_path": source_path.name,
        "netlist_structure_path": structure_path.name,
        "structure_scalar_features": summary.get("scalar_features", {}),
        "structure_warning_count": len(summary.get("warnings", [])),
    }


def ensure_waveform_control(testbench: str, node_map: dict[str, str], output_name: str) -> str:
    lower = testbench.lower()
    if ".control" in lower and "wrdata" in lower:
        return testbench
    command = "run" if ".tran" in lower else "tran 1n 1u"
    vectors = " ".join(f"v({node})" for node in node_map.values())
    control = "\n".join(
        [
            "",
            ".control",
            "set filetype=ascii",
            "set wr_singlescale",
            "set wr_vecnames",
            command,
            f"wrdata {output_name} time {vectors}",
            "quit",
            ".endc",
            "",
        ]
    )
    lines = testbench.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() == ".end":
            return "\n".join([*lines[:index], control, *lines[index:]]) + "\n"
    return testbench.rstrip() + control + "\n.end\n"


def run_ngspice(prepared: PreparedSky130Run, *, ngspice_cmd: str = "ngspice") -> None:
    if shutil.which(ngspice_cmd) is None:
        raise Sky130DependencyError(f'ngspice executable not found: "{ngspice_cmd}". Install ngspice or use --mock-ngspice for tests.')
    result = subprocess.run(
        [ngspice_cmd, "-b", prepared.testbench_path.name],
        cwd=prepared.run_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    (prepared.run_dir / "ngspice.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"ngspice failed with exit code {result.returncode}")
    if not prepared.raw_waveform_path.exists() or prepared.raw_waveform_path.stat().st_size == 0:
        raise RuntimeError("ngspice did not produce waveform_raw.txt")


def convert_ngspice_waveform(raw_path: Path, waveform_path: Path, node_map: dict[str, str]) -> None:
    if not raw_path.exists() or raw_path.stat().st_size == 0:
        raise RuntimeError(f"empty ngspice waveform output: {raw_path}")
    frame = pd.read_csv(raw_path, sep=r"\s+", engine="python", comment="#")
    if frame.empty:
        raise RuntimeError(f"empty ngspice waveform table: {raw_path}")
    columns = list(frame.columns)
    time_column = next((column for column in columns if str(column).lower() in {"time", "time[0]"}), columns[0])
    output = pd.DataFrame({"TIME": pd.to_numeric(frame[time_column], errors="coerce")})
    for alias, original in node_map.items():
        column = _find_vector_column(columns, original)
        if column is None:
            raise RuntimeError(f"ngspice output missing vector for {original}")
        output[f"v({alias})"] = pd.to_numeric(frame[column], errors="coerce")
    output = output.dropna(subset=["TIME"]).sort_values("TIME")
    output.to_csv(waveform_path, index=False)


def write_mock_waveform(path: Path, node_map: dict[str, str]) -> None:
    time = np.arange(0.0, 80e-9, 1.0e-9)
    frame = pd.DataFrame({"TIME": time})
    for index, alias in enumerate(node_map, start=1):
        start = 8e-9 + (index - 1) * 10e-9
        frame[f"v({alias})"] = np.where((time >= start) & (time < start + 14e-9), 1.8, 0.0)
    frame.to_csv(path, index=False)


def _write_recommendations_and_candidates(run_dir: Path, param_space_path: Path, *, max_candidates: int, seed: int) -> None:
    summary_path = run_dir / "real_summary.json"
    score_path = run_dir / "score_summary.json"
    metrics_path = run_dir / "real_metrics.csv"
    recommendations_path = run_dir / "recommendations.md"
    write_recommendations_markdown(
        summary_path=summary_path,
        score_path=score_path,
        metrics_path=metrics_path,
        output_path=recommendations_path,
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    score = json.loads(score_path.read_text(encoding="utf-8"))
    metrics = pd.read_csv(metrics_path)
    recommendations = build_recommendations(summary, score, metrics)
    candidates = constrained_random_candidates(
        load_param_space(param_space_path),
        recommendations,
        max_candidates=max_candidates,
        seed=seed,
    )
    write_candidate_outputs(candidates, csv_path=run_dir / "next_candidates.csv", markdown_path=run_dir / "next_candidates.md")


def _write_sky130_metadata(run_dir: Path, provenance: dict, node_map: dict[str, str], structure: dict) -> None:
    metadata = {
        **provenance,
        "original_output_nodes": list(node_map.values()),
        "structure_status": structure.get("structure_status"),
        "structure_message": structure.get("structure_message"),
        "structure_files": {
            "source_netlist": structure.get("source_netlist_path"),
            "netlist_structure": structure.get("netlist_structure_path"),
        },
        "structure_scalar_features": structure.get("structure_scalar_features", {}),
    }
    write_json(run_dir / "sky130_metadata.json", metadata)


def _status(
    run_dir: Path,
    provenance: dict,
    status: str,
    message: str,
    *,
    overall_score=None,
    failure_reasons: list[str] | None = None,
    structure: dict | None = None,
    score: dict | None = None,
    analysis: dict | None = None,
) -> dict:
    structure = structure or {}
    score = score or {}
    analysis = analysis or {}
    analysis_flat = _analysis_summary_columns(analysis)
    payload = {
        **provenance,
        "status": status,
        "message": message,
        "overall_score": overall_score,
        "failure_reasons": ";".join(failure_reasons or []),
        "run_dir": run_dir.name,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "structure_status": structure.get("structure_status"),
        "structure_message": structure.get("structure_message"),
        "source_netlist_field": structure.get("source_netlist_field"),
        "source_netlist_path": structure.get("source_netlist_path"),
        "netlist_structure_path": structure.get("netlist_structure_path"),
        "structure_warning_count": structure.get("structure_warning_count"),
        "topology_profile": score.get("topology_profile", analysis.get("topology_profile")),
        **analysis_flat,
        **(structure.get("structure_scalar_features") or {}),
    }
    write_json(run_dir / "sky130_status.json", payload)
    return payload


def _write_runs_summary(path: Path, rows: list[dict]) -> None:
    columns = [
        "status",
        "message",
        "overall_score",
        "failure_reasons",
        "circuit_id",
        "base_circuit_id",
        "topology",
        "source_dataset",
        "pdk",
        "dataset_split",
        "run_dir",
        "data_source",
        "engineering_validity",
        "structure_status",
        "structure_message",
        "source_netlist_field",
        "structure_warning_count",
        "topology_profile",
        "dc_gain_db",
        "bandwidth_3db_hz",
        "unity_gain_hz",
        "static_power_w",
        "switching_threshold_v",
        "frequency_hz",
        "mos_count",
        "cap_count",
        "resistor_count",
        "current_source_count",
        "voltage_source_count",
        "model_count",
        "node_count",
        "max_node_degree",
        "transistor_width_sum",
        "capacitance_sum",
    ]
    pd.DataFrame(rows).reindex(columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def _provenance(row: dict, split: str, index: int, run_dir: Path) -> dict:
    return {
        "circuit_id": str(row.get("circuit_id") or row.get("id") or f"row_{index:04d}"),
        "base_circuit_id": row.get("base_circuit_id"),
        "topology": row.get("topology"),
        "source_dataset": row.get("source_dataset"),
        "pdk": row.get("pdk", "sky130"),
        "dataset_split": split,
        "row_index": index,
        "run_dir": run_dir.name,
    }


def _run_dir_name(index: int, row: dict) -> str:
    label = str(row.get("circuit_id") or row.get("id") or f"row_{index:04d}")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or f"row_{index:04d}"
    return f"{index:04d}_{safe}"


def _walk_json(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _analysis_summary_columns(analysis: dict) -> dict:
    op = analysis.get("op_metrics", {}) or {}
    ac = analysis.get("ac_metrics", {}) or {}
    dc = analysis.get("dc_metrics", {}) or {}
    tran = analysis.get("tran_metrics", {}) or {}
    return {
        "dc_gain_db": ac.get("dc_gain_db"),
        "bandwidth_3db_hz": ac.get("bandwidth_3db_hz"),
        "unity_gain_hz": ac.get("unity_gain_hz"),
        "static_power_w": op.get("static_power_w"),
        "switching_threshold_v": dc.get("switching_threshold_v"),
        "frequency_hz": tran.get("frequency_hz"),
    }


def _select_source_netlist(row: dict) -> tuple[str, str] | None:
    for field_name in ["netlist", "spice_netlist", "testbench_spice"]:
        value = row.get(field_name)
        if value is None:
            continue
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        if text.strip():
            return field_name, text
    return None


def _strip_control_blocks(text: str) -> str:
    lines = []
    in_control = False
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped == ".control":
            in_control = True
            continue
        if in_control:
            if stripped == ".endc":
                in_control = False
            continue
        lines.append(line)
    return "\n".join(lines)


def _find_vector_column(columns: list, original: str) -> str | None:
    normalized = {_normalize_vector_name(str(column)): str(column) for column in columns}
    candidates = [original, f"v({original})", f"V({original})"]
    for candidate in candidates:
        key = _normalize_vector_name(candidate)
        if key in normalized:
            return normalized[key]
    return None


def _normalize_vector_name(name: str) -> str:
    return name.strip().lower().replace("[", "").replace("]", "")
