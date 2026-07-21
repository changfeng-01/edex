from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from goa_eval.pia_ca_llso.features import extract_physics_features, resolve_physics_feature_config
from goa_eval.pia_ca_llso.integration import CandidateAdapter
from goa_eval.pia_ca_llso.io import ensure_output_dir, read_config, write_json, write_markdown
from goa_eval.pia_ca_llso.labeling import assign_level_labels
from goa_eval.pia_ca_llso.sklearn_baseline import predict_candidates, train_baseline_models


DATA_SOURCE = "real_simulation_csv"
ENGINEERING_VALIDITY = "simulation_only"
MUST_RESIMULATE = True

PIA_HISTORY_COLUMNS = [
    "sample_id",
    "circuit_domain_id",
    "topology_family",
    "technology_family",
    "process_family",
    "fidelity_level",
    "selection_propensity",
    "TFT_pullup_W",
    "TFT_pullup_L",
    "TFT_pulldown_W",
    "TFT_pulldown_L",
    "TFT_reset_W",
    "TFT_reset_L",
    "TFT_bootstrap_W",
    "TFT_bootstrap_L",
    "C_boot",
    "C_load",
    "CLK_amp",
    "CLK_rise_time",
    "CLK_fall_time",
    "VGH",
    "VGL",
    "Vth_shift",
    "overall_score",
    "hard_constraint_passed",
    "sim_success",
    "status",
    "source",
]

PIA_PARAMETER_COLUMNS = [
    "TFT_pullup_W",
    "TFT_pullup_L",
    "TFT_pulldown_W",
    "TFT_pulldown_L",
    "TFT_reset_W",
    "TFT_reset_L",
    "TFT_bootstrap_W",
    "TFT_bootstrap_L",
    "C_boot",
    "C_load",
    "CLK_amp",
    "CLK_rise_time",
    "CLK_fall_time",
    "VGH",
    "VGL",
    "Vth_shift",
]

PIA_OUTPUT_COLUMNS = PIA_HISTORY_COLUMNS + [
    "data_source",
    "engineering_validity",
    "must_resimulate",
    "training_eligible",
    "missing_feature_count",
    "missing_reason",
]

SAFE_COLUMN_MAP = {
    "W_PU": "TFT_pullup_W",
    "W_PD": "TFT_pulldown_W",
    "C_boot": "C_boot",
    "C_load": "C_load",
    "load_cap": "C_load",
    "V_CLKH": "CLK_amp",
    "VGH": "VGH",
    "VGL": "VGL",
    "Vth_shift": "Vth_shift",
    "CLK_rise_time": "CLK_rise_time",
    "CLK_fall_time": "CLK_fall_time",
    "TFT_pullup_W": "TFT_pullup_W",
    "TFT_pullup_L": "TFT_pullup_L",
    "TFT_pulldown_W": "TFT_pulldown_W",
    "TFT_pulldown_L": "TFT_pulldown_L",
    "TFT_reset_W": "TFT_reset_W",
    "TFT_reset_L": "TFT_reset_L",
    "TFT_bootstrap_W": "TFT_bootstrap_W",
    "TFT_bootstrap_L": "TFT_bootstrap_L",
}

TRANSFER_METADATA_COLUMNS = (
    "circuit_domain_id",
    "topology_family",
    "technology_family",
    "process_family",
    "fidelity_level",
    "selection_propensity",
)

ROLE_AMBIGUOUS_COLUMNS = {"transistor_width", "transistor_length"}
PAPER_DB_FILES = [
    "paper_cases.csv",
    "paper_params_long.csv",
    "paper_waveform_index.csv",
    "paper_goa_leaderboard.csv",
]


@dataclass
class TrainingDataArtifacts:
    history: pd.DataFrame
    labeled_history: pd.DataFrame
    missing_report: pd.DataFrame
    train_report: dict[str, Any]
    candidate_predictions: pd.DataFrame | None = None
    parse_errors: list[dict[str, Any]] = field(default_factory=list)


