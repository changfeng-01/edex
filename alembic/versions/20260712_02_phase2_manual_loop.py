"""Add the Phase 2 manual simulation workflow tables."""

from alembic import op
import sqlalchemy as sa


revision = "20260712_02"
down_revision = "20260711_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_experiments",
        sa.Column("experiment_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.project_id"), nullable=False),
        sa.Column(
            "baseline_design_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=False,
        ),
        sa.Column("objective_spec", sa.JSON(), nullable=False),
        sa.Column("parameter_space_ref", sa.String(1024), nullable=True),
        sa.Column("strategy_config", sa.JSON(), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "best_confirmed_design_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("ix_optimization_experiments_project_id", "optimization_experiments", ["project_id"])
    op.create_index("ix_optimization_experiments_state", "optimization_experiments", ["state"])

    op.create_table(
        "simulation_jobs",
        sa.Column("simulation_job_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.project_id"), nullable=False),
        sa.Column("candidate_ids", sa.JSON(), nullable=False),
        sa.Column("adapter_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_manifest_ref", sa.String(1024), nullable=True),
        sa.Column("command_manifest_ref", sa.String(1024), nullable=True),
        sa.Column("result_manifest_ref", sa.String(1024), nullable=True),
        sa.Column("logs_ref", sa.String(1024), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("export_attempt", sa.Integer(), nullable=False),
        sa.Column("import_attempt", sa.Integer(), nullable=False),
        sa.Column("batch_ref", sa.JSON(), nullable=True),
        sa.Column("result_ref", sa.JSON(), nullable=True),
        sa.Column("result_sha256", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.UniqueConstraint("simulation_job_id", "result_sha256", name="uq_simulation_job_result"),
    )
    op.create_index("ix_simulation_jobs_project_id", "simulation_jobs", ["project_id"])
    op.create_index("ix_simulation_jobs_status", "simulation_jobs", ["status"])

    op.create_table(
        "candidates",
        sa.Column("candidate_id", sa.String(64), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(64),
            sa.ForeignKey("optimization_experiments.experiment_id"),
            nullable=False,
        ),
        sa.Column(
            "parent_design_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=False,
        ),
        sa.Column("parameter_changes", sa.JSON(), nullable=False),
        sa.Column("strategy", sa.String(128), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("selection_scores", sa.JSON(), nullable=False),
        sa.Column("selection_score", sa.Float(), nullable=True),
        sa.Column("evaluated_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("must_resimulate", sa.Boolean(), nullable=False),
        sa.Column("simulation_job_id", sa.String(64), nullable=True),
        sa.Column(
            "result_design_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("ix_candidates_experiment_id", "candidates", ["experiment_id"])
    op.create_index("ix_candidates_simulation_job_id", "candidates", ["simulation_job_id"])
    op.create_index("ix_candidates_status", "candidates", ["status"])

    op.create_table(
        "comparisons",
        sa.Column("comparison_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.project_id"), nullable=False),
        sa.Column(
            "baseline_design_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=False,
        ),
        sa.Column(
            "result_design_version_id",
            sa.String(64),
            sa.ForeignKey("design_versions.design_version_id"),
            nullable=False,
        ),
        sa.Column(
            "baseline_analysis_run_id",
            sa.String(64),
            sa.ForeignKey("analysis_runs.analysis_run_id"),
            nullable=True,
        ),
        sa.Column(
            "result_analysis_run_id",
            sa.String(64),
            sa.ForeignKey("analysis_runs.analysis_run_id"),
            nullable=True,
        ),
        sa.Column("metric_deltas", sa.JSON(), nullable=False),
        sa.Column("constraint_changes", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("ix_comparisons_project_id", "comparisons", ["project_id"])
    op.create_index("ix_comparisons_verdict", "comparisons", ["verdict"])


def downgrade() -> None:
    op.drop_table("comparisons")
    op.drop_table("candidates")
    op.drop_table("simulation_jobs")
    op.drop_table("optimization_experiments")
