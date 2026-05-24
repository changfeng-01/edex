from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd


DATA_LABEL = "data_source = real_simulation_csv | engineering_validity = simulation_only"


def configure_plot_fonts() -> None:
    names = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"]:
        if candidate in names:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False


def plot_o1_o8_overview(frame: pd.DataFrame, output_nodes: list[str], path: Path) -> None:
    configure_plot_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 5))
    time_us = _time_us(frame)
    for node in output_nodes:
        ax.plot(time_us, frame[node], lw=0.9, label=node)
    ax.set_title("o1~o8 输出波形总览")
    ax.set_xlabel("时间 / μs")
    ax.set_ylabel("电压 / V")
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=4)
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_o1_o8_stacked(frame: pd.DataFrame, output_nodes: list[str], path: Path) -> None:
    configure_plot_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(output_nodes), 1, figsize=(12, 10), sharex=True)
    if not isinstance(axes, np.ndarray):
        axes = np.array([axes])
    time_us = _time_us(frame)
    for ax, node in zip(axes, output_nodes):
        ax.plot(time_us, frame[node], lw=0.8)
        ax.set_ylabel(node, rotation=0, labelpad=18)
        ax.grid(True, alpha=0.25)
    axes[0].set_title("o1~o8 堆叠波形：逐级扫描顺序观察")
    axes[-1].set_xlabel("时间 / μs")
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_sample_outputs_overview(frame: pd.DataFrame, output_nodes: list[str], path: Path) -> None:
    configure_plot_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 5))
    time_us = _time_us(frame)
    for node in output_nodes:
        if node in frame:
            ax.plot(time_us, frame[node], lw=0.9, label=node)
    ax.set_title("抽样输出波形总览")
    ax.set_xlabel("时间 / μs")
    ax.set_ylabel("电压 / V")
    ax.grid(True, alpha=0.25)
    if output_nodes:
        ax.legend(ncol=min(4, max(1, len(output_nodes))))
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_sample_outputs_stacked(frame: pd.DataFrame, output_nodes: list[str], path: Path) -> None:
    configure_plot_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = [node for node in output_nodes if node in frame]
    if not nodes:
        nodes = []
    fig, axes = plt.subplots(max(1, len(nodes)), 1, figsize=(12, max(3, 0.75 * max(1, len(nodes)))), sharex=True)
    if not isinstance(axes, np.ndarray):
        axes = np.array([axes])
    time_us = _time_us(frame)
    for ax, node in zip(axes, nodes):
        ax.plot(time_us, frame[node], lw=0.8)
        ax.set_ylabel(node, rotation=0, labelpad=18)
        ax.grid(True, alpha=0.25)
    if not nodes:
        axes[0].text(0.5, 0.5, "No sample output nodes", ha="center", va="center")
    axes[0].set_title("抽样输出堆叠波形")
    axes[-1].set_xlabel("时间 / μs")
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_large_cascade_trends(metrics: pd.DataFrame, figure_dir: Path) -> None:
    configure_plot_fonts()
    figure_dir.mkdir(parents=True, exist_ok=True)
    trend_specs = [
        ("VOH_mean", "VOH 趋势", "电压 / V", "voh_trend.png"),
        ("VoltageLoss", "电压损失趋势", "电压 / V", "voltage_loss_trend.png"),
        ("Delay", "级间延迟趋势", "时间 / μs", "delay_trend.png"),
        ("Ripple", "纹波趋势", "电压 / V", "ripple_trend.png"),
    ]
    frame = metrics.copy()
    if "Delay" in frame:
        frame["Delay"] = frame["Delay"] * 1e6
    for column, title, ylabel, filename in trend_specs:
        if column not in frame:
            _empty_plot(figure_dir / filename, title)
            continue
        rows = frame.dropna(subset=[column])
        if rows.empty:
            _empty_plot(figure_dir / filename, title)
            continue
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(rows["stage"], rows[column], lw=1.0)
        ax.set_title(title)
        ax.set_xlabel("级数")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
        _add_data_label(fig)
        fig.tight_layout()
        fig.savefig(figure_dir / filename, dpi=160)
        plt.close(fig)


