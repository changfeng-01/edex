import pytest

from goa_eval.schemas import (
    RESULT_VERSION,
    SCHEMA_VERSION,
    BATCH_MANIFEST_REQUIRED_FIELDS,
    BATCH_METRICS_EXTRA_COLUMNS,
    BATCH_SCORES_COLUMNS,
    REAL_METRICS_COLUMNS,
    REAL_SUMMARY_REQUIRED_FIELDS,
    RECOMMENDATION_REQUIRED_FIELDS,
    validate_required_fields,
)


def test_schema_versions_are_public_strings():
    assert SCHEMA_VERSION == "1.0"
    assert RESULT_VERSION == "1.0"


def test_real_result_schema_contains_stable_boundary_fields():
    assert {"schema_version", "result_version", "data_source", "engineering_validity"} <= set(REAL_SUMMARY_REQUIRED_FIELDS)
    assert {"stage", "node", "Ripple", "Overlap", "OverlapRatio"} <= set(REAL_METRICS_COLUMNS)
    assert {
        "recommendation_id",
        "severity",
        "trigger_metric",
        "current_value",
        "threshold",
        "possible_physical_causes",
        "next_tuning_actions",
        "needs_metric_review",
        "message",
    } <= set(RECOMMENDATION_REQUIRED_FIELDS)


def test_batch_schema_contains_parameter_and_manifest_fields():
    assert {"run_id", "circuit_version", "C_store", "R_driver", "VDD", "temp", "corner"} <= set(BATCH_METRICS_EXTRA_COLUMNS)
    assert {"run_id", "overall_score", "failure_reasons", "warning_reasons"} <= set(BATCH_SCORES_COLUMNS)
    assert {"schema_version", "result_version", "run_count", "engineering_validity"} <= set(BATCH_MANIFEST_REQUIRED_FIELDS)


def test_validate_required_fields_reports_missing_keys():
    with pytest.raises(ValueError, match="missing required fields: engineering_validity, result_version"):
        validate_required_fields(
            {"schema_version": "1.0", "data_source": "real_simulation_csv"},
            ["schema_version", "result_version", "data_source", "engineering_validity"],
        )
