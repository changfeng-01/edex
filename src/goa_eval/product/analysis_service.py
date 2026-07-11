from __future__ import annotations

import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import pandas as pd

from goa_eval.product.artifact_store import ArtifactRef, ArtifactStore
from goa_eval.product.evidence_service import EvidenceService
from goa_eval.product.issue_service import IssueService
from goa_eval.product.models import (
    AnalysisExecutionResult,
    AnalysisRunRecord,
    AnalysisStatus,
    EvidenceBoundary,
    new_id,
    utc_now_iso,
)
from goa_eval.product.pipeline import PipelineResult, execute_analysis_pipeline
from goa_eval.product.project_service import ProductNotFoundError
from goa_eval.web.schemas import UploadedCaseConfig


REQUIRED_ANALYSIS_FILES = (
    "analysis/real_summary.json",
    "analysis/score_summary.json",
    "analysis/real_metrics.csv",
    "analysis/recommendations.md",
    "issues.json",
)


class AnalysisService:
    def __init__(
        self,
        repository: Any,
        artifact_store: ArtifactStore,
        *,
        pipeline: Callable[..., PipelineResult] = execute_analysis_pipeline,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._pipeline = pipeline

    def run_analysis(
        self,
        *,
        design_version_id: str,
        input_manifest_ref: ArtifactRef,
        config: UploadedCaseConfig,
    ) -> AnalysisExecutionResult:
        version = self._repository.get_design_version(design_version_id)
        if version is None:
            raise ProductNotFoundError(f"design version was not found: {design_version_id}")
        project = self._repository.get_project(version.project_id)
        if project is None:
            raise ProductNotFoundError(f"project was not found: {version.project_id}")
        manifest = self._load_manifest(input_manifest_ref)
        run = AnalysisRunRecord(
            analysis_run_id=new_id("run"),
            design_version_id=design_version_id,
            input_manifest_ref=input_manifest_ref.uri,
            spec_revision_id=project.spec_revision_id,
            profile_revision_id=str(manifest.get("profile_revision_id") or project.circuit_profile_id),
            status=AnalysisStatus.QUEUED,
        )
        self._repository.add_analysis_run(run)
        running = replace(run, status=AnalysisStatus.RUNNING, started_at=utc_now_iso())
        self._repository.update_analysis_run(running)

        try:
            with TemporaryDirectory(prefix="circuitpilot-analysis-") as temporary_name:
                run_dir = Path(temporary_name) / "run"
                input_dir = run_dir / "input"
                analysis_dir = run_dir / "analysis"
                product_demo_root = run_dir / "product_demo"
                self._copy_snapshot_inputs(input_manifest_ref, input_dir)
                pipeline_result = self._pipeline(
                    input_dir=input_dir,
                    analysis_dir=analysis_dir,
                    product_demo_root=product_demo_root,
                    case_id=config.case_id,
                    config=config,
                )
                prefix = (
                    f"workspaces/{project.workspace_id}/projects/{project.project_id}/"
                    f"design_versions/{design_version_id}/analysis_runs/{run.analysis_run_id}"
                )
                self._write_issues(run_dir, prefix, run.analysis_run_id, pipeline_result)
                missing = tuple(relative for relative in REQUIRED_ANALYSIS_FILES if not (run_dir / relative).exists())
                self._write_run_manifest(run_dir, running, input_manifest_ref, missing, config)
                refs = self._artifact_store.publish_directory(prefix, run_dir)
            refs_by_relative = {
                ref.key.removeprefix(f"{prefix}/"): ref
                for ref in refs
            }
            bundle_ref = refs_by_relative["run_manifest.json"]
            dashboard_ref = refs_by_relative.get(
                f"product_demo/{config.case_id}/06_dashboard_data/dashboard_summary.json"
            )
            issue_ref = refs_by_relative.get("issues.json")
            evidence = EvidenceService(self._repository).index_analysis_artifacts(
                run.analysis_run_id,
                refs,
                pipeline_result.summary,
            )
            all_missing = tuple(dict.fromkeys((*missing, *evidence.missing_required)))
            final_status = AnalysisStatus.EVIDENCE_INCOMPLETE if all_missing else AnalysisStatus.COMPLETED
            final = replace(
                running,
                status=final_status,
                artifact_bundle_ref=bundle_ref.uri,
                completed_at=utc_now_iso(),
            )
            self._repository.update_analysis_run(final)
            return AnalysisExecutionResult(
                analysis_run_id=run.analysis_run_id,
                status=final_status,
                boundary=final.evidence_boundary,
                artifact_bundle_ref=bundle_ref,
                dashboard_bundle_ref=dashboard_ref,
                issue_manifest_ref=issue_ref,
                evidence_ids=evidence.evidence_ids,
                missing_evidence=all_missing,
            )
        except Exception as exc:
            failed = replace(running, status=AnalysisStatus.FAILED, completed_at=utc_now_iso())
            self._repository.update_analysis_run(failed)
            return AnalysisExecutionResult(
                analysis_run_id=run.analysis_run_id,
                status=AnalysisStatus.FAILED,
                boundary=failed.evidence_boundary,
                error={"error_code": "ANALYSIS_EXECUTION_FAILED", "message": str(exc)},
            )

    def execute_compatibility(
        self,
        *,
        input_dir: Path,
        analysis_dir: Path,
        product_demo_root: Path,
        case_id: str,
        config: UploadedCaseConfig,
    ) -> PipelineResult:
        return self._pipeline(
            input_dir=input_dir,
            analysis_dir=analysis_dir,
            product_demo_root=product_demo_root,
            case_id=case_id,
            config=config,
        )

    def _load_manifest(self, ref: ArtifactRef) -> dict[str, Any]:
        manifest = json.loads(self._artifact_store.resolve(ref).read_text(encoding="utf-8"))
        if manifest.get("preview_status") not in {"preview_ready", "preview_ready_with_warnings"}:
            raise ValueError("input snapshot is not ready for analysis")
        return manifest

    def _copy_snapshot_inputs(self, ref: ArtifactRef, destination: Path) -> None:
        manifest_path = self._artifact_store.resolve(ref)
        source = manifest_path.parent / "input"
        if not source.exists():
            raise FileNotFoundError("input snapshot files are missing")
        shutil.copytree(source, destination)

    @staticmethod
    def _write_run_manifest(
        run_dir: Path,
        run: AnalysisRunRecord,
        input_ref: ArtifactRef,
        missing: tuple[str, ...],
        config: UploadedCaseConfig,
    ) -> None:
        payload = {
            "analysis_run_id": run.analysis_run_id,
            "design_version_id": run.design_version_id,
            "input_manifest_ref": input_ref.uri,
            "evidence_boundary": asdict(EvidenceBoundary()),
            "readonly_suggestions": bool(config.generate_candidates),
            "confirmed_improvement": False,
            "missing_evidence": list(missing),
        }
        (run_dir / "run_manifest.json").write_text(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_issues(
        run_dir: Path,
        prefix: str,
        run_id: str,
        pipeline_result: PipelineResult,
    ) -> None:
        metrics_path = run_dir / "analysis/real_metrics.csv"
        metrics = pd.read_csv(metrics_path).to_dict(orient="records") if metrics_path.exists() else []
        diagnosis_relative = "analysis/diagnosis_report.md"
        diagnosis_ref = (
            f"artifact://{prefix}/{diagnosis_relative}"
            if (run_dir / diagnosis_relative).exists()
            else None
        )
        issues = IssueService().build_issues(
            pipeline_result.score,
            pipeline_result.summary,
            metrics,
            diagnosis_ref,
        )
        payload = {
            "schema_version": "1.0",
            "analysis_run_id": run_id,
            "evidence_boundary": asdict(EvidenceBoundary()),
            "issues": [asdict(issue) for issue in issues],
        }
        (run_dir / "issues.json").write_text(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
