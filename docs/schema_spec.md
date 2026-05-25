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
| `metric_penalties` | object | 面向排序和优化的逐指标惩罚明细。 |
| `soft_scores` | object | 软评分明细。 |
| `score_explanations` | object | 评分解释。 |
| `function_score` | number/null | 功能得分。 |
| `quality_score` | number/null | 波形质量得分。 |
| `stability_score` | number/null | 稳定性得分。 |
| `consistency_score` | number/null | 一致性得分。 |
| `cost_score` | number/null | 成本或复杂度预留得分。 |
| `overall_score` | number/null | 总体得分。 |

硬约束与软评分保持分离，便于失败 run 继续参与排序、诊断和参数建议。

`metric_penalties` 对关键指标输出 `current_value`、`threshold`、`limit_type`、`severity`、`score`、`deduction` 和 `reason`。硬约束仍决定 pass/fail；惩罚分用于区分失败程度，例如轻微超限的 `Max_overlap_ratio` 会比严重超限保留更高排序分。

Topology-aware scoring adds optional fields without changing the existing waveform score contract:

| Field | Type | Description |
|---|---|---|
| `topology_profile` | string | Resolved profile name, currently `default`, `ota`, `comparator`, or `oscillator`. Unknown topology falls back to `default`. |
| `profile_metric_scores` | object | Per-profile OP/AC/DC/TRAN metric scores used by the profile score. |
| `analysis_metric_penalties` | object | Penalty details for profile metrics such as gain, bandwidth, switching threshold, frequency, startup, output swing, or static power. |
| `not_evaluable_metrics` | object | Missing or unreadable analysis inputs. These do not fail the run; they only mark profile metrics as unavailable. |
| `profile_score` | number/null | Weighted profile-specific score when a non-default profile is active or profile metrics are present. |

## analysis_metrics.json

Purpose: companion metrics for topology-aware evaluation. This file is written next to `real_summary.json` and `score_summary.json` when `evaluate-real`, `sky130-transient`, or `sky130-sweep` runs.

Stable top-level fields:

| Field | Type | Description |
|---|---|---|
| `topology_profile` | string | Resolved evaluation profile. |
| `op_metrics` | object | Basic operating-point metrics, including `static_power_w` when supply voltage and current are available. |
| `ac_metrics` | object | Basic AC metrics such as `dc_gain_db`, `bandwidth_3db_hz`, and `unity_gain_hz`. |
| `dc_metrics` | object | Basic DC metrics such as `switching_threshold_v`, `output_swing_v`, and `hysteresis_proxy_v`. |
| `tran_metrics` | object | Transient metrics such as `output_swing_v`, `frequency_hz`, `period_std_s`, `slew_rate_v_per_s`, and `startup_time_s`. |
| `not_evaluable` | object | Reasons for missing OP/AC/DC/TRAN inputs or missing derived metrics. |

These metrics are simulation-only analysis helpers. Missing OP/AC/DC data should be treated as `not_evaluable`, not as physical pass/fail evidence.

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

## next_candidates.csv

用途：基于单次评价结果、规则推荐和参数空间，生成下一轮仿真可参考的保守候选参数。默认 `constrained-random` 策略会生成单参数和两参数组合候选；`rule` 策略只输出规则映射的单参数候选。

稳定列：

| 字段 | 说明 |
|---|---|
| `schema_version` | Schema 版本。 |
| `result_version` | 结果格式版本。 |
| `candidate_id` | 稳定候选编号，例如 `cand_001`。 |
| `priority` | 规则优先级，数值越大越靠前。 |
| `parameter` | 建议调整或复核的参数名。 |
| `direction` | 调整方向，例如 `increase`、`decrease`、`review`。 |
| `candidate_value` | 参数空间中给出的候选值。 |
| `candidate_unit` | 参数单位；简单列表格式可为空。 |
| `source_recommendation` | 触发候选的推荐 ID。 |
| `trigger_metric` | 触发推荐的指标。 |
| `data_source` | 固定为 `real_simulation_csv`。 |
| `engineering_validity` | 固定为 `simulation_only`。 |
| `strategy` | 候选生成策略，例如 `constrained_random` 或 `rule`。 |
| `candidate_kind` | 候选类型，例如 `single_parameter` 或 `two_parameter_combo`。 |
| `changed_parameters` | 本候选改变的参数名，多个参数以分号分隔。 |
| `parameters_json` | 本候选的参数键值 JSON。 |
| `search_score` | 约束搜索排序分数，综合规则优先级、指标惩罚严重度和组合复杂度。 |
| `rationale` | 生成该候选的简要原因。 |

