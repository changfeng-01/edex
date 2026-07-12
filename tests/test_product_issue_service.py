import json
from pathlib import Path

from goa_eval.product.analysis_service import AnalysisService
from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.input_service import InputFile, InputService
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.web.schemas import UploadedCaseConfig


def test_fail_ripple_builds_stable_known_issue():
    from goa_eval.product.issue_service import IssueService

    score = {
        "hard_constraints": {
            "Max_ripple": {
                "passed": False,
                "current_value": 0.8,
                "threshold": 0.5,
                "reason": "Max_ripple exceeds max_ripple_v",
            }
        }
    }
    first = IssueService().build_issues(
        score,
        {"Overall_status": "FAIL_RIPPLE", "worst_stage": 7},
        [{"stage": 7, "Max_ripple": 0.8}],
        "artifact://run/diagnosis_report.md",
    )
    second = IssueService().build_issues(
        score,
        {"Overall_status": "FAIL_RIPPLE", "worst_stage": 7},
        [{"stage": 7, "Max_ripple": 0.8}],
        "artifact://run/diagnosis_report.md",
    )

    assert len(first) == 1
    issue = first[0]
    assert issue.issue_id == second[0].issue_id
    assert issue.constraint_key == "FAIL_RIPPLE"
    assert issue.category == "waveform_quality"
    assert issue.severity == "high"
    assert issue.affected_nodes == ("o7",)
    assert issue.metric_refs == ("max_ripple",)
    assert issue.possible_causes
    assert issue.recommended_actions
    assert issue.evidence_refs == ("artifact://run/diagnosis_report.md",)
    assert issue.classification == "known"


def test_unknown_failure_is_never_dropped():
    from goa_eval.product.issue_service import IssueService

    issues = IssueService().build_issues(
        {"hard_constraints": {"Novel_constraint": {"passed": False, "reason": "novel failure"}}},
        {"Overall_status": "FAIL_NOVEL"},
        [],
        None,
    )

    assert len(issues) == 1
    assert issues[0].constraint_key == "FAIL_NOVEL"
    assert issues[0].classification == "unclassified"
    assert issues[0].category == "unclassified"


def test_analysis_bundle_contains_issues_referencing_published_evidence(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    project_service = ProjectService(repository, artifact_store)
    workspace = project_service.create_workspace("GOA team")
    project = project_service.create_project(workspace.workspace_id, "GOA", "goa_8k", "spec_v1").project
    version = project_service.create_design_version(project.project_id, "baseline")
    snapshot = InputService(repository, artifact_store).create_input_snapshot(
        design_version_id=version.design_version_id,
        files=[InputFile("waveform.csv", Path("examples/sample_waveform.csv"))],
        preview_config=UploadedCaseConfig(case_id="preview"),
    )

    result = AnalysisService(repository, artifact_store).run_analysis(
        design_version_id=version.design_version_id,
        input_manifest_ref=snapshot.manifest_ref,
        config=UploadedCaseConfig(case_id="issues"),
    )

    assert result.issue_manifest_ref is not None
    issues = json.loads(artifact_store.resolve(result.issue_manifest_ref).read_text(encoding="utf-8"))
    assert issues["issues"]
    published_uris = {record.source_ref for record in repository.list_evidence("analysis_run", result.analysis_run_id)}
    assert all(set(issue["evidence_refs"]) <= published_uris for issue in issues["issues"])