def plot_block_stability_heatmap(*, summary_blocks: list[dict], path: Path) -> None:
    configure_plot_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not summary_blocks:
        _empty_plot(path, "分段稳定性热力图")
        return
    metrics = ["VOH_min", "Max_voltage_loss", "Max_ripple", "Delay_mean", "failed_stage_count"]
    values = np.array([[float(block.get(metric) or 0.0) for metric in metrics] for block in summary_blocks], dtype=float)
    normalized = values.copy()
    for col in range(normalized.shape[1]):
        column = normalized[:, col]
        span = float(np.nanmax(column) - np.nanmin(column))
        normalized[:, col] = 0.0 if span == 0.0 else (column - np.nanmin(column)) / span
    fig, ax = plt.subplots(figsize=(10, max(4, len(summary_blocks) * 0.28)))
    image = ax.imshow(normalized, aspect="auto", cmap="YlOrRd")
    ax.set_title("分段稳定性风险热力图")
    ax.set_xlabel("指标")
    ax.set_ylabel("分段")
    ax.set_xticks(np.arange(len(metrics)), metrics, rotation=25, ha="right")
    labels = [f"{block['stage_start']}-{block['stage_end']}" for block in summary_blocks]
    ax.set_yticks(np.arange(len(labels)), labels)
    fig.colorbar(image, ax=ax, label="归一化风险")
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_metric_bars(metrics: pd.DataFrame, figure_dir: Path, *, high_threshold: float, target_pulse_width_us: float = 10.0) -> None:
    configure_plot_fonts()
    figure_dir.mkdir(parents=True, exist_ok=True)
    metrics_us = metrics.copy()
    width_col = "PulseWidth" if "PulseWidth" in metrics_us.columns else "pulse_width"
    delay_col = "Delay" if "Delay" in metrics_us.columns else "delay_to_next"
    ripple_col = "Ripple" if "Ripple" in metrics_us.columns else "ripple"
    overlap_ratio_col = "OverlapRatio" if "OverlapRatio" in metrics_us.columns else "overlap_ratio"
    metrics_us["pulse_width_us"] = metrics_us[width_col] * 1e6
    metrics_us["delay_us"] = metrics_us[delay_col] * 1e6

    _bar(metrics_us, "node", "VOH_mean", "VOH 平均值", "电压 / V", figure_dir / "voh_bar.png", hline=high_threshold, hline_label="high_threshold")
    _bar(metrics_us, "node", "pulse_width_us", "脉冲宽度", "时间 / μs", figure_dir / "pulse_width_bar.png", hline=target_pulse_width_us, hline_label=f"目标脉宽 {target_pulse_width_us:g} μs")
    _bar(metrics_us, "node", "pulse_width_us", "脉冲宽度", "时间 / μs", figure_dir / "width_bar.png", hline=target_pulse_width_us, hline_label=f"目标脉宽 {target_pulse_width_us:g} μs")
    delay_rows = metrics_us.dropna(subset=["delay_us"])
    if not delay_rows.empty:
        delay_plot = delay_rows.copy()
        delay_plot["pair"] = [str(node) for node in delay_plot["node"]]
        _bar(delay_plot, "pair", "delay_us", "Delay_i 相邻级传播延迟", "时间 / μs", figure_dir / "delay_bar.png")
    if ripple_col in metrics_us:
        _bar(metrics_us, "node", ripple_col, "Ripple 非选通纹波", "电压 / V", figure_dir / "ripple_bar.png")
    if "VoltageLoss" in metrics_us:
        _bar(metrics_us, "node", "VoltageLoss", "VoltageLoss 电压损失", "电压 / V", figure_dir / "voltage_loss_bar.png")
    if overlap_ratio_col in metrics_us:
        _bar(metrics_us.dropna(subset=[overlap_ratio_col]), "node", overlap_ratio_col, "OverlapRatio 相邻级重叠比例", "比例", figure_dir / "overlap_ratio_bar.png")
    _paired_bar(metrics_us, "node", "VOL_max", ripple_col, "VOL_max / Ripple 对比", "电压 / V", figure_dir / "vol_ripple_bar.png")

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for ax, column, title, ylabel in [
        (axes[0], "VOH_mean", "VOH 平均值", "电压 / V"),
        (axes[1], "pulse_width_us", "Pulse Width 脉冲宽度", "时间 / μs"),
    ]:
        rows = metrics_us.dropna(subset=[column])
        ax.bar(rows["node"], rows[column])
        if column == "VOH_mean":
            ax.axhline(high_threshold, color="red", linestyle="--", linewidth=1.1, label="high_threshold")
            ax.legend()
        if column == "pulse_width_us":
            ax.axhline(target_pulse_width_us, color="red", linestyle="--", linewidth=1.1, label="目标脉宽 10 μs")
            ax.legend()
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
    axes[-1].set_xlabel("输出节点")
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(figure_dir / "voh_width_bar.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(10, 9))
    for ax, column, title, ylabel in [
        (axes[0], "VOH_mean", "VOH 平均值", "电压 / V"),
        (axes[1], "pulse_width_us", "脉冲宽度", "时间 / μs"),
        (axes[2], "delay_us", "传播延迟", "时间 / μs"),
    ]:
        rows = metrics_us.dropna(subset=[column])
        ax.bar(rows["node"], rows[column])
        if column == "VOH_mean":
            ax.axhline(high_threshold, color="red", linestyle="--", linewidth=1.1, label="high_threshold")
            ax.legend()
        if column == "pulse_width_us":
            ax.axhline(target_pulse_width_us, color="red", linestyle="--", linewidth=1.1, label="目标脉宽 10 μs")
            ax.legend()
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
    axes[-1].set_xlabel("输出节点")
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(figure_dir / "voh_width_delay_bar.png", dpi=160)
    plt.close(fig)


def plot_internal_xs4(frame: pd.DataFrame, path: Path) -> bool:
    required = ["xs4.pu", "xs4.pd", "o4"]
    if any(column not in frame.columns for column in required):
        return False
    configure_plot_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 4))
    time_us = _time_us(frame)
    for column in required:
        ax.plot(time_us, frame[column], lw=0.9, label=column)
    ax.set_title("第 4 级内部节点：xs4.pu / xs4.pd / o4")
    ax.set_xlabel("时间 / μs")
    ax.set_ylabel("电压 / V")
    ax.grid(True, alpha=0.25)
    ax.legend()
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return True