候选参数表只表示下一轮仿真输入建议，不表示自动优化闭环已经完成。默认随机搜索使用固定 seed 以保证可复现。当 `score_summary.json` 提供 `metric_penalties` 或 `analysis_metric_penalties` 时，严重超限指标会得到更高搜索权重；两参数组合会保留组合惩罚，避免过早偏向复杂改动。Topology-aware candidate generation uses `config/sky130_eval_profiles.yaml` `candidate_rules` to map active profile metrics such as `dc_gain_db`, `static_power_w`, `switching_threshold_v`, or `frequency_hz` onto parameters that exist in the current parameter space. If a profile rule references parameters that are absent from the current parameter space, those entries are skipped.

Hard-constraint failures such as `All_pulses_exist` and `Seq_pass` can also
produce recovery candidates for drive-strength, load, and threshold-review
parameters when those names exist in the parameter space. These candidates are
simulation-only next-run suggestions, not physical-validation evidence.

## next_candidates.md

用途：面向人工阅读的下一轮候选参数说明。

内容应包括：

- schema 和 result 版本；
- `real_simulation_csv` / `simulation_only` 边界；
- 候选来源和排序规则；
- 按优先级列出的候选参数；
- 明确声明：结果基于仿真 CSV 和规则建议，不是实物测试结果，也不是自动优化闭环完成证明。

## SKY130 transient outputs

`sky130-transient` creates one run directory per public SKY130 dataset row.

| File | Purpose |
|---|---|
| `testbench.spice` | ngspice input written from dataset `testbench_spice`. |
| `source_netlist.spice` | Source SPICE text selected from `netlist`, `spice_netlist`, or `testbench_spice` for structure analysis. |
| `netlist_structure.json` | AMS-Net-style structure companion data: device counts, models, node degrees, directives, and scalar size features. |
| `waveform.csv` | Converted `TIME,v(o1),...` waveform for `evaluate-real`. |
| `analysis_metrics.json` | Topology-aware OP/AC/DC/TRAN companion metrics and `not_evaluable` reasons. |
| `dataset_row.json` | Snapshot of the source dataset row. |
| `node_map.json` | Mapping from `o1/o2/...` aliases to original output nodes. |
| `sky130_metadata.json` | Dataset provenance, topology, PDK, split, original output nodes, and structure companion paths. |
| `sky130_status.json` | Per-row `evaluated`, `skipped`, or `failed` status. |

`output_root/sky130_runs.csv` summarizes status, `overall_score`, failure reasons, topology, resolved `topology_profile`, selected analysis metrics such as `dc_gain_db`, `bandwidth_3db_hz`, `unity_gain_hz`, `static_power_w`, `switching_threshold_v`, and `frequency_hz`, source, run directory, and compact structure columns such as `mos_count`, `cap_count`, `resistor_count`, `current_source_count`, `model_count`, `node_count`, and `transistor_width_sum`. Structure and analysis data are companion metadata only. This entrypoint still uses `data_source = real_simulation_csv` and `engineering_validity = simulation_only`; it does not represent physical test validation or a completed automatic optimization loop.

## SKY130 sweep outputs

`sky130-sweep` creates one run directory per explicit parameter combination and keeps the same per-run output contract as `sky130-transient`.

