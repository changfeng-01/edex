"""Create the CircuitPilot product core tables."""

from alembic import op
import sqlalchemy as sa


revision = "20260711_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("workspace_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("circuit_profile_id", sa.String(128), nullable=False),
        sa.Column("spec_revision_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])
    op.create_table(
        "design_versions",
        sa.Column("design_version_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.project_id"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("parameter_set_ref", sa.String(1024), nullable=True),
        sa.Column("netlist_ref", sa.String(1024), nullable=True),
        sa.Column(
            "parent_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=True,
        ),
        sa.Column("source_candidate_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("ix_design_versions_project_id", "design_versions", ["project_id"])
    op.create_table(
        "analysis_runs",
        sa.Column("analysis_run_id", sa.String(64), primary_key=True),
        sa.Column(
            "design_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=False,
        ),
        sa.Column("input_manifest_ref", sa.String(1024), nullable=False),
        sa.Column("spec_revision_id", sa.String(128), nullable=False),
        sa.Column("profile_revision_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("artifact_bundle_ref", sa.String(1024), nullable=True),
        sa.Column("evidence_boundary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.String(64), nullable=True),
        sa.Column("completed_at", sa.String(64), nullable=True),
    )
    op.create_index("ix_analysis_runs_design_version_id", "analysis_runs", ["design_version_id"])
    op.create_table(
        "evidence_records",
        sa.Column("evidence_id", sa.String(64), primary_key=True),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("source_ref", sa.String(1024), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("boundary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("ix_evidence_records_subject_type", "evidence_records", ["subject_type"])
    op.create_index("ix_evidence_records_subject_id", "evidence_records", ["subject_id"])
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_events_subject_type", "audit_events", ["subject_type"])
    op.create_index("ix_audit_events_subject_id", "audit_events", ["subject_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("evidence_records")
    op.drop_table("analysis_runs")
    op.drop_table("design_versions")
    op.drop_table("projects")
    op.drop_table("workspaces")
