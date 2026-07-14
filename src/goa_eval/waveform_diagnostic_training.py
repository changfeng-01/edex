from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re
from typing import Any

import numpy as np
import pandas as pd

from goa_eval.config import load_real_spec
from goa_eval.io_utils import sha256_file, write_json
from goa_eval.metrics import RealEvalConfig, compute_stage_metrics
from goa_eval.waveform_io import read_real_waveform


DATA_SOURCE = "real_simulation_csv"
ENGINEERING_VALIDITY = "simulation_only"
MUST_RESIMULATE = True
REGRESSION_TARGETS = {
    "risk_score",
    "propagation_delay_to_reference_s",
    "voltage_loss_vs_reference_v",
    "pixel_tracking_error_rms_v",
}


@dataclass
class WaveformDiagnosticArtifacts:
    samples: pd.DataFrame
    feature_matrix: pd.DataFrame
    predictions: pd.DataFrame
    report: dict[str, Any]


def train_waveform_diagnostic_model(
    *,
    waveform_path: Path,
    output_dir: Path,
    nominal_sp: Path | None = None,
    netlist: Path | None = None,
    model_cards: list[Path] | None = None,
    spec_path: Path | None = Path("config/spec.yaml"),
    random_state: int = 42,
) -> WaveformDiagnosticArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = load_real_spec(spec_path)
    config = _real_config(spec)
    waveform = read_real_waveform(waveform_path)
    nominal_params = parse_nominal_params(nominal_sp) if nominal_sp else {}

    samples = build_diagnostic_samples(waveform.frame, config=config, nominal_params=nominal_params)
    trained = _train_models(samples, random_state=random_state)
    predictions = _prediction_frame(samples, trained)
    feature_matrix = _encoded_feature_matrix(samples, trained)
    report = _build_report(
        samples=samples,
        trained=trained,
        waveform_path=waveform_path,
        nominal_sp=nominal_sp,
        netlist=netlist,
        model_cards=model_cards or [],
        spec_path=spec_path,
        nominal_params=nominal_params,
    )

    samples.to_csv(output_dir / "diagnostic_samples.csv", index=False, encoding="utf-8-sig")
    feature_matrix.to_csv(output_dir / "diagnostic_feature_matrix.csv", index=False, encoding="utf-8-sig")
    predictions.to_csv(output_dir / "diagnostic_predictions.csv", index=False, encoding="utf-8-sig")
    trained["feature_importance"].to_csv(output_dir / "feature_importance.csv", index=False, encoding="utf-8-sig")
    write_json(output_dir / "diagnostic_model_report.json", report)
    (output_dir / "diagnostic_model_card.md").write_text(_model_card(report), encoding="utf-8")
    _write_model_artifact(output_dir / "diagnostic_model.joblib", trained, report)

    return WaveformDiagnosticArtifacts(samples=samples, feature_matrix=feature_matrix, predictions=predictions, report=report)


def build_diagnostic_samples(frame: pd.DataFrame, *, config: RealEvalConfig, nominal_params: dict[str, str] | None = None) -> pd.DataFrame:
    nominal_params = nominal_params or {}
    time = frame["time"].to_numpy(dtype=float)
    raw_rows: list[dict[str, Any]] = []
    metrics_by_node: dict[str, dict[str, Any]] = {}
    for node in [str(column) for column in frame.columns if str(column) != "time"]:
        signal = frame[node].to_numpy(dtype=float)
        role = identify_signal_role(node)
        metrics = compute_stage_metrics(time, signal, config)
        metrics_by_node[node] = metrics
        row = {
            "sample_id": f"diag_{len(raw_rows) + 1:04d}",
            "node": node,
            **role,
            **_signal_stats(time, signal, config),
            **_selected_metric_values(metrics),
            "data_source": DATA_SOURCE,
            "engineering_validity": ENGINEERING_VALIDITY,
            "must_resimulate": MUST_RESIMULATE,
        }
        raw_rows.append(row)

    samples = pd.DataFrame(raw_rows)
    samples = _attach_reference_features(samples, frame, metrics_by_node, config)
    samples = _attach_risk_labels(samples, config=config, nominal_params=nominal_params)
    return samples


