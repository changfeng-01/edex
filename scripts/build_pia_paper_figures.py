from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch


BOUNDARY = {
    "data_source": "real_simulation_csv",
    "engineering_validity": "simulation_only",
    "must_resimulate": True,
}

OKABE_ITO = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "yellow": "#F0E442",
    "sky": "#56B4E9",
    "red": "#D55E00",
    "purple": "#CC79A7",
    "black": "#111111",
    "gray": "#777777",
    "light_gray": "#F4F6F8",
}

IMAGE2_PROMPTS = [
    {
        "figure_id": "fig01",
        "output_file": "figures/fig01_graphical_abstract.png",
        "model": "gpt-image-2",
        "purpose": "label-light graphical abstract base image; deterministic Python overlays provide final labels",
        "prompt": (
            "Publication-quality graphical abstract for a simulation-only GOA circuit optimization paper. "
            "Clean white background, left-to-right workflow: historical real_simulation_csv samples and candidate "
            "designs, physics feature mapping phi(x), CAPM-Distance physics manifold, PIA-CA-LLSO selector, "
            "next-run simulation batch, imported simulation results, evidence audit. Modern scientific schematic, "
            "colorblind-safe blue green orange palette, minimal text placeholders, no photorealistic lab hardware, "
            "no claim of silicon validation."
        ),
    },
    {
        "figure_id": "fig02",
        "output_file": "figures/fig02_closed_loop_architecture.png",
        "model": "gpt-image-2",
        "purpose": "label-light closed-loop architecture base image; deterministic Python overlays provide final labels",
        "prompt": (
            "Journal-quality systems architecture diagram for PIA-CA-LLSO closed-loop optimizer. Show modules as "
            "clean blocks: history CSV, level labeling L1 L2 L3 L4, LLSO offspring generation, repair candidates, "
            "PIA selector, simulation batch, offline or external simulator, result import, resume state, boundary "
            "audit. Arrows form a closed loop. Use professional vector-like style, white background, subtle "
            "circuit-grid motif, minimal text placeholders."
        ),
    },
    {
        "figure_id": "fig03",
        "output_file": "figures/fig03_capm_physics_manifold.png",
        "model": "gpt-image-2",
        "purpose": "label-light physics manifold base image; deterministic Python overlays provide final labels",
        "prompt": (
            "Conceptual scientific diagram of constraint-aware physics manifold distance for GOA circuit "
            "optimization. Show raw parameter space on the left transformed to physics feature space phi(x) on the "
            "right. In the physics manifold, show an L1 basin, candidate points, soft barrier risk region, geodesic "
            "path around risky region, missing-feature uncertainty halo. Clean academic style, colorblind-safe, no "
            "dense labels, no 3D clutter."
        ),
    },
    {
        "figure_id": "fig04",
        "output_file": "figures/fig04_acquisition_ensemble.png",
        "model": "gpt-image-2",
        "purpose": "label-light acquisition ensemble base image; deterministic Python overlays provide final labels",
        "prompt": (
            "Publication schematic for candidate acquisition ensemble. Central candidate x receives evidence from "
            "CAPM distance, adaptive physics weights, classifier probabilities p_L1 and p_hard, diversity, "
            "uncertainty, and literature-inspired ensemble components DEAOE HRCEA AIEA CESAEA ECCoEA-ASAA. These "
            "combine into acquisition score A(x), then top-k next-run simulation suggestions. Clean block diagram, "
            "white background, professional journal style, minimal text placeholders."
        ),
    },
]


@dataclass(frozen=True)
class DataBundle:
    repo_root: Path
    formal_method: Path
    sample_history: Path | None
    sample_candidates: Path | None
    sample_results: Path | None
    validation_summary: Path | None
    ablation_summary: Path | None
    selected_candidates: Path | None

    @property
    def evidence_role(self) -> str:
        if self.validation_summary is not None:
            return "formal_validation_csv"
        return "sample_smoke_visualization"


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def discover_data(repo_root: Path, validation_dir: Path | None) -> DataBundle:
    validation_candidates: list[Path] = []
    if validation_dir is not None:
        validation_candidates.append(validation_dir / "validation_summary.csv")
    validation_candidates.extend(
        [
            repo_root / "outputs" / "pia_phase3_validation" / "validation_summary.csv",
            repo_root / "outputs" / "pia_validation" / "validation_summary.csv",
            repo_root / "outputs" / "pia_paper_reproduction" / "validation_summary.csv",
            repo_root / "outputs" / "pia_reproduction_phase3" / "validation_summary.csv",
        ]
    )

    case_pack = repo_root / "examples" / "pia_ca_llso" / "case_packs" / "sample_goa"
    return DataBundle(
        repo_root=repo_root,
        formal_method=repo_root / "docs" / "pia_ca_llso_formal_method_zh.md",
        sample_history=first_existing(
            [
                repo_root / "examples" / "pia_ca_llso" / "sample_history.csv",
                case_pack / "history.csv",
            ]
        ),
        sample_candidates=first_existing(
            [
                repo_root / "examples" / "pia_ca_llso" / "sample_candidates.csv",
                case_pack / "candidate_pool.csv",
            ]
        ),
        sample_results=first_existing([case_pack / "simulation_results.csv"]),
        validation_summary=first_existing(validation_candidates),
        ablation_summary=first_existing(
            [
                repo_root / "outputs" / "pia_capm_benchmark" / "pia_ablation_summary.json",
                repo_root / "outputs" / "pia_benchmark" / "pia_ablation_summary.json",
            ]
        ),
        selected_candidates=first_existing(
            [
                repo_root / "outputs" / "pia_capm_suggest" / "pia_selected_candidates.csv",
                repo_root / "outputs" / "pia_suggest" / "pia_selected_candidates.csv",
            ]
        ),
    )


