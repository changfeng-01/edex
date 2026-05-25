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

    _add_hard_constraint_recommendations(recommendations, score, summary, data_source, engineering_validity)
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

    _add_topology_profile_recommendations(recommendations, score, data_source, engineering_validity)

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


def _add_topology_profile_recommendations(
    recommendations: list[dict],
    score: dict,
    data_source: str,
    engineering_validity: str,
) -> None:
    profile = str(score.get("topology_profile", "default"))
    penalties = score.get("analysis_metric_penalties", {}) if isinstance(score, dict) else {}
    if not isinstance(penalties, dict) or profile == "default":
        return
    for metric, penalty in penalties.items():
        if not _active_penalty(penalty):
            continue
        recommendation = _profile_recommendation(profile, str(metric), penalty, data_source, engineering_validity)
        if recommendation is not None:
            recommendations.append(recommendation)


def _add_hard_constraint_recommendations(
    recommendations: list[dict],
    score: dict,
    summary: dict,
    data_source: str,
    engineering_validity: str,
) -> None:
    failed = _failed_hard_constraints(score, summary)
    if "All_pulses_exist" in failed:
        recommendations.append(
            _item(
                "missing_pulse_recovery_review",
                "high",
                "All_pulses_exist",
                failed["All_pulses_exist"].get("current_value", False),
                failed["All_pulses_exist"].get("threshold", True),
                "One or more expected output pulses were not detected in the simulation window; likely causes include insufficient drive strength, excessive load, threshold/window settings, or an output alias mismatch.",
                "For the next sweep, prioritize drive-strength and load changes, then re-check output-node mapping and pulse-detection windows before treating the score as circuit behavior.",
                True,
                "All_pulses_exist failed. Generate recovery candidates for drive strength, load, and detection-window review before advancing to higher-level optimization.",
                data_source,
                engineering_validity,
            )
        )
    if "Seq_pass" in failed:
        recommendations.append(
            _item(
                "sequence_order_recovery_review",
                "high",
                "Seq_pass",
                failed["Seq_pass"].get("current_value", False),
                failed["Seq_pass"].get("threshold", True),
                "The observed pulse sequence did not pass the configured order check; likely causes include stage delay imbalance, missing intermediate pulses, excessive loading, or threshold/window settings.",
                "For the next sweep, prioritize timing and drive/load candidates, and keep the result marked simulation_only until the waveform sequence is directly reviewed.",
                True,
                "Seq_pass failed. Generate next-run candidates for timing recovery and drive/load balance before using advanced optimizers.",
                data_source,
                engineering_validity,
            )
        )


def _failed_hard_constraints(score: dict, summary: dict) -> dict[str, dict]:
    failed: dict[str, dict] = {}
    hard_constraints = score.get("hard_constraints", {}) if isinstance(score, dict) else {}
    if isinstance(hard_constraints, dict):
        for metric, details in hard_constraints.items():
            if not isinstance(details, dict):
                continue
            if details.get("passed") is False:
                failed[str(metric)] = details
    failures = score.get("hard_constraint_failures", []) if isinstance(score, dict) else []
    if isinstance(failures, list):
        for reason in failures:
            text = str(reason)
            for metric in ["All_pulses_exist", "Seq_pass"]:
                if metric in text:
                    failed.setdefault(metric, {"current_value": False, "threshold": True, "reason": text})
    for metric in ["All_pulses_exist", "Seq_pass"]:
        if summary.get(metric) is False:
            failed.setdefault(metric, {"current_value": False, "threshold": True})
    return failed


