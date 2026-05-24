# 8T1C / GOA 大规模级联摘要报告

## 1. 数据来源说明

- 外部波形文件：`examples\sample_waveform.csv`
- 数据来源标记：`real_simulation_csv`
- 工程有效性标记：`simulation_only`
- data_source = real_simulation_csv
- engineering_validity = simulation_only
- 图像时间轴统一换算为 μs；CSV 原始时间值仍保留在指标 CSV/JSON 中。
- 电压单位：默认按 V 处理。
- 评价级数：`3`
- 导师汇报口径：框架支持逐级完整数据、分段摘要、退化趋势和最差级定位。

## 2. 阈值说明

- high_threshold = `5.0` V
- low_threshold = `1.0` V
- max_voltage_loss_v_limit = `0.5` V
- target_refresh_hz = `60.0` Hz
- frame_hold_time = `0.016666666666666666` s
- 当前阈值是初步工程分析阈值，需要后续由电路规格进一步确认。

## 3. 关键逐级指标

| stage | node | PulseExist | LegalPulseCount | VOH_mean | VOH_max | VHoldEnd | VoltageLoss | VoltageLossRatio | VOL_max | PulseWidth | Delay | Ripple | FalseTrigger | FalseTriggerCount | Overlap | OverlapRatio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | o1 | True | 1 | 6.15 | 6.2 | 6.1 | 0.10000000000000053 | 0.016129032258064602 | 0.1 | 3.0000000000000005e-06 |  | 0.1 | False | 0 | 1.0000000000000006e-06 | 0.33333333333333354 |
| 2 | o2 | True | 1 | 6.15 | 6.2 | 6.1 | 0.10000000000000053 | 0.016129032258064602 | 0.2 | 3e-06 | 1.9999999999999995e-06 | 0.2 | False | 0 | 9.999999999999997e-07 | 0.33333333333333326 |
| 3 | o3 | True | 1 | 6.15 | 6.2 | 6.1 | 0.10000000000000053 | 0.016129032258064602 | 0.0 | 3e-06 | 2.000000000000001e-06 | 0.0 | False | 0 |  |  |

## 4. 级联扫描顺序判断

- Seq_pass：`True`
- All_pulses_exist：`True`
- False_trigger_count：`0`
- FalseTriggerCount：`0`
- Overall_status：`FAIL_OVERLAP`
- first_failed_stage：`1`
- worst_stage：`2`

## 5. 波形质量与一致性初步分析

- VOH_min：`6.15`
- VOH_std：`8.881784197001252e-16`
- VOL_max_all：`0.2`
- Delay_mean：`2.0000000000000003e-06`
- Delay_std：`8.470329472543003e-22`
- Width_mean：`3e-06`
- Width_std：`2.445173500548762e-22`
- Max_ripple：`0.2`
- Ripple_p95：`0.19`
- Max_voltage_loss：`0.10000000000000053`
- Max_voltage_loss_ratio：`0.016129032258064602`
- VoltageLoss_p95：`0.10000000000000053`
- Max_overlap：`1.0000000000000006e-06`
- Max_overlap_ratio：`0.33333333333333354`
- VOH_p1 / VOH_p5 / VOH_p50：`6.15` / `6.15` / `6.15`
- VOH_slope：`-1.8560187921164262e-15`
- VoltageLoss_slope：`-1.2402532341079812e-18`
- Delay_slope：`2.163720877622773e-21`
- LowFreqStable：`not_evaluable_with_current_waveform`
- 低频稳定性说明：当前波形时长短于目标刷新周期，只能计算扫描脉冲内电压损失，不能证明低 Hz 保持稳定性。

## 6. 分段摘要

| block_index | stage_start | stage_end | VOH_min | Max_voltage_loss | Max_ripple | Delay_mean | failed_stage_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0 | 1.0 | 3.0 | 6.15 | 0.10000000000000053 | 0.2 | 2.0000000000000003e-06 | 2.0 |

## 7. 内部节点 pu / pd / output 机理说明

PU 节点主要反映本级上拉控制状态。PU 被有效拉高后，通常对应输出节点进入拉高或保持高电平的能力增强；若 PU 上升慢或峰值不足，可能导致输出上升沿变慢或 VOH 降低。

