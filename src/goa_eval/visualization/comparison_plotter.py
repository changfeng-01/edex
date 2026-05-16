from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_v1_v8_comparison(designs, summary: dict, thresholds: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = [design for design in designs if design.name in {"v1", "v8"}]
    if not selected:
        selected = list(designs)
    selected = sorted(selected, key=lambda design: design.name)

    names = [design.name for design in selected]
    w_values = [_w_sum(design) * 1e6 for design in selected]
    c_values = [_c_sum(design) * 1e15 for design in selected]
    cost_values = [_proxy_cost(design, thresholds) for design in selected]
    hard_counts = [_hard_pass_count(summary, design.name) for design in selected]

    x = np.arange(len(names))
    width = 0.2
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(x - 1.5 * width, w_values, width, label="W_sum (um)")
    ax.bar(x - 0.5 * width, c_values, width, label="C_sum (fF)")
    ax.bar(x + 0.5 * width, cost_values, width, label="proxy cost")
    ax.bar(x + 1.5 * width, hard_counts, width, label="hard passes")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_title("v1/v8 workflow comparison (mock data only)")
    ax.text(0.01, 0.02, "workflow_test_only", transform=ax.transAxes, alpha=0.65)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _w_sum(design) -> float:
    return sum(device.params_si.get("W", 0.0) for device in design.devices if device.kind == "mos")


def _c_sum(design) -> float:
    return sum(device.params_si.get("C", 0.0) for device in design.devices if device.kind == "capacitor")


def _proxy_cost(design, thresholds: dict) -> float:
    cost_cfg = thresholds.get("cost", {})
    return float(cost_cfg.get("alpha_W", 1.0)) * _w_sum(design) + float(cost_cfg.get("alpha_C", 1e6)) * _c_sum(design)


def _hard_pass_count(summary: dict, version: str) -> int:
    checks = summary.get("hard_checks", {}).get(version, {})
    return sum(1 for value in checks.values() if value is True)
