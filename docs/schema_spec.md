# Schema Specification

本文档定义 CircuitPilot 当前公开输出文件的字段约定。schema 的目标是让评价结果可以被报告、批量比较和后续参数搜索稳定读取。

当前版本：

```text
schema_version = 1.0
result_version = 1.0
```

## 通用边界字段

真实仿真输出必须包含或明确记录：

```json
{
  "data_source": "real_simulation_csv",
  "engineering_validity": "simulation_only"
}
```

这些字段表示结果来自仿真 CSV，不是物理实验或样机测试结果。

## real_summary.json

用途：单次 `evaluate-real` 的整体摘要。

必需或稳定字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | Schema 版本。 |
| `result_version` | string | 结果格式版本。 |
| `run_id` | string/null | 本次运行 ID。 |
| `run_timestamp` | string/null | 运行时间。 |
| `data_source` | string | 固定为 `real_simulation_csv`。 |
| `engineering_validity` | string | 固定为 `simulation_only`。 |
| `input_file` | string | 外部波形文件路径。 |
| `high_threshold` | number | 高电平阈值，单位 V。 |
| `low_threshold` | number | 低电平阈值，单位 V。 |
| `stage_count` | integer | 实际评价级数。 |
| `Seq_pass` | boolean | 扫描顺序基础检查是否通过。 |
| `All_pulses_exist` | boolean | 是否每级都有合法脉冲。 |
| `FalseTriggerCount` | integer | 全局误触发数量。 |
| `Max_overlap_ratio` | number/null | 最大相邻级重叠比例。 |
| `Max_ripple` | number/null | 最大纹波，单位 V。 |
| `LowFreqStable` | boolean/string/null | 低频保持状态。 |
| `Overall_status` | string | 总体状态。 |
| `worst_stage` | integer/null | 风险最高级。 |
| `first_failed_stage` | integer/null | 第一个失败级。 |
| `block_summary` | array | 分段摘要，大规模级联时使用。 |
| `notes` | array | 兼容回退、节点选择等说明。 |

常见摘要统计还包括 `VOH_min`、`VOH_std`、`VOL_max_all`、`Width_mean`、`Width_std`、`Delay_mean`、`Delay_std`、`Max_voltage_loss`、`Max_voltage_loss_ratio`、`VoltageLoss_p95`、`VOH_p1`、`VOH_p5`、`VOH_p50`、`Ripple_p95`、`Delay_p95`、`VOH_slope`、`VoltageLoss_slope`、`Delay_slope`。

## real_metrics.csv

用途：单次评价的逐级指标表。每行对应一个输出级或输出节点。

稳定列：

| 类别 | 字段 |
|---|---|
| identity | `schema_version`, `result_version`, `stage`, `node` |
| pulse | `PulseExist`, `LegalPulseCount`, `FalseTrigger`, `FalseTriggerCount` |
| voltage | `VOH_mean`, `VOH_max`, `VHoldEnd`, `VoltageLoss`, `VoltageLossRatio`, `VOL_max`, `Ripple` |
| timing | `PulseWidth`, `Delay`, `RiseTime`, `FallTime` |
| overlap | `Overlap`, `OverlapRatio` |
| windows | `legal_windows`, `primary_window`, `repeated_windows`, `false_trigger_windows` |
| compatibility aliases | `pulse_exist`, `rise_edge_time`, `fall_edge_time`, `pulse_width`, `rising_time`, `falling_time`, `ripple`, `false_trigger`, `overlap_with_next`, `overlap_ratio`, `delay_to_next` |

窗口字段以 JSON 字符串写入 CSV 单元格。下游读取时应按 JSON 解析，不应依赖人工分隔字符串。

## score_summary.json

用途：单次评价的硬约束和软评分结果。

稳定字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | Schema 版本。 |
| `result_version` | string | 结果格式版本。 |
| `hard_constraint_passed` | boolean | 硬约束是否全部通过。 |
| `hard_constraint_failures` | array | 硬约束失败项。 |
| `hard_constraints` | object | 各硬约束明细。 |
| `failure_reasons` | array | 失败原因。 |
| `warning_reasons` | array | 警告原因。 |
| `soft_scores` | object | 软评分明细。 |
| `score_explanations` | object | 评分解释。 |
| `function_score` | number/null | 功能得分。 |
| `quality_score` | number/null | 波形质量得分。 |
| `stability_score` | number/null | 稳定性得分。 |
| `consistency_score` | number/null | 一致性得分。 |
| `cost_score` | number/null | 成本或复杂度预留得分。 |
| `overall_score` | number/null | 总体得分。 |

硬约束与软评分保持分离，便于失败 run 继续参与排序、诊断和参数建议。

## diagnosis_report.md

用途：面向人工复核的诊断说明。

内容应包括：

- 当前总体状态；
- 硬约束是否通过；
- 主要失败或警告原因；
- 需要优先复核的指标；
- `simulation_only` 边界说明。

