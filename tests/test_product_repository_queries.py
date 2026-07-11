import pytest

from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import AnalysisRunRecord, DesignVersionRecord, ProjectRecord, WorkspaceRecord
from goa_eval.product.repositories import SqlAlchemyProductRepository


@pytest.fixture
def product_repo(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    return SqlAlchemyProductRepository(engine)


def test_workspace_round_trip_and_listing(product_repo):
    first = WorkspaceRecord(
        workspace_id="workspace_a",
        name="A",
        created_at="2026-07-11T00:00:00+00:00",
    )
    second = WorkspaceRecord(
        workspace_id="workspace_b",
        name="B",
        created_at="2026-07-11T00:00:01+00:00",
    )
    product_repo.add_workspace(first)
    product_repo.add_workspace(second)

    assert product_repo.get_workspace("workspace_a") == first
    assert product_repo.list_workspaces() == [first, second]


def test_design_versions_are_project_scoped_and_deterministically_ordered(product_repo):
    _, first_project, second_project = _seed_projects(product_repo)
    later = DesignVersionRecord(
        design_version_id="version_b",
        project_id=first_project.project_id,
        label="later",
        created_at="2026-07-11T01:00:00+00:00",
    )
    tie_breaker = DesignVersionRecord(
        design_version_id="version_c",
        project_id=first_project.project_id,
        label="same time",
        created_at="2026-07-11T01:00:00+00:00",
    )
    earlier = DesignVersionRecord(
        design_version_id="version_a",
        project_id=first_project.project_id,
        label="earlier",
        created_at="2026-07-11T00:30:00+00:00",
    )
    other = DesignVersionRecord(
        design_version_id="version_other",
        project_id=second_project.project_id,
        label="other project",
    )
    for version in (later, other, tie_breaker, earlier):
        product_repo.add_design_version(version)

    assert product_repo.list_design_versions(first_project.project_id) == [earlier, later, tie_breaker]
    assert product_repo.list_design_versions("project_missing") == []


def test_analysis_runs_filter_by_exactly_one_scope(product_repo):
    _, first_project, second_project = _seed_projects(product_repo)
    first_version = _add_version(product_repo, first_project, "version_a")
    second_version = _add_version(product_repo, first_project, "version_b")
    other_version = _add_version(product_repo, second_project, "version_other")
    first_run = _add_run(product_repo, first_version, "run_a", "2026-07-11T01:00:00+00:00")
    second_run = _add_run(product_repo, second_version, "run_b", "2026-07-11T02:00:00+00:00")
    other_run = _add_run(product_repo, other_version, "run_other", "2026-07-11T03:00:00+00:00")

    assert product_repo.list_analysis_runs(project_id=first_project.project_id) == [first_run, second_run]
    assert product_repo.list_analysis_runs(design_version_id=second_version.design_version_id) == [second_run]
    assert product_repo.list_analysis_runs(project_id="project_missing") == []
    assert product_repo.list_analysis_runs(design_version_id="version_missing") == []
    assert other_run not in product_repo.list_analysis_runs(project_id=first_project.project_id)
    with pytest.raises(ValueError, match="exactly one"):
        product_repo.list_analysis_runs()
    with pytest.raises(ValueError, match="exactly one"):
        product_repo.list_analysis_runs(
            project_id=first_project.project_id,
            design_version_id=first_version.design_version_id,
        )


def test_latest_analysis_run_uses_started_at_then_id_order(product_repo):
    _, first_project, second_project = _seed_projects(product_repo)
    first_version = _add_version(product_repo, first_project, "version_a")
    second_version = _add_version(product_repo, first_project, "version_b")
    other_version = _add_version(product_repo, second_project, "version_other")
    _add_run(product_repo, first_version, "run_earlier", "2026-07-11T01:00:00+00:00")
    expected = _add_run(product_repo, second_version, "run_z", "2026-07-11T02:00:00+00:00")
    _add_run(product_repo, first_version, "run_a", "2026-07-11T02:00:00+00:00")
    _add_run(product_repo, other_version, "run_other", "2026-07-11T03:00:00+00:00")

    assert product_repo.get_latest_analysis_run(first_project.project_id) == expected
    assert product_repo.get_latest_analysis_run("project_missing") is None


def _seed_projects(product_repo):
    workspace = WorkspaceRecord(workspace_id="workspace_a", name="Workspace")
    first_project = ProjectRecord(
        project_id="project_a",
        workspace_id=workspace.workspace_id,
        name="First",
        circuit_profile_id="goa_8k_reference",
        spec_revision_id="spec_v1",
    )
    second_project = ProjectRecord(
        project_id="project_b",
        workspace_id=workspace.workspace_id,
        name="Second",
        circuit_profile_id="goa_8k_reference",
        spec_revision_id="spec_v1",
    )
    product_repo.add_workspace(workspace)
    product_repo.add_project(first_project)
    product_repo.add_project(second_project)
    return workspace, first_project, second_project


def _add_version(product_repo, project, version_id):
    version = DesignVersionRecord(
        design_version_id=version_id,
        project_id=project.project_id,
        label=version_id,
    )
    product_repo.add_design_version(version)
    return version


def _add_run(product_repo, version, run_id, started_at):
    run = AnalysisRunRecord(
        analysis_run_id=run_id,
        design_version_id=version.design_version_id,
        input_manifest_ref=f"artifact://inputs/{run_id}.json",
        spec_revision_id="spec_v1",
        profile_revision_id="profile_v1",
        started_at=started_at,
    )
    product_repo.add_analysis_run(run)
    return run
