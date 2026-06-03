from __future__ import annotations

from pathlib import Path
import datetime as dt
import json
import subprocess
import sys

import pandas as pd

from goa_eval.io_utils import sha256_file, write_json
from goa_eval.evidence import default_external_csv_evidence, with_evidence
from goa_eval.schemas import OPTIMIZATION_DATASET_COLUMNS, REAL_METRICS_COLUMNS, RESULT_VERSION, SCHEMA_VERSION


def write_real_summary(
    path: Path,
    *,
    waveform_path: Path,
    high_threshold: float,
    low_threshold: float,
    evaluation,
    run_id: str | None = None,
    run_timestamp: str | None = None,
    evidence_metadata: dict | None = None,
) -> dict:
    summary = with_evidence({
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "input_file": str(waveform_path),
        "high_threshold": high_threshold,
        "low_threshold": low_threshold,
        **evaluation.summary,
        "stage_count": evaluation.summary["stage_count"],
        "notes": evaluation.notes,
    }, evidence_metadata)
    write_json(path, summary)
    return summary


def write_real_metrics_csv(path: Path, stage_rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(stage_rows)
    if len(frame):
        frame.insert(0, "result_version", RESULT_VERSION)
        frame.insert(0, "schema_version", SCHEMA_VERSION)
    frame = frame.reindex(columns=REAL_METRICS_COLUMNS)
    for column in ["legal_windows", "primary_window", "repeated_windows", "false_trigger_windows"]:
        if column in frame:
            frame[column] = frame[column].map(_json_cell)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def write_real_report(
    path: Path,
    *,
    summary: dict,
    stage_rows: list[dict],
    generated_figures: list[str],
    skipped_figures: list[str],
    analysis_metrics: dict | None = None,
    score_summary: dict | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table_columns = [
        "stage",
        "node",
        "PulseExist",
        "LegalPulseCount",
        "VOH_mean",
        "VOH_max",
        "VHoldEnd",
        "VoltageLoss",
        "VoltageLossRatio",
        "VOL_max",
        "PulseWidth",
        "Delay",
        "Ripple",
        "FalseTrigger",
        "FalseTriggerCount",
        "Overlap",
        "OverlapRatio",
    ]
    large_cascade = int(summary.get("stage_count") or 0) > 32
    detail_table = (
        "完整逐级明细已写入 `real_metrics.csv`；Markdown 报告只展示摘要，避免 720 级数据淹没关键结论。"
        if large_cascade
        else _markdown_table(pd.DataFrame(stage_rows).reindex(columns=table_columns))
    )
    block_table = _markdown_table(pd.DataFrame(summary.get("block_summary", [])))
    figures_text = "\n".join(f"- `{figure}`" for figure in generated_figures) or "- 无"
    skipped_text = "\n".join(f"- {item}" for item in skipped_figures) or "- 无"
    goa_benchmark_section = _goa_benchmark_section(analysis_metrics or {}, score_summary or {})
    lines = [
        "# 8T1C / GOA 大规模级联摘要报告",
        "",
        "## 1. 数据来源说明",
        "",
        f"- 外部波形文件：`{summary['input_file']}`",
        "- 数据来源标记：`real_simulation_csv`",
        "- 工程有效性标记：`simulation_only`",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- 图像时间轴统一换算为 μs；CSV 原始时间值仍保留在指标 CSV/JSON 中。",
        "- 电压单位：默认按 V 处理。",
        f"- 评价级数：`{summary.get('stage_count')}`",
        "- 导师汇报口径：框架支持逐级完整数据、分段摘要、退化趋势和最差级定位。",
        "",
        "## 2. 阈值说明",
        "",
        f"- high_threshold = `{summary['high_threshold']}` V",
        f"- low_threshold = `{summary['low_threshold']}` V",
        f"- max_voltage_loss_v_limit = `{summary.get('max_voltage_loss_v_limit')}` V",
        f"- target_refresh_hz = `{summary.get('target_refresh_hz')}` Hz",
        f"- frame_hold_time = `{summary.get('frame_hold_time')}` s",
        "- 当前阈值是初步工程分析阈值，需要后续由电路规格进一步确认。",
        "",
        "## 3. 关键逐级指标",
        "",
        detail_table,
        "",
        "## 4. 级联扫描顺序判断",
        "",
        f"- Seq_pass：`{summary['Seq_pass']}`",
        f"- All_pulses_exist：`{summary['All_pulses_exist']}`",
        f"- False_trigger_count：`{summary['False_trigger_count']}`",
        f"- FalseTriggerCount：`{summary['FalseTriggerCount']}`",
        f"- Overall_status：`{summary['Overall_status']}`",
        f"- first_failed_stage：`{summary.get('first_failed_stage')}`",
        f"- worst_stage：`{summary.get('worst_stage')}`",
        "",
        "## 5. 波形质量与一致性初步分析",
        "",
        f"- VOH_min：`{summary['VOH_min']}`",
        f"- VOH_std：`{summary['VOH_std']}`",
        f"- VOL_max_all：`{summary['VOL_max_all']}`",
        f"- Delay_mean：`{summary['Delay_mean']}`",
        f"- Delay_std：`{summary['Delay_std']}`",
        f"- Width_mean：`{summary['Width_mean']}`",
        f"- Width_std：`{summary['Width_std']}`",
        f"- Max_ripple：`{summary['Max_ripple']}`",
        f"- Ripple_p95：`{summary.get('Ripple_p95')}`",
        f"- Max_voltage_loss：`{summary.get('Max_voltage_loss')}`",
        f"- Max_voltage_loss_ratio：`{summary.get('Max_voltage_loss_ratio')}`",
        f"- VoltageLoss_p95：`{summary.get('VoltageLoss_p95')}`",
        f"- Max_overlap：`{summary['Max_overlap']}`",
        f"- Max_overlap_ratio：`{summary['Max_overlap_ratio']}`",
        f"- VOH_p1 / VOH_p5 / VOH_p50：`{summary.get('VOH_p1')}` / `{summary.get('VOH_p5')}` / `{summary.get('VOH_p50')}`",
        f"- VOH_slope：`{summary.get('VOH_slope')}`",
        f"- VoltageLoss_slope：`{summary.get('VoltageLoss_slope')}`",
        f"- Delay_slope：`{summary.get('Delay_slope')}`",
        f"- LowFreqStable：`{summary.get('LowFreqStable')}`",
        f"- 低频稳定性说明：{summary.get('low_frequency_evaluation_note')}",
        "",
        "## 6. 分段摘要",
        "",
        block_table,
        "",
        goa_benchmark_section,
        "",
        "## 8. 内部节点 pu / pd / output 机理说明",
        "",
        "PU 节点主要反映本级上拉控制状态。PU 被有效拉高后，通常对应输出节点进入拉高或保持高电平的能力增强；若 PU 上升慢或峰值不足，可能导致输出上升沿变慢或 VOH 降低。",
        "",
        "PD 节点主要反映下拉/复位控制状态。PD 有效时，输出更容易被复位或保持在低电平；若 PD 在非选通期控制不足，可能造成输出残留、纹波偏大或低电平风险升高。",
        "",
        "本报告优先绘制 xs4 的 PU/PD/output 叠加图，并在内部节点完整时绘制 xs1/xs4/xs8 对比图，用于观察前级、中级、后级是否存在明显退化。",
        "",
        "## 9. 图像输出",
        "",
        figures_text,
        "",
        "图像物理意义说明：",
        "",
        "- `sample_outputs_overview.png`：抽样输出总览，用于快速确认大规模级联中的代表级波形。",
        "- `sample_outputs_stacked.png`：抽样输出堆叠图，用于观察代表级上升沿顺序、扫描节拍和级间时序关系。",
        "- `voh_trend.png`：VOH 随级数变化趋势，用于观察级联后高电平是否累积退化。",
        "- `voltage_loss_trend.png`：电压损失随级数变化趋势，用于观察保持能力是否随级数恶化。",
        "- `delay_trend.png`：级间延迟随级数变化趋势，用于观察传播延迟累积变化。",
        "- `ripple_trend.png`：纹波随级数变化趋势，用于观察非选通稳定性风险。",
        "- `block_stability_heatmap.png`：按分段统计的稳定性风险热力图，用于快速定位风险段。",
        "- `o1_o8_overview.png`：小规模级联输出总览，仅在级数较少时生成。",
        "- `o1_o8_stacked.png`：小规模级联输出堆叠图，仅在级数较少时生成。",
        "- `voh_bar.png`：每级 VOH 平均值柱状图，红色虚线为 high_threshold，用于判断输出高电平裕量。",
        "- `pulse_width_bar.png`：每级脉冲宽度对比，红色虚线为目标脉宽，用于判断扫描脉宽一致性。",
        "- `delay_bar.png`：Delay_i 柱状图，显示 o1→o2 到 o7→o8 的传播延迟，用于判断级间时序一致性。",
        "- `ripple_bar.png`：Ripple 柱状图，用于观察非选通纹波。",
        "- `voltage_loss_bar.png`：VoltageLoss 柱状图，用于观察写入后到保持窗口末端的电压损失。",
        "- `vol_ripple_bar.png`：VOL_max / Ripple 柱状图，用于观察非选通低电平风险和非选通纹波。",
        "- `overlap_ratio_bar.png`：OverlapRatio 柱状图，用于观察相邻级选通重叠比例。",
        "- `internal_xs4_pu_pd_o4.png`：第 4 级 PU/PD/output 叠加图，用于解释内部上拉、复位/保持低电平和输出响应关系。",
        "- `internal_xs1_xs4_xs8_compare.png`：前级、中级、后级内部节点对比图，用于观察级联后是否出现内部节点退化。",
        "",
        "跳过的内部节点图：",
        "",
        skipped_text,
        "",
        "## 10. 明确声明",
        "",
        "- 本结果来自电路仿真 CSV，仅代表 simulation-only 分析。",
        "- 本结果不是实物测试结果，不能视为实物测试结论。",
        "- 当前阈值为初步阈值，需要由电路规格确认。",
        "- 若 `LowFreqStable = not_evaluable_with_current_waveform`，表示当前波形时长不足以覆盖目标刷新周期，不能据此宣称低 Hz 显示已经稳定。",
        "- 后续仍需 PVT、Monte Carlo、负载变化和功耗分析。",
        "- `PASS_BASIC_SIMULATION_CHECK` 只表示仿真 CSV 的基础检查通过，不代表真实产品通过。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_real_manifest(
    path: Path,
    *,
    run_id: str,
    waveform_path: Path,
    internal_waveform_path: Path | None,
    thresholds: dict,
    evidence_metadata: dict | None = None,
) -> dict:
    inputs = [waveform_path]
    if internal_waveform_path is not None and internal_waveform_path.exists():
        inputs.append(internal_waveform_path)
    manifest = with_evidence({
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "run_id": run_id,
        "run_time": dt.datetime.now().isoformat(timespec="seconds"),
        "command": "python -m goa_eval.cli " + " ".join(sys.argv[1:]),
        "input_files": [str(path) for path in inputs],
        "input_file_hashes": {str(path): {"sha256": sha256_file(path), "size_bytes": path.stat().st_size} for path in inputs},
        "thresholds": thresholds,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "code_version_or_git_commit": _git_commit(),
    }, evidence_metadata)
    write_json(path, manifest)
    return manifest


def write_optimization_dataset(
    path: Path,
    *,
    run_id: str,
    run_timestamp: str,
    summary: dict,
    score_summary: dict,
    design_name: str = "unknown",
    parameter_set_id: str = "unknown",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "design_name": design_name,
        "parameter_set_id": parameter_set_id,
        "W_PU": None,
        "W_PD": None,
        "C_boot": None,
        "C_load": None,
        "V_CLKH": None,
        "capacitance": None,
        "drive_resistance": None,
        "transistor_width": None,
        "transistor_length": None,
        "vdd": None,
        "load_cap": None,
        "temp": None,
        "corner": None,
        **{key: summary.get(key) for key in _summary_metric_columns()},
        "hard_constraint_passed": score_summary.get("hard_constraint_passed"),
        "overall_status": summary.get("Overall_status"),
        "overall_score": score_summary.get("overall_score"),
        "metric_provenance": json.dumps(score_summary.get("metric_provenance", {}), ensure_ascii=False, sort_keys=True),
        "data_source": summary.get("data_source", "real_simulation_csv"),
        "engineering_validity": summary.get("engineering_validity", "simulation_only"),
    }
    frame = pd.DataFrame([row]).reindex(columns=OPTIMIZATION_DATASET_COLUMNS)
    frame.to_csv(path, mode="a", header=not path.exists(), index=False, encoding="utf-8-sig")


def _git_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path.cwd(), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _summary_metric_columns() -> list[str]:
    return [
        "VOH_min",
        "VOH_std",
        "VOL_max_all",
        "Width_mean",
        "Width_std",
        "Delay_mean",
        "Delay_std",
        "Max_ripple",
        "Max_voltage_loss",
        "Max_voltage_loss_ratio",
        "VoltageLoss_p95",
        "VOH_p1",
        "VOH_p5",
        "VOH_p50",
        "Ripple_p95",
        "Delay_p95",
        "VOH_slope",
        "VoltageLoss_slope",
        "Delay_slope",
        "Max_overlap",
        "Max_overlap_ratio",
        "LowFreqStable",
        "worst_stage",
        "first_failed_stage",
        "Seq_pass",
        "All_pulses_exist",
        "FalseTriggerCount",
        "Overall_status",
    ]


def _json_cell(value) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for _, row in frame.iterrows():
        values = ["" if pd.isna(row[column]) else str(row[column]) for column in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _goa_benchmark_section(analysis_metrics: dict, score_summary: dict) -> str:
    metrics = analysis_metrics.get("goa_benchmark_metrics") if isinstance(analysis_metrics, dict) else None
    if not isinstance(metrics, dict):
        return "## 7. GOA 论文 benchmark 对比\n\n- 未启用 GOA benchmark profile。"
    rows = [
        {
            "metric": "FallTime",
            "current": metrics.get("fall_time_s"),
            "literature_reference": metrics.get("reference_tfall_s"),
            "physical_meaning": "下降时间越短，扫描线放电和驱动能力越强。",
        },
        {
            "metric": "RiseTime",
            "current": metrics.get("rise_time_s"),
            "literature_reference": metrics.get("reference_trise_s"),
            "physical_meaning": "上升时间反映输出充电速度和高电平建立能力。",
        },
        {
            "metric": "FalseTriggerCount",
            "current": metrics.get("false_trigger_count"),
            "literature_reference": 0,
            "physical_meaning": "误脉冲代表非目标行被错误选通，是功能级风险。",
        },
        {
            "metric": "Max_overlap_ratio",
            "current": metrics.get("max_overlap_ratio"),
            "literature_reference": "",
            "physical_meaning": "相邻级合法窗口重叠越大，级间时序串扰风险越高。",
        },
        {
            "metric": "Power / Area / DeltaVTH",
            "current": "not_evaluable",
            "literature_reference": "P=0.10/0.04/0.23 W; DeltaVTH=+4/+3/+4 V",
            "physical_meaning": "当前 CSV 未提供功耗、版图代价或阈值漂移扫描，首版只列为缺失维度。",
        },
    ]
    not_evaluable = score_summary.get("not_evaluable_metrics", {}) if isinstance(score_summary, dict) else {}
    missing = ", ".join(
        sorted(
            str(metric)
            for metric in not_evaluable
            if metric
            in {
                "power_total_w",
                "power_static_w",
                "power_dynamic_w",
                "area_proxy",
                "width_proxy",
                "delta_vth_margin_v",
            }
        )
    ) or "无"
    grouped_rows = [
        {"dimension": "性能/速度", "available_metrics": "FallTime, RiseTime, Max_overlap_ratio", "not_evaluable_metrics": ""},
        {"dimension": "功耗/代价", "available_metrics": "", "not_evaluable_metrics": _missing_subset(not_evaluable, {"power_total_w", "power_static_w", "power_dynamic_w"})},
        {"dimension": "稳定性", "available_metrics": "FalseTriggerCount, Max_overlap_ratio", "not_evaluable_metrics": _missing_subset(not_evaluable, {"delta_vth_margin_v"})},
        {"dimension": "面积/复杂度", "available_metrics": "", "not_evaluable_metrics": _missing_subset(not_evaluable, {"area_proxy", "width_proxy"})},
    ]
    return "\n".join(
        [
            "## 7. GOA 论文 benchmark 对比",
            "",
            "- benchmark_scope：`literature_reference`",
            "- data_source = real_simulation_csv",
            "- engineering_validity = simulation_only",
            "- 论文中的 Proposed / Sharp-like / Samsung-like GOA 是文献基线，不是本仓库复现仿真结果。",
            "- 现有硬约束仍由当前配置判定；论文 8K 数值只作为 reference score 和物理解释口径。",
            f"- 论文参考负载：RL = `{metrics.get('reference_load_rl_ohm')}` ohm，CL = `{metrics.get('reference_load_cl_f')}` F。",
            f"- 当前不可评价维度：`{missing}`",
            "",
            _markdown_table(pd.DataFrame(rows)),
            "",
            "### 7.1 维度分组",
            "",
            _markdown_table(pd.DataFrame(grouped_rows)),
            "",
            "### 7.2 文献 baseline 归一化对比",
            "",
            _goa_baseline_comparison_table(metrics),
            "",
            "物理解释：下降时间代表 GOA 输出级下拉和扫描线放电能力；误脉冲代表错误选通风险，优先级高于单纯速度；overlap 代表相邻级时序窗口过近或波形窗口定义风险；功耗、面积和阈值漂移需要电源电流、器件参数或 PVT/漂移扫描证据，不能由当前输出 CSV 伪造。",
        ]
    )


def _missing_subset(not_evaluable: dict, names: set[str]) -> str:
    missing = sorted(str(name) for name in names if name in not_evaluable)
    return ", ".join(missing) if missing else "无"


def _goa_baseline_comparison_table(metrics: dict) -> str:
    comparisons = metrics.get("baseline_comparisons", {})
    if not isinstance(comparisons, dict) or not comparisons:
        return "- 未配置文献 baseline comparisons。"
    rows = []
    for baseline, payload in comparisons.items():
        metric_rows = payload.get("metrics", {}) if isinstance(payload, dict) else {}
        if not isinstance(metric_rows, dict):
            continue
        for metric_name, item in metric_rows.items():
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "baseline": baseline,
                    "structure": payload.get("structure", ""),
                    "metric": metric_name,
                    "current": item.get("current_value"),
                    "literature": item.get("baseline_value"),
                    "relative_improvement": item.get("relative_improvement"),
                    "status": item.get("status"),
                    "note": item.get("not_evaluable_reason", ""),
                }
            )
    if not rows:
        return "- 文献 baseline comparison 为空。"
    return _markdown_table(pd.DataFrame(rows))