def identify_signal_role(node: str) -> dict[str, Any]:
    text = node.strip().lower()
    if text in {"do", "de"}:
        return {"signal_role": "ideal_data", "position": "source", "data_phase": "odd" if text == "do" else "even"}
    match = re.fullmatch(r"clk<(\d+)>", text)
    if match:
        return {"signal_role": "clock_source", "clock_phase": int(match.group(1)), "position": "source"}
    if text == "com":
        return {"signal_role": "common_electrode", "position": "source"}
    if text in {"doi", "do_mid", "do_far"}:
        position = {"doi": "near", "do_mid": "mid", "do_far": "far"}[text]
        return {"signal_role": "data_line", "position": position, "data_phase": "odd"}
    match = re.fullmatch(r"xi8<(\d+)>\.pixel", text)
    if match:
        index = int(match.group(1))
        return {
            "signal_role": "pixel_electrode",
            "position": f"pixel_{index}",
            "pixel_index": index,
            "data_phase": "odd" if index % 2 else "even",
        }
    match = re.fullmatch(r"xi0<(\d+)>\.xi0<(\d+)>\.(.+)", text)
    if match:
        module_index = int(match.group(1))
        unit_index = int(match.group(2))
        terminal = match.group(3)
        return {
            "signal_role": "goa_internal",
            "position": "tail_dummy" if module_index >= 91 else "active",
            "goa_module_index": module_index,
            "goa_unit_index": unit_index,
            "goa_terminal": terminal,
        }
    match = re.fullmatch(r"g<(\d+)>", text)
    if match:
        return {"signal_role": "gate_raw", "position": "source", "gate_row": int(match.group(1))}
    match = re.fullmatch(r"gate_(mid|far)<(\d+)>", text)
    if match:
        return {"signal_role": "gate_line", "position": match.group(1), "gate_row": int(match.group(2))}
    return {"signal_role": "unknown", "position": "unknown"}


def parse_nominal_params(path: Path) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    params: dict[str, str] = {}
    in_param_block = False
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue
        starts_param = line.lower().startswith(".param")
        continues = line.startswith("+")
        if starts_param:
            in_param_block = True
            line = line[6:].strip()
        elif continues and in_param_block:
            line = line[1:].strip()
        else:
            in_param_block = False
            continue
        for name, value in re.findall(r"([A-Za-z_]\w*)\s*=\s*([^\s]+)", line):
            params[name] = value
    return params


def _real_config(spec: dict[str, Any]) -> RealEvalConfig:
    return RealEvalConfig(
        high_threshold=spec["high_threshold"],
        low_threshold=spec["low_threshold"],
        target_pulse_width=spec["target_pulse_width"],
        pulse_width_tolerance=spec["pulse_width_tolerance"],
        max_overlap_ratio=spec["max_overlap_ratio"],
        max_ripple_v=spec["max_ripple_v"],
        max_voltage_loss_v=spec["max_voltage_loss_v"],
        max_delay_std=spec["max_delay_std"],
        min_voh_margin_v=spec["min_voh_margin_v"],
        target_refresh_hz=spec["target_refresh_hz"],
        stage_group_size=spec["cascade"]["stage_group_size"],
        min_pulse_width=spec["min_pulse_width"],
        false_trigger_min_duration=spec["false_trigger_min_duration"],
        ripple_mode=spec["ripple_mode"],
    )


