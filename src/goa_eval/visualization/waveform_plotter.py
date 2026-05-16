from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from goa_eval.models.waveform import WaveformBundle


def plot_waveform_overview(waveform: WaveformBundle, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 7))
    for name, signal in waveform.signals.items():
        if name in {"clk", "clkb", "stv"} or name.startswith("o"):
            ax.plot(waveform.time * 1e6, signal, label=name, linewidth=0.9)
    ax.set_title(f"Waveform overview data_source={waveform.data_source}")
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("Voltage (V)")
    ax.text(0.01, 0.02, waveform.engineering_validity, transform=ax.transAxes, alpha=0.65)
    ax.legend(ncol=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