def plot_internal_compare(frame: pd.DataFrame, path: Path) -> bool:
    groups = [("xs1", "o1"), ("xs4", "o4"), ("xs8", "o8")]
    needed = [f"{stage}.pu" for stage, _ in groups] + [f"{stage}.pd" for stage, _ in groups] + [out for _, out in groups]
    if any(column not in frame.columns for column in needed):
        return False
    configure_plot_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    time_us = _time_us(frame)
    for stage, _ in groups:
        axes[0].plot(time_us, frame[f"{stage}.pu"], lw=0.8, label=f"{stage}.pu")
        axes[1].plot(time_us, frame[f"{stage}.pd"], lw=0.8, label=f"{stage}.pd")
    for _, output in groups:
        axes[2].plot(time_us, frame[output], lw=0.8, label=output)
    for ax, title in zip(axes, ["PU 节点对比", "PD 节点对比", "输出节点对比"]):
        ax.set_title(title)
        ax.set_ylabel("电压 / V")
        ax.grid(True, alpha=0.25)
        ax.legend(ncol=3)
    axes[-1].set_xlabel("时间 / μs")
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return True


def _bar(frame: pd.DataFrame, x_col: str, y_col: str, title: str, ylabel: str, path: Path, hline: float | None = None, hline_label: str | None = None) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    plot_frame = frame.copy()
    plot_frame[y_col] = pd.to_numeric(plot_frame[y_col], errors="coerce")
    plot_frame = plot_frame.dropna(subset=[y_col])
    if plot_frame.empty:
        ax.text(0.5, 0.5, f"No evaluable {y_col}", ha="center", va="center")
    else:
        ax.bar(plot_frame[x_col], plot_frame[y_col])
    if hline is not None:
        ax.axhline(hline, color="red", linestyle="--", linewidth=1.1, label=hline_label or "reference")
        ax.legend()
    ax.set_title(title)
    ax.set_xlabel("输出节点")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _paired_bar(frame: pd.DataFrame, x_col: str, left_col: str, right_col: str, title: str, ylabel: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    plot_frame = frame.copy()
    for column in [left_col, right_col]:
        plot_frame[column] = pd.to_numeric(plot_frame[column], errors="coerce")
    plot_frame = plot_frame.dropna(subset=[left_col, right_col], how="all")
    x = np.arange(len(plot_frame[x_col]))
    width = 0.36
    if plot_frame.empty:
        ax.text(0.5, 0.5, f"No evaluable {left_col}/{right_col}", ha="center", va="center")
    else:
        ax.bar(x - width / 2, plot_frame[left_col], width, label=left_col)
        ax.bar(x + width / 2, plot_frame[right_col], width, label=right_col)
    ax.set_xticks(x, plot_frame[x_col])
    ax.set_title(title)
    ax.set_xlabel("输出节点")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    if not plot_frame.empty:
        ax.legend()
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _empty_plot(path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.text(0.5, 0.5, "No data", ha="center", va="center")
    ax.set_title(title)
    ax.set_axis_off()
    _add_data_label(fig)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _time_us(frame: pd.DataFrame) -> pd.Series:
    return frame["time"] * 1e6


def _add_data_label(fig) -> None:
    fig.text(0.01, 0.01, DATA_LABEL, fontsize=8, color="#555555")
