from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


def build_recommendations(summary: dict, score: dict | None = None, metrics: pd.DataFrame | None = None) -> list[dict]:
    score = score or {}
    metrics = metrics if metrics is not None else pd.DataFrame()
    data_source = str(summary.get("data_source", "real_simulation_csv"))
    engineering_validity = str(summary.get("engineering_validity", "simulation_only"))
    recommendations: list[dict] = []

    if _gt(summary.get("Max_overlap_ratio"), summary.get("max_overlap_ratio_limit", summary.get("max_overlap_ratio"))):
        recommendations.append(
            _item(
                "overlap_timing_review",
                "high",
                "Max_overlap_ratio",
                _number(summary.get("Max_overlap_ratio")),
                _number(summary.get("max_overlap_ratio_limit", summary.get("max_overlap_ratio"))),
                "相邻级时序过近、下降沿速度不足、时钟相位重叠，或 overlap 统计窗口口径仍需复核。",
                "检查相邻级时序，缩短导通窗口，增加级间间隔，并复核 overlap 是否已按端点区间积分统计。",
                True,
                "Max_overlap_ratio 超过当前阈值。建议检查相邻级时序，缩短导通窗口，增加级间间隔，并复核 overlap 是否已按端点区间积分统计。",
                data_source,
                engineering_validity,
            )
        )

    if _gt(summary.get("Max_ripple"), summary.get("max_ripple_v_limit", summary.get("max_ripple_v"))):
        recommendations.append(
            _item(
                "ripple_hold_window_review",
                "high",
                "Max_ripple",
                _number(summary.get("Max_ripple")),
                _number(summary.get("max_ripple_v_limit", summary.get("max_ripple_v"))),
                "hold window 可能包含边沿、时钟馈通偏大、保持电容不足或泄漏路径偏强。",
                "先重定义 hold window 并排除上升沿/下降沿；若排除边沿后仍超限，再增大保持电容或检查泄漏路径。",
                True,
                "Max_ripple 超过当前阈值。建议先重定义 hold window 并排除上升沿/下降沿；若排除边沿后仍超限，再考虑增大保持电容或检查泄漏路径。",
                data_source,
                engineering_validity,
            )
        )

    delay_mean = _number(summary.get("Delay_mean"))
    target = _number(summary.get("target_pulse_width"))
    tolerance = _number(summary.get("pulse_width_tolerance", target * 0.2 if target else None))
    if delay_mean is not None and target is not None and tolerance is not None and abs(delay_mean - target) > tolerance:
        recommendations.append(
            _item(
                "delay_drive_load_review",
                "medium",
                "Delay_mean",
                delay_mean,
                target,
                "驱动能力、负载电容或开关尺寸导致级间传播节拍偏离目标。",
                "调整驱动能力、负载电容或开关尺寸，并用批量评价确认调整方向。",
                False,
                "Delay_mean 与目标节拍存在偏离。建议检查驱动能力、负载电容和开关尺寸，并用批量评价确认调整方向。",
                data_source,
                engineering_validity,
            )
        )

    false_trigger_count = int(summary.get("FalseTriggerCount", summary.get("False_trigger_count", 0)) or 0)
    if false_trigger_count > 0:
        recommendations.append(
            _item(
                "false_trigger_noise_review",
                "high",
                "FalseTriggerCount",
                float(false_trigger_count),
                0.0,
                "阈值设置不合适、噪声尖峰、非选通节点异常高电平或复位/下拉控制不足。",
                "检查阈值设置、噪声尖峰，以及非选通节点异常高电平。",
                True,
                "False_trigger_count 大于 0。建议检查阈值设置、噪声尖峰，以及非选通节点异常高电平。",
                data_source,
                engineering_validity,
            )
        )

    if summary.get("LowFreqStable") == "not_evaluable_with_current_waveform":
        recommendations.append(
            _item(
                "low_frequency_waveform_extension",
                "medium",
                "LowFreqStable",
                summary.get("LowFreqStable"),
                "full_frame_waveform",
                "当前仿真时长短于目标刷新周期，不能证明低频保持稳定性。",
                "增加至少一个完整帧周期或更长保持时间的仿真波形，再判断低频保持稳定性。",
                True,
                "LowFreqStable 当前不可评价。建议增加至少一个完整帧周期或更长保持时间的仿真波形，再判断低频保持稳定性。",
                data_source,
                engineering_validity,
            )
        )

    if not recommendations:
        recommendations.append(
            _item(
                "no_rule_failure_detected",
                "info",
                "none",
                None,
                None,
                "当前规则推荐器未发现明确超限项。",
                "继续补充 PVT、Monte Carlo、负载变化和功耗维度后再做参数推荐。",
                False,
                "当前规则推荐器未发现明确超限项。建议继续补充 PVT、Monte Carlo、负载变化和功耗维度后再做参数推荐。",
                data_source,
                engineering_validity,
            )
        )
    _attach_metric_penalty_context(recommendations, score)
    return recommendations


