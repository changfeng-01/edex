from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_voh_bar(features: dict, path: Path, data_source: str, validity: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = list(features["nodes"].keys())
    values = [features["nodes"][node]["VOH"] for node in nodes]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(nodes, values)
    ax.set_title(f"VOH by output data_source={data_source}")
    ax.set_ylabel("VOH (V)")
    ax.text(0.01, 0.02, validity, transform=ax.transAxes, alpha=0.65)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
