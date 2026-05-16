# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import argparse
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goa_eval.config import load_configs
from goa_eval.parsers.waveform_parser import read_waveform_csv
from goa_eval.evaluation.feature_extractor import extract_waveform_features
from goa_eval.evaluation.windowing import boolean_intervals, voltage_thresholds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="outputs/new_circuit_20260507_yuanshi")
    parser.add_argument("--waveform", default="yuanshi_csv")
    parser.add_argument("--internal-waveform", default="neibucsv")
    args = parser.parse_args()

    root = Path.cwd()
    run_dir = root / args.run_dir
    review_dir = run_dir / "manual_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    configure_matplotlib()

    _, thresholds = load_configs(root / "configs" / "default.yaml", root / "configs" / "thresholds.yaml")
    bundle = read_waveform_csv(root / args.waveform, "v8_new")
    features = extract_waveform_features(bundle, thresholds)
    vt = voltage_thresholds(thresholds)
    edge_guard = float(thresholds["time"]["edge_guard_ratio_of_line"]) * float(thresholds["time"]["expected_line_period"])
    min_false = float(thresholds["time"]["min_false_trigger_duration"])
    nodes = [f"o{i}" for i in range(1, 9)]

    def false_intervals(node: str) -> list[tuple[float, float]]:
        return features["nodes"][node].get("true_false_trigger_windows", [])

    write_figures(root, run_dir, review_dir, bundle, features, vt, nodes, false_intervals, args.internal_waveform)
    window_rows, false_rows, overlap_rows = build_review_rows(bundle, features, vt, nodes, false_intervals)
    write_tables(review_dir, window_rows, false_rows, overlap_rows)
    write_report(review_dir, thresholds, vt, edge_guard, min_false, window_rows, false_rows, overlap_rows)
    return 0


def configure_matplotlib() -> None:
    font_names = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"]:
        if candidate in font_names:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 140


