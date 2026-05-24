# 8T1C / GOA 规则化诊断与优化建议

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- 本诊断仅基于仿真 CSV 指标，不是实物测试结论。

## 关键状态

- Overall_status：`FAIL_OVERLAP`
- hard_constraint_passed：`False`
- overall_score：`61.99999999999997`

## 优化建议

- VOL_max_all 偏高：建议检查 PD 尺寸、reset 控制和非选通保持路径。
- Max_overlap_ratio 偏大：建议检查相邻级时序、下降沿速度和时钟相位。
- 脉宽偏离或 Width_std 偏大：建议检查时钟脉宽、级间耦合和边沿检测阈值。
- Hard constraints 未全部通过：建议优先处理 score_summary.json 中列出的失败原因，再进行参数优化。