def build_training_data_from_db(
    *,
    paper_db: Path,
    history_root: Path,
    output_dir: Path,
    config_path: Path | None = None,
    optimization_datasets: Iterable[Path] = (),
    candidate_csv: Path | None = None,
) -> TrainingDataArtifacts:
    output_dir = ensure_output_dir(output_dir)
    config = read_config(config_path)
    profile_config = resolve_physics_feature_config(config)

    missing_rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    paper_tables = _read_paper_database(paper_db, missing_rows)
    history_rows = _history_rows_from_optimization_datasets(
        history_root=history_root,
        optimization_datasets=optimization_datasets,
        missing_rows=missing_rows,
        parse_errors=parse_errors,
    )
    history_rows.extend(_history_rows_from_paper_leaderboard(paper_tables, missing_rows))

    history = _history_frame(history_rows)
    labeled_history = assign_level_labels(history) if not history.empty else _empty_labeled_history()
    if not labeled_history.empty:
        features, feature_report = extract_physics_features(labeled_history, profile_config)
        model_input = pd.concat([labeled_history.reset_index(drop=True), features.reset_index(drop=True)], axis=1)
        models = train_baseline_models(model_input, list(features.columns))
        model_report = _summarize_model_report(models, feature_report)
    else:
        features = pd.DataFrame()
        feature_report = _empty_feature_report()
        model_report = _empty_model_report()

    candidate_predictions = None
    if candidate_csv is not None:
        candidates = CandidateAdapter().load(candidate_csv)
        candidate_features, candidate_feature_report = extract_physics_features(candidates, profile_config)
        candidate_predictions = predict_candidates(models if not labeled_history.empty else {}, candidate_features, list(features.columns))
        candidate_predictions = pd.concat([candidates.reset_index(drop=True), candidate_predictions.reset_index(drop=True)], axis=1)
        candidate_predictions = _deduplicate_columns(candidate_predictions)
        candidate_predictions["data_source"] = DATA_SOURCE
        candidate_predictions["engineering_validity"] = ENGINEERING_VALIDITY
        candidate_predictions["must_resimulate"] = MUST_RESIMULATE
        candidate_predictions.to_csv(output_dir / "pia_candidate_predictions.csv", index=False, encoding="utf-8-sig")
        write_markdown(output_dir / "pia_candidate_prediction_report.md", _candidate_prediction_report(candidate_predictions))
        model_report["candidate_feature_report"] = candidate_feature_report

    missing_report = _missing_frame(missing_rows, history)
    train_report = _train_report(
        history=history,
        labeled_history=labeled_history,
        missing_report=missing_report,
        parse_errors=parse_errors,
        model_report=model_report,
        candidate_predictions=candidate_predictions,
    )

    history.to_csv(output_dir / "pia_training_history.csv", index=False, encoding="utf-8-sig")
    labeled_history.to_csv(output_dir / "pia_labeled_history.csv", index=False, encoding="utf-8-sig")
    missing_report.to_csv(output_dir / "pia_missing_data_report.csv", index=False, encoding="utf-8-sig")
    write_json(output_dir / "pia_missing_data_report.json", _json_ready(missing_report.to_dict("records")))
    write_json(output_dir / "pia_train_report.json", _json_ready(train_report))
    write_markdown(output_dir / "pia_training_dataset_card.md", _dataset_card(train_report))
    return TrainingDataArtifacts(
        history=history,
        labeled_history=labeled_history,
        missing_report=missing_report,
        train_report=train_report,
        candidate_predictions=candidate_predictions,
        parse_errors=parse_errors,
    )


