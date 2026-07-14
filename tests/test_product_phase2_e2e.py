import json
from dataclasses import replace

import pandas as pd
import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.comparison_service import ComparisonClaimError, ComparisonService
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    CandidateStatus,
    ComparisonVerdict,
    EvidenceRecord,
    SimulationJobStatus,
    new_id,
)
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.product.simulation_job_service import SimulationJobService
from goa_eval.product.state_machine import transition_candidate


def _deterministic_generator(_config, max_candidates, seed):
    assert max_candidates == 1
    return [
        {
            "parameter_changes": {"t1_width_um": 12.0 + seed, "c1_pf": 4.0},
            "reason_codes": ["reduce_ripple"],
            "selection_score": 0.91,
        }
    ]


def _analyze_version(repository, store, version_id, score, suffix):
    run = AnalysisRunRecord(
        analysis_run_id=new_id("run"),
        design_version_id=version_id,
        input_manifest_ref=f"artifact://inputs/{suffix}.json",
        spec_revision_id="spec_v1",
        profile_revision_id="profile_v1",
        status=AnalysisStatus.COMPLETED,
        started_at="2026-07-12T00:00:00+00:00",
        completed_at="2026-07-12T00:01:00+00:00",
    )
    repository.add_analysis_run(run)
    artifacts = {
        "real_summary.json": json.dumps({"Overall_status": "PASS"}),
        "score_summary.json": json.dumps(
            {
                "overall_score": score,
                "hard_constraint_passed": True,
                "hard_constraints": {"ripple": {"passed": True}},
            }
        ),
        "real_metrics.csv": f"metric,value\noverall_score,{score}\n",
    }
    for name, payload in artifacts.items():
        ref = store.put_bytes(f"runs/{run.analysis_run_id}/analysis/{name}", payload.encode())
        repository.add_evidence(
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


def test_phase2_manual_simulation_story_survives_restart_and_gates_improvement(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'product.db'}"
    engine = make_engine(database_url)
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    store = LocalArtifactStore(tmp_path / "artifacts")
    projects = ProjectService(repository, store)
    workspace = projects.create_workspace("GOA team")
    project = projects.create_project(
        workspace.workspace_id,
        "GOA manual loop",
        "goa_8k",
        "spec_v1",
    ).project
    baseline = projects.create_design_version(project.project_id, "baseline")
    baseline_run = _analyze_version(repository, store, baseline.design_version_id, 0.60, "baseline")

    experiments = ExperimentService(repository, generators={"rule": _deterministic_generator})
    experiment = experiments.create_experiment(
        project.project_id,
        baseline.design_version_id,
        {"strategy": "rule"},
    )
    candidate = experiments.generate_candidates(experiment.experiment_id, "rule", 1, 2)[0]
    assert candidate.must_resimulate is True
    assert candidate.status == CandidateStatus.PROPOSED
    approved = experiments.approve_candidate(candidate.candidate_id, "reviewer")
    assert approved.status == CandidateStatus.APPROVED

    jobs = SimulationJobService(repository, store, projects)
    exported = jobs.export_job(jobs.create_manual_job([approved.candidate_id]).simulation_job_id)
    assert exported.status == SimulationJobStatus.WAITING_FOR_RESULTS
    assert repository.get_candidate(candidate.candidate_id).status != CandidateStatus.CONFIRMED_IMPROVEMENT
    with pytest.raises(ComparisonClaimError):
        ComparisonService(repository, store).confirm_candidate(candidate.candidate_id, "comparison_missing")

    batch = pd.read_csv(store.resolve(exported.batch_ref))
    result_path = tmp_path / "manual-simulator-results.csv"
    pd.DataFrame(
        {
            "candidate_id": batch["candidate_id"],
            "parameter_hash": batch["parameter_hash"],
            "overall_score": [0.84],
            "hard_constraint_passed": [True],
        }
    ).to_csv(result_path, index=False)

    preview = jobs.preview_import(exported.simulation_job_id, result_path)
    engine.dispose()
    restarted_repository = SqlAlchemyProductRepository(make_engine(database_url))
    restarted_store = LocalArtifactStore(tmp_path / "artifacts")
    restarted_projects = ProjectService(restarted_repository, restarted_store)
    restarted_jobs = SimulationJobService(restarted_repository, restarted_store, restarted_projects)
    completed = restarted_jobs.commit_import(exported.simulation_job_id, preview.manifest_sha256)

    resimulated = restarted_repository.get_candidate(candidate.candidate_id)
    assert completed.status == SimulationJobStatus.COMPLETED
    assert resimulated.status == CandidateStatus.RESIMULATED
    assert resimulated.result_design_version_id
    provenance = json.loads(restarted_store.resolve(completed.result_ref).read_text(encoding="utf-8"))
    assert provenance["candidate_id"] == candidate.candidate_id
    assert provenance["simulation_job_id"] == exported.simulation_job_id
    assert provenance["result_sha256"] == preview.result_sha256 == completed.result_sha256
    assert provenance["data_source"] == "real_simulation_csv"
    assert provenance["engineering_validity"] == "simulation_only"
    assert provenance["must_resimulate"] is True

    result_run = _analyze_version(
        restarted_repository,
        restarted_store,
        resimulated.result_design_version_id,
        0.84,
        "result",
    )
    evaluated = replace(
        resimulated,
        status=transition_candidate(resimulated.status, CandidateStatus.EVALUATED),
        evaluated_score=0.84,
    )
    restarted_repository.update_candidate(evaluated)
    comparison_service = ComparisonService(restarted_repository, restarted_store)
    comparison = comparison_service.compare_versions(
        project.project_id,
        baseline.design_version_id,
        resimulated.result_design_version_id,
        baseline_run.analysis_run_id,
        result_run.analysis_run_id,
    )
    confirmed = comparison_service.confirm_candidate(candidate.candidate_id, comparison.comparison_id)

    assert comparison.verdict == ComparisonVerdict.IMPROVED
    assert comparison.metric_deltas["overall_score"] == pytest.approx(0.24)
    assert len(comparison.evidence_ids) == 6
    assert baseline_run.evidence_boundary == result_run.evidence_boundary
    assert baseline_run.evidence_boundary.data_source == "real_simulation_csv"
    assert baseline_run.evidence_boundary.engineering_validity == "simulation_only"
    assert baseline_run.evidence_boundary.must_resimulate is True
    assert confirmed.status == CandidateStatus.CONFIRMED_IMPROVEMENT
    approval_actions = [
        event.action
        for event in restarted_repository.list_audit_events("candidate", candidate.candidate_id)
    ]
    assert "candidate.approved" in approval_actions
