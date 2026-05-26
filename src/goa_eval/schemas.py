from __future__ import annotations

from collections.abc import Iterable, Mapping


SCHEMA_VERSION = "1.0"
RESULT_VERSION = "1.0"

BOUNDARY_FIELDS = [
    "schema_version",
    "result_version",
    "data_source",
    "engineering_validity",
]

REAL_SUMMARY_REQUIRED_FIELDS = [
    *BOUNDARY_FIELDS,
    "run_id",
    "run_timestamp",
    "stage_count",
    "Seq_pass",
    "All_pulses_exist",
    "FalseTriggerCount",
    "Max_overlap_ratio",
    "Max_ripple",
    "WaveformActivityScore",
    "LowFreqStable",
    "Overall_status",
]

REAL_METRICS_COLUMNS = [
    "schema_version",
    "result_version",
    "stage",
    "node",
    "PulseExist",
    "LegalPulseCount",
    "VOH_mean",
    "VOH_max",
    "VHoldEnd",
    "VoltageLoss",
    "VoltageLossRatio",
    "VOL_max",
    "PulseWidth",
    "Delay",
    "RiseTime",
    "FallTime",
    "Ripple",
    "RippleRaw",
    "FalseTrigger",
    "FalseTriggerCount",
    "Overlap",
    "OverlapRatio",
    "SignalMin",
    "SignalMax",
    "SignalSwing",
    "HighCrossingCount",
    "LowCrossingCount",
    "TimeAboveHighRatio",
    "TimeBelowLowRatio",
    "WaveformActivityScore",
    "legal_windows",
    "primary_window",
    "repeated_windows",
    "false_trigger_windows",
    "pulse_exist",
    "rise_edge_time",
    "fall_edge_time",
    "pulse_width",
    "rising_time",
    "falling_time",
    "ripple",
    "ripple_mode",
    "false_trigger",
    "overlap_with_next",
    "overlap_ratio",
    "delay_to_next",
]

SCORE_SUMMARY_REQUIRED_FIELDS = [
    "schema_version",
    "result_version",
    "hard_constraint_passed",
    "hard_constraint_failures",
    "hard_constraints",
    "failure_reasons",
    "warning_reasons",
    "metric_penalties",
    "soft_scores",
    "score_explanations",
    "overall_score",
]

OPTIMIZATION_DATASET_COLUMNS = [
    "schema_version",
    "result_version",
    "run_id",
    "run_timestamp",
    "design_name",
    "parameter_set_id",
    "W_PU",
    "W_PD",
    "C_boot",
    "C_load",
    "V_CLKH",
    "capacitance",
    "drive_resistance",
    "transistor_width",
    "transistor_length",
    "vdd",
    "load_cap",
    "temp",
    "corner",
    "VOH_min",
    "VOH_std",
    "VOL_max_all",
    "Width_mean",
    "Width_std",
    "Delay_mean",
    "Delay_std",
    "Max_ripple",
    "Max_voltage_loss",
    "Max_voltage_loss_ratio",
    "VoltageLoss_p95",
    "VOH_p1",
    "VOH_p5",
    "VOH_p50",
    "Ripple_p95",
    "Delay_p95",
    "VOH_slope",
    "VoltageLoss_slope",
    "Delay_slope",
    "Max_overlap",
    "Max_overlap_ratio",
    "LowFreqStable",
    "worst_stage",
    "first_failed_stage",
    "Seq_pass",
    "All_pulses_exist",
    "FalseTriggerCount",
    "WaveformActivityScore",
    "Overall_status",
    "hard_constraint_passed",
    "overall_status",
    "overall_score",
    "metric_provenance",
    "data_source",
    "engineering_validity",
]

RECOMMENDATION_REQUIRED_FIELDS = [
    "schema_version",
    "result_version",
    "recommendation_id",
    "severity",
    "trigger_metric",
    "current_value",
    "threshold",
    "possible_physical_causes",
    "next_tuning_actions",
    "needs_metric_review",
    "message",
    "data_source",
    "engineering_validity",
]

BATCH_METRICS_EXTRA_COLUMNS = [
    "run_id",
    "circuit_version",
    "C_store",
    "R_driver",
    "W_pmos",
    "W_nmos",
    "VDD",
    "load_cap",
    "temp",
    "corner",
]

BATCH_SCORES_COLUMNS = [
    "run_id",
    "overall_score",
    "hard_constraint_passed",
    "failure_reasons",
    "warning_reasons",
    "function_score",
    "quality_score",
    "stability_score",
    "consistency_score",
    "cost_score",
]

BATCH_MANIFEST_REQUIRED_FIELDS = [
    "schema_version",
    "result_version",
    "run_count",
    "runs_dir",
    "output_dir",
    "engineering_validity",
]


def with_versions(payload: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "result_version": RESULT_VERSION, **payload}


def validate_required_fields(payload: Mapping[str, object], required_fields: Iterable[str]) -> None:
    missing = sorted(field for field in required_fields if field not in payload)
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