## real_waveform_report.md

用途：面向人工阅读的波形评价报告。

报告应包含：

- 数据来源说明；
- 阈值说明；
- 关键逐级指标或大规模摘要；
- 扫描顺序判断；
- 波形质量与一致性分析；
- 分段摘要；
- 图像输出列表；
- 明确声明：结果来自仿真 CSV，不是实物测试结论。

当级数很大时，Markdown 报告只展示摘要；完整逐级明细保留在 `real_metrics.csv`。

## run_manifest_real.json

用途：记录单次运行的可追溯信息。

稳定字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | Schema 版本。 |
| `result_version` | string | 结果格式版本。 |
| `run_id` | string | 本次运行 ID。 |
| `run_time` | string | 运行时间。 |
| `command` | string | 命令行。 |
| `input_files` | array | 输入文件路径。 |
| `input_file_hashes` | object | 输入文件 sha256 和大小。 |
| `thresholds` | object | 实际使用的阈值和级联配置。 |
| `data_source` | string | 固定为 `real_simulation_csv`。 |
| `engineering_validity` | string | 固定为 `simulation_only`。 |
| `code_version_or_git_commit` | string | 当前 git 短提交或 `unknown`。 |

## optimization_dataset.csv

用途：为后续参数搜索或优化流程提供单行结构化数据。每次单次评价会追加一行。

稳定列：

| 类别 | 字段 |
|---|---|
| version | `schema_version`, `result_version` |
| run identity | `run_id`, `run_timestamp`, `design_name`, `parameter_set_id` |
| future design parameters | `W_PU`, `W_PD`, `C_boot`, `C_load`, `V_CLKH` |
| generic parameters | `capacitance`, `drive_resistance`, `transistor_width`, `transistor_length`, `vdd`, `load_cap`, `temp`, `corner` |
| metric summary | `VOH_min`, `VOH_std`, `VOL_max_all`, `Width_mean`, `Width_std`, `Delay_mean`, `Delay_std`, `Max_ripple`, `Max_voltage_loss`, `Max_voltage_loss_ratio`, `VoltageLoss_p95`, `VOH_p1`, `VOH_p5`, `VOH_p50`, `Ripple_p95`, `Delay_p95`, `VOH_slope`, `VoltageLoss_slope`, `Delay_slope`, `Max_overlap`, `Max_overlap_ratio`, `LowFreqStable`, `worst_stage`, `first_failed_stage` |
| status | `Seq_pass`, `All_pulses_exist`, `FalseTriggerCount`, `Overall_status`, `hard_constraint_passed`, `overall_status`, `overall_score` |
| boundary | `data_source`, `engineering_validity` |

当前无法从输入推断的参数保持空值，不应编造。

## params.yaml

用途：批量评价时描述每个 run 的参数和仿真条件。

推荐字段：

```yaml
run_id: run_001
circuit_version: goa_8t1c_v1
parameters:
  C_store: 1pF
  R_driver: 10k
  W_pmos: 2u
  W_nmos: 1u
  VDD: 15
  load_cap: 5pF
conditions:
  temp: 25
  corner: TT
```

工程后缀如 `1pF`、`10k`、`2u` 会尽量解析出数值辅助字段；无法数值化的值如 `TT` 保留为标签。

## 批量输出

`evaluate-batch` 写入：

| 文件 | 说明 |
|---|---|
| `all_metrics.csv` | 所有 run 的逐级指标合并表，附带 `run_id`、`circuit_version`、参数字段和条件字段。 |
| `all_scores.csv` | 每个 run 一行评分摘要，包含 `failure_reasons` 和 `warning_reasons`。 |
| `leaderboard.csv` | 每个 run 一行，按 `overall_score` 降序排序。 |
| `recommendations.md` | 按 run 分组的规则化参数建议。 |
| `run_manifest_batch.json` | 批量评价元数据。 |

`run_manifest_batch.json` 稳定字段：

- `schema_version`
- `result_version`
- `run_count`
- `runs_dir`
- `output_dir`
- `engineering_validity`

## recommendations.md

每条推荐项包含：

| 字段 | 说明 |
|---|---|
| `recommendation_id` | 稳定推荐 ID。 |
| `severity` | 建议严重程度。 |
| `trigger_metric` | 触发建议的指标。 |
| `current_value` | 当前值。 |
| `threshold` | 阈值。 |
| `possible_physical_causes` | 可能物理原因，仅作为工程假设。 |
| `next_tuning_actions` | 下一轮调参或复核建议。 |
| `needs_metric_review` | 是否需要优先复核指标定义或波形窗口。 |
| `message` | 人类可读说明。 |
| `data_source` | 固定为 `real_simulation_csv`。 |
| `engineering_validity` | 固定为 `simulation_only`。 |

推荐报告必须说明其基于仿真数据，不是实物测试结果，也不是自动优化闭环已经完成的证明。
