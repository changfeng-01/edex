from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from goa_eval.product_demo.artifact_collector import ProductDemoArtifacts
from goa_eval.product_demo.schemas import FIGURE_FILES
from goa_eval.product_demo.tables import (
    build_before_after_table,
    build_candidate_table,
    build_constraint_table,
)


def write_figures(artifacts: ProductDemoArtifacts, figure_dir: Path, case_id: str) -> dict[str, Path]:
    figure_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "waveform": figure_dir / FIGURE_FILES["waveform"],
        "constraints": figure_dir / FIGURE_FILES["constraints"],
        "metrics": figure_dir / FIGURE_FILES["metrics"],
        "candidates": figure_dir / FIGURE_FILES["candidates"],
        "before_after": figure_dir / FIGURE_FILES["before_after"],
        "evidence": figure_dir / FIGURE_FILES["evidence"],
    }
    _plot_waveform_overview(artifacts, paths["waveform"])
    _plot_constraint_status(build_constraint_table(artifacts), paths["constraints"])
    _plot_metric_comparison(artifacts, paths["metrics"])
    _plot_candidate_ranking(build_candidate_table(artifacts), paths["candidates"])
    _plot_before_after(build_before_after_table(artifacts), paths["before_after"])
    _plot_evidence_card(artifacts, case_id, paths["evidence"])
    return paths


def _plot_waveform_overview(artifacts: ProductDemoArtifacts, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    waveform = artifacts.waveform
    if waveform.empty:
        _placeholder(ax, "Waveform overview", "waveform.csv unavailable")
        _save(fig, path)
        return
    time_col = _first_existing(waveform, ["time", "Time", "t", "T"])
    if time_col is None:
        _placeholder(ax, "Waveform overview", "No time column found in waveform.csv")
        _save(fig, path)
        return
    value_cols = [col for col in waveform.columns if col != time_col][:8]
    if not value_cols:
        _placeholder(ax, "Waveform overview", "No signal columns found in waveform.csv")
        _save(fig, path)
        return
    for col in value_cols:
        ax.plot(waveform[time_col], waveform[col], linewidth=1.2, label=str(col))
    ax.set_title("Waveform overview")
    ax.set_xlabel("Time")
    ax.set_ylabel("Voltage")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    _note(ax, f"Showing {len(value_cols)} signal(s); source: waveform.csv")
    _save(fig, path)


def _plot_constraint_status(table: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    counts = table["status"].value_counts().reindex(["pass", "fail", "unknown", "missing"]).fillna(0)
    colors = ["#2e7d32", "#c62828", "#757575", "#9e9e9e"]
    ax.bar(counts.index, counts.values, color=colors)
    ax.set_title("Constraint status")
    ax.set_xlabel("Status")
    ax.set_ylabel("Count")
    ax.grid(axis="y", alpha=0.25)
    _note(ax, "Question: which hard constraints need attention?")
    _save(fig, path)


def _plot_metric_comparison(artifacts: ProductDemoArtifacts, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    metrics = {
        "VOH_min": artifacts.summary.get("VOH_min"),
        "Max_ripple": artifacts.summary.get("Max_ripple"),
        "Max_voltage_loss": artifacts.summary.get("Max_voltage_loss"),
        "Max_overlap_ratio": artifacts.summary.get("Max_overlap_ratio"),
        "overall_score": artifacts.score.get("overall_score"),
    }
    labels = []
    values = []
    for label, value in metrics.items():
        numeric = _as_float(value)
        if numeric is not None:
            labels.append(label)
            values.append(numeric)
    if not labels:
        _placeholder(ax, "Metric comparison", "No numeric metric summary available")
        _save(fig, path)
        return
    ax.bar(labels, values, color="#1565c0")
    ax.set_title("Key metric comparison")
    ax.set_xlabel("Metric")
    ax.set_ylabel("Value")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.25)
    _note(ax, "Question: what is the current run quality profile?")
    _save(fig, path)


def _plot_candidate_ranking(table: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ready = table[table["status"] != "awaiting_candidate_generation"].head(10)
    if ready.empty:
        _placeholder(ax, "Candidate ranking", "Candidate data unavailable")
        _save(fig, path)
        return
    labels = ready["candidate_id"].astype(str).tolist()
    values = [_as_float(value) or 0.0 for value in ready["search_score"].tolist()]
    if not any(values):
        values = [_as_float(value) or 0.0 for value in ready["priority"].tolist()]
    ax.barh(labels[::-1], values[::-1], color="#6a1b9a")
    ax.set_title("Top candidate ranking")
    ax.set_xlabel("Search score or priority")
    ax.set_ylabel("Candidate")
    ax.grid(axis="x", alpha=0.25)
    _note(ax, "Question: which candidate should be rerun first?")
    _save(fig, path)


def _plot_before_after(table: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    available = table[table["status"] != "awaiting_rerun_results"]
    if available.empty:
        _placeholder(ax, "Before/after comparison", "awaiting_rerun_results")
        _save(fig, path)
        return
    labels = available["metric"].astype(str).tolist()
    before = [_as_float(value) or 0.0 for value in available["before_value"].tolist()]
    after = [_as_float(value) or 0.0 for value in available["after_value"].tolist()]
    x = range(len(labels))
    ax.bar([i - 0.18 for i in x], before, width=0.36, label="before", color="#546e7a")
    ax.bar([i + 0.18 for i in x], after, width=0.36, label="after", color="#00897b")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_title("Before/after comparison")
    ax.set_ylabel("Value")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    _note(ax, "Question: did rerun evidence improve the design?")
    _save(fig, path)


def _plot_evidence_card(artifacts: ProductDemoArtifacts, case_id: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.axis("off")
    evidence = artifacts.evidence
    lines = [
        f"Case: {case_id}",
        f"data_source: {evidence.get('data_source')}",
        f"engineering_validity: {evidence.get('engineering_validity')}",
        f"evidence_level: {evidence.get('evidence_level')}",
        f"simulation_backend: {evidence.get('simulation_backend')}",
        f"mock_used: {evidence.get('mock_used')}",
        f"reportable_as_real_ngspice: {evidence.get('reportable_as_real_ngspice')}",
        f"optimizer_claim_level: {evidence.get('optimizer_claim_level')}",
        f"validation_status: {artifacts.validation_status}",
    ]
    ax.text(0.04, 0.92, "Evidence card", fontsize=18, fontweight="bold", va="top")
    ax.text(0.04, 0.78, "\n".join(lines), fontsize=12, va="top", family="monospace")
    ax.text(
        0.04,
        0.08,
        "Boundary: simulation-only evidence package; no physical or lab validation is claimed.",
        fontsize=10,
        color="#424242",
    )
    _save(fig, path)


def _placeholder(ax: Any, title: str, message: str) -> None:
    ax.set_title(title)
    ax.axis("off")
    ax.text(0.5, 0.55, message, ha="center", va="center", fontsize=16, color="#616161")
    ax.text(0.5, 0.42, "Generated placeholder figure", ha="center", va="center", fontsize=10, color="#757575")


def _note(ax: Any, text: str) -> None:
    ax.text(0.01, 0.01, text, transform=ax.transAxes, fontsize=9, color="#616161", va="bottom")


def _save(fig: Any, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _first_existing(frame: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _as_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
