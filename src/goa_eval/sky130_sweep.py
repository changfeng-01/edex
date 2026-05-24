from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
import json
import os
import re
from typing import Any

import pandas as pd
import yaml

from goa_eval.io_utils import write_json
from goa_eval.sky130_transient import (
    DEFAULT_DATASET,
    Sky130DependencyError,
    load_sky130_rows,
    process_sky130_row,
)


@dataclass(frozen=True)
class RewriteResult:
    success: bool
    text: str
    message: str = ""


def load_sweep_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def generate_sweep_points(config: dict, *, max_runs: int | None = None) -> list[dict[str, object]]:
    explicit_points = config.get("points")
    if isinstance(explicit_points, list):
        limit = int(max_runs if max_runs is not None else config.get("max_runs", len(explicit_points)))
        return [dict(point) for point in explicit_points[: max(0, limit)] if isinstance(point, dict)]
    parameters = config.get("parameters", {}) or {}
    names = list(parameters)
    value_lists = [_values(parameters[name]) for name in names]
    limit = int(max_runs if max_runs is not None else config.get("max_runs", 50))
    points: list[dict[str, object]] = []
    for combo in product(*value_lists):
        points.append(dict(zip(names, combo)))
        if len(points) >= max(0, limit):
            break
    return points


def rewrite_spice_parameters(text: str, values: dict[str, object], targets: dict[str, dict]) -> RewriteResult:
    rewritten = text
    missing: list[str] = []
    for parameter, value in values.items():
        target = str((targets.get(parameter) or {}).get("target", ""))
        if not target:
            missing.append(parameter)
            continue
        updated = _rewrite_one(rewritten, target, str(value))
        if updated is None:
            missing.append(target)
            continue
        rewritten = updated
    if missing:
        return RewriteResult(False, text, f"missing rewrite target(s): {', '.join(missing)}")
    return RewriteResult(True, rewritten)


def run_sky130_sweep(
    *,
    sweep_path: Path,
    output_root: Path,
    pdk_root: Path | None = None,
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
    max_runs: int | None = None,
) -> list[dict]:
    config = load_sweep_config(sweep_path)
    resolved_pdk_root = _resolve_pdk_root(pdk_root, mock_ngspice=mock_ngspice)
    rows = load_sky130_rows(
        split=split,
        max_rows=max_rows,
        topology=topology,
        source_dataset=source_dataset,
        dataset_name=dataset_name,
        mock_dataset_json=mock_dataset_json,
    )
    points = generate_sweep_points(config, max_runs=max_runs)
    output_root.mkdir(parents=True, exist_ok=True)
    targets = dict(config.get("parameters", {}) or {})
    summaries: list[dict] = []
    run_index = 0
    old_env = {"PDK_ROOT": os.environ.get("PDK_ROOT"), "SKYWATER_PDK_ROOT": os.environ.get("SKYWATER_PDK_ROOT")}
    try:
        if resolved_pdk_root is not None:
            os.environ["PDK_ROOT"] = str(resolved_pdk_root)
            os.environ["SKYWATER_PDK_ROOT"] = str(resolved_pdk_root)
        for row_index, row in enumerate(rows, start=1):
            for point_index, point in enumerate(points, start=1):
                run_index += 1
                run_dir = output_root / _sweep_run_dir_name(run_index, row, point_index)
                result = _process_sweep_point(
                    row=dict(row),
                    point=point,
                    targets=targets,
                    run_dir=run_dir,
                    split=split,
                    row_index=row_index,
                    point_index=point_index,
                    mock_ngspice=mock_ngspice,
                    ngspice_cmd=ngspice_cmd,
                    spec_path=spec_path,
                    param_space_path=param_space_path,
                    max_candidates=max_candidates,
                    seed=seed,
                    pdk_root=resolved_pdk_root,
                )
                summaries.append(result)
    finally:
        _restore_env(old_env)
    _write_sweep_outputs(output_root, summaries, targets)
    return summaries


