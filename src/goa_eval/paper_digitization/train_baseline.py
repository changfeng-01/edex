from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.io_utils import write_json
from goa_eval.paper_digitization.schemas import IDENTITY_COLUMNS, LABEL_COLUMNS


def train_baseline(
    *,
    dataset_path: Path,
    split_path: Path,
    target: str,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(dataset_path)
    split = pd.read_csv(split_path) if split_path.exists() else pd.DataFrame()
    if not split.empty and "sample_id" in data.columns and "sample_id" in split.columns:
        data = data.merge(split[["sample_id", "train_val_test"]], on="sample_id", how="left", suffixes=("", "_split"))
        if "train_val_test_split" in data.columns:
            data["train_val_test"] = data["train_val_test_split"].fillna(data.get("train_val_test"))
    if "do_not_train" in data.columns:
        trainable_mask = data["do_not_train"].astype(str).str.lower() != "true"
    else:
        trainable_mask = pd.Series([True] * len(data), index=data.index)
    usable = data[trainable_mask].copy()
    usable[target] = pd.to_numeric(usable.get(target), errors="coerce")
    usable = usable.dropna(subset=[target])
    if len(usable) < 10:
        report = {
            "status": "insufficient_data",
            "sample_count": int(len(usable)),
            "target": target,
            "message": "At least 10 usable samples are required before training a baseline model.",
        }
        _write_baseline_outputs(output_dir, report, pd.DataFrame())
        return report
    feature_columns = _numeric_feature_columns(usable, target)
    if not feature_columns:
        report = {"status": "insufficient_features", "sample_count": int(len(usable)), "target": target}
        _write_baseline_outputs(output_dir, report, pd.DataFrame())
        return report
    train = usable[usable.get("train_val_test", "train").astype(str).eq("train")]
    test = usable[usable.get("train_val_test", "").astype(str).eq("test")]
    if len(train) < 5 or test.empty:
        train = usable.sample(frac=0.8, random_state=17)
        test = usable.drop(train.index)
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
    except Exception as exc:
        report = {"status": "sklearn_unavailable", "message": f"{type(exc).__name__}: {exc}", "sample_count": int(len(usable))}
        _write_baseline_outputs(output_dir, report, pd.DataFrame())
        return report
    model = RandomForestRegressor(n_estimators=64, random_state=17)
    weights = pd.to_numeric(train.get("evidence_weight"), errors="coerce").fillna(1.0)
    model.fit(train[feature_columns], train[target], sample_weight=weights)
    predictions = model.predict(test[feature_columns]) if not test.empty else model.predict(train[feature_columns])
    y_true = test[target] if not test.empty else train[target]
    metrics = {
        "status": "trained_random_forest",
        "sample_count": int(len(usable)),
        "train_count": int(len(train)),
        "test_count": int(len(test)),
        "target": target,
        "feature_count": len(feature_columns),
        "mae": float(mean_absolute_error(y_true, predictions)),
        "r2": float(r2_score(y_true, predictions)) if len(y_true) > 1 else None,
    }
    importance = pd.DataFrame({"feature": feature_columns, "importance": model.feature_importances_}).sort_values(
        "importance", ascending=False
    )
    _write_baseline_outputs(output_dir, metrics, importance)
    return metrics


def _numeric_feature_columns(frame: pd.DataFrame, target: str) -> list[str]:
    excluded = set(IDENTITY_COLUMNS) | set(LABEL_COLUMNS) | {target, "notes", "failure_reason_text"}
    columns = []
    for column in frame.columns:
        if column in excluded or column.endswith("_id") or column.startswith("Unnamed:"):
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.notna().sum() >= 3:
            frame[column] = numeric.fillna(numeric.median())
            columns.append(column)
    return columns


def _write_baseline_outputs(output_dir: Path, metrics: dict[str, Any], importance: pd.DataFrame) -> None:
    write_json(output_dir / "baseline_metrics.json", metrics)
    if importance.empty:
        importance = pd.DataFrame(columns=["feature", "importance"])
    importance.to_csv(output_dir / "feature_importance.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# Paper ML Baseline Model Report",
        "",
        f"- status: {metrics.get('status')}",
        f"- sample_count: {metrics.get('sample_count')}",
        "- boundary: paper-digitized rows are weak labels.",
        "- purpose: validate that the database is trainable.",
        "- limitation: this baseline cannot claim real optimization performance.",
    ]
    (output_dir / "baseline_model_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a minimal RandomForest baseline on GOA training samples.")
    parser.add_argument("--dataset", dest="dataset_path", type=Path, required=True)
    parser.add_argument("--split", dest="split_path", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    metrics = train_baseline(dataset_path=args.dataset_path, split_path=args.split_path, target=args.target, output_dir=args.output_dir)
    print(metrics.get("status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
