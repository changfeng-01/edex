from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.evidence import default_external_csv_evidence
from goa_eval.io_utils import read_json
from goa_eval.llm_analysis import run_llm_parameter_analysis
from goa_eval.optimizer import constrained_random_candidates, load_param_space, write_candidate_outputs
from goa_eval.product_demo.schemas import normalize_evidence_boundary
from goa_eval.product_demo.workflow import run_product_demo
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown
from goa_eval.web.schemas import UploadedCaseConfig


DEFAULT_MOCK_RESPONSE = (
    "CircuitPilot upload analysis mock response. The current evidence is simulation_only, "
    "derived from real_simulation_csv artifacts. Treat candidates as next-run simulation suggestions."
)


@dataclass(frozen=True)
class PipelineResult:
    summary: dict[str, Any]
    score: dict[str, Any]
    boundary: dict[str, Any]
    product_demo_case_dir: Path
    generated_files: tuple[Path, ...]


def execute_analysis_pipeline(
    *,
    input_dir: Path,
    analysis_dir: Path,
    product_demo_root: Path,
    case_id: str,
    config: UploadedCaseConfig,
) -> PipelineResult:
    """Orchestrate existing analysis components without changing their algorithms."""
    waveform_path = input_dir / "waveform.csv"
    if not waveform_path.exists():
        raise FileNotFoundError("waveform.csv is required")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    product_demo_root.mkdir(parents=True, exist_ok=True)
    boundary = normalize_evidence_boundary()
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
        strict_output_coverage=config.stage_count is not None,
        evidence_metadata=evidence_metadata,
    )
    paths = pipeline_paths(analysis_dir)
    write_recommendations_markdown(
        summary_path=paths["summary"],
        score_path=paths["score"],
        metrics_path=paths["metrics"],
        output_path=paths["recommendations"],
    )
    if config.generate_candidates and (input_dir / "params.yaml").exists():
        score = read_json(paths["score"])
        metrics = pd.read_csv(paths["metrics"]) if paths["metrics"].exists() else pd.DataFrame()
        recommendations = build_recommendations(summary, score, metrics)
        candidates = constrained_random_candidates(
            load_param_space(input_dir / "params.yaml"),
            recommendations,
            max_candidates=10,
            seed=42,
        )
        write_candidate_outputs(
            candidates,
            csv_path=paths["candidates_csv"],
            markdown_path=paths["candidates_md"],
        )
        _stamp_readonly_candidate_boundary(paths["candidates_csv"])
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
        case_id=case_id,
        evidence_boundary=boundary,
    )
    return PipelineResult(
        summary=summary,
        score=read_json(paths["score"]),
        boundary=boundary,
        product_demo_case_dir=product_demo_case_dir,
        generated_files=tuple(sorted(path for path in analysis_dir.rglob("*") if path.is_file())),
    )


def pipeline_paths(output_dir: Path) -> dict[str, Path]:
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


def _stamp_readonly_candidate_boundary(path: Path) -> None:
    candidates = pd.read_csv(path)
    candidates["must_resimulate"] = True
    candidates.to_csv(path, index=False)