def _process_sweep_point(
    *,
    row: dict,
    point: dict[str, object],
    targets: dict[str, dict],
    run_dir: Path,
    split: str,
    row_index: int,
    point_index: int,
    mock_ngspice: bool,
    ngspice_cmd: str,
    spec_path: Path,
    param_space_path: Path,
    max_candidates: int,
    seed: int,
    pdk_root: Path | None,
) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    rewrite = rewrite_spice_parameters(str(row.get("testbench_spice", "")), point, targets)
    _write_params(run_dir / "params.yaml", row, point, pdk_root)
    if not rewrite.success:
        payload = _sweep_status(row, point, run_dir, split, row_index, point_index, "skipped", rewrite.message)
        write_json(run_dir / "sky130_status.json", payload)
        return payload
    row["testbench_spice"] = rewrite.text
    for field_name in ["spice_netlist", "netlist"]:
        value = row.get(field_name)
        if isinstance(value, str) and value.strip():
            source_rewrite = rewrite_spice_parameters(value, point, targets)
            if source_rewrite.success:
                row[field_name] = source_rewrite.text
    result = process_sky130_row(
        row=row,
        run_dir=run_dir,
        split=split,
        index=row_index,
        mock_ngspice=mock_ngspice,
        ngspice_cmd=ngspice_cmd,
        spec_path=spec_path,
        param_space_path=param_space_path,
        max_candidates=max_candidates,
        seed=seed,
    )
    result.update({"sweep_point_index": point_index, "pdk_root": str(pdk_root) if pdk_root else ""})
    result.update(point)
    status_path = run_dir / "sky130_status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status.update({"sweep_point_index": point_index, "pdk_root": str(pdk_root) if pdk_root else "", **point})
        write_json(status_path, status)
    return result


def _write_sweep_outputs(output_root: Path, rows: list[dict], targets: dict[str, dict]) -> None:
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame.to_csv(output_root / "sky130_sweep_runs.csv", index=False, encoding="utf-8-sig")
        frame.to_csv(output_root / "sky130_sweep_leaderboard.csv", index=False, encoding="utf-8-sig")
    else:
        frame.to_csv(output_root / "sky130_sweep_runs.csv", index=False, encoding="utf-8-sig")
        leaderboard = _leaderboard(frame)
        leaderboard.to_csv(output_root / "sky130_sweep_leaderboard.csv", index=False, encoding="utf-8-sig")
    _sensitivity(frame, targets).to_csv(output_root / "sky130_sweep_sensitivity.csv", index=False, encoding="utf-8-sig")
    _write_next_param_space(output_root / "next_param_space.yaml", frame, targets)


def _leaderboard(frame: pd.DataFrame) -> pd.DataFrame:
    ranked = frame.copy()
    ranked["_score"] = pd.to_numeric(ranked.get("overall_score"), errors="coerce").fillna(float("-inf"))
    ranked["_evaluated"] = ranked.get("status", "").eq("evaluated").astype(int)
    ranked = ranked.sort_values(["_evaluated", "_score"], ascending=[False, False])
    return ranked.drop(columns=["_score", "_evaluated"])


def _sensitivity(frame: pd.DataFrame, targets: dict[str, dict]) -> pd.DataFrame:
    rows = []
    if frame.empty or "overall_score" not in frame:
        return pd.DataFrame(columns=["parameter", "best_value", "best_score", "worst_value", "worst_score", "score_delta"])
    scores = pd.to_numeric(frame["overall_score"], errors="coerce")
    for parameter in targets:
        if parameter not in frame:
            continue
        grouped = pd.DataFrame({"value": frame[parameter], "score": scores}).dropna(subset=["score"])
        if grouped.empty:
            continue
        means = grouped.groupby("value", dropna=False)["score"].mean().sort_values(ascending=False)
        rows.append(
            {
                "parameter": parameter,
                "best_value": means.index[0],
                "best_score": means.iloc[0],
                "worst_value": means.index[-1],
                "worst_score": means.iloc[-1],
                "score_delta": means.iloc[0] - means.iloc[-1],
            }
        )
    return pd.DataFrame(rows, columns=["parameter", "best_value", "best_score", "worst_value", "worst_score", "score_delta"])


