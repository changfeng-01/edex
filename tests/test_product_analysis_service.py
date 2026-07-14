import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from goa_eval.product.artifact_store import ArtifactStoreError, LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.input_service import InputFile, InputService
from goa_eval.product.models import AnalysisStatus
from goa_eval.product.orm import CandidateORM
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.web.schemas import UploadedCaseConfig


@pytest.fixture
def analysis_context(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    project_service = ProjectService(repository, artifact_store)
    workspace = project_service.create_workspace("GOA team")
    project = project_service.create_project(
        workspace.workspace_id,
        "GOA",
        "goa_8k",
        "spec_v1",
    ).project
    version = project_service.create_design_version(project.project_id, "baseline")
    snapshot = InputService(repository, artifact_store).create_input_snapshot(
        design_version_id=version.design_version_id,
        files=[
            InputFile("waveform.csv", Path("examples/sample_waveform.csv")),
            InputFile("params.yaml", Path("examples/sample_params.yaml")),
        ],
        preview_config=UploadedCaseConfig(case_id="preview"),
    )
    return repository, artifact_store, version, snapshot


def test_real_sample_analysis_publishes_complete_bundle(analysis_context):
    from goa_eval.product.analysis_service import AnalysisService

    repository, artifact_store, version, snapshot = analysis_context
    result = AnalysisService(repository, artifact_store).run_analysis(
        design_version_id=version.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="product_run", generate_candidates=True),
    )

    assert result.status == AnalysisStatus.COMPLETED
    assert result.boundary.data_source == "real_simulation_csv"
    assert result.boundary.engineering_validity == "simulation_only"
    assert result.boundary.must_resimulate is True
    assert result.artifact_bundle_ref.uri.startswith("artifact://")
    run_root = artifact_store.resolve(result.artifact_bundle_ref).parent
    for relative in (
        "analysis/real_summary.json",
        "analysis/score_summary.json",
        "analysis/real_metrics.csv",
        "analysis/recommendations.md",
        "product_demo/product_run/06_dashboard_data/dashboard_summary.json",
        "run_manifest.json",
    ):
        assert (run_root / relative).exists(), relative


def test_run_transitions_running_before_pipeline_and_completed_after(analysis_context):
    from goa_eval.product.analysis_service import AnalysisService
    from goa_eval.product.pipeline import execute_analysis_pipeline

    repository, artifact_store, version, snapshot = analysis_context
    observed = []

    def pipeline(**kwargs):
        runs = repository.list_analysis_runs(design_version_id=version.design_version_id)
        observed.append(runs[-1].status)
        return execute_analysis_pipeline(**kwargs)

    result = AnalysisService(repository, artifact_store, pipeline=pipeline).run_analysis(
        design_version_id=version.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="state_run"),
    )

    assert observed == [AnalysisStatus.RUNNING]
    assert repository.get_analysis_run(result.analysis_run_id).status == AnalysisStatus.COMPLETED


def test_pipeline_failure_retains_structured_failed_result(analysis_context):
    from goa_eval.product.analysis_service import AnalysisService

    repository, artifact_store, version, snapshot = analysis_context

    def broken_pipeline(**_kwargs):
        raise RuntimeError("pipeline exploded")

    result = AnalysisService(repository, artifact_store, pipeline=broken_pipeline).run_analysis(
        design_version_id=version.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="failed_run"),
    )

    assert result.status == AnalysisStatus.FAILED
    assert result.error == {"error_code": "ANALYSIS_EXECUTION_FAILED", "message": "pipeline exploded"}
    assert repository.get_analysis_run(result.analysis_run_id).status == AnalysisStatus.FAILED


def test_missing_required_output_becomes_evidence_incomplete(analysis_context):
    from goa_eval.product.analysis_service import AnalysisService
    from goa_eval.product.pipeline import execute_analysis_pipeline

    repository, artifact_store, version, snapshot = analysis_context

    def incomplete_pipeline(**kwargs):
        result = execute_analysis_pipeline(**kwargs)
        (kwargs["analysis_dir"] / "real_metrics.csv").unlink()
        return result

    result = AnalysisService(repository, artifact_store, pipeline=incomplete_pipeline).run_analysis(
        design_version_id=version.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="incomplete_run"),
    )

    assert result.status == AnalysisStatus.EVIDENCE_INCOMPLETE
    assert "analysis/real_metrics.csv" in result.missing_evidence


def test_publication_failure_never_leaves_completed_state(analysis_context):
    from goa_eval.product.analysis_service import AnalysisService

    repository, artifact_store, version, snapshot = analysis_context

    class FailingPublishStore:
        def __getattr__(self, name):
            return getattr(artifact_store, name)

        def publish_directory(self, prefix, source):
            raise ArtifactStoreError("publication failed")

    result = AnalysisService(repository, FailingPublishStore()).run_analysis(
        design_version_id=version.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="publish_failure"),
    )

    assert result.status == AnalysisStatus.FAILED
    assert result.artifact_bundle_ref is None
    assert repository.get_analysis_run(result.analysis_run_id).status == AnalysisStatus.FAILED


def test_readonly_suggestions_are_boundary_marked_without_candidate_records(analysis_context):
    from goa_eval.product.analysis_service import AnalysisService

    repository, artifact_store, version, snapshot = analysis_context
    result = AnalysisService(repository, artifact_store).run_analysis(
        design_version_id=version.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="suggestions", generate_candidates=True),
    )

    run_root = artifact_store.resolve(result.artifact_bundle_ref).parent
    candidates = (run_root / "analysis/next_candidates.csv").read_text(encoding="utf-8")
    manifest = json.loads((run_root / "run_manifest.json").read_text(encoding="utf-8"))
    assert "must_resimulate" in candidates
    assert "True" in candidates or "true" in candidates
    assert "confirmed_improvement" not in candidates.lower()
    assert manifest["readonly_suggestions"] is True
    with repository._sessions() as session:
        assert session.scalar(select(func.count()).select_from(CandidateORM)) == 0