def write_recommendations_markdown(
    *,
    summary_path: Path,
    score_path: Path | None,
    metrics_path: Path | None,
    output_path: Path,
) -> list[dict]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    score = json.loads(score_path.read_text(encoding="utf-8")) if score_path and score_path.exists() else {}
    metrics = pd.read_csv(metrics_path) if metrics_path and metrics_path.exists() else pd.DataFrame()
    recommendations = build_recommendations(summary, score, metrics)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CircuitPilot 参数建议报告",
        "",
        f"- schema_version: `{SCHEMA_VERSION}`",
        f"- result_version: `{RESULT_VERSION}`",
        f"- data_source: `{summary.get('data_source', 'real_simulation_csv')}`",
        f"- engineering_validity: `{summary.get('engineering_validity', 'simulation_only')}`",
        "",
        "本报告仅基于仿真 CSV 的结构化指标生成，属于 simulation_only 分析，不是实物测试结果，也不代表可直接替代人工优化决策。",
        "",
        "## Recommendations",
        "",
    ]
    for item in recommendations:
        lines.extend(
            [
                f"### {item['recommendation_id']}",
                "",
                f"- severity: `{item['severity']}`",
                f"- trigger_metric: `{item['trigger_metric']}`",
                f"- current_value: `{item['current_value']}`",
                f"- threshold: `{item['threshold']}`",
                f"- possible_physical_causes: {item['possible_physical_causes']}",
                f"- next_tuning_actions: {item['next_tuning_actions']}",
                f"- needs_metric_review: `{item['needs_metric_review']}`",
                f"- message: {item['message']}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return recommendations


def _item(
    recommendation_id: str,
    severity: str,
    trigger_metric: str,
    current_value,
    threshold,
    possible_physical_causes: str,
    next_tuning_actions: str,
    needs_metric_review: bool,
    message: str,
    data_source: str,
    engineering_validity: str,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "recommendation_id": recommendation_id,
        "severity": severity,
        "trigger_metric": trigger_metric,
        "current_value": current_value,
        "threshold": threshold,
        "possible_physical_causes": possible_physical_causes,
        "next_tuning_actions": next_tuning_actions,
        "needs_metric_review": bool(needs_metric_review),
        "message": message,
        "data_source": data_source,
        "engineering_validity": engineering_validity,
    }


def _attach_metric_penalty_context(recommendations: list[dict], score: dict) -> None:
    penalties = score.get("metric_penalties", {}) if isinstance(score, dict) else {}
    if not isinstance(penalties, dict):
        return
    for recommendation in recommendations:
        penalty = penalties.get(recommendation.get("trigger_metric"))
        if not isinstance(penalty, dict):
            continue
        recommendation["metric_penalty_severity"] = penalty.get("severity")
        recommendation["metric_penalty_score"] = _number(penalty.get("score"))
        recommendation["metric_penalty_deduction"] = _number(penalty.get("deduction"))


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gt(value, limit) -> bool:
    value = _number(value)
    limit = _number(limit)
    return value is not None and limit is not None and value > limit
