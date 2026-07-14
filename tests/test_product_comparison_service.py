import json
from dataclasses import replace

import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    CandidateRecord,
    CandidateStatus,
    ComparisonVerdict,
    EvidenceRecord,
    OptimizationExperimentRecord,
    ProjectRecord,
    SimulationJobRecord,
    WorkspaceRecord,
    DesignVersionRecord,
    new_id,
)
from goa_eval.product.repositories import SqlAlchemyProductRepository


@pytest.fixture
def comparison_context(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    store = LocalArtifactStore(tmp_path / "artifacts")
    workspace = WorkspaceRecord(workspace_id=new_id("workspace"), name="GOA team")
    project = ProjectRecord(
        project_id=new_id("project"),
        workspace_id=workspace.workspace_id,
        name="GOA",
        circuit_profile_id="goa_8k",
        spec_revision_id="spec_v1",
    )
    baseline = DesignVersionRecord(new_id("version"), project.project_id, "baseline")
    result = DesignVersionRecord(
        new_id("version"),
        project.project_id,
        "result",
        parent_version_id=baseline.design_version_id,
    )
    repository.add_workspace(workspace)
    repository.add_project(project)
    repository.add_design_version(baseline)
    repository.add_design_version(result)
    return repository, store, project, baseline, result


def add_completed_run(repository, store, version, score, constraints, *, suffix):
    run = AnalysisRunRecord(
        analysis_run_id=new_id("run"),
        design_version_id=version.design_version_id,
        input_manifest_ref=f"artifact://inputs/{suffix}.json",
        spec_revision_id="spec_v1",
        profile_revision_id="profile_v1",
        status=AnalysisStatus.COMPLETED,
        started_at="2026-07-12T00:00:00+00:00",
        completed_at="2026-07-12T00:01:00+00:00",
    )
    repository.add_analysis_run(run)
    payloads = {
        "real_summary.json": {"Overall_status": "PASS" if all(constraints.values()) else "FAIL"},
        "score_summary.json": {
            "overall_score": score,
            "hard_constraint_passed": all(constraints.values()),
            "hard_constraints": {key: {"passed": passed} for key, passed in constraints.items()},
        },
        "real_metrics.csv": "metric,value\noverall_score,%s\n" % score,
    }
    for filename, payload in payloads.items():
        data = payload if isinstance(payload, str) else json.dumps(payload)
        ref = store.put_bytes(f"runs/{run.analysis_run_id}/analysis/{filename}", data.encode())
        repository.add_evidence(
            EvidenceRecord(
                evidence_id=new_id("evidence"),
                subject_type="analysis_run",
                subject_id=run.analysis_run_id,
                evidence_type=filename,
                source_ref=ref.uri,
                checksum=ref.sha256,
            )
        )
    return run


@pytest.mark.parametrize(
    ("baseline_score", "result_score", "baseline_constraints", "result_constraints", "verdict"),
    [
        (0.60, 0.75, {"ripple": True}, {"ripple": True}, ComparisonVerdict.IMPROVED),
        (0.75, 0.60, {"ripple": True}, {"ripple": True}, ComparisonVerdict.REGRESSED),
        (0.60, 0.60, {"ripple": True}, {"ripple": True}, ComparisonVerdict.NEUTRAL),
        (0.60, 0.90, {"ripple": True}, {"ripple": False}, ComparisonVerdict.REGRESSED),
    ],
)
def test_compare_versions_uses_evaluated_artifacts(
    comparison_context,
    baseline_score,
    result_score,
    baseline_constraints,
    result_constraints,
    verdict,
):
    from goa_eval.product.comparison_service import ComparisonService

    repository, store, project, baseline, result = comparison_context
    baseline_run = add_completed_run(
        repository, store, baseline, baseline_score, baseline_constraints, suffix="baseline"
    )
    result_run = add_completed_run(repository, store, result, result_score, result_constraints, suffix="result")

    comparison = ComparisonService(repository, store).compare_versions(
        project.project_id,
        baseline.design_version_id,
        result.design_version_id,
        baseline_run.analysis_run_id,
        result_run.analysis_run_id,
    )

    assert comparison.verdict == verdict
    assert comparison.metric_deltas["overall_score"] == pytest.approx(result_score - baseline_score)
    assert repository.get_comparison(comparison.comparison_id) == comparison


def test_high_selection_score_without_result_run_is_evidence_insufficient(comparison_context):
    from goa_eval.product.comparison_service import ComparisonService

    repository, store, project, baseline, result = comparison_context
    baseline_run = add_completed_run(repository, store, baseline, 0.4, {"ripple": True}, suffix="baseline")
    experiment = OptimizationExperimentRecord(
        experiment_id=new_id("experiment"),
        project_id=project.project_id,
        baseline_design_version_id=baseline.design_version_id,
    )
    candidate = CandidateRecord(
        candidate_id=new_id("candidate"),
        experiment_id=experiment.experiment_id,
        parent_design_version_id=baseline.design_version_id,
        parameter_changes={"w": 100},
        strategy="rule",
        selection_score=999.0,
    )
    repository.add_experiment(experiment)
    repository.add_candidate(candidate)

    comparison = ComparisonService(repository, store).compare_versions(
        project.project_id,
        baseline.design_version_id,
        result.design_version_id,
        baseline_run.analysis_run_id,
        None,
    )

    assert comparison.verdict == ComparisonVerdict.EVIDENCE_INSUFFICIENT
    assert comparison.metric_deltas == {}


def test_confirm_candidate_requires_improved_matching_import_provenance(comparison_context):
    from goa_eval.product.comparison_service import ComparisonService

    repository, store, project, baseline, result = comparison_context
    baseline_run = add_completed_run(repository, store, baseline, 0.4, {"ripple": True}, suffix="baseline")
    result_run = add_completed_run(repository, store, result, 0.8, {"ripple": True}, suffix="result")
    experiment = OptimizationExperimentRecord(
        experiment_id=new_id("experiment"),
        project_id=project.project_id,
        baseline_design_version_id=baseline.design_version_id,
    )
    repository.add_experiment(experiment)
    candidate = CandidateRecord(
        candidate_id=new_id("candidate"),
        experiment_id=experiment.experiment_id,
        parent_design_version_id=baseline.design_version_id,
        parameter_changes={"w": 12.5},
        strategy="rule",
        selection_score=0.9,
        evaluated_score=0.8,
        status=CandidateStatus.EVALUATED,
        result_design_version_id=result.design_version_id,
    )
    provenance = {
        "candidate_id": candidate.candidate_id,
        "simulation_job_id": "pending",
        "result_sha256": "a" * 64,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }
    result_ref = store.put_bytes("imports/result_manifest.json", json.dumps(provenance).encode())
    job = SimulationJobRecord(
        simulation_job_id=new_id("job"),
        project_id=project.project_id,
        candidate_ids=(candidate.candidate_id,),
        adapter_type="manual",
        result_ref=result_ref,
        result_sha256="a" * 64,
    )
    provenance["simulation_job_id"] = job.simulation_job_id
    corrected_ref = store.put_bytes("imports/corrected_result_manifest.json", json.dumps(provenance).encode())
    job = replace(job, result_ref=corrected_ref)
    candidate = replace(candidate, simulation_job_id=job.simulation_job_id)
    repository.add_candidate(candidate)
    repository.add_simulation_job(job)
    comparison = ComparisonService(repository, store).compare_versions(
        project.project_id,
        baseline.design_version_id,
        result.design_version_id,
        baseline_run.analysis_run_id,
        result_run.analysis_run_id,
    )

    confirmed = ComparisonService(repository, store).confirm_candidate(
        candidate.candidate_id,
        comparison.comparison_id,
    )

    assert confirmed.status == CandidateStatus.CONFIRMED_IMPROVEMENT
    assert confirmed.selection_score == 0.9
    assert confirmed.evaluated_score == 0.8


def test_confirm_candidate_rejects_mismatched_job_provenance(comparison_context):
    from goa_eval.product.comparison_service import ComparisonClaimError, ComparisonService

    repository, store, project, baseline, result = comparison_context
    baseline_run = add_completed_run(repository, store, baseline, 0.4, {"ripple": True}, suffix="baseline")
    result_run = add_completed_run(repository, store, result, 0.8, {"ripple": True}, suffix="result")
    experiment = OptimizationExperimentRecord(new_id("experiment"), project.project_id, baseline.design_version_id)
    repository.add_experiment(experiment)
    candidate = CandidateRecord(
        new_id("candidate"),
        experiment.experiment_id,
        baseline.design_version_id,
        {"w": 12.5},
        "rule",
        status=CandidateStatus.EVALUATED,
        result_design_version_id=result.design_version_id,
    )
    result_ref = store.put_bytes(
        "imports/mismatch.json",
        json.dumps({"candidate_id": candidate.candidate_id, "simulation_job_id": "job_wrong"}).encode(),
    )
    job = SimulationJobRecord(new_id("job"), project.project_id, (candidate.candidate_id,), "manual", result_ref=result_ref)
    candidate = replace(candidate, simulation_job_id=job.simulation_job_id)
    repository.add_candidate(candidate)
    repository.add_simulation_job(job)
    comparison = ComparisonService(repository, store).compare_versions(
        project.project_id,
        baseline.design_version_id,
        result.design_version_id,
        baseline_run.analysis_run_id,
        result_run.analysis_run_id,
    )

    with pytest.raises(ComparisonClaimError, match="provenance"):
        ComparisonService(repository, store).confirm_candidate(candidate.candidate_id, comparison.comparison_id)

