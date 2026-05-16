from __future__ import annotations

import math
import numpy as np

from goa_eval.models.design import DesignVersion
from goa_eval.models.metric import MetricResult


def compute_metric_results(
    design: DesignVersion,
    features: dict,
    waveform_source: str,
    engineering_validity: str,
    thresholds: dict,
) -> list[MetricResult]:
    nodes = features["nodes"]
    chain = design.cascade_chain or sorted(nodes.keys())
    results: list[MetricResult] = []

    trises = [nodes[node]["trise"] for node in chain if node in nodes and nodes[node]["trise"] is not None]
    seq_pass = len(trises) == len(chain) and all(a < b for a, b in zip(trises, trises[1:]))
    results.append(_result(design.name, "逐级扫描顺序", "Seq", "o1~o8", seq_pass, None, seq_pass, "hard", waveform_source, engineering_validity))

    for node in chain:
        if node not in nodes:
            continue
        item = nodes[node]
        results.extend(
            [
                _result(design.name, "有效脉冲存在性", "PulseExist_i", node, item["PulseExist"], None, item["PulseExist"], "hard", waveform_source, engineering_validity),
                _result(design.name, "误触发", "FalseTrigger_i", node, item["FalseTrigger"], None, not item["FalseTrigger"], "hard", waveform_source, engineering_validity),
                _result(design.name, "合法扫描脉冲数量", "legitimate_pulse_count", node, item.get("legitimate_pulse_count"), "count", None, "diagnosis", waveform_source, engineering_validity),
                _result(design.name, "第一轮扫描窗口", "first_scan_window", node, _format_window(item.get("first_scan_window")), "s", None, "diagnosis", waveform_source, engineering_validity),
                _result(design.name, "重复扫描窗口", "repeated_scan_windows", node, _format_windows(item.get("repeated_scan_windows", [])), "s", None, "diagnosis", waveform_source, engineering_validity),
                _result(design.name, "真实误触发数量", "true_false_trigger_count", node, item.get("true_false_trigger_count"), "count", item.get("true_false_trigger_count") == 0, "hard", waveform_source, engineering_validity),
                _result(design.name, "输出高电平", "VOH_i", node, item["VOH"], "V", None, "quality", waveform_source, engineering_validity),
                _result(design.name, "输出低电平", "VOL_i", node, item["VOL"], "V", None, "quality", waveform_source, engineering_validity),
                _result(design.name, "脉冲宽度", "Twidth_i", node, item["Twidth"], "s", None, "quality", waveform_source, engineering_validity),
                _result(design.name, "上升时间", "tr_i", node, item["tr"], "s", None, "diagnosis", waveform_source, engineering_validity),
                _result(design.name, "下降时间", "tf_i", node, item["tf"], "s", None, "diagnosis", waveform_source, engineering_validity),
                _result(design.name, "非选通纹波", "Ripple_i", node, item["Ripple"], "V", None, "diagnosis", waveform_source, engineering_validity),
            ]
        )

    for pair, value in features["overlaps"].items():
        results.append(_result(design.name, "相邻级重叠", "Toverlap_i", pair, value, "s", value <= 0.0, "hard / quality", waveform_source, engineering_validity))

    delays = []
    for left, right in zip(chain, chain[1:]):
        if left in nodes and right in nodes and nodes[left]["trise"] is not None and nodes[right]["trise"] is not None:
            delay = nodes[right]["trise"] - nodes[left]["trise"]
            delays.append(delay)
            results.append(_result(design.name, "传播延迟", "tpd_i", f"{left}->{right}", delay, "s", None, "quality", waveform_source, engineering_validity))

    voh_values = [_finite(nodes[node]["VOH"]) for node in chain if node in nodes]
    vol_values = [_finite(nodes[node]["VOL"]) for node in chain if node in nodes]
    ripple_values = [_finite(nodes[node]["Ripple"]) for node in chain if node in nodes]
    voh_values = [value for value in voh_values if value is not None]
    vol_values = [value for value in vol_values if value is not None]
    ripple_values = [value for value in ripple_values if value is not None]

    results.extend(
        [
            _result(design.name, "最弱级高电平", "VOH_min", "o1~o8", min(voh_values) if voh_values else None, "V", None, "ranking", waveform_source, engineering_validity),
            _result(design.name, "最大非选通风险", "Voff_max", "o1~o8", max(vol_values) if vol_values else None, "V", None, "ranking", waveform_source, engineering_validity),
            _result(design.name, "延迟离散度", "sigma_pd", "o1~o8", float(np.std(delays)) if delays else None, "s", None, "ranking", waveform_source, engineering_validity),
            _result(design.name, "高电平离散度", "sigma_VOH", "o1~o8", float(np.std(voh_values)) if voh_values else None, "V", None, "ranking", waveform_source, engineering_validity),
            _result(design.name, "设计代价", "Cost", "netlist", _proxy_cost(design, thresholds), "proxy", None, "ranking", waveform_source, engineering_validity, "proxy cost only, not manufacturing cost"),
        ]
    )
    return results


def _proxy_cost(design: DesignVersion, thresholds: dict) -> float:
    cost_cfg = thresholds.get("cost", {})
    alpha_w = float(cost_cfg.get("alpha_W", 1.0))
    alpha_c = float(cost_cfg.get("alpha_C", 1e6))
    w_sum = sum(device.params_si.get("W", 0.0) for device in design.devices if device.kind == "mos")
    c_sum = sum(device.params_si.get("C", 0.0) for device in design.devices if device.kind == "capacitor")
    return alpha_w * w_sum + alpha_c * c_sum


def _finite(value):
    if value is None:
        return None
    try:
        if math.isnan(value):
            return None
    except TypeError:
        pass
    return value


def _result(version, name, symbol, obj, value, unit, passed, metric_type, source, validity, notes=""):
    return MetricResult(version, name, symbol, obj, value, unit, passed, metric_type, source, validity, notes)


def _format_window(window) -> str:
    if not window:
        return ""
    start, end = window
    return f"{start:.12g}~{end:.12g}"


def _format_windows(windows) -> str:
    return "; ".join(_format_window(window) for window in windows)
