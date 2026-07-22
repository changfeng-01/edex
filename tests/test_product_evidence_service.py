from pathlib import Path

import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import AnalysisRunRecord, AnalysisStatus, new_id
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository


@pytest.fixture
def evidence_context(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    store = LocalArtifactStore(tmp_path / "artifacts")
    project_service = ProjectService(repository, store)
    workspace = project_service.create_workspace("GOA team")
    project = project_service.create_project(workspace.workspace_id, "GOA", "goa_8k", "spec_v1").project
    version = project_service.create_design_version(project.project_id, "baseline")
    run = AnalysisRunRecord(
        analysis_run_id=new_id("run"),
        design_version_id=version.design_version_id,
        input_manifest_ref="artifact://inputs/manifest.json",
        spec_revision_id="spec_v1",
        profile_revision_id="profile_v1",
        status=AnalysisStatus.RUNNING,
    )
    repository.add_analysis_run(run)
    return repository, store, run


def test_index_normalizes_boundary_and_records_every_artifact(evidence_context, tmp_path: Path):
    from goa_eval.product.evidence_service import EvidenceService

    repository, store, run = evidence_context
    source = tmp_path / "bundle"
    source.mkdir()
    for name in (
        "real_summary.json",
        "score_summary.json",
        "real_metrics.csv",
        "recommendations.md",
        "issues.json",
        "run_manifest.json",
    ):
        (source / name).write_text(name, encoding="utf-8")
    refs = store.publish_directory(f"runs/{run.analysis_run_id}", source)

    result = EvidenceService(repository).index_analysis_artifacts(
        run.analysis_run_id,
        refs,
        {"data_source": "untrusted", "engineering_validity": "hardware", "must_resimulate": False},
    )

    records = repository.list_evidence("analysis_run", run.analysis_run_id)
    assert len(records) == len(refs)
    assert result.completeness == "complete"
    assert all(record.boundary.data_source == "real_simulation_csv" for record in records)
    assert all(record.boundary.engineering_validity == "simulation_only" for record in records)
    assert all(record.boundary.must_resimulate is True for record in records)


def test_missing_required_files_is_incomplete(evidence_context, tmp_path: Path):
    from goa_eval.product.evidence_service import EvidenceService

    repository, store, run = evidence_context
    artifact = tmp_path / "real_summary.json"
    artifact.write_text("{}", encoding="utf-8")
    ref = store.put_file(f"runs/{run.analysis_run_id}/real_summary.json", artifact)

    result = EvidenceService(repository).index_analysis_artifacts(run.analysis_run_id, [ref], {})

    assert result.completeness == "incomplete"
    assert "score_summary.json" in result.missing_required


def test_retired_evidence_fields_are_tolerated_as_legacy_extensions(evidence_context):
    from goa_eval.product.evidence_service import EvidenceService

    repository, _, _ = evidence_context
    service = EvidenceService(repository)

    boundary = service.validate_boundary({"mock_used": True, "reportable_as_real_ngspice": True})

    assert boundary["data_source"] == "real_simulation_csv"
    assert boundary["engineering_validity"] == "simulation_only"
    assert boundary["must_resimulate"] is True


def test_readonly_suggestion_can_never_confirm_improvement(evidence_context):
    from goa_eval.product.evidence_service import EvidenceService

    repository, _, run = evidence_context
    assert EvidenceService(repository).can_confirm_improvement(
        {"readonly": True, "must_resimulate": True},
        run,
    ) is False


def test_confirm_gate_requires_evaluated_candidate_and_matching_provenance(evidence_context):
    from goa_eval.product.evidence_service import EvidenceService

    _, _, run = evidence_context
    completed = AnalysisRunRecord(
        analysis_run_id=run.analysis_run_id,
        design_version_id="version_result",
        input_manifest_ref=run.input_manifest_ref,
        spec_revision_id=run.spec_revision_id,
        profile_revision_id=run.profile_revision_id,
        status=AnalysisStatus.COMPLETED,
    )
    candidate = {
        "candidate_id": "candidate_1",
        "status": "evaluated",
        "result_design_version_id": "version_result",
        "simulation_job_id": "job_1",
    }
    comparison = {"verdict": "improved", "result_analysis_run_id": completed.analysis_run_id}
    provenance = {"candidate_id": "candidate_1", "simulation_job_id": "job_1"}

    assert EvidenceService.can_confirm_improvement(candidate, completed, comparison, provenance) is True
    assert EvidenceService.can_confirm_improvement(
        candidate,
        completed,
        comparison,
        {**provenance, "simulation_job_id": "job_wrong"},
    ) is False


def test_summary_separates_complete_incomplete_and_invalid(evidence_context, tmp_path: Path):
    from goa_eval.product.evidence_service import EvidenceService

    repository, store, run = evidence_context
    source = tmp_path / "bundle"
    source.mkdir()
    required = (
        "real_summary.json",
        "score_summary.json",
        "real_metrics.csv",
        "recommendations.md",
        "issues.json",
        "run_manifest.json",
    )
    for name in required:
        (source / name).write_text(name, encoding="utf-8")
    refs = store.publish_directory(f"runs/{run.analysis_run_id}", source)
    service = EvidenceService(repository)
    service.index_analysis_artifacts(run.analysis_run_id, refs, {})

    complete = service.summarize_completeness(run.analysis_run_id)
    incomplete = service.summarize_completeness("run_missing")
    invalid = service.summarize_completeness(
        run.analysis_run_id,
        raw_evidence={"mock_used": True, "reportable_as_real_ngspice": True},
    )

    assert complete.completeness == "complete"
    assert incomplete.completeness == "incomplete"
    assert invalid.completeness == "complete"
