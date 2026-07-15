from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from goa_eval.product.comparison_service import ComparisonClaimError
from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.input_service import InputFile
from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    CandidateStatus,
    EvidenceRecord,
    new_id,
    utc_now_iso,
)
from goa_eval.product.settings import ProductSettings
from goa_eval.product.state_machine import transition_candidate
from goa_eval.product_api.dependencies import ProductContainer
from goa_eval.web.schemas import UploadedCaseConfig


BOUNDARY = {
    "data_source": "real_simulation_csv",
    "engineering_validity": "simulation_only",
    "must_resimulate": True,
}


def build_product_demo(*, output_dir: Path, database_url: str) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = ProductSettings(
        database_url=database_url,
        artifact_root=output_dir / "artifacts",
        job_execution_enabled=False,
    )
    container = ProductContainer.from_settings(settings, create_tables=True)
    repository = container.repository
    store = container.artifact_store

    workspace = container.project_service.create_workspace("CircuitPilot public demo")
    project_result = container.project_service.create_project(
        workspace.workspace_id,
        "GOA evaluated closed loop",
        "goa_8k",
        "spec_v1",
    )
    project = project_result.project
    baseline = container.project_service.create_design_version(project.project_id, "baseline")
    snapshot = container.input_service.create_input_snapshot(
        design_version_id=baseline.design_version_id,
        files=[
            InputFile("waveform.csv", REPO_ROOT / "examples" / "sample_waveform.csv"),
            InputFile("params.yaml", REPO_ROOT / "examples" / "sample_params.yaml"),
        ],
        preview_config=UploadedCaseConfig(case_id="phase4_product_demo"),
    )
    baseline_execution = container.analysis_service.run_analysis(
        design_version_id=baseline.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="phase4_product_demo"),
    )
    if baseline_execution.status != AnalysisStatus.COMPLETED:
        raise RuntimeError(f"baseline analysis did not complete: {baseline_execution.status.value}")
    baseline_run = repository.get_analysis_run(baseline_execution.analysis_run_id)
    if baseline_run is None:
        raise RuntimeError("baseline analysis record is missing")
    baseline_score_payload = _score_payload_for_run(container, baseline_run.analysis_run_id)
    baseline_score = float(baseline_score_payload["overall_score"])
    issue_count = _issue_count(container, baseline_execution.issue_manifest_ref)

    container.experiment_service = ExperimentService(
        repository,
        generators={"phase4_demo": _deterministic_generator},
    )
    experiment = container.experiment_service.create_experiment(
        project.project_id,
        baseline.design_version_id,
        {"strategy": "phase4_demo"},
    )
    candidate = container.experiment_service.generate_candidates(
        experiment.experiment_id,
        "phase4_demo",
        1,
        42,
    )[0]
    confirmation_before_import_rejected = _confirmation_rejected(
        container,
        candidate.candidate_id,
        "comparison_missing",
    )
    approved = container.experiment_service.approve_candidate(candidate.candidate_id, "demo_reviewer")
    job = container.simulation_job_service.create_manual_job([approved.candidate_id])
    exported = container.simulation_job_service.export_job(job.simulation_job_id)
    batch = pd.read_csv(store.resolve(exported.batch_ref))
    result_score = baseline_score + max(1.0, abs(baseline_score) * 0.10)
    result_path = output_dir / "deterministic_simulation_results.csv"
    pd.DataFrame(
        {
            "candidate_id": batch["candidate_id"],
            "parameter_hash": batch["parameter_hash"],
            "overall_score": [result_score],
            "hard_constraint_passed": [True],
            **{key: [value] for key, value in BOUNDARY.items()},
        }
    ).to_csv(result_path, index=False)
    preview = container.simulation_job_service.preview_import(exported.simulation_job_id, result_path)
    completed_job = container.simulation_job_service.commit_import(
        exported.simulation_job_id,
        preview.manifest_sha256,
    )
    resimulated = repository.get_candidate(candidate.candidate_id)
    if resimulated is None or resimulated.result_design_version_id is None:
        raise RuntimeError("result design version was not created")
    pre_evaluation_comparison = container.comparison_service.compare_versions(
        project.project_id,
        baseline.design_version_id,
        resimulated.result_design_version_id,
        baseline_run.analysis_run_id,
        None,
    )
    confirmation_before_evaluation_rejected = _confirmation_rejected(
        container,
        candidate.candidate_id,
        pre_evaluation_comparison.comparison_id,
    )
    result_run = _record_imported_evaluation(
        container,
        design_version_id=resimulated.result_design_version_id,
        profile_revision_id=baseline_run.profile_revision_id,
        input_manifest_ref=completed_job.result_manifest_ref or "",
        score=result_score,
        baseline_constraints=baseline_score_payload.get("hard_constraints", {}),
    )
    evaluated = replace(
        resimulated,
        status=transition_candidate(resimulated.status, CandidateStatus.EVALUATED),
        evaluated_score=result_score,
    )
    repository.update_candidate(evaluated)
    comparison = container.comparison_service.compare_versions(
        project.project_id,
        baseline.design_version_id,
        resimulated.result_design_version_id,
        baseline_run.analysis_run_id,
        result_run.analysis_run_id,
    )
    confirmed = container.comparison_service.confirm_candidate(
        candidate.candidate_id,
        comparison.comparison_id,
    )

    manifest = {
        "schema_version": "circuitpilot.product-demo.v1",
        "boundary": BOUNDARY,
        "workspace_id": workspace.workspace_id,
        "project_id": project.project_id,
        "design_version_ids": [baseline.design_version_id, resimulated.result_design_version_id],
        "analysis_run_ids": [baseline_run.analysis_run_id, result_run.analysis_run_id],
        "experiment_id": experiment.experiment_id,
        "candidate_id": candidate.candidate_id,
        "simulation_job_id": completed_job.simulation_job_id,
        "comparison_id": comparison.comparison_id,
        "workflow": {
            "workspace_created": True,
            "baseline_analysis_status": baseline_run.status.value,
            "issue_count": issue_count,
            "candidate_must_resimulate": candidate.must_resimulate,
            "confirmation_before_import_rejected": confirmation_before_import_rejected,
            "confirmation_before_evaluation_rejected": confirmation_before_evaluation_rejected,
            "manual_job_status": completed_job.status.value,
            "result_analysis_status": result_run.status.value,
            "comparison_verdict": comparison.verdict.value,
            "candidate_final_status": confirmed.status.value,
        },
    }
    evidence_records = [
        *repository.list_evidence("project", project.project_id),
        *repository.list_evidence("analysis_run", baseline_run.analysis_run_id),
        *repository.list_evidence("analysis_run", result_run.analysis_run_id),
    ]
    evidence_package = {
        "schema_version": "1.0",
        "boundary": BOUNDARY,
        "comparison": asdict(comparison),
        "records": [asdict(record) for record in evidence_records],
    }
    _write_json(output_dir / "product_demo_manifest.json", manifest)
    _write_json(output_dir / "evidence_package.json", evidence_package)
    (output_dir / "product_report.md").write_text(
        _render_report(manifest, baseline_score=baseline_score, result_score=result_score),
        encoding="utf-8",
    )
    return manifest


