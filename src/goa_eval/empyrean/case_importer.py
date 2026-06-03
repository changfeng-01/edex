from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import pandas as pd
import yaml

from goa_eval.empyrean.manifest import write_empyrean_case_manifest
from goa_eval.empyrean.model_artifact import MODEL_EXTENSIONS, summarize_model_artifacts
from goa_eval.empyrean.pve_report_parser import parse_physical_verification_reports
from goa_eval.empyrean.rc_result_parser import parse_rc_result
from goa_eval.empyrean.schemas import DATA_SOURCE_EXPORTED, ENGINEERING_VALIDITY, evidence_boundary
from goa_eval.empyrean.waveform_adapter import convert_empyrean_waveform_csv
from goa_eval.io_utils import write_json
from goa_eval.optimizer import constrained_random_candidates, load_baseline_params, load_param_space, write_candidate_outputs
from goa_eval.parameter_semantics import load_parameter_semantics
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown


def run_empyrean_import(
    *,
    input_dir: Path,
    output_dir: Path,
    case_id: str,
    spec_path: Path = Path("config/spec.yaml"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    generate_candidates: bool = False,
    stage_count: int | None = None,
    output_node_pattern: str | None = None,
    topology: str | None = None,
    circuit_profile: str | None = None,
    profile_file: Path | None = None,
    params_file: Path | None = None,
    max_candidates: int = 10,
    seed: int = 42,
    data_source: str = DATA_SOURCE_EXPORTED,
) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Empyrean input directory not found: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    discovered = discover_empyrean_case_files(input_dir)
    waveform_path = discovered["waveform"]
    if waveform_path is None:
        raise FileNotFoundError(f"empyrean-import requires an exported waveform CSV under {input_dir}")

    conversion = convert_empyrean_waveform_csv(waveform_path, output_dir)
    physical_summary_path = output_dir / "physical_verification_summary.json"
    parasitic_summary_path = output_dir / "parasitic_summary.json"
    model_summary_path = output_dir / "model_artifact_summary.json"
    physical_summary = parse_physical_verification_reports(discovered["verification_reports"], physical_summary_path)
    parasitic_summary = parse_rc_result(discovered["rc"], parasitic_summary_path)
    model_summary = summarize_model_artifacts(discovered["artifacts"].get("model", []), model_summary_path)

    metadata = {
        "adapter": "empyrean-import",
        "case_id": case_id,
        "input_dir": str(input_dir),
        "data_source": data_source,
        "engineering_validity": ENGINEERING_VALIDITY,
        "toolchain": "empyrean_fpd_offline",
        "execution_mode": "offline_import_only",
        "tool_invocation": False,
        **evidence_boundary(data_source),
        "evidence_level": "level_1_external_csv",
        "simulation_backend": "empyrean_exported_files",
        "mock_used": False,
        "pdk_available": False,
        "ngspice_available": False,
        "reportable_as_real_ngspice": False,
        "optimizer_claim_level": "candidate_generated" if generate_candidates else "evaluation_only",
    }
    write_json(output_dir / "simulation_metadata.json", metadata)
    write_json(
        output_dir / "adapter_status.json",
        {
            "adapter": "empyrean-import",
            "status": "imported",
            "message": "",
            "case_id": case_id,
            "input_dir": str(input_dir),
            "data_source": data_source,
            "engineering_validity": ENGINEERING_VALIDITY,
            "tool_invocation": False,
        },
    )

    summary = run_real_waveform_evaluation(
        waveform_path=Path(conversion.normalized_waveform_path),
        internal_waveform_path=None,
        output_dir=output_dir,
        spec_path=spec_path,
        stage_count=stage_count,
        output_node_pattern=output_node_pattern,
        topology=topology or circuit_profile,
        circuit_profile=circuit_profile,
        profile_file=profile_file,
        evidence_metadata=metadata,
    )
    recommendations = write_recommendations_markdown(
        summary_path=output_dir / "real_summary.json",
        score_path=output_dir / "score_summary.json",
        metrics_path=output_dir / "real_metrics.csv",
        output_path=output_dir / "recommendations.md",
    )
    if generate_candidates:
        score = json.loads((output_dir / "score_summary.json").read_text(encoding="utf-8"))
        metrics = pd.read_csv(output_dir / "real_metrics.csv")
        param_space = load_param_space(param_space_path)
        semantics = load_parameter_semantics(params_file) if params_file else None
        candidates = constrained_random_candidates(
            param_space,
            recommendations or build_recommendations(summary, score, metrics),
            max_candidates=max_candidates,
            seed=seed,
            baseline_params=_load_case_params(discovered.get("params")),
            profile_file=profile_file,
            parameter_semantics=semantics,
        )
        write_candidate_outputs(candidates, csv_path=output_dir / "next_candidates.csv", markdown_path=output_dir / "next_candidates.md")

    manifest = write_empyrean_case_manifest(
        output_dir / "empyrean_case_manifest.json",
        case_id=case_id,
        input_dir=input_dir,
        output_dir=output_dir,
        artifacts=discovered["artifacts"],
        normalized_waveform_path=Path(conversion.normalized_waveform_path),
        physical_verification_summary_path=physical_summary_path,
        parasitic_summary_path=parasitic_summary_path,
        model_artifact_summary_path=model_summary_path,
        data_source=data_source,
    )
    return {
        "case_id": case_id,
        "output_dir": str(output_dir),
        "manifest": manifest,
        "waveform_conversion": conversion.__dict__,
        "physical_verification": physical_summary,
        "parasitic": parasitic_summary,
        "model_artifacts": model_summary,
    }


def discover_empyrean_case_files(input_dir: Path) -> dict[str, Any]:
    files = [path for path in sorted(input_dir.rglob("*")) if path.is_file()]
    waveform = _first_existing(
        [
            input_dir / "simulation" / "waveform.csv",
            input_dir / "waveform.csv",
            *[path for path in files if path.suffix.lower() == ".csv" and "waveform" in path.name.lower()],
        ]
    )
    verification_reports = {
        "drc": _find_by_keywords(files, ["drc"]),
        "lvs": _find_by_keywords(files, ["lvs"]),
        "erc": _find_by_keywords(files, ["erc"]),
        "pve": _find_by_keywords(files, ["pve"]),
    }
    rc = _first_existing(
        [
            input_dir / "rc" / "rc_result.csv",
            input_dir / "rc_result.csv",
            *[path for path in files if _is_rc_file(path)],
        ]
    )
    params = _first_existing([input_dir / "params.yaml", input_dir / "params.yml"])
    artifacts = {
        "simulation": [waveform] if waveform else [],
        "verification": [path for path in verification_reports.values() if path],
        "rc": [rc] if rc else [],
        "model": [path for path in files if _is_under_or_ext(path, input_dir / "model", MODEL_EXTENSIONS)],
        "schematic": [path for path in files if _is_schematic_artifact(path)],
        "layout": [path for path in files if _is_layout_artifact(path)],
    }
    return {
        "waveform": waveform,
        "verification_reports": verification_reports,
        "rc": rc,
        "params": params,
        "artifacts": artifacts,
    }


def _first_existing(paths: list[Path | None]) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    return None


def _find_by_keywords(files: list[Path], keywords: list[str]) -> Path | None:
    supported = {".txt", ".rpt", ".log", ".csv"}
    for path in files:
        name = path.name.lower()
        if path.suffix.lower() in supported and all(keyword in name for keyword in keywords):
            return path
    return None


def _is_rc_file(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in {".csv", ".txt", ".rpt"} and any(token in name for token in ["rc", "parasitic", "rce"])


def _is_under_or_ext(path: Path, directory: Path, extensions: set[str]) -> bool:
    try:
        path.relative_to(directory)
        return path.suffix.lower() in extensions
    except ValueError:
        return path.suffix.lower() in extensions and ("model" in path.name.lower() or path.parent.name.lower() == "model")


def _is_schematic_artifact(path: Path) -> bool:
    name = path.name.lower()
    if path.parent.name.lower() == "schematic":
        return True
    return path.suffix.lower() in {".sp", ".spi", ".spice", ".cdl", ".v", ".json", ".txt"} and any(
        token in name for token in ["netlist", "schematic", "symbol", "pin", "label"]
    )


def _is_layout_artifact(path: Path) -> bool:
    name = path.name.lower()
    if path.parent.name.lower() == "layout":
        return True
    return path.suffix.lower() in {".gds", ".dxf", ".tf", ".map", ".json", ".txt"} and any(
        token in name for token in ["layout", "layer", "gds", "dxf", "cell", "library", "display"]
    )


def _load_case_params(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    if path.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return dict(raw.get("parameters", raw) or {})
    return load_baseline_params(path)
