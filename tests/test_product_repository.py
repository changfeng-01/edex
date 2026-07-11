from dataclasses import replace

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    AuditEventRecord,
    DesignVersionRecord,
    EvidenceRecord,
    ProjectRecord,
    WorkspaceRecord,
    new_id,
)
from goa_eval.product.repositories import SqlAlchemyProductRepository


def build_repository(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    return engine, SqlAlchemyProductRepository(engine)


def test_project_round_trip(tmp_path):
    _, repo = build_repository(tmp_path)
    workspace = WorkspaceRecord(workspace_id=new_id("workspace"), name="GOA team")
    project = ProjectRecord(
        project_id=new_id("project"),
        workspace_id=workspace.workspace_id,
        name="720-stage GOA",
        circuit_profile_id="goa_8k_reference",
        spec_revision_id="spec_v1",
    )

    repo.add_workspace(workspace)
    repo.add_project(project)

    assert repo.get_project(project.project_id) == project
    assert repo.list_projects(workspace.workspace_id) == [project]


def test_design_analysis_and_evidence_round_trip(tmp_path):
    _, repo = build_repository(tmp_path)
    workspace = WorkspaceRecord(workspace_id=new_id("workspace"), name="GOA team")
    project = ProjectRecord(
        project_id=new_id("project"),
        workspace_id=workspace.workspace_id,
        name="720-stage GOA",
        circuit_profile_id="goa_8k_reference",
        spec_revision_id="spec_v1",
    )
    version = DesignVersionRecord(
        design_version_id=new_id("version"),
        project_id=project.project_id,
        label="baseline",
        parameter_set_ref="artifact://params/base.yaml",
    )
    run = AnalysisRunRecord(
        analysis_run_id=new_id("run"),
        design_version_id=version.design_version_id,
        input_manifest_ref="artifact://inputs/manifest.json",
        spec_revision_id="spec_v1",
        profile_revision_id="goa_profile_v1",
    )
    evidence = EvidenceRecord(
        evidence_id=new_id("evidence"),
        subject_type="analysis_run",
        subject_id=run.analysis_run_id,
        evidence_type="input_manifest",
        source_ref=run.input_manifest_ref,
        checksum="a" * 64,
    )

    repo.add_workspace(workspace)
    repo.add_project(project)
    repo.add_design_version(version)
    repo.add_analysis_run(run)
    repo.add_evidence(evidence)

    assert repo.get_design_version(version.design_version_id) == version
    assert repo.get_analysis_run(run.analysis_run_id) == run
    assert repo.list_evidence("analysis_run", run.analysis_run_id) == [evidence]

    completed = replace(run, status=AnalysisStatus.COMPLETED, completed_at="2026-07-11T12:00:00+00:00")
    repo.update_analysis_run(completed)
    assert repo.get_analysis_run(run.analysis_run_id) == completed


def test_audit_event_is_appended(tmp_path):
    _, repo = build_repository(tmp_path)
    event = AuditEventRecord(
        event_id=new_id("event"),
        actor_id="user_local",
        action="project.created",
        subject_type="project",
        subject_id="project_example",
        details={"profile": "goa_8k_reference"},
    )

    repo.append_audit_event(event)

    assert repo.list_audit_events("project", "project_example") == [event]


def test_alembic_upgrade_creates_product_tables(tmp_path):
    database_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")

    table_names = set(inspect(make_engine(f"sqlite:///{database_path.as_posix()}")).get_table_names())
    assert {
        "workspaces",
        "projects",
        "design_versions",
        "analysis_runs",
        "evidence_records",
        "audit_events",
    } <= table_names