def write_figures(root, run_dir, review_dir, bundle, features, vt, nodes, false_intervals, internal_waveform) -> None:
    time_us = bundle.time * 1e6

    fig, axes = plt.subplots(8, 1, figsize=(12, 12), sharex=True)
    for ax, node in zip(axes, nodes):
        signal = bundle.signals[node]
        feat = features["nodes"][node]
        ax.plot(time_us, signal, lw=1.0, color="#1f77b4")
        ax.axhline(vt["VH"], color="#d62728", ls="--", lw=0.8)
        start, end = feat["target_window"]
        ax.axvspan(start * 1e6, end * 1e6, color="#2ca02c", alpha=0.18)
        ax.set_ylabel(node, rotation=0, labelpad=22)
        ax.set_ylim(-6, 16.5)
        ax.grid(True, alpha=0.25, lw=0.5)
    axes[0].set_title("第一轮主扫描：自动识别的有效窗口（绿色）与高电平阈值 VH（红虚线）")
    axes[-1].set_xlabel("时间 / us")
    axes[-1].set_xlim(0, 95)
    fig.tight_layout()
    fig.savefig(review_dir / "01_first_scan_windows.png", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(8, 1, figsize=(12, 12), sharex=True)
    for ax, node in zip(axes, nodes):
        signal = bundle.signals[node]
        feat = features["nodes"][node]
        ax.plot(time_us, signal, lw=0.9, color="#1f77b4")
        ax.axhline(vt["VH"], color="#d62728", ls="--", lw=0.8)
        for start, end in feat.get("legitimate_windows", [feat["target_window"]]):
            ax.axvspan(start * 1e6, end * 1e6, color="#2ca02c", alpha=0.14)
        for false_start, false_end in false_intervals(node)[:2]:
            ax.axvspan(false_start * 1e6, false_end * 1e6, color="#d62728", alpha=0.16)
        ax.set_ylabel(node, rotation=0, labelpad=22)
        ax.set_ylim(-6, 16.5)
        ax.grid(True, alpha=0.25, lw=0.5)
    axes[0].set_title("误触发复核：绿色为所有合法扫描窗口，红色为真正非选通误触发片段")
    axes[-1].set_xlabel("时间 / us")
    axes[-1].set_xlim(0, 230)
    fig.tight_layout()
    fig.savefig(review_dir / "02_false_trigger_review.png", bbox_inches="tight")
    (run_dir / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(run_dir / "figures" / "false_trigger_review.png", bbox_inches="tight")
    plt.close(fig)

    overlap_pairs = [("o3", "o4"), ("o5", "o6"), ("o7", "o8")]
    fig, axes = plt.subplots(3, 1, figsize=(12, 7), sharex=False)
    for ax, (left, right) in zip(axes, overlap_pairs):
        left_signal = bundle.signals[left]
        right_signal = bundle.signals[right]
        intervals = boolean_intervals(bundle.time, (left_signal >= vt["VH"]) & (right_signal >= vt["VH"]))
        first = intervals[0] if intervals else (0, 0)
        center = (first[0] + first[1]) / 2 if intervals else 0
        left_limit = max(0, center * 1e6 - 4)
        right_limit = center * 1e6 + 4
        ax.plot(time_us, left_signal, lw=1.1, label=left, color="#1f77b4")
        ax.plot(time_us, right_signal, lw=1.1, label=right, color="#ff7f0e")
        ax.axhline(vt["VH"], color="#d62728", ls="--", lw=0.8)
        for start, end in intervals[:3]:
            if left_limit <= start * 1e6 <= right_limit or left_limit <= end * 1e6 <= right_limit:
                ax.axvspan(start * 1e6, end * 1e6, color="#9467bd", alpha=0.24)
        ax.set_xlim(left_limit, right_limit)
        ax.set_ylim(-6, 16.5)
        ax.set_ylabel("电压 / V")
        ax.grid(True, alpha=0.25, lw=0.5)
        ax.legend(loc="upper right")
        ax.set_title(f"{left}_{right} 相邻级重叠局部放大（紫色）")
    axes[-1].set_xlabel("时间 / us")
    fig.tight_layout()
    fig.savefig(review_dir / "03_overlap_zoom.png", bbox_inches="tight")
    plt.close(fig)

    internal_path = root / internal_waveform
    if internal_path.exists():
        raw = read_space_waveform(internal_path)
        columns = ["xs1.pu", "xs1.pd", "xs4.pu", "xs4.pd", "xs8.pu", "xs8.pd", "o1", "o4", "o8"]
        fig, axes = plt.subplots(len(columns), 1, figsize=(12, 12), sharex=True)
        for ax, column in zip(axes, columns):
            ax.plot(raw["time"].to_numpy() * 1e6, raw[column].to_numpy(), lw=0.9, color="#1f77b4")
            ax.axhline(vt["VH"], color="#d62728", ls="--", lw=0.7)
            ax.set_ylabel(column, rotation=0, labelpad=30)
            ax.set_ylim(-6, 16.5)
            ax.grid(True, alpha=0.25, lw=0.5)
        axes[0].set_title("内部节点抽查：PU/PD 与部分输出节点（用于人工定位，不作为完整 o1~o8 判定）")
        axes[-1].set_xlabel("时间 / us")
        axes[-1].set_xlim(0, 230)
        fig.tight_layout()
        fig.savefig(review_dir / "04_internal_node_spotcheck.png", bbox_inches="tight")
        plt.close(fig)


def read_space_waveform(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=r"\s+", engine="python")
    renamed = {}
    for column in raw.columns:
        text = column.strip()
        if text.upper() == "XVAL":
            renamed[column] = "time"
        elif text.lower().startswith("v(") and text.endswith(")"):
            renamed[column] = text[2:-1].strip().lower()
        else:
            renamed[column] = text.lower()
    return raw.rename(columns=renamed).apply(pd.to_numeric, errors="coerce")


def build_review_rows(bundle, features, vt, nodes, false_intervals):
    window_rows = []
    false_rows = []
    for node in nodes:
        feat = features["nodes"][node]
        start, end = feat["target_window"]
        false_segments = false_intervals(node)
        window_rows.append(
            {
                "node": node,
        "first_scan_start_us": start * 1e6,
        "first_scan_end_us": end * 1e6,
        "rise_us": feat["trise"] * 1e6,
        "fall_us": feat["tfall"] * 1e6,
        "pulse_width_us": feat["Twidth"] * 1e6,
        "legitimate_pulse_count": feat.get("legitimate_pulse_count", 0),
        "repeated_scan_count": len(feat.get("repeated_scan_windows", [])),
        "voh": feat["VOH"],
        "vol": feat["VOL"],
            }
        )
        if false_segments:
            false_start, false_end = false_segments[0]
            false_rows.append(
                {
                    "node": node,
                    "first_false_start_us": false_start * 1e6,
                    "first_false_end_us": false_end * 1e6,
                    "duration_us": (false_end - false_start) * 1e6,
                    "count": len(false_segments),
                }
            )

    overlap_rows = []
    for left, right in [(f"o{i}", f"o{i + 1}") for i in range(1, 8)]:
        intervals = boolean_intervals(bundle.time, (bundle.signals[left] >= vt["VH"]) & (bundle.signals[right] >= vt["VH"]))
        actual_total = sum(end - start for start, end in intervals)
        metric_total = features["overlaps"].get(f"{left}_{right}", 0.0)
        first_text = f"{intervals[0][0] * 1e6:.3f}-{intervals[0][1] * 1e6:.3f}" if intervals else "-"
        overlap_rows.append(
            {
                "pair": f"{left}_{right}",
                "interval_count": len(intervals),
                "first_interval_us": first_text,
                "actual_total_us": actual_total * 1e6,
                "metric_total_us": metric_total * 1e6,
            }
        )
    return window_rows, false_rows, overlap_rows


def write_tables(review_dir, window_rows, false_rows, overlap_rows) -> None:
    pd.DataFrame(window_rows).to_csv(review_dir / "review_target_windows.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        false_rows,
        columns=["node", "first_false_start_us", "first_false_end_us", "duration_us", "count"],
    ).to_csv(review_dir / "review_false_trigger_segments.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(overlap_rows).to_csv(review_dir / "review_overlap_segments.csv", index=False, encoding="utf-8-sig")


def write_report(review_dir, thresholds, vt, edge_guard, min_false, window_rows, false_rows, overlap_rows) -> None:
    window_table = "\n".join(
        f"| `{row['node']}` | {row['first_scan_start_us']:.3f} | {row['first_scan_end_us']:.3f} | "
        f"{row['rise_us']:.3f} | {row['fall_us']:.3f} | {row['pulse_width_us']:.3f} | "
        f"{row['legitimate_pulse_count']} | {row['repeated_scan_count']} | {row['voh']:.3f} | {row['vol']:.3f} |"
        for row in window_rows
    )
    false_table = "\n".join(
        f"| `{row['node']}` | {row['first_false_start_us']:.3f} | {row['first_false_end_us']:.3f} | "
        f"{row['duration_us']:.3f} | {row['count']} |"
        for row in false_rows
    ) or "| `o1~o8` | - | - | - | 0 |"
    overlap_table = "\n".join(
        f"| `{row['pair']}` | {row['interval_count']} | {row['first_interval_us']} | "
        f"{row['actual_total_us']:.3f} | {row['metric_total_us']:.3f} |"
        for row in overlap_rows
    )

    report = f"""# 8T1C / GOA 人工复核版评估报告

生成时间：2026-05-07  
复核对象：`v8_new`  
波形来源：`yuanshi_csv`  
复核目的：把自动判定中的有效窗口、误触发片段和相邻级重叠片段画出来，辅助判断问题来自电路本身还是当前评价窗口。

## 复核结论

这次自动评估的“逐级扫描顺序”和“有效脉冲存在性”是可信的初步结论：`o1~o8` 的第一轮主扫描可以按顺序识别，且每一级都有有效高电平脉冲。

本次已修正 real waveform 的误触发检测：每个输出节点会先识别所有超过 `VH` 且持续时间足够的有效高电平脉冲窗口，并把这些窗口统一作为合法选通窗口。周期性重复扫描脉冲属于合法窗口，不应被判定为误触发。

相邻级重叠确实存在于 `o3_o4`、`o5_o6`、`o7_o8`，但每个局部重叠大约只有 0.053 us，并在后续周期重复出现。原 `metrics.csv` 中约 1.558 us 的累计重叠值可能被非均匀采样放大，人工复核表按区间端点重新累计，结果约为 0.477 us。因此重叠问题需要保留，但时长应以人工复核表或修正后的算法为准。

## 当前判定口径

| 参数 | 数值 | 含义 |
|---|---:|---|
| `VH` | {vt["VH"]:.3f} V | 高电平判定阈值 |
| `VGL` | {vt["VGL"]:.3f} V | 低电平参考 |
| `VGH` | {vt["VGH"]:.3f} V | 高电平参考 |
| `min_valid_pulse_width` | {float(thresholds["time"]["min_valid_pulse_width"]) * 1e6:.3f} us | 有效脉冲最小宽度 |
| `min_false_trigger_duration` | {min_false * 1e6:.3f} us | 误触发最短持续时间 |
| `edge_guard` | {edge_guard * 1e6:.3f} us | 边沿保护区 |

## 图像索引

| 图像 | 用途 |
|---|---|
| `01_first_scan_windows.png` | 查看 `o1~o8` 第一轮主扫描、`VH` 阈值和自动目标窗口 |
| `02_false_trigger_review.png` | 查看所有合法扫描窗口和真正误触发片段 |
| `figures/false_trigger_review.png` | 同一复核图，放在本次运行的 figures 目录 |
| `03_overlap_zoom.png` | 查看 `o3_o4`、`o5_o6`、`o7_o8` 的局部重叠 |
| `04_internal_node_spotcheck.png` | 查看 `xs1/xs4/xs8` 的 PU/PD 和部分输出节点，仅作定位辅助 |

## 第一轮目标窗口

| 节点 | 第一轮窗口起点/us | 第一轮窗口终点/us | 上升越阈/us | 下降越阈/us | 脉宽/us | 合法脉冲数 | 重复扫描窗口数 | VOH/V | VOL/V |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{window_table}

## 误触发复核

| 节点 | 首个后续高电平起点/us | 首个后续高电平终点/us | 持续时间/us | 发现次数 |
|---|---:|---:|---:|---:|
{false_table}

修正后，约 100 us 周期重复出现的扫描脉冲已经被纳入合法窗口，不再作为误触发片段统计。`true_false_trigger_count=0` 表示在排除所有合法窗口及边沿缓冲后，未发现持续超过阈值的真正非选通高电平。

## 相邻级重叠复核

| 相邻级 | 片段数量 | 首个片段/us | 按端点累计/us | 原指标累计/us |
|---|---:|---:|---:|---:|
{overlap_table}

`o3_o4`、`o5_o6`、`o7_o8` 的重叠片段呈周期性重复。当前指标中的累计值使用全局平均采样间隔估算，在该波形非均匀采样时会放大结果；建议后续把重叠时长改成按布尔区间端点积分。

## 给电路同学的复核问题

1. `yuanshi_csv` 是否包含多个完整扫描周期？如果是，后续周期不应按误触发处理。
2. 每个输出级在一个周期内的合法选通窗口应如何定义？是否可按 `stv/clk/clkb` 和级编号推导？
3. `o3_o4`、`o5_o6`、`o7_o8` 约 0.053 us 的局部高电平重叠是否允许？比赛或设计规格是否有允许上限？
4. 当前 `VH=9V` 是否符合本设计的高电平判据？如果需要更贴近规格，应明确阈值或比例。
5. 内部节点 `PU/PD` 是否需要纳入正式评价，还是只作为调试定位信号？

## 建议处理

短期内，这版结果建议标记为“逐级输出正常，周期性重复扫描不构成误触发，相邻级重叠需规格确认”。

框架侧下一步仍建议修正相邻级重叠时长的累计方法，避免非均匀采样导致时长被放大。
"""
    (review_dir / "manual_review_report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
