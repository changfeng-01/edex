from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.llm_analysis import run_llm_parameter_analysis
from goa_eval.evidence import default_external_csv_evidence
from goa_eval.optimizer import constrained_random_candidates, load_param_space, write_candidate_outputs
from goa_eval.product_demo.workflow import run_product_demo
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown
from goa_eval.web.schemas import CaseRunResult, UploadedCaseConfig, evidence_boundary
from goa_eval.web.storage import write_status


DEFAULT_MOCK_RESPONSE = (
    "CircuitPilot upload analysis mock response. The current evidence is simulation_only, "
    "derived from real_simulation_csv artifacts. Treat candidates as next-run simulation suggestions."
)


def run_uploaded_case(case_dir: Path, config: UploadedCaseConfig) -> CaseRunResult:
    started_at = dt.datetime.now(dt.UTC).isoformat()
    input_dir = case_dir / "input"
    analysis_dir = case_dir / "analysis"
    product_demo_root = case_dir / "product_demo"
    product_demo_case_dir: Path | None = None
    boundary = evidence_boundary()
    write_status(
        case_dir,
        {
            "case_id": config.case_id,
            "status": "running",
            "started_at": started_at,
            "input_dir": _display_path(input_dir),
            "analysis_dir": _display_path(analysis_dir),
            "product_demo_case_dir": None,
            "bundle_url": None,
            "error": None,
            "evidence_boundary": boundary,
        },
    )

    try:
        waveform_path = input_dir / "waveform.csv"
        if not waveform_path.exists():
            raise FileNotFoundError("waveform.csv is required")
        evidence_metadata = default_external_csv_evidence()
        evidence_metadata.update(boundary)
        summary = run_real_waveform_evaluation(
            waveform_path=waveform_path,
            internal_waveform_path=None,
            output_dir=analysis_dir,
            stage_count=config.stage_count,
            output_node_pattern=config.output_node_pattern,
            topology=config.topology,
            circuit_profile=config.circuit_profile,
            evidence_metadata=evidence_metadata,
        )
        paths = _pipeline_paths(analysis_dir)
        recommendations = write_recommendations_markdown(
            summary_path=paths["summary"],
            score_path=paths["score"],
            metrics_path=paths["metrics"],
            output_path=paths["recommendations"],
        )
        if config.generate_candidates and (input_dir / "params.yaml").exists():
            score = _read_json(paths["score"])
            metrics = pd.read_csv(paths["metrics"]) if paths["metrics"].exists() else pd.DataFrame()
            recommendations = build_recommendations(summary, score, metrics)
            candidates = constrained_random_candidates(load_param_space(input_dir / "params.yaml"), recommendations, max_candidates=10, seed=42)
            write_candidate_outputs(candidates, csv_path=paths["candidates_csv"], markdown_path=paths["candidates_md"])
        if config.run_llm_analysis:
            run_llm_parameter_analysis(
                summary_path=paths["summary"],
                score_path=paths["score"],
                metrics_path=paths["metrics"],
                candidates_path=paths["candidates_csv"] if paths["candidates_csv"].exists() else None,
                params_path=input_dir / "params.yaml" if (input_dir / "params.yaml").exists() else None,
                mock_response=os.getenv("CIRCUITPILOT_LLM_MOCK_RESPONSE", DEFAULT_MOCK_RESPONSE),
                output_md=paths["analysis_md"],
                output_json=paths["analysis_json"],
            )
        product_demo_case_dir = run_product_demo(
            input_dir=analysis_dir,
            output_dir=product_demo_root,
            case_id=config.case_id,
            evidence_boundary=boundary,
        )
        result = CaseRunResult(
            case_id=config.case_id,
            status="completed",
            case_dir=_display_path(case_dir),
            input_dir=_display_path(input_dir),
            analysis_dir=_display_path(analysis_dir),
            product_demo_case_dir=_display_path(product_demo_case_dir),
            bundle_url=f"/api/cases/{config.case_id}/bundle",
            error=None,
            evidence_boundary=boundary,
        )
    except Exception as exc:
        result = CaseRunResult(
            case_id=config.case_id,
            status="failed",
            case_dir=_display_path(case_dir),
            input_dir=_display_path(input_dir),
            analysis_dir=_display_path(analysis_dir),
            product_demo_case_dir=_display_path(product_demo_case_dir) if product_demo_case_dir else None,
            bundle_url=None,
            error=str(exc),
            evidence_boundary=boundary,
        )
    finished_at = dt.datetime.now(dt.UTC).isoformat()
    payload = result.model_dump()
    payload["started_at"] = started_at
    payload["finished_at"] = finished_at
    write_status(case_dir, payload)
    return result


def _pipeline_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "summary": output_dir / "real_summary.json",
        "score": output_dir / "score_summary.json",
        "metrics": output_dir / "real_metrics.csv",
        "recommendations": output_dir / "recommendations.md",
        "candidates_csv": output_dir / "next_candidates.csv",
        "candidates_md": output_dir / "next_candidates.md",
        "analysis_md": output_dir / "llm_parameter_analysis.md",
        "analysis_json": output_dir / "llm_parameter_analysis.json",
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
