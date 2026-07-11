import json
from pathlib import Path

import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import AnalysisRunRecord, AnalysisStatus
from goa_eval.product.project_service import InvalidCircuitProfile, ProductNotFoundError, ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository


@pytest.fixture
def service_context(tmp_path: Path):
    profile_path = tmp_path / "profiles.yaml"
    profile_path.write_text(
        """
profiles:
  default:
    aliases: []
    metrics: {}
  goa_reference:
    aliases: [goa_alias]
    boundary:
      data_source: real_simulation_csv
      engineering_validity: simulation_only
      must_resimulate: true
    metrics:
      fall_time_s:
        unit: s
        maximum: 0.000001
""".strip(),
        encoding="utf-8",
    )
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """
thresholds:
  max_ripple_v: 0.5
cascade:
  stage_count: 720
""".strip(),
        encoding="utf-8",
    )
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    service = ProjectService(
        repository,
        artifact_store,
        circuit_profile_path=profile_path,
        default_spec_path=spec_path,
    )
    return service, repository, artifact_store, profile_path, spec_path


def test_create_workspace_uses_prefixed_id_and_appends_audit_event(service_context):
    service, repository, _, _, _ = service_context

    workspace = service.create_workspace("GOA team", actor_id="engineer_a")

    assert workspace.workspace_id.startswith("workspace_")
    assert repository.get_workspace(workspace.workspace_id) == workspace
    events = repository.list_audit_events("workspace", workspace.workspace_id)
    assert [(event.actor_id, event.action) for event in events] == [("engineer_a", "workspace.created")]


def test_create_project_validates_workspace_and_profile(service_context):
    service, _, _, _, _ = service_context

    with pytest.raises(ProductNotFoundError, match="workspace_missing"):
        service.create_project("workspace_missing", "GOA", "goa_alias", "spec_v1")

    workspace = service.create_workspace("GOA team")
    with pytest.raises(InvalidCircuitProfile, match="unknown_profile"):
        service.create_project(workspace.workspace_id, "GOA", "unknown_profile", "spec_v1")


def test_create_project_publishes_deterministic_config_snapshots_and_evidence(service_context):
    service, repository, artifact_store, profile_path, spec_path = service_context
    workspace = service.create_workspace("GOA team")

    first = service.create_project(
        workspace.workspace_id,
        "GOA first",
        "goa_alias",
        "spec_v1",
        actor_id="engineer_a",
    )
    second = service.create_project(
        workspace.workspace_id,
        "GOA second",
        "goa_alias",
        "spec_v1",
    )

    assert first.project.workspace_id == workspace.workspace_id
    assert first.project.name == "GOA first"
    assert first.project.circuit_profile_id == "goa_reference"
    assert first.project.spec_revision_id == "spec_v1"
    assert first.profile_snapshot.uri.startswith("artifact://")
    assert first.spec_snapshot.uri.startswith("artifact://")
    assert first.profile_snapshot.sha256 == second.profile_snapshot.sha256
    assert first.spec_snapshot.sha256 == second.spec_snapshot.sha256

    profile_snapshot = json.loads(artifact_store.resolve(first.profile_snapshot).read_text(encoding="utf-8"))
    spec_snapshot = json.loads(artifact_store.resolve(first.spec_snapshot).read_text(encoding="utf-8"))
    assert profile_snapshot["name"] == "goa_reference"
    assert profile_snapshot["boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }
    assert spec_snapshot == {
        "cascade": {"stage_count": 720},
        "evidence_boundary": {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        },
        "thresholds": {"max_ripple_v": 0.5},
    }
    assert str(profile_path.resolve()) not in first.project.spec_revision_id
    assert str(spec_path.resolve()) not in first.project.spec_revision_id

    evidence = repository.list_evidence("project", first.project.project_id)
    assert tuple(record.evidence_type for record in evidence) == ("profile_snapshot", "spec_snapshot")
    assert {record.source_ref for record in evidence} == {
        first.profile_snapshot.uri,
        first.spec_snapshot.uri,
    }
    assert all(record.checksum for record in evidence)
    assert all(record.boundary.data_source == "real_simulation_csv" for record in evidence)
    assert all(record.boundary.engineering_validity == "simulation_only" for record in evidence)
    assert all(record.boundary.must_resimulate is True for record in evidence)
    events = repository.list_audit_events("project", first.project.project_id)
    assert [(event.actor_id, event.action) for event in events] == [("engineer_a", "project.created")]


def test_create_design_version_validates_project_and_parent_scope(service_context):
    service, _, _, _, _ = service_context
    workspace = service.create_workspace("GOA team")
    first_project = service.create_project(workspace.workspace_id, "First", "goa_alias", "spec_v1").project
    second_project = service.create_project(workspace.workspace_id, "Second", "goa_alias", "spec_v1").project

    baseline = service.create_design_version(first_project.project_id, "baseline")
    assert baseline.design_version_id.startswith("version_")
    assert baseline.project_id == first_project.project_id
    child = service.create_design_version(first_project.project_id, "iteration 1", parent_version_id=baseline.design_version_id)
    assert child.parent_version_id == baseline.design_version_id

    with pytest.raises(ProductNotFoundError, match="project_missing"):
        service.create_design_version("project_missing", "baseline")
    other_parent = service.create_design_version(second_project.project_id, "other baseline")
    with pytest.raises(ValueError, match="same project"):
        service.create_design_version(
            first_project.project_id,
            "invalid child",
            parent_version_id=other_parent.design_version_id,
        )


def test_project_overview_returns_small_counts_latest_state_and_evidence_summary(service_context):
    service, repository, _, _, _ = service_context
    workspace = service.create_workspace("GOA team")
    project_result = service.create_project(workspace.workspace_id, "GOA", "goa_alias", "spec_v1")
    baseline = service.create_design_version(project_result.project.project_id, "baseline")
    iteration = service.create_design_version(project_result.project.project_id, "iteration")
    run = AnalysisRunRecord(
        analysis_run_id="run_latest",
        design_version_id=iteration.design_version_id,
        input_manifest_ref="artifact://inputs/input_manifest.json",
        spec_revision_id="spec_v1",
        profile_revision_id=project_result.profile_snapshot.uri,
        status=AnalysisStatus.COMPLETED,
        started_at="2026-07-11T02:00:00+00:00",
    )
    repository.add_analysis_run(run)

    overview = service.get_project_overview(project_result.project.project_id)

    assert overview.project == project_result.project
    assert overview.design_versions == (baseline, iteration)
    assert overview.version_count == 2
    assert overview.analysis_count == 1
    assert overview.latest_analysis_run == run
    assert overview.latest_analysis_status == AnalysisStatus.COMPLETED
    assert overview.evidence_count == 2
    assert overview.evidence_types == ("profile_snapshot", "spec_snapshot")
    assert not hasattr(overview, "waveform")

    with pytest.raises(ProductNotFoundError, match="project_missing"):
        service.get_project_overview("project_missing")