| File | Purpose |
|---|---|
| `params.yaml` | Parameter values used for this sweep point. |
| `testbench.spice` | Per-run SPICE copy after parameter rewrite. |
| `waveform.csv` | Converted transient waveform for `evaluate-real`. |
| `analysis_metrics.json` | Topology-aware OP/AC/DC/TRAN companion metrics and `not_evaluable` reasons. |
| `real_summary.json` / `score_summary.json` | Existing waveform evaluation and topology-aware score outputs. |
| `next_candidates.csv` | Existing constrained-random next-candidate output for the run. |

At the sweep root, `sky130_sweep_runs.csv` summarizes every sweep point, `sky130_sweep_leaderboard.csv` sorts evaluated points by score, `sky130_sweep_sensitivity.csv` reports coarse one-parameter score deltas, and `next_param_space.yaml` preserves a narrowed next-round parameter-space suggestion. These files are simulation-only ranking artifacts, not physical validation and not proof of a completed multi-round optimizer.

## optimize-rounds outputs

`optimize-rounds` runs `sky130-sweep` repeatedly and adapts each later round from
the best previous run's `next_candidates.csv`, while skipping parameter points
already present in the accumulated history. The command is still bounded by
`engineering_validity = simulation_only`; its outputs are search traces and next
simulation suggestions, not physical-validation evidence.

`--strategy` supports `adaptive`, `genetic`, `bayesian`, `surrogate`, and
`hybrid`. Advanced strategies operate on the discrete sweep grid only.
`bayesian` uses Gaussian-process expected improvement, `surrogate` uses a
random-forest score model, and `hybrid` combines rule candidates, genetic
variation, model ranking, and diversity fallback. If there are fewer than three
valid history rows or the composite objective has zero variance, model-based
strategies record a fallback status and choose diverse untried points.

| File | Purpose |
|---|---|
| `round_001/`, `round_002/`, ... | Per-round `sky130-sweep` roots, each with the normal sweep outputs. |
| `optimization_history.json` | Combined machine-readable round summaries and per-run history rows, including candidate provenance fields when a point came from `next_candidates.csv`. |
| `optimization_leaderboard.csv` | All attempted runs sorted by stable `rank_status` first and `overall_score` second. |
| `round_summary.csv` | One row per optimization round with `best_score`, `best_run_dir`, and `stop_reason`. |
| `final_param_space.yaml` | Final explicit point list or narrowed sweep config used by the last round. |
| `best_next_candidates.csv` | Candidate table copied from the best run when available. |

The leaderboard keeps these candidate-result ingestion fields on each run row:
`candidate_source`, `source_run_dir`, `source_candidate_id`,
`source_candidate_trigger_metric`, `source_candidate_kind`,
`source_candidate_score`, `source_candidate_parameters_json`, and
`source_candidate_rationale`. `rank_status` normalizes run state for sorting:
`evaluated` rows with numeric scores rank first, followed by `not_evaluable`,
`skipped`, and `failed`.

Advanced strategy rows may also include `optimizer_strategy`, `objective_score`,
`model_status`, and `model_prediction`. The composite objective prioritizes
fewer hard-constraint failures, then higher `overall_score`, fewer
not-evaluable metrics, and available profile/analysis scores.

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

## llm_parameter_analysis.md

用途：面向人工阅读的 DeepSeek V4 参数分析结果。

内容应包含：

- 使用模型，例如 `deepseek-v4-pro`；
- `data_source = real_simulation_csv`；
- `engineering_validity = simulation_only`；
- 基于当前参数、指标、评分和候选项生成的分析正文；
- 明确说明：该分析不是实物测试结论，也不是自动优化闭环完成证明。

## llm_parameter_analysis.json

用途：保留 DeepSeek V4 参数分析的结构化结果，便于后续归档或汇报脚本读取。

稳定字段：

| 字段 | 说明 |
|---|---|
| `model` | 调用模型，默认 `deepseek-v4-pro`。 |
| `boundary` | 包含 `data_source` 和 `engineering_validity`。 |
| `analysis` | 模型返回的分析正文。 |
| `metadata` | 模型、token 用量或 mock 标记等元数据。 |
| `input_files` | 本次分析读取的 summary、score、metrics、candidates 和 params 文件路径。 |

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
