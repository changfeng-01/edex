from __future__ import annotations

from pathlib import Path
import datetime as dt

import pandas as pd

from goa_eval.config import load_real_spec
from goa_eval.diagnosis import write_diagnosis_report
from goa_eval.io_utils import write_json
from goa_eval.metrics import RealEvalConfig, evaluate_waveform_metrics
from goa_eval.plotter import (
    plot_block_stability_heatmap,
    plot_internal_compare,
    plot_internal_xs4,
    plot_large_cascade_trends,
    plot_metric_bars,
    plot_o1_o8_overview,
    plot_o1_o8_stacked,
    plot_sample_outputs_overview,
    plot_sample_outputs_stacked,
)
from goa_eval.reporter import write_optimization_dataset, write_real_manifest, write_real_metrics_csv, write_real_report, write_real_summary
from goa_eval.scorer import score_real_evaluation
from goa_eval.waveform_io import read_real_waveform


def run_real_waveform_evaluation(
    *,
    waveform_path: Path,
    internal_waveform_path: Path | None,
    output_dir: Path,
    high_threshold: float | None = None,
    low_threshold: float | None = None,
    spec_path: Path | None = Path("config/spec.yaml"),
    output_nodes: list[str] | None = None,
    stage_count: int | None = None,
    output_node_pattern: str | None = None,
    stage_group_size: int | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    run_timestamp = dt.datetime.now().isoformat(timespec="seconds")
    run_id = "real_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    spec = load_real_spec(spec_path, high_threshold=high_threshold, low_threshold=low_threshold)
    cascade = spec["cascade"]
    if stage_count is not None:
        cascade["stage_count"] = int(stage_count)
    if output_node_pattern is not None:
        cascade["output_node_pattern"] = output_node_pattern
    if stage_group_size is not None:
        cascade["stage_group_size"] = int(stage_group_size)

    if output_nodes is None:
        waveform = read_real_waveform(waveform_path)
        output_nodes, node_selection_note = resolve_output_nodes(waveform.frame, spec)
    else:
        waveform = read_real_waveform(waveform_path, required_nodes=output_nodes)
        node_selection_note = f"使用调用方显式指定的 {len(output_nodes)} 个输出节点。"
    config = RealEvalConfig(
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
        stage_group_size=cascade["stage_group_size"],
    )
    evaluation = evaluate_waveform_metrics(waveform.frame, config, output_nodes=output_nodes)
    evaluation.notes.append(node_selection_note)
    metrics_frame = pd.DataFrame(evaluation.stage_rows)

    generated_figures: list[str] = []
    skipped_figures: list[str] = []
    sample_nodes = sample_output_nodes(output_nodes, cascade.get("sample_nodes", []))
    plot_sample_outputs_overview(waveform.frame, sample_nodes, figure_dir / "sample_outputs_overview.png")
    generated_figures.append("figures/sample_outputs_overview.png")
    plot_sample_outputs_stacked(waveform.frame, sample_nodes, figure_dir / "sample_outputs_stacked.png")
    generated_figures.append("figures/sample_outputs_stacked.png")
    if len(output_nodes) <= 32:
        plot_o1_o8_overview(waveform.frame, output_nodes, figure_dir / "o1_o8_overview.png")
        generated_figures.append("figures/o1_o8_overview.png")
        plot_o1_o8_stacked(waveform.frame, output_nodes, figure_dir / "o1_o8_stacked.png")
        generated_figures.append("figures/o1_o8_stacked.png")
        plot_metric_bars(metrics_frame, figure_dir, high_threshold=config.high_threshold, target_pulse_width_us=config.target_pulse_width * 1e6)
        generated_figures.extend(
            [
                "figures/voh_bar.png",
                "figures/pulse_width_bar.png",
                "figures/delay_bar.png",
                "figures/ripple_bar.png",
                "figures/voltage_loss_bar.png",
                "figures/overlap_ratio_bar.png",
                "figures/width_bar.png",
                "figures/voh_width_bar.png",
                "figures/voh_width_delay_bar.png",
                "figures/vol_ripple_bar.png",
            ]
        )
        if (figure_dir / "delay_bar.png").exists():
            generated_figures.append("figures/delay_bar.png")
    else:
        skipped_figures.append("级数较大，跳过逐级柱状图，保留趋势图、热力图和抽样波形图。")
    plot_large_cascade_trends(metrics_frame, figure_dir)
    plot_block_stability_heatmap(summary_blocks=evaluation.summary.get("block_summary", []), path=figure_dir / "block_stability_heatmap.png")
    generated_figures.extend(
        [
            "figures/voh_trend.png",
            "figures/voltage_loss_trend.png",
            "figures/delay_trend.png",
            "figures/ripple_trend.png",
            "figures/block_stability_heatmap.png",
        ]
    )

    internal_path_for_manifest = None
    if internal_waveform_path is not None and internal_waveform_path.exists():
        internal_path_for_manifest = internal_waveform_path
        internal = read_real_waveform(internal_waveform_path)
        if plot_internal_xs4(internal.frame, figure_dir / "internal_xs4_pu_pd_o4.png"):
            generated_figures.append("figures/internal_xs4_pu_pd_o4.png")
        else:
            skipped_figures.append("缺少 xs4.pu、xs4.pd 或 o4，跳过 internal_xs4_pu_pd_o4.png。")
        if plot_internal_compare(internal.frame, figure_dir / "internal_xs1_xs4_xs8_compare.png"):
            generated_figures.append("figures/internal_xs1_xs4_xs8_compare.png")
        else:
            skipped_figures.append("缺少 xs1/xs4/xs8 的 PU、PD 或输出列，跳过 internal_xs1_xs4_xs8_compare.png。")
    elif internal_waveform_path is not None:
        skipped_figures.append(f"内部节点文件不存在：{internal_waveform_path}。")
    else:
        skipped_figures.append("未提供内部节点文件。")

    write_real_metrics_csv(output_dir / "real_metrics.csv", evaluation.stage_rows)
    summary = write_real_summary(
        output_dir / "real_summary.json",
        waveform_path=waveform_path,
        high_threshold=config.high_threshold,
        low_threshold=config.low_threshold,
        evaluation=evaluation,
        run_id=run_id,
        run_timestamp=run_timestamp,
    )
    score_summary = score_real_evaluation(summary, evaluation.stage_rows, spec)
    write_json(output_dir / "score_summary.json", score_summary)
    write_optimization_dataset(
        output_dir / "optimization_dataset.csv",
        run_id=run_id,
        run_timestamp=run_timestamp,
        summary=summary,
        score_summary=score_summary,
    )
    write_diagnosis_report(output_dir / "diagnosis_report.md", summary=summary, stage_rows=evaluation.stage_rows, score_summary=score_summary)
    write_real_report(
        output_dir / "real_waveform_report.md",
        summary=summary,
        stage_rows=evaluation.stage_rows,
        generated_figures=generated_figures,
        skipped_figures=skipped_figures,
    )
    write_real_manifest(
        output_dir / "run_manifest_real.json",
        run_id=run_id,
        waveform_path=waveform_path,
        internal_waveform_path=internal_path_for_manifest,
        thresholds={
            "spec_path": str(spec_path) if spec_path else None,
            "high_threshold": config.high_threshold,
            "low_threshold": config.low_threshold,
            "target_pulse_width": config.target_pulse_width,
            "pulse_width_tolerance": config.pulse_width_tolerance,
            "max_overlap_ratio": config.max_overlap_ratio,
            "max_ripple_v": config.max_ripple_v,
            "max_voltage_loss_v": config.max_voltage_loss_v,
            "max_delay_std": config.max_delay_std,
            "min_voh_margin_v": config.min_voh_margin_v,
            "target_refresh_hz": config.target_refresh_hz,
            "frame_hold_time": summary.get("frame_hold_time"),
            "cascade": cascade,
            "resolved_output_node_count": len(output_nodes),
            "selected_center_ratio": config.selected_center_ratio,
            "edge_buffer_ratio": config.edge_buffer_ratio,
            "min_pulse_width": config.min_pulse_width,
            "false_trigger_min_duration": config.false_trigger_min_duration,
        },
    )
    return summary


def build_output_nodes(spec: dict) -> list[str]:
    cascade = spec.get("cascade", {})
    stage_count = int(cascade.get("stage_count", 720))
    pattern = str(cascade.get("output_node_pattern", "o{index}"))
    return [pattern.format(index=index) for index in range(1, stage_count + 1)]


def resolve_output_nodes(frame: pd.DataFrame, spec: dict) -> tuple[list[str], str]:
    configured = build_output_nodes(spec)
    available = set(str(column) for column in frame.columns)
    if all(node in available for node in configured):
        return configured, f"按配置使用 {len(configured)} 个输出节点。"
    detected = sorted(
        [column for column in available if column.startswith("o") and column[1:].isdigit()],
        key=lambda name: int(name[1:]),
    )
    if not detected:
        missing = ", ".join(configured[:5])
        raise ValueError(f"Waveform file does not contain configured output nodes such as: {missing}")
    return detected, f"配置要求 {len(configured)} 个输出节点，但当前 CSV 只有 {len(detected)} 个可识别输出节点，已按当前 CSV 兼容评价。"


def sample_output_nodes(output_nodes: list[str], sample_indices: list[int]) -> list[str]:
    by_stage = {index + 1: node for index, node in enumerate(output_nodes)}
    selected = [by_stage[index] for index in sample_indices if index in by_stage]
    if selected:
        return selected
    if len(output_nodes) <= 16:
        return output_nodes
    step = max(1, len(output_nodes) // 12)
    sampled = output_nodes[::step]
    if output_nodes[-1] not in sampled:
        sampled.append(output_nodes[-1])
    return sampled