def _profile_recommendation(
    profile: str,
    metric: str,
    penalty: dict,
    data_source: str,
    engineering_validity: str,
) -> dict | None:
    current = _number(penalty.get("current_value"))
    threshold = _number(penalty.get("threshold"))
    if profile == "ota":
        if metric in {"dc_gain_db", "bandwidth_3db_hz", "unity_gain_hz", "slew_rate_v_per_s"}:
            return _profile_item(
                profile,
                "ota_gain_bandwidth_review",
                "high" if metric == "dc_gain_db" else "medium",
                metric,
                current,
                threshold,
                "OTA profile metric is outside the configured simulation threshold; likely causes include device sizing, bias current, load capacitance, or compensation choices.",
                "Review input/output transistor sizing and bias first for gain, then load/compensation and slew limits for bandwidth-related misses.",
                True,
                f"{metric} is outside the OTA profile threshold; use this as a simulation-only tuning hint, not a silicon conclusion.",
                data_source,
                engineering_validity,
            )
        if metric == "static_power_w":
            return _profile_item(
                profile,
                "ota_power_bias_review",
                "high",
                metric,
                current,
                threshold,
                "Static power is above the OTA profile threshold; bias current or always-on branches may be too large for this sweep point.",
                "Review bias source values and transistor operating points before widening devices further.",
                False,
                "OTA static power exceeds the configured simulation threshold; bias should be checked before the next sweep.",
                data_source,
                engineering_validity,
            )
    if profile == "comparator":
        if metric in {"switching_threshold_v", "hysteresis_proxy_v"}:
            return _profile_item(
                profile,
                "comparator_dc_sweep_review",
                "medium",
                metric,
                current,
                threshold,
                "Comparator DC behavior is outside the configured threshold; input pair balance, regeneration bias, or sweep direction may be involved.",
                "Review DC sweep setup and input/regeneration-stage sizing before trusting delay-only ranking.",
                True,
                f"{metric} suggests comparator switching behavior needs DC-sweep review.",
                data_source,
                engineering_validity,
            )
        if metric in {"output_swing_v", "static_power_w"}:
            return _profile_item(
                profile,
                "comparator_drive_power_review",
                "medium",
                metric,
                current,
                threshold,
                "Comparator output swing or power is outside the profile threshold; output load, latch drive, or bias values may dominate.",
                "Check output loading, regeneration strength, and bias values in the next sweep space.",
                False,
                f"{metric} is outside the comparator profile threshold.",
                data_source,
                engineering_validity,
            )
    if profile == "oscillator":
        if metric in {"frequency_hz", "period_std_s", "startup_time_s"}:
            return _profile_item(
                profile,
                "oscillator_frequency_stability_review",
                "medium",
                metric,
                current,
                threshold,
                "Oscillator frequency, startup, or period stability is outside the configured threshold; RC/load/bias or transient window length may dominate.",
                "Review RC/load/bias parameters and confirm the transient window excludes startup before narrowing the next sweep.",
                True,
                f"{metric} is outside the oscillator profile threshold.",
                data_source,
                engineering_validity,
            )
        if metric == "output_swing_v":
            return _profile_item(
                profile,
                "oscillator_amplitude_review",
                "medium",
                metric,
                current,
                threshold,
                "Oscillator amplitude is outside the configured threshold; load, bias, or insufficient startup time may be involved.",
                "Review load and bias values, then rerun with a long enough transient window.",
                True,
                "Oscillator output swing is below the configured simulation threshold.",
                data_source,
                engineering_validity,
            )
    return None


def _profile_item(profile: str, *args) -> dict:
    item = _item(*args)
    item["topology_profile"] = profile
    return item


def _attach_metric_penalty_context(recommendations: list[dict], score: dict) -> None:
    penalties = score.get("metric_penalties", {}) if isinstance(score, dict) else {}
    analysis_penalties = score.get("analysis_metric_penalties", {}) if isinstance(score, dict) else {}
    if not isinstance(penalties, dict):
        penalties = {}
    if not isinstance(analysis_penalties, dict):
        analysis_penalties = {}
    combined = {**analysis_penalties, **penalties}
    for recommendation in recommendations:
        penalty = combined.get(recommendation.get("trigger_metric"))
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


def _active_penalty(penalty: object) -> bool:
    if not isinstance(penalty, dict):
        return False
    severity = str(penalty.get("severity", "")).lower()
    if severity in {"fail", "critical"}:
        return True
    score = _number(penalty.get("score"))
    return score is not None and score < 100.0