def _signal_stats(time: np.ndarray, signal: np.ndarray, config: RealEvalConfig) -> dict[str, Any]:
    finite = signal[np.isfinite(signal)]
    if len(finite) == 0:
        return {
            "signal_min_v": None,
            "signal_max_v": None,
            "signal_mean_v": None,
            "signal_std_v": None,
            "signal_swing_v": None,
            "time_above_high_ratio": None,
            "time_below_low_ratio": None,
            "max_abs_slew_v_per_s": None,
        }
    duration = float(time[-1] - time[0]) if len(time) > 1 else 0.0
    return {
        "signal_min_v": float(np.nanmin(finite)),
        "signal_max_v": float(np.nanmax(finite)),
        "signal_mean_v": float(np.nanmean(finite)),
        "signal_std_v": float(np.nanstd(finite)),
        "signal_swing_v": float(np.nanmax(finite) - np.nanmin(finite)),
        "time_above_high_ratio": _duration_ratio(time, signal > config.high_threshold, duration),
        "time_below_low_ratio": _duration_ratio(time, signal < config.low_threshold, duration),
        "max_abs_slew_v_per_s": _max_abs_slew(time, signal),
    }


def _selected_metric_values(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "PulseExist",
        "LegalPulseCount",
        "rise_edge_time",
        "fall_edge_time",
        "PulseWidth",
        "VOH_mean",
        "VOH_max",
        "VOL_max",
        "RiseTime",
        "FallTime",
        "Ripple",
        "RippleRaw",
        "VHoldEnd",
        "VoltageLoss",
        "VoltageLossRatio",
        "FalseTrigger",
        "FalseTriggerCount",
        "SignalSwing",
        "HighCrossingCount",
        "LowCrossingCount",
        "WaveformActivityScore",
    ]
    return {key: _json_scalar(metrics.get(key)) for key in keys}


def _attach_reference_features(
    samples: pd.DataFrame,
    frame: pd.DataFrame,
    metrics_by_node: dict[str, dict[str, Any]],
    config: RealEvalConfig,
) -> pd.DataFrame:
    samples = samples.copy()
    for column in [
        "reference_node",
        "propagation_delay_to_reference_s",
        "voltage_loss_vs_reference_v",
        "max_abs_delta_vs_reference_v",
        "rms_delta_vs_reference_v",
        "pixel_tracking_error_rms_v",
        "pixel_tracking_error_max_v",
        "pixel_com_offset_mean_v",
        "dummy_active_delta_rms_v",
    ]:
        samples[column] = None

    for index, row in samples.iterrows():
        node = str(row["node"])
        reference = _reference_node(row, frame)
        if reference and reference in frame.columns:
            samples.at[index, "reference_node"] = reference
            samples.at[index, "propagation_delay_to_reference_s"] = _difference(
                metrics_by_node.get(node, {}).get("rise_edge_time"),
                metrics_by_node.get(reference, {}).get("rise_edge_time"),
            )
            samples.at[index, "voltage_loss_vs_reference_v"] = _difference(
                metrics_by_node.get(reference, {}).get("VOH_max"),
                metrics_by_node.get(node, {}).get("VOH_max"),
            )
            delta = frame[node].to_numpy(dtype=float) - frame[reference].to_numpy(dtype=float)
            samples.at[index, "max_abs_delta_vs_reference_v"] = _safe_float(np.nanmax(np.abs(delta)))
            samples.at[index, "rms_delta_vs_reference_v"] = _safe_float(math.sqrt(float(np.nanmean(delta * delta))))

        if row.get("signal_role") == "pixel_electrode":
            ideal = "do" if row.get("data_phase") == "odd" else "de"
            if ideal in frame.columns:
                delta = frame[node].to_numpy(dtype=float) - frame[ideal].to_numpy(dtype=float)
                samples.at[index, "pixel_tracking_error_rms_v"] = _safe_float(math.sqrt(float(np.nanmean(delta * delta))))
                samples.at[index, "pixel_tracking_error_max_v"] = _safe_float(np.nanmax(np.abs(delta)))
            if "com" in frame.columns:
                samples.at[index, "pixel_com_offset_mean_v"] = _safe_float(
                    np.nanmean(frame[node].to_numpy(dtype=float) - frame["com"].to_numpy(dtype=float))
                )

    samples = _attach_dummy_active_pairs(samples, frame)
    return samples


