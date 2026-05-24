# CircuitPilot 下一轮参数候选

- schema_version: `1.0`
- result_version: `1.0`
- data_source: `real_simulation_csv`
- engineering_validity: `simulation_only`

本报告基于仿真 CSV 的结构化指标和规则建议生成，不是实物测试结果，也不表示自动优化闭环已经完成。
候选项按约束、规则优先级和搜索得分排序；constrained_random 策略只生成单参数和两参数组合候选。

## Candidates

### cand_001

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `single_parameter`
- parameter: `drive_resistance`
- direction: `review_timing`
- candidate_value: `1000 ohm`
- changed_parameters: `drive_resistance`
- search_score: `85.0`
- source_recommendation: `overlap_timing_review`
- trigger_metric: `Max_overlap_ratio`
- rationale: single-parameter constrained candidate from rule triggers: drive_resistance review_timing

### cand_002

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `single_parameter`
- parameter: `drive_resistance`
- direction: `review_timing`
- candidate_value: `1500 ohm`
- changed_parameters: `drive_resistance`
- search_score: `85.0`
- source_recommendation: `overlap_timing_review`
- trigger_metric: `Max_overlap_ratio`
- rationale: single-parameter constrained candidate from rule triggers: drive_resistance review_timing

### cand_003

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `single_parameter`
- parameter: `drive_resistance`
- direction: `review_timing`
- candidate_value: `2000 ohm`
- changed_parameters: `drive_resistance`
- search_score: `85.0`
- source_recommendation: `overlap_timing_review`
- trigger_metric: `Max_overlap_ratio`
- rationale: single-parameter constrained candidate from rule triggers: drive_resistance review_timing

### cand_004

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `two_parameter_combo`
- parameter: `drive_resistance;transistor_width`
- direction: `review_timing;increase`
- candidate_value: `1000 ohm`
- changed_parameters: `drive_resistance;transistor_width`
- search_score: `80.0`
- source_recommendation: `overlap_timing_review;delay_drive_load_review`
- trigger_metric: `Max_overlap_ratio;Delay_mean`
- rationale: two-parameter constrained candidate from rule triggers: drive_resistance review_timing, transistor_width increase

### cand_005

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `two_parameter_combo`
- parameter: `drive_resistance;transistor_width`
- direction: `review_timing;increase`
- candidate_value: `1000 ohm`
- changed_parameters: `drive_resistance;transistor_width`
- search_score: `80.0`
- source_recommendation: `overlap_timing_review;delay_drive_load_review`
- trigger_metric: `Max_overlap_ratio;Delay_mean`
- rationale: two-parameter constrained candidate from rule triggers: drive_resistance review_timing, transistor_width increase

### cand_006

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `two_parameter_combo`
- parameter: `drive_resistance;transistor_width`
- direction: `review_timing;increase`
- candidate_value: `1000 ohm`
- changed_parameters: `drive_resistance;transistor_width`
- search_score: `80.0`
- source_recommendation: `overlap_timing_review;delay_drive_load_review`
- trigger_metric: `Max_overlap_ratio;Delay_mean`
- rationale: two-parameter constrained candidate from rule triggers: drive_resistance review_timing, transistor_width increase

### cand_007

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `two_parameter_combo`
- parameter: `drive_resistance;transistor_width`
- direction: `review_timing;increase`
- candidate_value: `1500 ohm`
- changed_parameters: `drive_resistance;transistor_width`
- search_score: `80.0`
- source_recommendation: `overlap_timing_review;delay_drive_load_review`
- trigger_metric: `Max_overlap_ratio;Delay_mean`
- rationale: two-parameter constrained candidate from rule triggers: drive_resistance review_timing, transistor_width increase

### cand_008

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `two_parameter_combo`
- parameter: `drive_resistance;transistor_width`
- direction: `review_timing;increase`
- candidate_value: `1500 ohm`
- changed_parameters: `drive_resistance;transistor_width`
- search_score: `80.0`
- source_recommendation: `overlap_timing_review;delay_drive_load_review`
- trigger_metric: `Max_overlap_ratio;Delay_mean`
- rationale: two-parameter constrained candidate from rule triggers: drive_resistance review_timing, transistor_width increase

### cand_009

- priority: `85`
- strategy: `constrained_random`
- candidate_kind: `two_parameter_combo`
- parameter: `drive_resistance;transistor_width`
- direction: `review_timing;increase`
- candidate_value: `2000 ohm`
- changed_parameters: `drive_resistance;transistor_width`
- search_score: `80.0`
- source_recommendation: `overlap_timing_review;delay_drive_load_review`
- trigger_metric: `Max_overlap_ratio;Delay_mean`
- rationale: two-parameter constrained candidate from rule triggers: drive_resistance review_timing, transistor_width increase

### cand_010

- priority: `80`
- strategy: `constrained_random`
- candidate_kind: `single_parameter`
- parameter: `drive_resistance`
- direction: `decrease`
- candidate_value: `1000 ohm`
- changed_parameters: `drive_resistance`
- search_score: `80.0`
- source_recommendation: `delay_drive_load_review`
- trigger_metric: `Delay_mean`
- rationale: single-parameter constrained candidate from rule triggers: drive_resistance decrease
