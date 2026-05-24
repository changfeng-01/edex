# CircuitPilot 参数建议报告

- schema_version: `1.0`
- result_version: `1.0`
- data_source: `real_simulation_csv`
- engineering_validity: `simulation_only`

本报告仅基于仿真 CSV 的结构化指标生成，属于 simulation_only 分析，不是实物测试结果，也不代表可直接替代人工优化决策。

## Recommendations

### overlap_timing_review

- severity: `high`
- trigger_metric: `Max_overlap_ratio`
- current_value: `0.33333333333333354`
- threshold: `0.1`
- possible_physical_causes: 相邻级时序过近、下降沿速度不足、时钟相位重叠，或 overlap 统计窗口口径仍需复核。
- next_tuning_actions: 检查相邻级时序，缩短导通窗口，增加级间间隔，并复核 overlap 是否已按端点区间积分统计。
- needs_metric_review: `True`
- message: Max_overlap_ratio 超过当前阈值。建议检查相邻级时序，缩短导通窗口，增加级间间隔，并复核 overlap 是否已按端点区间积分统计。

### delay_drive_load_review

- severity: `medium`
- trigger_metric: `Delay_mean`
- current_value: `2.0000000000000003e-06`
- threshold: `9.999999999999999e-06`
- possible_physical_causes: 驱动能力、负载电容或开关尺寸导致级间传播节拍偏离目标。
- next_tuning_actions: 调整驱动能力、负载电容或开关尺寸，并用批量评价确认调整方向。
- needs_metric_review: `False`
- message: Delay_mean 与目标节拍存在偏离。建议检查驱动能力、负载电容和开关尺寸，并用批量评价确认调整方向。

### low_frequency_waveform_extension

- severity: `medium`
- trigger_metric: `LowFreqStable`
- current_value: `not_evaluable_with_current_waveform`
- threshold: `full_frame_waveform`
- possible_physical_causes: 当前仿真时长短于目标刷新周期，不能证明低频保持稳定性。
- next_tuning_actions: 增加至少一个完整帧周期或更长保持时间的仿真波形，再判断低频保持稳定性。
- needs_metric_review: `True`
- message: LowFreqStable 当前不可评价。建议增加至少一个完整帧周期或更长保持时间的仿真波形，再判断低频保持稳定性。