def _write_next_param_space(path: Path, frame: pd.DataFrame, targets: dict[str, dict]) -> None:
    parameters: dict[str, dict] = {}
    if not frame.empty and "overall_score" in frame:
        scores = pd.to_numeric(frame["overall_score"], errors="coerce")
        for parameter, spec in targets.items():
            values = list(dict.fromkeys(_values(spec)))
            if parameter in frame and scores.notna().any():
                grouped = pd.DataFrame({"value": frame[parameter], "score": scores}).dropna(subset=["score"])
                if not grouped.empty:
                    ordered = list(grouped.groupby("value")["score"].mean().sort_values(ascending=False).index)
                    values = [*ordered, *[value for value in values if value not in ordered]]
            parameters[parameter] = {"target": spec.get("target"), "values": values[:3]}
    else:
        parameters = {name: {"target": spec.get("target"), "values": _values(spec)[:3]} for name, spec in targets.items()}
    path.write_text(yaml.safe_dump({"parameters": parameters}, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _rewrite_one(text: str, target: str, value: str) -> str | None:
    if target.startswith(".param:") or target.startswith("param:"):
        name = target.split(":", 1)[1]
        return _rewrite_param(text, name, value)
    if "." not in target:
        return None
    device_name, field = target.split(".", 1)
    field = field.upper()
    if field == "DC_VALUE":
        return _rewrite_source_dc(text, device_name, value)
    if field in {"W", "L"}:
        return _rewrite_key_value_device(text, device_name, field, value)
    if field in {"C", "R"}:
        return _rewrite_two_terminal_value(text, device_name, value)
    return None


def _rewrite_param(text: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^(\s*\.param\s+{re.escape(name)}\s*=\s*)(\S+)(.*)$", re.IGNORECASE | re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(rf"\g<1>{value}\g<3>", text, count=1)
    lines = text.splitlines()
    insertion = f".param {name}={value}"
    for index, line in enumerate(lines):
        if line.strip().lower() == ".end":
            return "\n".join([*lines[:index], insertion, *lines[index:]]) + "\n"
    return text.rstrip() + "\n" + insertion + "\n"


def _rewrite_key_value_device(text: str, device_name: str, key: str, value: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _line_starts_with_device(line, device_name):
            continue
        pattern = re.compile(rf"(\b{re.escape(key)}\s*=\s*)(\S+)", re.IGNORECASE)
        if not pattern.search(line):
            return None
        lines[index] = pattern.sub(rf"\g<1>{value}", line, count=1)
        return "\n".join(lines) + "\n"
    return None


def _rewrite_two_terminal_value(text: str, device_name: str, value: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _line_starts_with_device(line, device_name):
            continue
        tokens = line.split()
        if len(tokens) < 4:
            return None
        tokens[3] = value
        lines[index] = " ".join(tokens)
        return "\n".join(lines) + "\n"
    return None


def _rewrite_source_dc(text: str, device_name: str, value: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _line_starts_with_device(line, device_name):
            continue
        tokens = line.split()
        if len(tokens) < 4:
            return None
        if len(tokens) >= 5 and tokens[3].upper() == "DC":
            tokens[4] = value
        else:
            tokens = [*tokens[:3], "DC", value]
        lines[index] = " ".join(tokens)
        return "\n".join(lines) + "\n"
    return None


def _line_starts_with_device(line: str, device_name: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("*") or stripped.startswith("."):
        return False
    return stripped.split()[0].lower() == device_name.lower()


def _values(spec: Any) -> list[object]:
    if isinstance(spec, dict):
        values = spec.get("values", [])
        return list(values) if isinstance(values, list) else [values]
    return list(spec) if isinstance(spec, list) else [spec]


def _write_params(path: Path, row: dict, point: dict[str, object], pdk_root: Path | None) -> None:
    payload = {
        "run_id": path.parent.name,
        "circuit_version": row.get("circuit_id") or row.get("id") or "unknown",
        "parameters": point,
        "conditions": {"pdk_root": str(pdk_root) if pdk_root else "", "engineering_validity": "simulation_only"},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _sweep_status(row: dict, point: dict[str, object], run_dir: Path, split: str, row_index: int, point_index: int, status: str, message: str) -> dict:
    payload = {
        "status": status,
        "message": message,
        "overall_score": None,
        "failure_reasons": "",
        "circuit_id": str(row.get("circuit_id") or row.get("id") or f"row_{row_index:04d}"),
        "base_circuit_id": row.get("base_circuit_id"),
        "topology": row.get("topology"),
        "source_dataset": row.get("source_dataset"),
        "pdk": row.get("pdk", "sky130"),
        "dataset_split": split,
        "run_dir": run_dir.name,
        "sweep_point_index": point_index,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        **point,
    }
    return payload


def _sweep_run_dir_name(run_index: int, row: dict, point_index: int) -> str:
    label = str(row.get("circuit_id") or row.get("id") or f"row_{run_index:04d}")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or f"row_{run_index:04d}"
    return f"{run_index:04d}_{safe}_sweep_{point_index:04d}"


def _resolve_pdk_root(pdk_root: Path | None, *, mock_ngspice: bool) -> Path | None:
    if mock_ngspice:
        return pdk_root
    raw = pdk_root or os.environ.get("PDK_ROOT") or os.environ.get("SKYWATER_PDK_ROOT")
    if raw is None:
        raise Sky130DependencyError("PDK root not found. Pass --pdk-root or set PDK_ROOT/SKYWATER_PDK_ROOT.")
    path = Path(raw)
    if not path.exists():
        raise Sky130DependencyError(f"PDK root does not exist: {path}")
    return path


def _restore_env(values: dict[str, str | None]) -> None:
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
