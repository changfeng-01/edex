# Metrics Specification

本文档定义 CircuitPilot 当前指标语义。所有指标均来自仿真 CSV，并保持：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

指标用于仿真结果筛查、参数对比和下一轮建议，不等同于实物测试结论。

## 单位约定

- 时间：内部和 CSV 指标默认使用秒 `s`。
- 配置文件中的 `*_us` 字段以微秒 `us` 表示，读取后转换为秒。
- 电压：默认使用伏特 `V`。
- 比例：使用无量纲 ratio，例如 `0.10` 表示 10%。
- 计数：使用整数 count。
- 布尔：使用 `True` / `False`。

## 配置阈值

默认阈值来自 `config/spec.yaml`。

| 配置字段 | 单位 | 用途 |
|---|---:|---|
| `high_threshold` | V | 判断输出节点是否达到高电平。 |
| `low_threshold` | V | 判断非选通期异常高电平或低电平风险。 |
| `target_pulse_width_us` | us | 目标扫描脉冲宽度。 |
| `pulse_width_tolerance_us` | us | 脉宽允许偏差。 |
| `max_overlap_ratio` | ratio | 相邻级合法脉冲最大允许重叠比例。 |
| `max_ripple_v` | V | 非选通窗口最大允许纹波。 |
| `max_voltage_loss_v` | V | 保持电压损失阈值。 |
| `max_delay_std_us` | us | 级间延迟标准差阈值。 |
| `min_voh_margin_v` | V | 高电平相对阈值的最小裕量。 |
| `target_refresh_hz` | Hz | 低频保持评价目标刷新率。 |

## 窗口术语

- `legal_windows`：持续时间达到 `min_pulse_width` 的高电平窗口。
- `primary_window`：第一个合法高电平窗口，作为主要评价窗口。
- `repeated_windows`：同一波形中后续合法高电平窗口。它们代表合法重复扫描，不计为误触发。
- `selected_window`：`primary_window` 中间区域，用于 VOH 和保持末端估计，避免边沿污染。
- `hold / non-selected window`：排除所有合法脉冲和边沿缓冲后的非选通区域。
- `edge buffer`：上升沿和下降沿附近的缓冲区，用于避免把边沿过渡误计为纹波或误触发。

## 逐级指标

| 字段 | 单位 | 定义 |
|---|---:|---|
| `stage` | count | 级序号，从 1 开始。 |
| `node` | text | 输出节点名，例如 `o1`。 |
| `PulseExist` | bool | 是否存在合法高电平脉冲。 |
| `LegalPulseCount` | count | 合法高电平窗口数量。 |
| `VOH_mean` | V | `selected_window` 内平均高电平。 |
| `VOH_max` | V | `selected_window` 内最高电平。 |
| `VHoldEnd` | V | `selected_window` 末端有限值。 |
| `VoltageLoss` | V | `max(0, VOH_max - VHoldEnd)`。 |
| `VoltageLossRatio` | ratio | `VoltageLoss / VOH_max`，当 `VOH_max` 为 0 或不可用时为空。 |
| `VOL_max` | V | hold / non-selected 窗口最大电压。 |
| `PulseWidth` | s | `primary_window.end - primary_window.start`。 |
| `Delay` | s | 当前级与相邻级上升阈值穿越时间差。 |
| `RiseTime` | s | 10% 到 90% 上升沿估计时间。 |
| `FallTime` | s | 90% 到 10% 下降沿估计时间。 |
| `Ripple` | V | hold / non-selected 窗口内 `max(signal) - min(signal)`。 |
| `FalseTrigger` | bool | 非选通区域是否存在异常高电平窗口。 |
| `FalseTriggerCount` | count | 排除所有合法脉冲和边沿缓冲后的异常高电平窗口数量。 |
| `Overlap` | s | 当前级与下一相邻级合法窗口的时间交集总和。 |
| `OverlapRatio` | ratio | `Overlap / min(left PulseWidth, right PulseWidth)`。 |
| `legal_windows` | JSON text | 合法窗口列表。 |
| `primary_window` | JSON text | 主窗口。 |
| `repeated_windows` | JSON text | 合法重复窗口列表。 |
| `false_trigger_windows` | JSON text | 误触发窗口列表。 |

`real_metrics.csv` 同时保留部分旧字段别名，例如 `pulse_exist`、`pulse_width`、`overlap_ratio` 等，用于兼容早期脚本。

## 摘要指标

`real_summary.json` 汇总整次评价，常用字段包括：

| 字段 | 单位 | 定义 |
|---|---:|---|
| `stage_count` | count | 本次实际评价的输出级数。 |
| `Seq_pass` | bool | 扫描顺序是否满足当前基础检查。 |
| `All_pulses_exist` | bool | 所有输出级是否都有合法脉冲。 |
| `FalseTriggerCount` | count | 全局误触发数量。 |
| `VOH_min` | V | 所有级 `VOH_mean` 或相关高电平统计中的最低值。 |
| `VOH_std` | V | 高电平离散程度。 |
| `VOL_max_all` | V | 全部级非选通窗口最大低电平风险值。 |
| `Width_mean` | s | 脉宽均值。 |
| `Width_std` | s | 脉宽标准差。 |
| `Delay_mean` | s | 级间延迟均值。 |
| `Delay_std` | s | 级间延迟标准差。 |
| `Max_ripple` | V | 所有级最大纹波。 |
| `Max_voltage_loss` | V | 所有级最大保持电压损失。 |
| `Max_voltage_loss_ratio` | ratio | 所有级最大保持电压损失比例。 |
| `Max_overlap` | s | 所有相邻级最大重叠时间。 |
| `Max_overlap_ratio` | ratio | 所有相邻级最大重叠比例。 |
| `LowFreqStable` | text/bool | 低频保持评价结果；波形时长不足时为 `not_evaluable_with_current_waveform`。 |
| `Overall_status` | text | 当前阈值下的总体状态。 |
| `worst_stage` | count/null | 风险最高的级序号。 |
| `first_failed_stage` | count/null | 第一个失败级序号。 |

