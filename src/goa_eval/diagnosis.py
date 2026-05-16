from __future__ import annotations

from pathlib import Path


def build_diagnosis(summary: dict, stage_rows: list[dict], score_summary: dict) -> list[str]:
    suggestions: list[str] = []
    if _margin_low(summary):
        suggestions.append("VOH_min 偏低：建议检查 PU 尺寸、自举电容、CLK 高电平和负载条件。")
    if _positive(summary.get("VOL_max_all")):
        suggestions.append("VOL_max_all 偏高：建议检查 PD 尺寸、reset 控制和非选通保持路径。")
    if _exceeds(summary, "Max_ripple", "max_ripple_v_limit"):
        suggestions.append("Max_ripple 偏大：建议检查时钟馈通、寄生耦合和非选通保持能力。")
    if _exceeds(summary, "Max_overlap_ratio", "max_overlap_ratio_limit"):
        suggestions.append("Max_overlap_ratio 偏大：建议检查相邻级时序、下降沿速度和时钟相位。")
    if _exceeds(summary, "Delay_std", "max_delay_std_limit"):
        suggestions.append("Delay_std 偏大：建议检查级间负载一致性、器件尺寸一致性和级联驱动能力。")
    tolerance = summary.get("pulse_width_tolerance")
    width_mean = summary.get("Width_mean")
    target = summary.get("target_pulse_width")
    width_std = summary.get("Width_std")
    if _abs_exceeds(width_mean, target, tolerance) or _greater(width_std, tolerance):
        suggestions.append("脉宽偏离或 Width_std 偏大：建议检查时钟脉宽、级间耦合和边沿检测阈值。")
    if score_summary.get("hard_constraint_failures"):
        suggestions.append("Hard constraints 未全部通过：建议优先处理 score_summary.json 中列出的失败原因，再进行参数优化。")
    if not suggestions:
        suggestions.append("当前规则未发现明确异常；后续建议结合 PVT、Monte Carlo、负载变化和功耗结果继续验证。")
    return suggestions


def write_diagnosis_report(path: Path, *, summary: dict, stage_rows: list[dict], score_summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suggestions = build_diagnosis(summary, stage_rows, score_summary)
    lines = [
        "# 8T1C / GOA 规则化诊断与优化建议",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- 本诊断仅基于仿真 CSV 指标，不是实物测试结论。",
        "",
        "## 关键状态",
        "",
        f"- Overall_status：`{summary.get('Overall_status')}`",
        f"- hard_constraint_passed：`{score_summary.get('hard_constraint_passed')}`",
        f"- overall_score：`{score_summary.get('overall_score')}`",
        "",
        "## 优化建议",
        "",
    ]
    lines.extend(f"- {item}" for item in suggestions)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _margin_low(summary: dict) -> bool:
    voh = summary.get("VOH_min")
    threshold = summary.get("high_threshold")
    margin = summary.get("min_voh_margin_v")
    return voh is not None and threshold is not None and margin is not None and float(voh) - float(threshold) < float(margin)


def _exceeds(summary: dict, metric: str, limit: str) -> bool:
    return _greater(summary.get(metric), summary.get(limit))


def _greater(value, limit) -> bool:
    return value is not None and limit is not None and float(value) > float(limit)


def _abs_exceeds(value, target, tolerance) -> bool:
    return value is not None and target is not None and tolerance is not None and abs(float(value) - float(target)) > float(tolerance)


def _positive(value) -> bool:
    return value is not None and float(value) > 0.0