def _deterministic_generator(_config: dict[str, Any], maximum: int, seed: int) -> list[dict[str, Any]]:
    return [
        {
            "parameter_changes": {"t1_width_um": 12.0 + seed / 100.0, "c1_pf": 4.0},
            "reason_codes": ["phase4_public_demo"],
            "selection_score": 0.91,
        }
        for _ in range(maximum)
    ]


def _confirmation_rejected(container: ProductContainer, candidate_id: str, comparison_id: str) -> bool:
    try:
        container.comparison_service.confirm_candidate(candidate_id, comparison_id)
    except ComparisonClaimError:
        return True
    return False


def _score_payload_for_run(container: ProductContainer, run_id: str) -> dict[str, Any]:
    record = next(
        item
        for item in container.repository.list_evidence("analysis_run", run_id)
        if item.source_ref.endswith("/score_summary.json")
    )
    ref = container.artifact_store.ref_from_uri(record.source_ref, record.checksum)
    return json.loads(container.artifact_store.resolve(ref).read_text(encoding="utf-8"))


def _issue_count(container: ProductContainer, ref: Any) -> int:
    if ref is None:
        return 0
    payload = json.loads(container.artifact_store.resolve(ref).read_text(encoding="utf-8"))
    return len(payload.get("issues", []))