def _read_paper_database(paper_db: Path, missing_rows: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    tables = {}
    for filename in PAPER_DB_FILES:
        path = paper_db / filename
        if not path.exists():
            tables[filename] = pd.DataFrame()
            missing_rows.append(_missing_row("paper_database", path, "", filename, "missing_database_file"))
            continue
        try:
            tables[filename] = pd.read_csv(path)
        except Exception as exc:
            tables[filename] = pd.DataFrame()
            missing_rows.append(_missing_row("paper_database", path, "", filename, f"parse_error:{type(exc).__name__}"))
    cases = tables.get("paper_cases.csv", pd.DataFrame())
    if cases.empty:
        for column in PIA_PARAMETER_COLUMNS + ["overall_score", "hard_constraint_passed"]:
            missing_rows.append(_missing_row("paper_database", paper_db / "paper_cases.csv", "", column, "empty_paper_database"))
    else:
        for _, row in cases.iterrows():
            case_id = _clean_string(row.get("case_id"))
            missing_rows.append(
                _missing_row("paper_database", paper_db / "paper_cases.csv", case_id, "real_simulation_csv", "needs_real_simulation_csv")
            )
    return tables


def _history_rows_from_optimization_datasets(
    *,
    history_root: Path,
    optimization_datasets: Iterable[Path],
    missing_rows: list[dict[str, Any]],
    parse_errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _optimization_dataset_paths(history_root, optimization_datasets):
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            error = {"source_path": str(path), "error_type": "parse_error", "message": f"{type(exc).__name__}: {exc}"}
            parse_errors.append(error)
            missing_rows.append(_missing_row("optimization_dataset", path, "", "csv", "parse_error"))
            continue
        for index, raw_row in frame.iterrows():
            raw = raw_row.to_dict()
            sample_id = _sample_id(raw, path, index)
            if not _has_training_boundary(raw):
                missing_rows.append(_missing_row("optimization_dataset", path, sample_id, "data_source", "not_training_boundary"))
                continue
            row, row_missing = _map_history_row(raw, sample_id=sample_id, source_path=path)
            rows.append(row)
            missing_rows.extend(row_missing)
    return rows


def _history_rows_from_paper_leaderboard(
    paper_tables: dict[str, pd.DataFrame],
    missing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    leaderboard = paper_tables.get("paper_goa_leaderboard.csv", pd.DataFrame())
    if leaderboard.empty:
        return []
    rows: list[dict[str, Any]] = []
    for index, raw_row in leaderboard.iterrows():
        raw = raw_row.to_dict()
        sample_id = _clean_string(raw.get("run_id")) or _clean_string(raw.get("case_id")) or f"paper_leaderboard_{index}"
        if not _has_training_boundary(raw):
            missing_rows.append(
                _missing_row("paper_leaderboard", Path("paper_goa_leaderboard.csv"), sample_id, "data_source", "not_training_boundary")
            )
            continue
        parameters = _parse_parameters(raw.get("parameters_json"))
        merged = {**raw, **parameters}
        row, row_missing = _map_history_row(merged, sample_id=sample_id, source_path=Path("paper_goa_leaderboard.csv"))
        rows.append(row)
        missing_rows.extend(row_missing)
    return rows


def _optimization_dataset_paths(history_root: Path, optimization_datasets: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    if history_root.exists():
        paths.extend(sorted(history_root.rglob("optimization_dataset.csv")))
    paths.extend(Path(path) for path in optimization_datasets)
    seen: set[str] = set()
    unique = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _map_history_row(raw: dict[str, Any], *, sample_id: str, source_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row: dict[str, Any] = {column: None for column in PIA_OUTPUT_COLUMNS}
    row["sample_id"] = sample_id
    row["overall_score"] = _value(raw.get("overall_score") if "overall_score" in raw else raw.get("score"))
    row["hard_constraint_passed"] = _value(raw.get("hard_constraint_passed") if "hard_constraint_passed" in raw else raw.get("hard_pass"))
    row["sim_success"] = _value(raw.get("sim_success", True))
    row["status"] = _status(raw)
    row["source"] = str(source_path)
    row["data_source"] = DATA_SOURCE
    row["engineering_validity"] = ENGINEERING_VALIDITY
    row["must_resimulate"] = MUST_RESIMULATE
    row["training_eligible"] = True
    row["missing_reason"] = ""

    for column in TRANSFER_METADATA_COLUMNS:
        if column in raw and not _is_missing(raw.get(column)):
            row[column] = _value(raw[column])
    if _is_missing(row.get("fidelity_level")):
        row["fidelity_level"] = 3

    for source_column, target_column in SAFE_COLUMN_MAP.items():
        if source_column in raw and not _is_missing(raw.get(source_column)) and _is_missing(row.get(target_column)):
            row[target_column] = _value(raw[source_column])
    if "W_T1" in raw or "L_T1" in raw or any(column in raw for column in ROLE_AMBIGUOUS_COLUMNS):
        row["missing_reason"] = "missing_role_mapping"

    missing_rows = []
    for column in PIA_PARAMETER_COLUMNS:
        if _is_missing(row.get(column)):
            reason = "missing_role_mapping" if _needs_role_mapping(raw, column) else "missing_feature"
            missing_rows.append(_missing_row("training_history", source_path, sample_id, column, reason))
    if _is_missing(row.get("overall_score")):
        row["training_eligible"] = False
        row["missing_reason"] = "missing_label"
        missing_rows.append(_missing_row("training_history", source_path, sample_id, "overall_score", "missing_label"))
    if _is_missing(row.get("hard_constraint_passed")):
        missing_rows.append(_missing_row("training_history", source_path, sample_id, "hard_constraint_passed", "missing_label"))
    row["missing_feature_count"] = sum(1 for column in PIA_PARAMETER_COLUMNS if _is_missing(row.get(column)))
    return row, missing_rows


def _history_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in PIA_OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    if frame.empty:
        return pd.DataFrame(columns=PIA_OUTPUT_COLUMNS)
    trainable = frame[frame["training_eligible"].astype(str).str.lower().eq("true")].copy()
    return trainable[PIA_OUTPUT_COLUMNS].reset_index(drop=True)


def _empty_labeled_history() -> pd.DataFrame:
    return pd.DataFrame(columns=PIA_OUTPUT_COLUMNS + ["level_label", "label_reason"])


def _missing_frame(missing_rows: list[dict[str, Any]], history: pd.DataFrame) -> pd.DataFrame:
    for _, row in history.iterrows():
        sample_id = _clean_string(row.get("sample_id"))
        for column in PIA_PARAMETER_COLUMNS:
            if _is_missing(row.get(column)):
                missing_rows.append(_missing_row("pia_training_history", Path(row.get("source") or ""), sample_id, column, "missing_feature"))
    frame = pd.DataFrame(missing_rows)
    columns = ["source_kind", "source_path", "sample_id", "field", "missing_reason", "must_resimulate"]
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[columns].drop_duplicates().reset_index(drop=True)


def _train_report(
    *,
    history: pd.DataFrame,
    labeled_history: pd.DataFrame,
    missing_report: pd.DataFrame,
    parse_errors: list[dict[str, Any]],
    model_report: dict[str, Any],
    candidate_predictions: pd.DataFrame | None,
) -> dict[str, Any]:
    sample_count = int(len(history))
    model_statuses = {
        name: detail.get("model_status")
        for name, detail in model_report.get("models", {}).items()
        if isinstance(detail, dict) and "model_status" in detail
    }
    trained = sample_count >= 4 and any(status == "ok" for status in model_statuses.values())
    status = "trained" if trained else "insufficient_data"
    return {
        "status": status,
        "sample_count": sample_count,
        "labeled_sample_count": int(len(labeled_history)),
        "missing_item_count": int(len(missing_report)),
        "parse_error_count": int(len(parse_errors)),
        "parse_errors": parse_errors,
        "model_report": model_report,
        "candidate_prediction_count": 0 if candidate_predictions is None else int(len(candidate_predictions)),
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": MUST_RESIMULATE,
        "claim_boundary": "next-run simulation suggestions",
    }


def _summarize_model_report(models: dict[str, Any], feature_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "models": {
            name: {key: value for key, value in detail.items() if key != "model"}
            for name, detail in models.items()
            if isinstance(detail, dict)
        },
        "feature_cols": list(models.get("feature_cols", [])),
        "feature_report": feature_report,
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": MUST_RESIMULATE,
    }


def _empty_model_report() -> dict[str, Any]:
    return {
        "models": {
            "level": {"model_status": "insufficient_data", "unavailable_reason": "insufficient_data"},
            "score": {"model_status": "insufficient_data", "unavailable_reason": "insufficient_data"},
            "hard_pass": {"model_status": "insufficient_data", "unavailable_reason": "insufficient_data"},
        },
        "feature_cols": [],
        "feature_report": _empty_feature_report(),
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": MUST_RESIMULATE,
    }


def _empty_feature_report() -> dict[str, Any]:
    return {
        "feature_count": 0,
        "feature_names": [],
        "missing_inputs": PIA_PARAMETER_COLUMNS,
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
    }


def _dataset_card(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# PIA-CA-LLSO Database Training Dataset Card",
            "",
            f"- status: {report.get('status')}",
            f"- sample_count: {report.get('sample_count')}",
            f"- missing_item_count: {report.get('missing_item_count')}",
            f"- parse_error_count: {report.get('parse_error_count')}",
            "- data_source = real_simulation_csv",
            "- engineering_validity = simulation_only",
            "- must_resimulate = true",
            "- weak_label: paper-derived rows remain weak labels until externally evaluated.",
            "- claim_boundary: next-run simulation suggestions only.",
            "- not_intended_use: physical validation or replacement for rerun simulation.",
            "",
        ]
    )


def _candidate_prediction_report(candidate_predictions: pd.DataFrame) -> str:
    lines = [
        "# PIA-CA-LLSO Candidate Prediction Report",
        "",
        f"- candidate_count: {len(candidate_predictions)}",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "- claim_boundary: next-run simulation suggestions only.",
        "",
    ]
    for _, row in candidate_predictions.head(10).iterrows():
        candidate_id = row.get("candidate_id", "")
        predicted_score = row.get("predicted_score", "")
        p_hard_pass = row.get("p_hard_pass", "")
        lines.append(f"- {candidate_id}: predicted_score={predicted_score}, p_hard_pass={p_hard_pass}")
    return "\n".join(lines) + "\n"


def _missing_row(source_kind: str, source_path: Path, sample_id: str, field: str, reason: str) -> dict[str, Any]:
    return {
        "source_kind": source_kind,
        "source_path": str(source_path),
        "sample_id": sample_id,
        "field": field,
        "missing_reason": reason,
        "must_resimulate": MUST_RESIMULATE,
    }


def _sample_id(raw: dict[str, Any], path: Path, index: int) -> str:
    for key in ["sample_id", "run_id", "case_id", "parameter_set_id"]:
        value = _clean_string(raw.get(key))
        if value and value.lower() != "unknown":
            return value
    return f"{path.stem}_{index}"


def _status(raw: dict[str, Any]) -> str:
    explicit = _clean_string(raw.get("status"))
    if explicit:
        return explicit
    if not _truthy(raw.get("sim_success", True)):
        return "sim_failed"
    if "hard_constraint_passed" in raw:
        return "evaluated_feasible" if _truthy(raw.get("hard_constraint_passed")) else "evaluated_soft_fail"
    return "not_evaluable"


def _has_training_boundary(raw: dict[str, Any]) -> bool:
    return _clean_string(raw.get("data_source")) == DATA_SOURCE and _clean_string(raw.get("engineering_validity")) == ENGINEERING_VALIDITY


def _needs_role_mapping(raw: dict[str, Any], column: str) -> bool:
    if column.startswith("TFT_") and any(key in raw for key in ROLE_AMBIGUOUS_COLUMNS):
        return True
    if column.startswith("TFT_") and any(str(key).startswith(("W_T", "L_T")) for key in raw):
        return True
    return False


def _parse_parameters(value: Any) -> dict[str, Any]:
    if _is_missing(value):
        return {}
    try:
        data = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _deduplicate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[:, ~frame.columns.duplicated()].copy()


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "passed"}
    return bool(value)


def _clean_string(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() in {"", "TODO_NEEDS_MANUAL_EXTRACTION"}


def _value(value: Any) -> Any:
    if _is_missing(value):
        return None
    return value.item() if hasattr(value, "item") else value


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if not isinstance(value, (dict, list, tuple)):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    return value