def _reference_node(row: pd.Series, frame: pd.DataFrame) -> str | None:
    role = row.get("signal_role")
    if role == "gate_line":
        gate_row = row.get("gate_row")
        return f"g<{int(gate_row)}>" if pd.notna(gate_row) else None
    if role == "data_line":
        return "do"
    if role == "pixel_electrode":
        return "do" if row.get("data_phase") == "odd" else "de"
    return None


def _attach_dummy_active_pairs(samples: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    samples = samples.copy()
    active_by_terminal = {
        str(row.get("goa_terminal")): str(row.get("node"))
        for _, row in samples.iterrows()
        if row.get("signal_role") == "goa_internal" and row.get("position") == "active" and row.get("goa_terminal")
    }
    for index, row in samples.iterrows():
        if row.get("signal_role") != "goa_internal" or row.get("position") != "tail_dummy":
            continue
        reference = active_by_terminal.get(str(row.get("goa_terminal")))
        node = str(row.get("node"))
        if reference and reference in frame.columns and node in frame.columns:
            delta = frame[node].to_numpy(dtype=float) - frame[reference].to_numpy(dtype=float)
            samples.at[index, "reference_node"] = reference
            samples.at[index, "dummy_active_delta_rms_v"] = _safe_float(math.sqrt(float(np.nanmean(delta * delta))))
            samples.at[index, "max_abs_delta_vs_reference_v"] = _safe_float(np.nanmax(np.abs(delta)))
            samples.at[index, "rms_delta_vs_reference_v"] = samples.at[index, "dummy_active_delta_rms_v"]
    return samples


def _attach_risk_labels(samples: pd.DataFrame, *, config: RealEvalConfig, nominal_params: dict[str, str]) -> pd.DataFrame:
    samples = samples.copy()
    vgh = _param_float(nominal_params, "VGH")
    vgl = _param_float(nominal_params, "VGL")
    scores = []
    reasons = []
    for _, row in samples.iterrows():
        score, reason = _risk_score(row, config=config, vgh=vgh, vgl=vgl)
        scores.append(score)
        reasons.append(";".join(reason))
    samples["risk_score"] = scores
    samples["risk_level"] = [_risk_level(score) for score in scores]
    samples["risk_reasons"] = reasons
    return samples


def _risk_score(row: pd.Series, *, config: RealEvalConfig, vgh: float | None, vgl: float | None) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    role = str(row.get("signal_role"))
    if role in {"gate_raw", "gate_line", "clock_source"} and not _truthy(row.get("PulseExist")):
        score += 45.0
        reasons.append("missing_pulse")
    false_count = _number(row.get("FalseTriggerCount")) or 0.0
    if false_count > 0:
        score += min(30.0, false_count * 15.0)
        reasons.append("false_trigger")
    score += _limited_ratio(row.get("Ripple"), config.max_ripple_v, 22.0, "ripple", reasons)
    score += _limited_ratio(row.get("VoltageLoss"), config.max_voltage_loss_v, 22.0, "voltage_loss", reasons)
    score += _limited_ratio(row.get("propagation_delay_to_reference_s"), config.max_delay_std, 18.0, "reference_delay", reasons, absolute=True)
    score += _limited_ratio(row.get("voltage_loss_vs_reference_v"), config.max_voltage_loss_v, 18.0, "reference_voltage_loss", reasons)
    score += _limited_ratio(row.get("pixel_tracking_error_rms_v"), config.max_voltage_loss_v, 18.0, "pixel_tracking_error", reasons)
    if _number(row.get("VOH_mean")) is not None and role in {"gate_raw", "gate_line", "clock_source"}:
        voh_margin = float(row["VOH_mean"]) - config.high_threshold
        if voh_margin < config.min_voh_margin_v:
            score += min(15.0, (config.min_voh_margin_v - voh_margin) / max(config.min_voh_margin_v, 1e-12) * 15.0)
            reasons.append("low_voh_margin")
    if vgh is not None and _number(row.get("signal_max_v")) is not None and float(row["signal_max_v"]) > vgh + 0.5:
        score += min(15.0, (float(row["signal_max_v"]) - vgh) * 3.0)
        reasons.append("high_overshoot")
    if vgl is not None and _number(row.get("signal_min_v")) is not None and float(row["signal_min_v"]) < vgl - 0.5:
        score += min(15.0, (vgl - float(row["signal_min_v"])) * 3.0)
        reasons.append("low_undershoot")
    if not reasons:
        reasons.append("within_basic_diagnostic_limits")
    return float(min(100.0, max(0.0, score))), reasons


def _limited_ratio(
    value: Any,
    limit: float | None,
    weight: float,
    reason: str,
    reasons: list[str],
    *,
    absolute: bool = False,
) -> float:
    number = _number(value)
    if number is None or not limit:
        return 0.0
    if absolute:
        number = abs(number)
    if number <= limit:
        return 0.0
    reasons.append(reason)
    return float(min(weight, weight * number / limit))


def _risk_level(score: float) -> str:
    if score >= 60.0:
        return "high"
    if score >= 25.0:
        return "medium"
    return "low"


def _train_models(samples: pd.DataFrame, *, random_state: int) -> dict[str, Any]:
    feature_cols = _feature_columns(samples)
    categorical_cols = _categorical_columns(samples, feature_cols)
    numeric_cols = [column for column in feature_cols if column not in categorical_cols]
    models: dict[str, Any] = {}
    model_reports: dict[str, Any] = {}
    predictions: dict[str, Any] = {}
    importances: list[pd.DataFrame] = []

    classifier_result = _fit_classifier(samples, feature_cols, categorical_cols, numeric_cols, random_state)
    models["risk_level"] = classifier_result["model"]
    model_reports["risk_level"] = classifier_result["report"]
    predictions.update(classifier_result["predictions"])
    if not classifier_result["importance"].empty:
        importances.append(classifier_result["importance"])

    for target in [
        "risk_score",
        "propagation_delay_to_reference_s",
        "voltage_loss_vs_reference_v",
        "pixel_tracking_error_rms_v",
    ]:
        result = _fit_regressor(samples, target, feature_cols, categorical_cols, numeric_cols, random_state)
        models[target] = result["model"]
        model_reports[target] = result["report"]
        predictions.update(result["predictions"])
        if not result["importance"].empty:
            importances.append(result["importance"])

    feature_importance = pd.concat(importances, ignore_index=True) if importances else pd.DataFrame(columns=["target", "feature", "importance"])
    return {
        "models": models,
        "model_reports": model_reports,
        "model_predictions": predictions,
        "feature_cols": feature_cols,
        "categorical_cols": categorical_cols,
        "numeric_cols": numeric_cols,
        "feature_importance": feature_importance,
        "encoded_features": _encode_for_report(samples, feature_cols, categorical_cols, numeric_cols),
    }


def _fit_classifier(
    samples: pd.DataFrame,
    feature_cols: list[str],
    categorical_cols: list[str],
    numeric_cols: list[str],
    random_state: int,
) -> dict[str, Any]:
    usable = samples.dropna(subset=["risk_level"]).copy()
    if len(usable) < 4 or usable["risk_level"].nunique() < 2:
        return _model_result(
            report={"model_status": "insufficient_data", "sample_count": int(len(usable)), "target": "risk_level"},
            predictions={
                "predicted_risk_level": samples["risk_level"].to_list(),
                "risk_level_model_status": ["insufficient_data"] * len(samples),
            },
        )
    feature_cols, categorical_cols, numeric_cols = _observed_feature_columns(usable, feature_cols, categorical_cols, numeric_cols)
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score
        from sklearn.pipeline import Pipeline
    except Exception as exc:
        return _sklearn_error("risk_level", exc, len(usable), samples)
    pipeline = Pipeline(
        [
            ("preprocess", _preprocessor(numeric_cols, categorical_cols)),
            ("model", RandomForestClassifier(n_estimators=96, random_state=random_state, min_samples_leaf=1)),
        ]
    )
    pipeline.fit(usable[feature_cols], usable["risk_level"])
    predicted = pipeline.predict(samples[feature_cols])
    report = {
        "model_status": "ok",
        "target": "risk_level",
        "sample_count": int(len(usable)),
        "class_count": int(usable["risk_level"].nunique()),
        "training_accuracy": float(accuracy_score(usable["risk_level"], pipeline.predict(usable[feature_cols]))),
    }
    predictions = {
        "predicted_risk_level": predicted,
        "risk_level_model_status": ["ok"] * len(samples),
    }
    for class_name, probability in zip(pipeline.named_steps["model"].classes_, pipeline.predict_proba(samples[feature_cols]).T):
        predictions[f"p_risk_{class_name}"] = probability
    return _model_result(report=report, model=pipeline, predictions=predictions, importance=_feature_importance(pipeline, "risk_level"))


def _fit_regressor(
    samples: pd.DataFrame,
    target: str,
    feature_cols: list[str],
    categorical_cols: list[str],
    numeric_cols: list[str],
    random_state: int,
) -> dict[str, Any]:
    target_values = pd.to_numeric(samples[target], errors="coerce") if target in samples.columns else pd.Series(dtype=float)
    usable = samples[target_values.notna()].copy()
    if len(usable) < 4 or target_values.dropna().nunique() < 2:
        return _model_result(
            report={"model_status": "insufficient_data", "sample_count": int(len(usable)), "target": target},
            predictions={
                f"predicted_{target}": target_values.to_list() if len(target_values) == len(samples) else [None] * len(samples),
                f"{target}_model_status": ["insufficient_data"] * len(samples),
            },
        )
    feature_cols, categorical_cols, numeric_cols = _observed_feature_columns(usable, feature_cols, categorical_cols, numeric_cols)
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
        from sklearn.pipeline import Pipeline
    except Exception as exc:
        return _sklearn_error(target, exc, len(usable), samples)
    pipeline = Pipeline(
        [
            ("preprocess", _preprocessor(numeric_cols, categorical_cols)),
            ("model", RandomForestRegressor(n_estimators=96, random_state=random_state, min_samples_leaf=1)),
        ]
    )
    y = pd.to_numeric(usable[target], errors="coerce")
    pipeline.fit(usable[feature_cols], y)
    trained_pred = pipeline.predict(usable[feature_cols])
    predicted = pipeline.predict(samples[feature_cols])
    report = {
        "model_status": "ok",
        "target": target,
        "sample_count": int(len(usable)),
        "training_mae": float(mean_absolute_error(y, trained_pred)),
        "training_r2": float(r2_score(y, trained_pred)) if len(usable) > 1 else None,
    }
    return _model_result(
        report=report,
        model=pipeline,
        predictions={f"predicted_{target}": predicted, f"{target}_model_status": ["ok"] * len(samples)},
        importance=_feature_importance(pipeline, target),
    )


def _preprocessor(numeric_cols: list[str], categorical_cols: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    try:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", encoder)])
    return ColumnTransformer([("num", numeric, numeric_cols), ("cat", categorical, categorical_cols)], remainder="drop")


def _observed_feature_columns(
    frame: pd.DataFrame,
    feature_cols: list[str],
    categorical_cols: list[str],
    numeric_cols: list[str],
) -> tuple[list[str], list[str], list[str]]:
    categorical = [column for column in categorical_cols if column in frame.columns and frame[column].notna().sum() > 0]
    numeric = [
        column
        for column in numeric_cols
        if column in frame.columns and pd.to_numeric(frame[column], errors="coerce").notna().sum() > 0
    ]
    selected = [column for column in feature_cols if column in set(categorical) | set(numeric)]
    return selected, categorical, numeric


def _feature_importance(model: Any, target: str) -> pd.DataFrame:
    estimator = model.named_steps.get("model")
    preprocess = model.named_steps.get("preprocess")
    importances = getattr(estimator, "feature_importances_", None)
    if importances is None:
        return pd.DataFrame(columns=["target", "feature", "importance"])
    try:
        names = list(preprocess.get_feature_names_out())
    except Exception:
        names = [f"feature_{index}" for index in range(len(importances))]
    return pd.DataFrame({"target": target, "feature": names, "importance": importances}).sort_values(
        ["target", "importance"], ascending=[True, False]
    )


def _model_result(
    *,
    report: dict[str, Any],
    model: Any = None,
    predictions: dict[str, Any] | None = None,
    importance: pd.DataFrame | None = None,
) -> dict[str, Any]:
    return {
        "report": report,
        "model": model,
        "predictions": predictions or {},
        "importance": importance if importance is not None else pd.DataFrame(),
    }


def _sklearn_error(target: str, exc: Exception, sample_count: int, samples: pd.DataFrame) -> dict[str, Any]:
    status_col = "risk_level_model_status" if target == "risk_level" else f"{target}_model_status"
    pred_col = "predicted_risk_level" if target == "risk_level" else f"predicted_{target}"
    return _model_result(
        report={
            "model_status": "sklearn_unavailable",
            "target": target,
            "sample_count": int(sample_count),
            "message": f"{type(exc).__name__}: {exc}",
        },
        predictions={pred_col: [None] * len(samples), status_col: ["sklearn_unavailable"] * len(samples)},
    )


def _feature_columns(samples: pd.DataFrame) -> list[str]:
    excluded = {
        "sample_id",
        "node",
        "reference_node",
        "risk_level",
        "risk_reasons",
        "data_source",
        "engineering_validity",
        "must_resimulate",
    }
    excluded.update(REGRESSION_TARGETS)
    excluded.update(column for column in samples.columns if column.startswith("predicted_") or column.endswith("_model_status"))
    return [column for column in samples.columns if column not in excluded]


def _categorical_feature_names() -> set[str]:
    return {"signal_role", "position", "data_phase", "goa_terminal"}


def _categorical_columns(samples: pd.DataFrame, feature_cols: list[str]) -> list[str]:
    categorical = set(_categorical_feature_names())
    selected = []
    for column in feature_cols:
        if column in categorical:
            selected.append(column)
            continue
        numeric = pd.to_numeric(samples[column], errors="coerce")
        if numeric.notna().sum() == 0 and samples[column].notna().sum() > 0:
            selected.append(column)
    return selected


def _encode_for_report(samples: pd.DataFrame, feature_cols: list[str], categorical_cols: list[str], numeric_cols: list[str]) -> pd.DataFrame:
    encoded_numeric = samples[numeric_cols].apply(pd.to_numeric, errors="coerce") if numeric_cols else pd.DataFrame(index=samples.index)
    encoded_categorical = pd.get_dummies(samples[categorical_cols].fillna(""), columns=categorical_cols) if categorical_cols else pd.DataFrame(index=samples.index)
    return pd.concat([encoded_numeric.reset_index(drop=True), encoded_categorical.reset_index(drop=True)], axis=1)


def _encoded_feature_matrix(samples: pd.DataFrame, trained: dict[str, Any]) -> pd.DataFrame:
    identity = samples[["sample_id", "node", "signal_role", "position", "risk_level", "risk_score"]].reset_index(drop=True)
    encoded = trained["encoded_features"].reset_index(drop=True)
    return pd.concat([identity, encoded], axis=1)


def _prediction_frame(samples: pd.DataFrame, trained: dict[str, Any]) -> pd.DataFrame:
    prediction_cols = pd.DataFrame(trained["model_predictions"])
    base = samples[
        [
            "sample_id",
            "node",
            "signal_role",
            "position",
            "reference_node",
            "risk_level",
            "risk_score",
            "risk_reasons",
            "data_source",
            "engineering_validity",
            "must_resimulate",
        ]
    ].reset_index(drop=True)
    return pd.concat([base, prediction_cols.reset_index(drop=True)], axis=1)


def _build_report(
    *,
    samples: pd.DataFrame,
    trained: dict[str, Any],
    waveform_path: Path,
    nominal_sp: Path | None,
    netlist: Path | None,
    model_cards: list[Path],
    spec_path: Path | None,
    nominal_params: dict[str, str],
) -> dict[str, Any]:
    statuses = {target: report.get("model_status") for target, report in trained["model_reports"].items()}
    return {
        "status": "trained" if any(status == "ok" for status in statuses.values()) else "insufficient_data",
        "sample_count": int(len(samples)),
        "role_counts": samples["signal_role"].value_counts().to_dict() if "signal_role" in samples else {},
        "risk_level_counts": samples["risk_level"].value_counts().to_dict() if "risk_level" in samples else {},
        "model_reports": trained["model_reports"],
        "feature_count": int(len(trained["feature_cols"])),
        "feature_cols": trained["feature_cols"],
        "numeric_cols": trained["numeric_cols"],
        "categorical_cols": trained["categorical_cols"],
        "source_files": _source_files(waveform_path, nominal_sp, netlist, model_cards, spec_path),
        "nominal_params": nominal_params,
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": MUST_RESIMULATE,
        "claim_boundary": "simulation-only waveform diagnostics; not a SPICE replacement or direct parameter optimizer",
    }


def _source_files(
    waveform_path: Path,
    nominal_sp: Path | None,
    netlist: Path | None,
    model_cards: list[Path],
    spec_path: Path | None,
) -> list[dict[str, Any]]:
    rows = []
    for kind, path in [
        ("waveform", waveform_path),
        ("nominal_sp", nominal_sp),
        ("netlist", netlist),
        ("spec", spec_path),
    ]:
        if path:
            rows.append(_source_file_row(kind, path))
    for path in model_cards:
        rows.append(_source_file_row("model_card", path))
    return rows


def _source_file_row(kind: str, path: Path) -> dict[str, Any]:
    path = Path(path)
    row: dict[str, Any] = {"kind": kind, "path": str(path), "exists": path.exists()}
    if path.exists():
        row.update({"size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return row


def _model_card(report: dict[str, Any]) -> str:
    lines = [
        "# Waveform Diagnostic Model Card",
        "",
        f"- status: {report.get('status')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- feature_count: {report.get('feature_count')}",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "- purpose: diagnose simulated waveform quality, delay, loss, overshoot, and pixel tracking risk.",
        "- limitation: this model is not a SPICE replacement and not a direct parameter optimizer.",
        "",
        "## Model Status",
        "",
    ]
    for target, detail in report.get("model_reports", {}).items():
        lines.append(f"- {target}: {detail.get('model_status')}")
    return "\n".join(lines) + "\n"


def _write_model_artifact(path: Path, trained: dict[str, Any], report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import joblib
    except Exception:
        path.write_bytes(b"")
        return
    package = {
        "models": trained["models"],
        "feature_cols": trained["feature_cols"],
        "numeric_cols": trained["numeric_cols"],
        "categorical_cols": trained["categorical_cols"],
        "report": report,
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": MUST_RESIMULATE,
    }
    joblib.dump(package, path)


def _duration_ratio(time: np.ndarray, mask: np.ndarray, duration: float) -> float | None:
    if duration <= 0 or len(time) < 2:
        return None
    total = 0.0
    for left, right, active in zip(time[:-1], time[1:], mask[:-1]):
        if active:
            total += float(right - left)
    return float(total / duration)


def _max_abs_slew(time: np.ndarray, signal: np.ndarray) -> float | None:
    if len(time) < 2:
        return None
    dt = np.diff(time)
    dv = np.diff(signal)
    valid = dt > 0
    if not np.any(valid):
        return None
    return float(np.nanmax(np.abs(dv[valid] / dt[valid])))


def _difference(value: Any, reference: Any) -> float | None:
    left = _number(value)
    right = _number(reference)
    if left is None or right is None:
        return None
    return float(left - right)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return _safe_float(value)


def _param_float(params: dict[str, str], key: str) -> float | None:
    value = params.get(key)
    if value is None:
        return None
    cleaned = str(value).strip().rstrip("Vv")
    return _safe_float(cleaned)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, (bool, str)) or value is None:
        return value
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (int, float)):
        return value
    return value


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "passed"}
    return bool(value)