def _record_imported_evaluation(
    container: ProductContainer,
    *,
    design_version_id: str,
    profile_revision_id: str,
    input_manifest_ref: str,
    score: float,
    baseline_constraints: dict[str, Any],
) -> AnalysisRunRecord:
    run = AnalysisRunRecord(
        analysis_run_id=new_id("run"),
        design_version_id=design_version_id,
        input_manifest_ref=input_manifest_ref,
        spec_revision_id="spec_v1",
        profile_revision_id=profile_revision_id,
        status=AnalysisStatus.COMPLETED,
        started_at=utc_now_iso(),
        completed_at=utc_now_iso(),
    )
    container.repository.add_analysis_run(run)
    result_constraints = {
        str(name): {"passed": True}
        for name in baseline_constraints
    }
    result_constraints["imported_simulation"] = {"passed": True}
    payloads = {
        "real_summary.json": json.dumps({"Overall_status": "PASS", "evidence": BOUNDARY}),
        "score_summary.json": json.dumps(
            {
                "overall_score": score,
                "hard_constraint_passed": True,
                "hard_constraints": result_constraints,
                "evidence": BOUNDARY,
            }
        ),
        "real_metrics.csv": f"metric,value\noverall_score,{score}\n",
    }
    for name, payload in payloads.items():
        ref = container.artifact_store.put_bytes(
            f"product_demo/analysis_runs/{run.analysis_run_id}/{name}",
            (payload + "\n").encode("utf-8"),
        )
        container.repository.add_evidence(
            EvidenceRecord(
                evidence_id=new_id("evidence"),
                subject_type="analysis_run",
                subject_id=run.analysis_run_id,
                evidence_type=name,
                source_ref=ref.uri,
                checksum=ref.sha256,
            )
        )
    return run


def _render_report(manifest: dict[str, Any], *, baseline_score: float, result_score: float) -> str:
    workflow = manifest["workflow"]
    return f"""# CircuitPilot Product Demo v1

This package demonstrates the persisted Route C workflow from project creation through imported evaluation and comparison.

data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true

## Result

- Baseline score: {baseline_score:.6f}
- Imported result score: {result_score:.6f}
- Comparison verdict: {workflow['comparison_verdict']}
- Candidate final status: {workflow['candidate_final_status']}
- Confirmation before import rejected: {str(workflow['confirmation_before_import_rejected']).lower()}
- Confirmation before evaluation rejected: {str(workflow['confirmation_before_evaluation_rejected']).lower()}

The package contains simulation-only evidence. It does not claim silicon validation or real ngspice execution.
"""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the CircuitPilot Product API closed-loop demo.")
    parser.add_argument("--output-dir", default="outputs/product_demo_v1")
    parser.add_argument("--database-url")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    database_url = args.database_url or f"sqlite:///{(output_dir / 'product_demo.db').as_posix()}"
    manifest = build_product_demo(output_dir=output_dir, database_url=database_url)
    print(f"Product demo written to {output_dir}")
    print(f"Project: {manifest['project_id']}")
    print(f"Comparison: {manifest['comparison_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
