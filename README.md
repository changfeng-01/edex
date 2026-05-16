# CircuitPilot / 芯智调参

中文名：芯智调参：基于仿真数据的电路参数智能推荐系统  
English name: CircuitPilot: Simulation-Driven Intelligent Parameter Recommendation for Circuit Design

CircuitPilot is a simulation-driven circuit evaluation, diagnosis, and rule-based parameter recommendation prototype. It is extracted from an 8T1C / GOA waveform evaluation workflow and keeps the reusable software engine under the Python package name `goa_eval`.

## 项目定位

当前版本不是完整自动优化电路系统，也不是实物测试平台。它完成的是：

- 读取仿真 CSV 波形；
- 自动识别输出节点扫描窗口；
- 计算电压、时序、重叠、纹波、保持损失和误触发等指标；
- 生成 CSV / JSON / Markdown / PNG 评价包；
- 基于失败原因和关键指标给出下一轮参数调整建议；
- 支持 `runs/run_001`、`runs/run_002` 形式的批量评价入口。

所有真实 CSV 结果均保持：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

## 为什么做这个项目

电路迭代过程中通常会产生大量仿真波形、手工记录和截图。CircuitPilot 将这些结果整理为稳定的数据 schema，使下一步参数空间搜索、规则推荐或优化算法能够基于结构化数据继续发展。

## 当前已实现功能

- 识别 `XVAL` / `TIME` 时间列，以及 `v(o1)`、`v(o2)`、`v(xs4.pu)` 等波形列名。
- 对 `o1~oN` 输出节点做逐级扫描窗口识别；CSV 只有 `o1~o8` 时按 8 级兼容评价。
- 支持 720 级级联配置接口；这代表框架可扩展，不代表示例数据已经覆盖 720 级真实结果。
- 区分合法重复扫描脉冲和真正误触发。
- overlap 使用时间区间端点交集累计，适配非均匀采样。
- ripple 在 hold / non-selected 窗口计算，并排除上升沿和下降沿。
- 低频保持时长不足时输出 `not_evaluable_with_current_waveform`，不硬判失败。
- 评分结果区分 `hard_constraints`、`soft_scores`、`failure_reasons` 和 `warning_reasons`。
- 批量评价输出 `all_metrics.csv`、`all_scores.csv`、`leaderboard.csv` 和 `recommendations.md`。

## 系统架构

```text
src/goa_eval/
├── cli.py              # evaluate-real / recommend / evaluate-batch
├── waveform_io.py      # 仿真 CSV 读取与列名归一化
├── windowing.py        # 脉冲窗口、重复扫描窗口、边沿区域、overlap 积分
├── metrics.py          # 单次波形指标计算
├── scorer.py           # 硬约束与软评分
├── diagnosis.py        # 诊断信息
├── recommendation.py   # 规则化参数建议
├── batch_eval.py       # 多 run 批量评价
├── param_space.py      # run 参数与参数空间读取
├── optimizer.py        # 未来优化器接口
├── reporter.py         # CSV / JSON / Markdown 输出
├── plotter.py          # PNG 图表
└── schemas.py          # schema_version、字段名和基础校验
```

## 快速开始

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

运行示例波形：

```bash
python -m goa_eval.cli evaluate-real --waveform examples/sample_waveform.csv --output-dir outputs/example
```

生成单次推荐报告：

```bash
python -m goa_eval.cli recommend ^
  --summary outputs/example/real_summary.json ^
  --score outputs/example/score_summary.json ^
  --metrics outputs/example/real_metrics.csv ^
  --output outputs/example/recommendations.md
```

批量评价多个 run：

```bash
python -m goa_eval.cli evaluate-batch --runs-dir runs --output-dir outputs_batch
```

`runs` 目录示例：

```text
runs/
├── run_001/
│   ├── params.yaml
│   └── waveform.csv
└── run_002/
    ├── params.yaml
    └── waveform.csv
```

`params.yaml` 示例：

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

## 输出结果说明

单次 `evaluate-real` 主要输出：

- `real_metrics.csv`：逐级指标。
- `real_summary.json`：整次评价摘要。
- `score_summary.json`：硬约束、软评分、失败原因和警告原因。
- `diagnosis_report.md`：诊断报告。
- `real_waveform_report.md`：波形评价报告。
- `optimization_dataset.csv`：面向后续参数搜索的一行结构化数据。
- `run_manifest_real.json`：输入、配置、版本和有效性边界记录。
- `figures/`：波形和趋势图。

批量 `evaluate-batch` 主要输出：

- `all_metrics.csv`：所有 run 的逐级指标合并表，并附带参数字段。
- `all_scores.csv`：所有 run 的评分摘要。
- `leaderboard.csv`：按 `overall_score` 排序的候选结果表。
- `recommendations.md`：按 run 分组的下一轮参数建议。
- `run_manifest_batch.json`：批量评价元数据。

## 当前边界：simulation_only

CircuitPilot 当前只处理仿真数据。推荐器是规则系统，不训练深度学习模型，不直接调用 SPICE，也不声明已经完成全自动闭环优化。建议内容用于指导下一轮仿真设计和指标复核。

## Roadmap

- 固定更多输出 schema 与公开示例数据。
- 扩展参数空间定义和候选生成策略。
- 增加 PVT、Monte Carlo、负载变化和功耗指标。
- 在足够多真实参数-结果数据积累后，再评估贝叶斯优化、进化算法或机器学习模型。
- 增加外部仿真器调度接口，但保持仿真结果与实物验证边界清晰。

## License

MIT License. See [LICENSE](LICENSE).

## Acknowledgement

This project started from an 8T1C / GOA circuit simulation review workflow. The open-source version preserves the reusable software parts: simulation-data parsing, metric extraction, structured reporting, diagnosis, and conservative rule-based recommendations.
