from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_timing_overview(features: dict, path: Path, data_source: str, validity: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = list(features["nodes"].keys())
    trises = [features["nodes"][node]["trise"] for node in nodes]
    delays = [None]
    for left, right in zip(nodes, nodes[1:]):
        left_t = features["nodes"][left]["trise"]
        right_t = features["nodes"][right]["trise"]
        delays.append(None if left_t is None or right_t is None else right_t - left_t)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(nodes, [value * 1e6 if value is not None else None for value in trises], marker="o", label="trise")
    ax.plot(nodes, [value * 1e6 if value is not None else None for value in delays], marker="s", label="tpd")
    ax.set_title(f"Timing overview data_source={data_source}")
    ax.set_ylabel("Time (us)")
    ax.text(0.01, 0.02, validity, transform=ax.transAxes, alpha=0.65)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