PD 节点主要反映下拉/复位控制状态。PD 有效时，输出更容易被复位或保持在低电平；若 PD 在非选通期控制不足，可能造成输出残留、纹波偏大或低电平风险升高。

本报告优先绘制 xs4 的 PU/PD/output 叠加图，并在内部节点完整时绘制 xs1/xs4/xs8 对比图，用于观察前级、中级、后级是否存在明显退化。

## 8. 图像输出

- `figures/sample_outputs_overview.png`
- `figures/sample_outputs_stacked.png`
- `figures/o1_o8_overview.png`
- `figures/o1_o8_stacked.png`
- `figures/voh_bar.png`
- `figures/pulse_width_bar.png`
- `figures/delay_bar.png`
- `figures/ripple_bar.png`
- `figures/voltage_loss_bar.png`
- `figures/overlap_ratio_bar.png`
- `figures/width_bar.png`
- `figures/voh_width_bar.png`
- `figures/voh_width_delay_bar.png`
- `figures/vol_ripple_bar.png`
- `figures/delay_bar.png`
- `figures/voh_trend.png`
- `figures/voltage_loss_trend.png`
- `figures/delay_trend.png`
- `figures/ripple_trend.png`
- `figures/block_stability_heatmap.png`

图像物理意义说明：

- `sample_outputs_overview.png`：抽样输出总览，用于快速确认大规模级联中的代表级波形。
- `sample_outputs_stacked.png`：抽样输出堆叠图，用于观察代表级上升沿顺序、扫描节拍和级间时序关系。
- `voh_trend.png`：VOH 随级数变化趋势，用于观察级联后高电平是否累积退化。
- `voltage_loss_trend.png`：电压损失随级数变化趋势，用于观察保持能力是否随级数恶化。
- `delay_trend.png`：级间延迟随级数变化趋势，用于观察传播延迟累积变化。
- `ripple_trend.png`：纹波随级数变化趋势，用于观察非选通稳定性风险。
- `block_stability_heatmap.png`：按分段统计的稳定性风险热力图，用于快速定位风险段。
- `o1_o8_overview.png`：小规模级联输出总览，仅在级数较少时生成。
- `o1_o8_stacked.png`：小规模级联输出堆叠图，仅在级数较少时生成。
- `voh_bar.png`：每级 VOH 平均值柱状图，红色虚线为 high_threshold，用于判断输出高电平裕量。
- `pulse_width_bar.png`：每级脉冲宽度对比，红色虚线为目标脉宽，用于判断扫描脉宽一致性。
- `delay_bar.png`：Delay_i 柱状图，显示 o1→o2 到 o7→o8 的传播延迟，用于判断级间时序一致性。
- `ripple_bar.png`：Ripple 柱状图，用于观察非选通纹波。
- `voltage_loss_bar.png`：VoltageLoss 柱状图，用于观察写入后到保持窗口末端的电压损失。
- `vol_ripple_bar.png`：VOL_max / Ripple 柱状图，用于观察非选通低电平风险和非选通纹波。
- `overlap_ratio_bar.png`：OverlapRatio 柱状图，用于观察相邻级选通重叠比例。
- `internal_xs4_pu_pd_o4.png`：第 4 级 PU/PD/output 叠加图，用于解释内部上拉、复位/保持低电平和输出响应关系。
- `internal_xs1_xs4_xs8_compare.png`：前级、中级、后级内部节点对比图，用于观察级联后是否出现内部节点退化。

跳过的内部节点图：

- 未提供内部节点文件。

## 9. 明确声明

- 本结果来自电路仿真 CSV，仅代表 simulation-only 分析。
- 本结果不是实物测试结果，不能视为实物测试结论。
- 当前阈值为初步阈值，需要由电路规格确认。
- 若 `LowFreqStable = not_evaluable_with_current_waveform`，表示当前波形时长不足以覆盖目标刷新周期，不能据此宣称低 Hz 显示已经稳定。
- 后续仍需 PVT、Monte Carlo、负载变化和功耗分析。
- `PASS_BASIC_SIMULATION_CHECK` 只表示仿真 CSV 的基础检查通过，不代表真实产品通过。
