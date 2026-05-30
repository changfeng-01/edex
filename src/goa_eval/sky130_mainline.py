from __future__ import annotations

from pathlib import Path
import os
import shutil
from typing import Any

import pandas as pd
import yaml

from goa_eval.evidence import build_evidence_metadata, infer_evidence_level
from goa_eval.io_utils import write_json
from goa_eval.multi_round_optimizer import enrich_history_row, run_multi_round_optimization
from goa_eval.sky130_sweep import Sky130DependencyError, run_sky130_sweep


def run_sky130_mainline(
    *,
    sweep_path: Path,
    output_root: Path,
    validation_config_path: Path | None = None,
    rounds: int = 1,
    max_runs_per_round: int = 3,
    patience: int = 2,
    min_improvement: float = 0.0,
    exploration_ratio: float = 0.25,
    pdk_root: Path | None = None,
    split: str = "train",
    max_rows: int = 1,
    topology: str | None = None,
    source_dataset: str | None = None,
    dataset_name: str = "pphilip/analog-circuits-sky130",
    mock_dataset_json: Path | None = None,
    mock_ngspice: bool = False,
    mock_if_unavailable: bool = True,
    require_real_ngspice: bool = False,
    ngspice_cmd: str = "ngspice",
    spec_path: Path = Path("config/sky130_transient_spec.yaml"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    max_candidates: int = 10,
    seed: int = 42,
    strategy: str = "adaptive",
    full_validation: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    validation_config = _load_yaml(validation_config_path)
    target_config = validation_config.get("target", {}) if isinstance(validation_config.get("target"), dict) else {}
    target_metric = str(target_config.get("metric", "Max_overlap_ratio"))
    target_threshold = float(target_config.get("threshold", 0.1))
    if require_real_ngspice and mock_ngspice:
        raise Sky130DependencyError("--require-real-ngspice cannot be combined with --mock-ngspice.")
    if require_real_ngspice:
        mock_if_unavailable = False
    effective_mock_ngspice, preflight = _preflight(
        pdk_root=pdk_root,
        ngspice_cmd=ngspice_cmd,
        mock_ngspice=mock_ngspice,
        mock_if_unavailable=mock_if_unavailable,
        require_real_ngspice=require_real_ngspice,
        sweep_path=sweep_path,
        validation_config_path=validation_config_path,
        mock_dataset_json=mock_dataset_json,
    )
    evidence_metadata = build_evidence_metadata(
        simulation_backend="mock_ngspice" if effective_mock_ngspice else "ngspice",
        mock_used=effective_mock_ngspice,
        pdk_available=bool(preflight["pdk_available"]),
        ngspice_available=bool(preflight["ngspice_available"]),
    )
    optimizer_validation_path = _write_optimizer_validation_config(output_root, validation_config)
    run_multi_round_optimization(
        sweep_path=sweep_path,
        output_root=output_root,
        rounds=rounds,
        max_runs_per_round=max_runs_per_round,
        patience=patience,
        min_improvement=min_improvement,
        exploration_ratio=exploration_ratio,
        pdk_root=pdk_root,
        split=split,
        max_rows=max_rows,
        topology=topology,
        source_dataset=source_dataset,
        dataset_name=dataset_name,
        mock_dataset_json=mock_dataset_json,
        mock_ngspice=effective_mock_ngspice,
        ngspice_cmd=ngspice_cmd,
        spec_path=spec_path,
        param_space_path=param_space_path,
        max_candidates=max_candidates,
        seed=seed,
        strategy=strategy,
        validation_config_path=optimizer_validation_path,
    )
    validation_cases = _run_validation_cases(
        output_root=output_root,
        sweep_path=sweep_path,
        validation_config=validation_config,
        target_metric=target_metric,
        target_threshold=target_threshold,
        full_validation=full_validation,
        pdk_root=pdk_root,
        split=split,
        max_rows=max_rows,
        topology=topology,
        source_dataset=source_dataset,
        dataset_name=dataset_name,
        mock_dataset_json=mock_dataset_json,
        mock_ngspice=effective_mock_ngspice,
        ngspice_cmd=ngspice_cmd,
        spec_path=spec_path,
        param_space_path=param_space_path,
        max_candidates=max_candidates,
        seed=seed,
    )
    payload = _mainline_payload(
        output_root=output_root,
        preflight=preflight,
        full_validation=full_validation,
        validation_cases=validation_cases,
        target_metric=target_metric,
        target_threshold=target_threshold,
        evidence_metadata=evidence_metadata,
    )
    write_json(output_root / "mainline_validation.json", payload)
    _write_mainline_report(output_root / "sky130_mainline_report.md", payload)
    validation_rows = _validation_rows_with_rollup(validation_cases, payload["validation_matrix_summary"])
    pd.DataFrame(validation_rows).to_csv(output_root / "validation_summary.csv", index=False, encoding="utf-8-sig")
    return payload


def _preflight(
    *,
    pdk_root: Path | None,
    ngspice_cmd: str,
    mock_ngspice: bool,
    mock_if_unavailable: bool,
    require_real_ngspice: bool,
    sweep_path: Path,
    validation_config_path: Path | None,
    mock_dataset_json: Path | None,
) -> tuple[bool, dict[str, Any]]:
    env_pdk = _env_pdk_root()
    pdk_available = bool((pdk_root is not None and pdk_root.exists()) or env_pdk is not None)
    ngspice_available = bool(_command_available(ngspice_cmd))
    missing = []
    if not pdk_available:
        missing.append("pdk_root")
    if not ngspice_available:
        missing.append("ngspice")
    if require_real_ngspice and missing:
        raise Sky130DependencyError(
            "--require-real-ngspice requires real ngspice and a SKY130 PDK; missing: "
            + ", ".join(missing)
        )
    effective_mock = bool(mock_ngspice or (mock_if_unavailable and missing))
    return effective_mock, {
        "mock_ngspice": effective_mock,
        "mock_requested": mock_ngspice,
        "mock_if_unavailable": mock_if_unavailable,
        "require_real_ngspice": require_real_ngspice,
        "fallback_reason": ", ".join(missing) if effective_mock and not mock_ngspice else "",
        "pdk_root": str(pdk_root) if pdk_root else "",
        "env_pdk_root": str(env_pdk) if env_pdk else "",
        "pdk_available": pdk_available,
        "ngspice_cmd": ngspice_cmd,
        "ngspice_available": ngspice_available,
        "sweep_config": str(sweep_path),
        "sweep_config_exists": sweep_path.exists(),
        "validation_config": str(validation_config_path) if validation_config_path else "",
        "validation_config_exists": validation_config_path.exists() if validation_config_path else False,
        "mock_dataset_json": str(mock_dataset_json) if mock_dataset_json else "",
        "mock_dataset_json_exists": mock_dataset_json.exists() if mock_dataset_json else False,
    }


def _command_available(command: str) -> bool:
    path = Path(command)
    if path.exists():
        return True
    return shutil.which(command) is not None


def _env_pdk_root() -> Path | None:
    raw = os.environ.get("PDK_ROOT") or os.environ.get("SKYWATER_PDK_ROOT")
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def _write_optimizer_validation_config(output_root: Path, validation_config: dict[str, Any]) -> Path:
    payload: dict[str, Any] = {}
    if isinstance(validation_config.get("target"), dict):
        payload["target"] = validation_config["target"]
    if isinstance(validation_config.get("candidate_replay"), dict):
        payload["candidate_replay"] = validation_config["candidate_replay"]
    path = output_root / "mainline_optimizer_validation.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _run_validation_cases(
    *,
    output_root: Path,
    sweep_path: Path,
    validation_config: dict[str, Any],
    target_metric: str,
    target_threshold: float,
    full_validation: bool,
    pdk_root: Path | None,
    split: str,
    max_rows: int,
    topology: str | None,
    source_dataset: str | None,
    dataset_name: str,
    mock_dataset_json: Path | None,
    mock_ngspice: bool,
    ngspice_cmd: str,
    spec_path: Path,
    param_space_path: Path,
    max_candidates: int,
    seed: int,
) -> list[dict[str, Any]]:
    matrix = validation_config.get("validation_matrix", [])
    if not isinstance(matrix, list):
        matrix = []
    matrix = _ensure_nominal_rerun(matrix)
    best = _best_leaderboard_row(output_root)
    target_passed = best.get("target_passed") is True or str(best.get("target_passed")).lower() == "true"
    base_parameters = _best_parameter_values(sweep_path, best)
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(matrix, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"validation_{index}")
        full_only = name.lower() in {"pvt_load", "pvt", "full_validation"}
        row = _base_validation_row(name, best, target_metric, target_threshold, full_validation=full_validation)
        if not target_passed:
            row.update({"validation_status": "skipped", "skip_reason": "target metric not passed"})
        elif full_only and not full_validation:
            row.update({"validation_status": "skipped", "skip_reason": "full validation disabled in lightweight mode"})
        else:
            row.update(
                _execute_validation_case(
                    output_root=output_root,
                    name=name,
                    index=index,
                    case=item,
                    sweep_path=sweep_path,
                    base_parameters=base_parameters,
                    target_metric=target_metric,
                    target_threshold=target_threshold,
                    pdk_root=pdk_root,
                    split=split,
                    max_rows=max_rows,
                    topology=topology,
                    source_dataset=source_dataset,
                    dataset_name=dataset_name,
                    mock_dataset_json=mock_dataset_json,
                    mock_ngspice=mock_ngspice,
                    ngspice_cmd=ngspice_cmd,
                    spec_path=spec_path,
                    param_space_path=param_space_path,
                    max_candidates=max_candidates,
                    seed=seed + index,
                )
            )
        rows.append(row)
    return rows


def _execute_validation_case(
    *,
    output_root: Path,
    name: str,
    index: int,
    case: dict[str, Any],
    sweep_path: Path,
    base_parameters: dict[str, dict[str, Any]],
    target_metric: str,
    target_threshold: float,
    pdk_root: Path | None,
    split: str,
    max_rows: int,
    topology: str | None,
    source_dataset: str | None,
    dataset_name: str,
    mock_dataset_json: Path | None,
    mock_ngspice: bool,
    ngspice_cmd: str,
    spec_path: Path,
    param_space_path: Path,
    max_candidates: int,
    seed: int,
) -> dict[str, Any]:
    case_dir = output_root / "validation" / _safe_name(name)
    case_sweep_path = output_root / f"validation_{index:03d}_{_safe_name(name)}.yaml"
    case_config = _validation_sweep_config(sweep_path, base_parameters, case)
    case_sweep_path.write_text(yaml.safe_dump(case_config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    summaries = run_sky130_sweep(
        sweep_path=case_sweep_path,
        output_root=case_dir,
        pdk_root=pdk_root,
        split=split,
        max_rows=max_rows,
        topology=topology,
        source_dataset=source_dataset,
        dataset_name=dataset_name,
        mock_dataset_json=mock_dataset_json,
        mock_ngspice=mock_ngspice,
        ngspice_cmd=ngspice_cmd,
        spec_path=spec_path,
        param_space_path=param_space_path,
        max_candidates=max_candidates,
        seed=seed,
        max_runs=int(case.get("max_runs", case_config.get("max_runs", 1)) or 1),
    )
    enriched = [
        enrich_history_row(
            {**summary, "run_dir": str(case_dir / str(summary.get("run_dir", "")))},
            target_metric=target_metric,
            target_threshold=target_threshold,
        )
        for summary in summaries
    ]
    statuses = [str(row.get("status", "")).lower() for row in enriched]
    target_statuses = [str(row.get("target_status", "")).lower() for row in enriched]
    if not enriched:
        status = "not_evaluable"
    elif any(status == "failed" for status in statuses):
        status = "failed"
    elif any(target == "not_evaluable" for target in target_statuses):
        status = "not_evaluable"
    elif all(target == "passed" for target in target_statuses):
        status = "passed"
    else:
        status = "failed"
    values = [_as_float(row.get("target_value")) for row in enriched]
    values = [value for value in values if value is not None]
    return {
        "validation_status": status,
        "skip_reason": "",
        "validation_output_dir": str(case_dir.relative_to(output_root)),
        "validation_sweep_config": case_sweep_path.name,
        "validation_run_count": len(enriched),
        "worst_target_value": max(values) if values else "",
        "best_target_value": min(values) if values else "",
    }


def _base_validation_row(
    name: str,
    best: dict[str, Any],
    target_metric: str,
    target_threshold: float,
    *,
    full_validation: bool,
) -> dict[str, Any]:
    return {
        "validation_name": name,
        "validation_status": "not_evaluable",
        "skip_reason": "",
        "source_run_dir": best.get("run_dir", ""),
        "target_metric": best.get("target_metric", target_metric),
        "target_threshold": best.get("target_threshold", target_threshold),
        "target_value": best.get("target_value", ""),
        "target_passed": best.get("target_passed", ""),
        "full_validation_enabled": bool(full_validation),
        "validation_output_dir": "",
        "validation_sweep_config": "",
        "validation_run_count": 0,
        "worst_target_value": "",
        "best_target_value": "",
    }


def _mainline_payload(
    *,
    output_root: Path,
    preflight: dict[str, Any],
    full_validation: bool,
    validation_cases: list[dict[str, Any]],
    target_metric: str,
    target_threshold: float,
    evidence_metadata: dict[str, Any],
) -> dict[str, Any]:
    best = _best_leaderboard_row(output_root)
    matrix_summary = _validation_matrix_summary(validation_cases, target_metric)
    optimizer_claim_level = _optimizer_claim_level(best, validation_cases, matrix_summary)
    evidence_metadata = {
        **evidence_metadata,
        "optimizer_claim_level": optimizer_claim_level,
        "evidence_level": infer_evidence_level(
            simulation_backend=str(evidence_metadata.get("simulation_backend", "external_csv")),
            mock_used=bool(evidence_metadata.get("mock_used")),
            pdk_available=bool(evidence_metadata.get("pdk_available")),
            ngspice_available=bool(evidence_metadata.get("ngspice_available")),
            optimizer_claim_level=optimizer_claim_level,
        ),
    }
    return {
        "schema_version": 1,
        "mode": "full_validation" if full_validation else "lightweight",
        "full_validation": bool(full_validation),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        **evidence_metadata,
        "target": {
            "metric": target_metric,
            "threshold": target_threshold,
            "status": best.get("target_status", "not_evaluable"),
            "passed": best.get("target_passed", ""),
            "value": best.get("target_value", ""),
        },
        "best_run": {
            "run_dir": best.get("run_dir", ""),
            "overall_score": best.get("overall_score", ""),
            "rank_status": best.get("rank_status", ""),
            "candidate_source": best.get("candidate_source", ""),
            "source_candidate_id": best.get("source_candidate_id", ""),
        },
        "preflight": preflight,
        "validation_cases": validation_cases,
        "validation_matrix_summary": matrix_summary,
        "artifacts": {
            "leaderboard": "optimization_leaderboard.csv",
            "history": "optimization_history.json",
            "round_summary": "round_summary.csv",
            "best_next_candidates": "best_next_candidates.csv",
            "validation_summary": "validation_summary.csv",
            "report": "sky130_mainline_report.md",
        },
    }


def _write_mainline_report(path: Path, payload: dict[str, Any]) -> None:
    target = payload["target"]
    best = payload["best_run"]
    lines = [
        "# SKY130 Mainline Report",
        "",
        f"- Mode: {payload['mode']}",
        f"- Data source: {payload['data_source']}",
        f"- Engineering validity: {payload['engineering_validity']}",
        f"- Evidence level: {payload['evidence_level']}",
        f"- Simulation backend: {payload['simulation_backend']}",
        f"- Mock used: {payload['mock_used']}",
        f"- Reportable as real ngspice: {payload['reportable_as_real_ngspice']}",
        f"- Optimizer claim level: {payload['optimizer_claim_level']}",
        f"- Target: {target['metric']} < {target['threshold']}",
        f"- Target status: {target['status']}",
        f"- Target value: {target['value']}",
        f"- Best run: {best['run_dir']}",
        f"- Best score: {best['overall_score']}",
        "",
        "## Validation Cases",
        "",
    ]
    for case in payload["validation_cases"]:
        reason = f" ({case['skip_reason']})" if case.get("skip_reason") else ""
        lines.append(f"- {case['validation_name']}: {case['validation_status']}{reason}")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This artifact is simulation_only. It supports software flow checks, parameter suggestions, and ngspice-based comparison only.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _ensure_nominal_rerun(matrix: list[Any]) -> list[dict[str, Any]]:
    normalized = [item for item in matrix if isinstance(item, dict)]
    names = {str(item.get("name", "")).lower() for item in normalized}
    if "nominal_rerun" not in names:
        return [*normalized, {"name": "nominal_rerun", "max_runs": 1}]
    return normalized


def _validation_matrix_summary(cases: list[dict[str, Any]], target_metric: str) -> dict[str, Any]:
    count = len(cases)
    pass_count = sum(1 for case in cases if str(case.get("validation_status")) == "passed")
    fail_count = sum(1 for case in cases if str(case.get("validation_status")) == "failed")
    not_evaluable_count = count - pass_count - fail_count
    worst_case = _worst_validation_case(cases)
    return {
        "validation_matrix_pass_rate": (pass_count / count) if count else 0.0,
        "validation_case_count": count,
        "validation_pass_count": pass_count,
        "validation_fail_count": fail_count,
        "validation_not_evaluable_count": not_evaluable_count,
        "worst_case_name": worst_case.get("validation_name", ""),
        "worst_case_metric": worst_case.get("target_metric", target_metric),
        "worst_case_value": worst_case.get("_worst_value", ""),
    }


def _validation_rows_with_rollup(cases: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**case, **summary} for case in cases]


def _worst_validation_case(cases: list[dict[str, Any]]) -> dict[str, Any]:
    best_case: dict[str, Any] = {}
    best_value: float | None = None
    for case in cases:
        value = _as_float(case.get("worst_target_value"))
        if value is None:
            value = _as_float(case.get("target_value"))
        if value is None:
            continue
        if best_value is None or value > best_value:
            best_value = value
            best_case = dict(case)
            best_case["_worst_value"] = value
    return best_case


def _optimizer_claim_level(best: dict[str, Any], cases: list[dict[str, Any]], matrix_summary: dict[str, Any]) -> str:
    if matrix_summary.get("validation_case_count") and matrix_summary.get("validation_pass_count") == matrix_summary.get("validation_case_count"):
        return "validation_matrix_passed"
    for case in cases:
        if str(case.get("validation_name")).lower() == "nominal_rerun" and str(case.get("validation_status")) == "passed":
            return "nominal_rerun_passed"
    if best.get("target_passed") is True or str(best.get("target_passed")).lower() == "true":
        return "nominal_rerun_passed"
    return "candidate_generated"


def _best_leaderboard_row(output_root: Path) -> dict[str, Any]:
    path = output_root / "optimization_leaderboard.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    if frame.empty:
        return {}
    return frame.iloc[0].to_dict()


def _best_parameter_values(sweep_path: Path, best: dict[str, Any]) -> dict[str, dict[str, Any]]:
    config = _load_yaml(sweep_path)
    parameters = config.get("parameters", {})
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(parameters, dict):
        return result
    for name, spec in parameters.items():
        if not isinstance(spec, dict):
            continue
        value = best.get(name)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            values = spec.get("values", [])
            value = values[0] if isinstance(values, list) and values else ""
        if value == "":
            continue
        result[name] = {"target": spec.get("target"), "values": [str(value)]}
    return result


def _validation_sweep_config(sweep_path: Path, base_parameters: dict[str, dict[str, Any]], case: dict[str, Any]) -> dict[str, Any]:
    source = _load_yaml(sweep_path)
    parameters = dict(base_parameters)
    case_parameters = case.get("parameters", {})
    if isinstance(case_parameters, dict):
        for name, spec in case_parameters.items():
            if isinstance(spec, dict):
                parameters[name] = spec
    return {
        "max_runs": int(case.get("max_runs", 1) or 1),
        "parameters": parameters or source.get("parameters", {}),
    }


def _safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value).strip("_")
    return safe or "validation"


def _as_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