## 大规模级联指标

当级数较大时，Markdown 报告不直接展开所有逐级明细，而使用摘要字段：

- `VOH_p1`、`VOH_p5`、`VOH_p50`：高电平分位数。
- `VoltageLoss_p95`：保持电压损失 95 分位。
- `Ripple_p95`：纹波 95 分位。
- `Delay_p95`：延迟 95 分位。
- `VOH_slope`：高电平随级数变化趋势。
- `VoltageLoss_slope`：保持损失随级数变化趋势。
- `Delay_slope`：延迟随级数变化趋势。
- `block_summary`：按 `stage_group_size` 分段的稳定性摘要。

完整逐级结果始终保留在 `real_metrics.csv`。

## 重要判定策略

- 合法重复扫描脉冲不计为误触发。
- 误触发只在排除合法脉冲和边沿缓冲后的非选通区域中检测。
- overlap 使用时间区间端点交集累计，不使用样本数乘平均步长，避免非均匀采样下的误差。
- ripple 排除上升沿和下降沿区域，只评价 hold / non-selected 窗口。
- `LowFreqStable = not_evaluable_with_current_waveform` 表示波形时长不足以覆盖目标刷新周期，不能据此宣称低频保持通过或失败。
- `PASS_BASIC_SIMULATION_CHECK` 只表示当前仿真 CSV 和阈值下的基础检查通过，不表示实物测试通过。

## 评分指标

`score_summary.json` 将硬约束和软评分分开：

- `hard_constraint_passed`：硬约束是否全部通过。
- `hard_constraint_failures`：硬约束失败项。
- `failure_reasons`：失败原因列表。
- `warning_reasons`：警告原因列表。
- `function_score`：功能类得分。
- `quality_score`：波形质量类得分。
- `stability_score`：稳定性类得分。
- `consistency_score`：一致性类得分。
- `cost_score`：成本或复杂度预留得分。
- `overall_score`：按权重聚合后的总体得分。

`metric_penalties` 记录关键指标的可排序惩罚项，包括 `Max_overlap_ratio`、`Max_ripple`、`Max_voltage_loss`、`Delay_std`、`Width_std`、`Width_mean`、`VOH_min_margin` 和 `FalseTriggerCount`。每个惩罚项包含当前值、阈值、限制类型、严重程度、分数、扣分和原因。

硬约束失败不会删除软评分。这样可以在失败 run 中继续判断主要短板来自功能、质量、稳定性还是一致性。软评分采用连续惩罚函数，超过阈值后仍保留排序梯度，避免把轻微失败和严重失败都压成同一个分数。

`propose-candidates --strategy constrained-random` 会读取这些惩罚项辅助排序：规则优先级决定基础方向，惩罚严重度和扣分提高当前主要失效指标的候选权重，两参数组合再扣除复杂度惩罚。

## Topology-aware analysis metrics

`config/sky130_eval_profiles.yaml` defines the first profile set: `default`, `ota`, `comparator`, and `oscillator`. Aliases map common topologies such as `two_stage_opamp` to `ota` and `vco` to `oscillator`.

Profile metrics are stored in `analysis_metrics.json` and then summarized in `score_summary.json`:

- OTA / two-stage op-amp: `dc_gain_db`, `bandwidth_3db_hz`, `unity_gain_hz`, `slew_rate_v_per_s`, `output_swing_v`, `static_power_w`.
- Comparator: `switching_threshold_v`, `output_swing_v`, `static_power_w`, with hysteresis treated as a proxy when data is available.
- Oscillator / VCO: `frequency_hz`, `period_std_s`, `output_swing_v`, `startup_time_s`, `static_power_w`.

If OP/AC/DC/TRAN files are missing or unreadable, the metric is recorded under `not_evaluable`; the run can still complete and remain eligible for simulation-only sorting by available metrics.

## 参数元数据

批量评价会把 `params.yaml` 中的参数拼接到指标表和榜单中。常见参数包括：

- `C_store`
- `R_driver`
- `W_pmos`
- `W_nmos`
- `VDD`
- `load_cap`
- `temp`
- `corner`

这些参数不改变指标定义，只让输出表可以用于后续比较、排序和推荐。

## 推荐规则使用的指标

推荐规则可能读取：

- `Max_overlap_ratio`
- `Max_ripple`
- `Delay_mean`
- `Delay_std`
- `FalseTriggerCount`
- `LowFreqStable`
- `Max_voltage_loss`
- `worst_stage`
- `first_failed_stage`

推荐文本是下一轮工程建议，不是自动优化已经完成的结果。