def validate_sources(bundle: DataBundle) -> list[str]:
    missing: list[str] = []
    if not bundle.formal_method.exists():
        missing.append(str(bundle.formal_method))
    if bundle.sample_history is None:
        missing.append("examples/pia_ca_llso sample history")
    if bundle.sample_candidates is None:
        missing.append("examples/pia_ca_llso sample candidates")
    return missing


def ensure_output_dirs(output_dir: Path) -> None:
    (output_dir / "figures").mkdir(parents=True, exist_ok=True)
    (output_dir / "prompts").mkdir(parents=True, exist_ok=True)


def boundary_text() -> str:
    return (
        "Boundary: data_source = real_simulation_csv | "
        "engineering_validity = simulation_only | must_resimulate = true"
    )


def clean_axis(ax: plt.Axes) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)


def add_box(
    ax: plt.Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    title: str,
    body: str,
    color: str,
    *,
    face: str = "white",
    lw: float = 1.5,
    fontsize: int = 10,
) -> FancyBboxPatch:
    box = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.018,rounding_size=0.018",
        linewidth=lw,
        edgecolor=color,
        facecolor=face,
        zorder=2,
    )
    ax.add_patch(box)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height - 0.045,
        title,
        ha="center",
        va="top",
        fontsize=fontsize,
        fontweight="bold",
        color=color,
        zorder=3,
    )
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2 - 0.018,
        body,
        ha="center",
        va="center",
        fontsize=max(fontsize - 1, 7),
        color=OKABE_ITO["black"],
        linespacing=1.25,
        zorder=3,
    )
    return box


def arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = "#243447",
    lw: float = 1.7,
    curve: float = 0.0,
) -> None:
    style = f"arc3,rad={curve}"
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=16,
            linewidth=lw,
            color=color,
            connectionstyle=style,
            zorder=1,
        )
    )


def save_figure(fig: plt.Figure, output_dir: Path, stem: str) -> list[Path]:
    png = output_dir / "figures" / f"{stem}.png"
    pdf = output_dir / "figures" / f"{stem}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return [png, pdf]


def draw_circuit_icon(ax: plt.Axes, x: float, y: float, scale: float, color: str) -> None:
    xs = np.array([0.0, 0.2, 0.2, 0.45, 0.45, 0.7, 0.7, 1.0]) * scale + x
    ys = np.array([0.5, 0.5, 0.78, 0.78, 0.25, 0.25, 0.5, 0.5]) * scale + y
    ax.plot(xs, ys, color=color, linewidth=1.3, zorder=3)
    for px, py in zip(xs[[0, 3, 5, 7]], ys[[0, 3, 5, 7]], strict=True):
        ax.add_patch(Circle((px, py), 0.012 * scale, color=color, zorder=3))


def figure_01(output_dir: Path) -> list[Path]:
    fig, ax = plt.subplots(figsize=(14.0, 5.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    clean_axis(ax)
    ax.text(0.5, 0.965, "PIA-CA-LLSO Graphical Abstract", ha="center", fontsize=18, fontweight="bold")
    ax.text(0.5, 0.915, "Simulation-only closed-loop GOA circuit optimization", ha="center", fontsize=11)

    titles = [
        "History\n+ Pool",
        "Physics\nMap",
        "CAPM\nDistance",
        "PIA\nSelector",
        "Simulation\nBatch",
        "Imported\nResults",
        "Evidence\nAudit",
    ]
    bodies = [
        "D_t from CSV\ncandidate designs",
        "phi(x)\nphysics features",
        "L1 basin\nbarrier + geodesic",
        "A(x)\nrank top-k",
        "next-run\nsuggestions",
        "append D_new\nresume state",
        "boundary fields\nclaim checks",
    ]
    colors = [
        OKABE_ITO["blue"],
        OKABE_ITO["green"],
        OKABE_ITO["sky"],
        OKABE_ITO["orange"],
        OKABE_ITO["red"],
        OKABE_ITO["purple"],
        OKABE_ITO["green"],
    ]
    xs = np.linspace(0.035, 0.815, len(titles))
    for idx, (x, title, body, color) in enumerate(zip(xs, titles, bodies, colors, strict=True), start=1):
        add_box(ax, (x, 0.34), 0.11, 0.38, f"{idx}. {title}", body, color, face="#FFFFFF", fontsize=8)
        draw_circuit_icon(ax, x + 0.025, 0.39, 0.06, color)
        if idx < len(titles):
            arrow(ax, (x + 0.113, 0.53), (xs[idx] - 0.006, 0.53), color=OKABE_ITO["black"])

    arrow(ax, (0.887, 0.34), (0.06, 0.28), color=OKABE_ITO["blue"], lw=2.0, curve=-0.19)
    ax.text(0.49, 0.235, "Close the loop: append new simulation evidence and repeat until budget/target/patience stops", ha="center", fontsize=10)
    ax.text(0.5, 0.075, boundary_text(), ha="center", fontsize=9, color=OKABE_ITO["gray"])
    return save_figure(fig, output_dir, "fig01_graphical_abstract")


def figure_02(output_dir: Path) -> list[Path]:
    fig, ax = plt.subplots(figsize=(12.5, 7.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    clean_axis(ax)
    ax.text(0.5, 0.955, "PIA-CA-LLSO Closed-Loop Architecture", ha="center", fontsize=18, fontweight="bold")
    ax.text(0.5, 0.914, "Labeling, LLSO generation, acquisition, simulation import, and audit", ha="center", fontsize=11)

    boxes = [
        ((0.05, 0.68), "History CSV", "x, S, H, metrics\nmetadata", OKABE_ITO["green"]),
        ((0.27, 0.68), "L1-L4 Labeling", "L1 high-score feasible\nL3 boundary learning", OKABE_ITO["blue"]),
        ((0.49, 0.68), "LLSO Offspring", "local variation\nrepair candidates", OKABE_ITO["purple"]),
        ((0.71, 0.68), "PIA Selector", "CAPM + classifier\nensemble A(x)", OKABE_ITO["orange"]),
        ((0.71, 0.36), "Simulation Batch", "top-k next-run\nsuggestions", OKABE_ITO["red"]),
        ((0.49, 0.16), "Result Import", "S(x), H(x), m(x)\nappend evidence", OKABE_ITO["blue"]),
        ((0.27, 0.16), "Resume State", "generation state\nrandom seed", OKABE_ITO["sky"]),
        ((0.05, 0.36), "Boundary Audit", "source lock\nsimulation-only", OKABE_ITO["green"]),
    ]
    centers: list[tuple[float, float]] = []
    for xy, title, body, color in boxes:
        add_box(ax, xy, 0.16, 0.16, title, body, color, fontsize=10)
        centers.append((xy[0] + 0.08, xy[1] + 0.08))
    for start, end in zip(centers, centers[1:] + centers[:1], strict=True):
        arrow(ax, start, end, color=OKABE_ITO["black"], lw=1.8)

    ax.add_patch(Circle((0.5, 0.47), 0.11, edgecolor=OKABE_ITO["blue"], facecolor="#EAF4FB", linewidth=1.5))
    ax.text(0.5, 0.49, "Closed-loop\niteration", ha="center", va="center", fontsize=12, fontweight="bold", color=OKABE_ITO["blue"])
    ax.text(0.5, 0.43, "t = t + 1", ha="center", va="center", fontsize=10)
    ax.text(0.5, 0.055, boundary_text(), ha="center", fontsize=9, color=OKABE_ITO["gray"])
    return save_figure(fig, output_dir, "fig02_closed_loop_architecture")


def figure_03(output_dir: Path) -> list[Path]:
    fig, ax = plt.subplots(figsize=(12.5, 6.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    clean_axis(ax)
    ax.text(0.5, 0.95, "CAPM-Distance in Physics Feature Space", ha="center", fontsize=18, fontweight="bold")

    rng = np.random.default_rng(17)
    raw_points = rng.normal(loc=[0.22, 0.51], scale=[0.07, 0.12], size=(14, 2))
    ax.add_patch(Ellipse((0.23, 0.52), 0.34, 0.52, angle=-8, edgecolor=OKABE_ITO["gray"], facecolor="#F8F8F8", linewidth=1.3))
    ax.scatter(raw_points[:, 0], raw_points[:, 1], s=34, color="#9A9A9A", zorder=3)
    ax.scatter([0.16], [0.48], s=70, facecolor="white", edgecolor=OKABE_ITO["black"], linewidth=1.5, zorder=4)
    for px, py in raw_points[:9]:
        ax.plot([0.16, px], [0.48, py], "--", color="#AAAAAA", linewidth=0.9, zorder=1)
    ax.text(0.23, 0.83, "Raw parameter space X", ha="center", fontsize=12, fontweight="bold")
    arrow(ax, (0.405, 0.52), (0.52, 0.52), color=OKABE_ITO["black"], lw=2.2)
    ax.text(0.462, 0.575, "phi: X -> R^d", ha="center", fontsize=12, fontweight="bold")

    manifold = Ellipse((0.73, 0.52), 0.42, 0.58, angle=5, edgecolor=OKABE_ITO["blue"], facecolor="#F5FBFF", linewidth=1.5)
    ax.add_patch(manifold)
    ax.add_patch(Ellipse((0.62, 0.48), 0.13, 0.11, angle=20, edgecolor=OKABE_ITO["blue"], facecolor="#BBD7F0", alpha=0.7))
    ax.scatter([0.595], [0.47], s=75, color=OKABE_ITO["blue"], edgecolor="white", linewidth=1.0, zorder=4)
    ax.text(0.61, 0.38, "L1 basin", ha="center", fontsize=10, color=OKABE_ITO["blue"], fontweight="bold")

    ax.add_patch(Ellipse((0.76, 0.54), 0.15, 0.20, angle=-20, edgecolor=OKABE_ITO["red"], facecolor="#FAD7CB", alpha=0.8, linestyle="--", linewidth=1.3))
    ax.text(0.78, 0.67, "soft barrier\nrisk proxy", ha="center", fontsize=9, color=OKABE_ITO["red"])

    cand = np.array([[0.68, 0.35], [0.84, 0.75], [0.88, 0.40], [0.68, 0.74], [0.82, 0.30]])
    ax.scatter(cand[:, 0], cand[:, 1], s=60, facecolor="white", edgecolor=OKABE_ITO["black"], linewidth=1.4, zorder=4)
    for cx, cy in cand[[1, 2, 4]]:
        ax.add_patch(Ellipse((cx, cy), 0.09, 0.08, angle=25, facecolor="#E6D8F2", edgecolor=OKABE_ITO["purple"], linestyle="--", alpha=0.5))

    path_x = [0.61, 0.66, 0.74, 0.85]
    path_y = [0.48, 0.34, 0.32, 0.72]
    ax.plot(path_x, path_y, color=OKABE_ITO["green"], linewidth=2.4, zorder=5)
    arrow(ax, (0.80, 0.51), (0.85, 0.72), color=OKABE_ITO["green"], lw=2.0, curve=0.17)
    ax.plot([0.61, 0.84], [0.48, 0.75], "--", color=OKABE_ITO["gray"], linewidth=1.1)
    ax.text(0.74, 0.20, "constraint-aware geodesic avoids barrier", ha="center", fontsize=9, color=OKABE_ITO["green"], fontweight="bold")
    ax.text(0.74, 0.83, "Physics feature space phi(x)", ha="center", fontsize=12, fontweight="bold")
    ax.text(0.5, 0.06, boundary_text(), ha="center", fontsize=9, color=OKABE_ITO["gray"])
    return save_figure(fig, output_dir, "fig03_capm_physics_manifold")


def figure_04(output_dir: Path) -> list[Path]:
    fig, ax = plt.subplots(figsize=(13.5, 7.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    clean_axis(ax)
    ax.text(0.5, 0.955, "Candidate Acquisition Ensemble", ha="center", fontsize=18, fontweight="bold")
    left = [
        ("CAPM distance", "1 - norm(D_geodesic)", OKABE_ITO["blue"]),
        ("Adaptive CAPM", "physics weights + barriers", OKABE_ITO["green"]),
        ("Classifier hybrid", "p_L1, p_hard, pred_score", OKABE_ITO["purple"]),
        ("Diversity", "batch coverage", OKABE_ITO["orange"]),
        ("Uncertainty", "candidate risk / missingness", OKABE_ITO["red"]),
    ]
    for idx, (title, body, color) in enumerate(left):
        y = 0.75 - idx * 0.13
        add_box(ax, (0.05, y), 0.22, 0.09, title, body, color, face="#FFFFFF", fontsize=9)
        arrow(ax, (0.27, y + 0.045), (0.43, 0.50), color=color, lw=1.3)

    ax.add_patch(Circle((0.49, 0.50), 0.075, edgecolor=OKABE_ITO["black"], facecolor="#F6FBFF", linewidth=1.4))
    ax.text(0.49, 0.515, "x", ha="center", va="center", fontsize=22, fontweight="bold")
    ax.text(0.49, 0.465, "candidate", ha="center", fontsize=9)

    ensemble = [
        ("DEAOE", "operator prior"),
        ("HRCEA", "archive cue"),
        ("AIEA", "influence cue"),
        ("CESAEA", "constraint cue"),
        ("ECCoEA-ASAA", "surrogate cue"),
    ]
    for idx, (title, body) in enumerate(ensemble):
        y = 0.76 - idx * 0.115
        add_box(ax, (0.60, y), 0.18, 0.075, title, body, OKABE_ITO["blue"], face="#F8FBFF", fontsize=8)
        arrow(ax, (0.56, 0.50), (0.60, y + 0.038), color=OKABE_ITO["gray"], lw=1.0)
    add_box(ax, (0.82, 0.44), 0.12, 0.12, "A(x)", "acquisition\nscore", OKABE_ITO["orange"], face="#FFF8E6", fontsize=12)
    arrow(ax, (0.78, 0.50), (0.82, 0.50), color=OKABE_ITO["black"])
    add_box(ax, (0.82, 0.23), 0.12, 0.10, "Top-k", "next-run\nsimulation", OKABE_ITO["green"], face="#F2FBF7", fontsize=11)
    arrow(ax, (0.88, 0.44), (0.88, 0.33), color=OKABE_ITO["black"])
    ax.text(0.50, 0.10, "Literature components are auditable acquisition subcomponents, not full reproductions of the five papers.", ha="center", fontsize=9)
    ax.text(0.50, 0.055, boundary_text(), ha="center", fontsize=9, color=OKABE_ITO["gray"])
    return save_figure(fig, output_dir, "fig04_acquisition_ensemble")


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    return pd.read_csv(path)


def choose_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    for name in candidates:
        if name in frame.columns:
            return name
    return None


def figure_05(output_dir: Path, bundle: DataBundle) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), gridspec_kw={"width_ratios": [1.45, 1.0]})
    fig.suptitle("Strategy Benchmark Evidence View", fontsize=17, fontweight="bold", y=0.98)

    validation = read_csv(bundle.validation_summary)
    ablation = load_json(bundle.ablation_summary)
    methods = ablation.get("methods") or []
    if validation.empty and methods:
        ax = axes[0]
        y = np.arange(len(methods))
        ax.barh(y, [1] * len(methods), color=[OKABE_ITO["blue"], OKABE_ITO["sky"], OKABE_ITO["green"], OKABE_ITO["orange"]][: len(methods)])
        ax.set_yticks(y, methods)
        ax.set_xlim(0, 1.15)
        ax.set_xlabel("Included in smoke benchmark artifact")
        ax.set_title("Available strategy records")
        best = ablation.get("best_method")
        if best in methods:
            idx = methods.index(best)
            ax.text(1.03, idx, "reported best", va="center", fontsize=9, color=OKABE_ITO["red"])
        ax.text(
            0.02,
            0.03,
            "No formal Phase 3 validation_summary.csv found locally.",
            fontsize=9,
            color=OKABE_ITO["gray"],
            transform=ax.transAxes,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 2.0},
        )
    elif not validation.empty:
        method_col = choose_column(validation, ["method", "strategy", "selector", "method_name"]) or validation.columns[0]
        metric_col = choose_column(validation, ["target_hit_rate", "best_score", "mean_best_score", "convergence_auc"])
        ax = axes[0]
        if metric_col is None:
            counts = validation[method_col].value_counts()
            ax.barh(counts.index.astype(str), counts.values, color=OKABE_ITO["blue"])
            ax.set_xlabel("Validation rows")
        else:
            grouped = validation.groupby(method_col, dropna=False)[metric_col].mean().sort_values()
            ax.barh(grouped.index.astype(str), grouped.values, color=OKABE_ITO["blue"])
            ax.set_xlabel(metric_col)
        ax.set_title("Formal validation summary")
    else:
        axes[0].text(0.5, 0.5, "No strategy benchmark source found", ha="center", va="center", fontsize=12)
        axes[0].set_axis_off()

    ax2 = axes[1]
    labels = ["data_source", "engineering_validity", "must_resimulate"]
    values = [
        ablation.get("data_source") == BOUNDARY["data_source"],
        ablation.get("engineering_validity") == BOUNDARY["engineering_validity"],
        bool(BOUNDARY["must_resimulate"]),
    ]
    colors = [OKABE_ITO["green"] if value else OKABE_ITO["red"] for value in values]
    ax2.bar(labels, [1 if value else 0 for value in values], color=colors)
    ax2.set_ylim(0, 1.2)
    ax2.set_ylabel("Boundary present")
    ax2.set_title("Evidence boundary check")
    ax2.tick_params(axis="x", rotation=25)
    for idx, value in enumerate(values):
        ax2.text(idx, 1.04, "pass" if value else "missing", ha="center", fontsize=9)

    fig.text(0.5, 0.01, boundary_text(), ha="center", fontsize=9, color=OKABE_ITO["gray"])
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    return save_figure(fig, output_dir, "fig05_strategy_benchmark")


def figure_06(output_dir: Path, bundle: DataBundle) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4), gridspec_kw={"width_ratios": [1.2, 1.0]})
    fig.suptitle("Ablation and Boundary Audit", fontsize=17, fontweight="bold", y=0.98)

    validation = read_csv(bundle.validation_summary)
    ablation = load_json(bundle.ablation_summary)
    ax = axes[0]
    if not validation.empty:
        metric_names = ["target_hit_rate", "best_score", "hard_pass_rate", "convergence_auc"]
        present = [name for name in metric_names if name in validation.columns]
        if present:
            means = validation[present].mean(numeric_only=True)
            ax.bar(means.index, means.values, color=[OKABE_ITO["blue"], OKABE_ITO["green"], OKABE_ITO["orange"], OKABE_ITO["purple"]][: len(means)])
            ax.tick_params(axis="x", rotation=25)
            ax.set_ylabel("Mean metric")
        else:
            ax.text(0.5, 0.5, "Validation CSV found\nmetrics need mapping", ha="center", va="center", fontsize=12)
        ax.set_title("Formal validation metrics")
    else:
        methods = ablation.get("methods") or []
        labels = ["target_hit", "sim_to_target", "hard_pass", "auc"]
        ax.bar(labels, [0, 0, 0, 0], color=OKABE_ITO["light_gray"], edgecolor=OKABE_ITO["gray"])
        ax.set_ylim(0, 1)
        ax.set_title("Phase 3 metrics not available")
        ax.set_ylabel("Deferred until validation_summary.csv")
        ax.text(
            0.5,
            0.58,
            f"Smoke artifact methods: {len(methods)}\nNo performance values fabricated",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=11,
            color=OKABE_ITO["black"],
        )

    ax2 = axes[1]
    boundary_items = [
        ("real_simulation_csv", ablation.get("data_source") == BOUNDARY["data_source"] or bundle.validation_summary is not None),
        ("simulation_only", ablation.get("engineering_validity") == BOUNDARY["engineering_validity"] or bundle.validation_summary is not None),
        ("must_resimulate", BOUNDARY["must_resimulate"]),
        ("claim_boundary", bool(ablation.get("claim_boundary")) or bundle.validation_summary is not None),
    ]
    y = np.arange(len(boundary_items))
    ax2.barh(y, [1 if item[1] else 0 for item in boundary_items], color=[OKABE_ITO["green"] if item[1] else OKABE_ITO["red"] for item in boundary_items])
    ax2.set_yticks(y, [item[0] for item in boundary_items])
    ax2.set_xlim(0, 1.1)
    ax2.set_xlabel("Audit status")
    ax2.set_title("Boundary fields")
    for idx, (_, ok) in enumerate(boundary_items):
        ax2.text(1.02, idx, "pass" if ok else "missing", va="center", fontsize=9)

    fig.text(0.5, 0.01, boundary_text(), ha="center", fontsize=9, color=OKABE_ITO["gray"])
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    return save_figure(fig, output_dir, "fig06_ablation_and_boundary")


def figure_07(output_dir: Path, bundle: DataBundle) -> list[Path]:
    candidates = read_csv(bundle.selected_candidates)
    if candidates.empty:
        candidates = read_csv(bundle.sample_candidates)
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.2), gridspec_kw={"width_ratios": [1.1, 1.1]})
    fig.suptitle("Candidate Acquisition Diagnostics", fontsize=17, fontweight="bold", y=0.98)

    ax = axes[0]
    if not candidates.empty:
        id_col = choose_column(candidates, ["candidate_id", "id", "name"]) or candidates.index.name or "index"
        score_col = choose_column(candidates, ["acquisition_score", "overall_score", "predicted_score"])
        role_col = choose_column(candidates, ["candidate_role", "source"])
        frame = candidates.head(12).copy()
        labels = frame[id_col].astype(str).tolist() if id_col in frame.columns else [f"cand_{i}" for i in range(len(frame))]
        values = frame[score_col].astype(float).tolist() if score_col else [1.0] * len(frame)
        colors = [OKABE_ITO["blue"], OKABE_ITO["green"], OKABE_ITO["orange"], OKABE_ITO["purple"], OKABE_ITO["sky"]]
        ax.bar(labels, values, color=[colors[i % len(colors)] for i in range(len(labels))])
        ax.set_title(score_col or "candidate count")
        ax.tick_params(axis="x", rotation=35)
        ax.set_ylabel("Score")
        ax.set_ylim(0, max(values) * 1.22 if values else 1.0)
        if role_col and role_col in frame.columns:
            for idx, role in enumerate(frame[role_col].astype(str).tolist()):
                ax.text(idx, values[idx] + max(values) * 0.025, role.replace("_", "\n"), ha="center", va="bottom", fontsize=7)
    else:
        ax.text(0.5, 0.5, "No candidate source found", ha="center", va="center")
        ax.set_axis_off()

    ax2 = axes[1]
    if not candidates.empty:
        dist_col = choose_column(candidates, ["capm_distance_to_l1", "capm_geodesic_distance_to_l1", "capm_distance_to_l1_normalized"])
        barrier_col = choose_column(candidates, ["capm_barrier_score", "capm_missing_penalty"])
        score_col = choose_column(candidates, ["acquisition_score", "overall_score", "predicted_score"])
        if dist_col and barrier_col:
            size = candidates[score_col].astype(float).to_numpy() if score_col else np.ones(len(candidates))
            size = 70 + 160 * (size - np.nanmin(size)) / (np.nanmax(size) - np.nanmin(size) + 1e-9)
            ax2.scatter(candidates[dist_col], candidates[barrier_col], s=size, color=OKABE_ITO["orange"], edgecolor=OKABE_ITO["black"], alpha=0.85)
            ax2.set_xlabel(dist_col)
            ax2.set_ylabel(barrier_col)
            ax2.set_title("CAPM distance vs barrier")
        else:
            numeric_cols = candidates.select_dtypes(include=[np.number]).columns[:4]
            if len(numeric_cols) > 0:
                means = candidates[numeric_cols].mean(numeric_only=True)
                ax2.bar(means.index, means.values, color=OKABE_ITO["green"])
                ax2.tick_params(axis="x", rotation=35)
                ax2.set_title("Available numeric diagnostics")
            else:
                ax2.text(0.5, 0.5, "No numeric diagnostics", ha="center", va="center")
                ax2.set_axis_off()
    else:
        ax2.set_axis_off()

    fig.text(0.5, 0.01, boundary_text(), ha="center", fontsize=9, color=OKABE_ITO["gray"])
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    return save_figure(fig, output_dir, "fig07_candidate_acquisition_diagnostics")


def write_prompts(output_dir: Path) -> Path:
    prompts = []
    for item in IMAGE2_PROMPTS:
        record = dict(item)
        record.update(
            {
                "status": "gpt-image-2 prompt recorded; final repository figure uses deterministic label overlay",
                "boundary": BOUNDARY,
            }
        )
        prompts.append(record)
    path = output_dir / "prompts" / "image2_prompts.json"
    path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def rel(path: Path | None, root: Path) -> str:
    if path is None:
        return "not_found"
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def write_manifest(output_dir: Path, bundle: DataBundle, generated: list[Path]) -> Path:
    data_role = "formal validation evidence" if bundle.validation_summary else "sample/smoke visualization; not full validation evidence"
    content = f"""# PIA-CA-LLSO Paper Figure Manifest

This package contains publication-preparation figures for the PIA-CA-LLSO manuscript.

Evidence boundary fixed for every figure:

- `data_source = {BOUNDARY["data_source"]}`
- `engineering_validity = {BOUNDARY["engineering_validity"]}`
- `must_resimulate = true`

## Data Sources

- Formal method definition: `{rel(bundle.formal_method, bundle.repo_root)}`
- Sample history: `{rel(bundle.sample_history, bundle.repo_root)}`
- Sample candidates: `{rel(bundle.sample_candidates, bundle.repo_root)}`
- Sample simulation results: `{rel(bundle.sample_results, bundle.repo_root)}`
- Validation summary: `{rel(bundle.validation_summary, bundle.repo_root)}`
- Ablation summary: `{rel(bundle.ablation_summary, bundle.repo_root)}`
- Selected candidates: `{rel(bundle.selected_candidates, bundle.repo_root)}`

## Figure Entries

| Figure | File | Evidence role | Supports | Does not support |
|---|---|---|---|---|
| Fig. 1 | `figures/fig01_graphical_abstract.png` | Conceptual schematic; GPT image2 prompt recorded and deterministic labels rendered locally | Overall closed-loop workflow and terminology alignment | Physical silicon validation, tapeout validation, or measured lab performance |
| Fig. 2 | `figures/fig02_closed_loop_architecture.png` | Conceptual schematic | Module boundary of labeling, LLSO, selection, simulation import, and audit | Claim that every simulator backend has been experimentally validated |
| Fig. 3 | `figures/fig03_capm_physics_manifold.png` | Conceptual schematic | CAPM-Distance idea: physics features, L1 basin, barrier proxy, geodesic path, missingness | Claim that barrier proxy equals real hard-constraint failure |
| Fig. 4 | `figures/fig04_acquisition_ensemble.png` | Conceptual schematic | Acquisition ensemble composition and five-paper-inspired extension layer | Full reproduction of DEAOE, HRCEA, AIEA, CESAEA, or ECCoEA-ASAA |
| Fig. 5 | `figures/fig05_strategy_benchmark.png` | {data_role} | Available benchmark/evidence fields and boundary audit | Final method superiority without Phase 3 validation CSV |
| Fig. 6 | `figures/fig06_ablation_and_boundary.png` | {data_role} | Boundary pass status and deferred formal validation slots | Numeric ablation conclusions if formal validation CSV is absent |
| Fig. 7 | `figures/fig07_candidate_acquisition_diagnostics.png` | Candidate suggestion diagnostics from CSV where available | Why top candidates were suggested for next-run simulation | That suggestions are already physical validation evidence |

## Generated Files

"""
    for path in sorted(generated):
        content += f"- `{rel(path, bundle.repo_root)}`\n"
    path = output_dir / "figure_manifest.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_captions(output_dir: Path) -> Path:
    content = """# PIA-CA-LLSO 论文图注草稿

**图 1. PIA-CA-LLSO 图形摘要。** 该图概述从历史仿真 CSV 与候选设计出发，经物理语义特征映射、CAPM-Distance、PIA 采集选择、下一轮仿真批次和结果导入形成闭环的流程。图中所有结果边界限定为 `data_source = real_simulation_csv`、`engineering_validity = simulation_only`、`must_resimulate = true`。

**图 2. PIA-CA-LLSO 闭环架构。** 该图展示 L1/L2/L3/L4 标签、LLSO offspring、候选修复、PIA selector、仿真批次、结果导入、resume state 与 boundary audit 的模块关系。

**图 3. CAPM-Distance 物理语义流形示意。** 原始设计变量通过 `phi(x)` 映射到物理特征空间，候选点到 L1 basin 的距离由 tensor/coupling 距离、soft barrier、missing penalty 和图上 geodesic 共同刻画。barrier 仅是仿真前风险 proxy，不等同于真实硬约束失败。

**图 4. 候选采集集成层。** CAPM 距离、自适应物理权重、分类器概率、多样性、不确定性和五篇论文启发式子分量共同形成 `A(x)`，用于排序下一轮仿真建议；该层不是对五篇论文算法的完整复现。

**图 5. 策略基准证据视图。** 若本地存在 Phase 3 `validation_summary.csv`，该图展示正式验证汇总；否则展示已有 sample/smoke benchmark artifact 中可审计的方法和边界字段，不作为最终优越性证据。

**图 6. 消融与边界审计。** 该图汇总可用的验证指标或在正式验证缺失时显式标记待补指标，同时展示 `real_simulation_csv / simulation_only / must_resimulate` 等边界字段。

**图 7. 候选采集诊断。** 该图基于 `pia_selected_candidates.csv` 或样例候选池展示 `acquisition_score`、CAPM 距离、barrier 和候选角色，用于解释下一轮仿真建议，不代表最终真实性能证据。
"""
    path = output_dir / "figure_captions_zh.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_readme(output_dir: Path, bundle: DataBundle) -> Path:
    validation_note = (
        "Formal validation CSV was found and used."
        if bundle.validation_summary
        else "No formal Phase 3 validation_summary.csv was found; figures 5-6 are marked as sample/smoke visualizations."
    )
    content = f"""# PIA-CA-LLSO Paper Figures

This directory contains the manuscript figure package generated from the current repository state.

## Regenerate

```bash
python scripts/build_pia_paper_figures.py
```

Optional:

```bash
python scripts/build_pia_paper_figures.py --validation-dir outputs/pia_phase3_validation
python scripts/build_pia_paper_figures.py --dry-run
```

## Contents

- `figures/`: PNG and PDF figure exports.
- `prompts/image2_prompts.json`: GPT image2 prompt records for the four concept schematics.
- `figure_manifest.md`: source paths, evidence role, supported claims, and unsupported claims.
- `figure_captions_zh.md`: Chinese manuscript caption drafts.

## Evidence Boundary

- `data_source = {BOUNDARY["data_source"]}`
- `engineering_validity = {BOUNDARY["engineering_validity"]}`
- `must_resimulate = true`

{validation_note}

The generated figures are publication-preparation artifacts. They do not add new experimental evidence and do not claim silicon, tapeout, laboratory, or physical measurement validation.
"""
    path = output_dir / "README.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_summary(output_dir: Path, bundle: DataBundle, generated: list[Path]) -> Path:
    summary = {
        "boundary": BOUNDARY,
        "evidence_role": bundle.evidence_role,
        "sources": {
            "formal_method": rel(bundle.formal_method, bundle.repo_root),
            "sample_history": rel(bundle.sample_history, bundle.repo_root),
            "sample_candidates": rel(bundle.sample_candidates, bundle.repo_root),
            "sample_results": rel(bundle.sample_results, bundle.repo_root),
            "validation_summary": rel(bundle.validation_summary, bundle.repo_root),
            "ablation_summary": rel(bundle.ablation_summary, bundle.repo_root),
            "selected_candidates": rel(bundle.selected_candidates, bundle.repo_root),
        },
        "generated_files": [rel(path, bundle.repo_root) for path in sorted(generated)],
    }
    path = output_dir / "figure_generation_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_figure_package(output_dir: Path, validation_dir: Path | None = None) -> list[Path]:
    repo_root = repo_root_from_script()
    bundle = discover_data(repo_root, validation_dir)
    missing = validate_sources(bundle)
    if missing:
        raise FileNotFoundError("Required PIA figure source missing: " + ", ".join(missing))

    ensure_output_dirs(output_dir)
    generated: list[Path] = []
    generated.extend(figure_01(output_dir))
    generated.extend(figure_02(output_dir))
    generated.extend(figure_03(output_dir))
    generated.extend(figure_04(output_dir))
    generated.extend(figure_05(output_dir, bundle))
    generated.extend(figure_06(output_dir, bundle))
    generated.extend(figure_07(output_dir, bundle))
    generated.append(write_prompts(output_dir))
    generated.append(write_manifest(output_dir, bundle, generated))
    generated.append(write_captions(output_dir))
    generated.append(write_readme(output_dir, bundle))
    generated.append(write_summary(output_dir, bundle, generated))
    return generated


def dry_run(validation_dir: Path | None) -> dict[str, Any]:
    repo_root = repo_root_from_script()
    bundle = discover_data(repo_root, validation_dir)
    return {
        "missing_required_sources": validate_sources(bundle),
        "evidence_role": bundle.evidence_role,
        "sources": {
            "formal_method": rel(bundle.formal_method, repo_root),
            "sample_history": rel(bundle.sample_history, repo_root),
            "sample_candidates": rel(bundle.sample_candidates, repo_root),
            "sample_results": rel(bundle.sample_results, repo_root),
            "validation_summary": rel(bundle.validation_summary, repo_root),
            "ablation_summary": rel(bundle.ablation_summary, repo_root),
            "selected_candidates": rel(bundle.selected_candidates, repo_root),
        },
        "boundary": BOUNDARY,
        "image2_prompt_count": len(IMAGE2_PROMPTS),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PIA-CA-LLSO paper figure package.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root_from_script() / "docs" / "pia_ca_llso_paper_figures",
        help="Output directory for generated figure package.",
    )
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=None,
        help="Optional directory containing validation_summary.csv.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only report discovered sources.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.dry_run:
        print(json.dumps(dry_run(args.validation_dir), ensure_ascii=False, indent=2))
        return
    generated = build_figure_package(args.output_dir, args.validation_dir)
    print(f"Generated {len(generated)} files under {args.output_dir}")


if __name__ == "__main__":
    main()
