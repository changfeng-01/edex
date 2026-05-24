# CircuitPilot Project Overview

CircuitPilot / 芯智调参是一个基于仿真 CSV 的电路评价、诊断和规则化参数推荐原型。项目面向 8T1C / GOA 级联波形分析场景，但核心模块尽量保持通用：输入是仿真波形和可选参数表，输出是稳定的指标、报告、图表和推荐结果。

Python 包名仍为 `goa_eval`，这是为了兼容已有 GOA 波形评价脚本和测试；公开项目名使用 CircuitPilot。

## 目标

本项目要解决的问题是：把仿真波形从“人工看图和手工记录”转成“可复核、可比较、可继续优化”的结构化数据。

当前目标包括：

- 统一读取不同导出习惯下的 CSV 波形列名；
- 自动识别输出节点扫描窗口；
- 用固定单位计算电压、时序、重叠、纹波和保持类指标；
- 将单次仿真结果输出为 CSV / JSON / Markdown / PNG 文件包；
- 将多个参数 run 汇总成可排序、可筛选的批量评价结果；
- 给出保守的下一轮参数调整建议；
- 为未来参数搜索、贝叶斯优化或代理模型训练保留稳定数据接口。

## 当前边界

所有真实波形输出必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

这意味着：

- 结果来自仿真 CSV，不是物理样机测试；
- 当前版本不直接调用外部 SPICE 或 AETHER；
- 当前推荐器是规则系统，不是训练完成的机器学习模型；
- `PASS_BASIC_SIMULATION_CHECK` 只表示配置下的仿真 CSV 检查通过，不表示真实产品或实验样机通过。

## 数据流

```text
simulation CSV / sample CSV
        |
        v
waveform_io.py
  - read XVAL / TIME
  - normalize v(o1), v(xs4.pu), etc.
        |
        v
real_waveform_eval.py
  - resolve output nodes
  - apply config/spec.yaml
        |
        v
metrics.py + windowing.py
  - legal pulse windows
  - voltage / timing / overlap / ripple / hold metrics
        |
        v
scorer.py + diagnosis.py + recommendation.py
  - hard constraints
  - soft scores
  - failure and warning reasons
  - next tuning suggestions
        |
        v
reporter.py + plotter.py
  - CSV / JSON / Markdown / PNG outputs
```

## 主要入口

### 单次真实仿真 CSV 评价

```bash
python -m goa_eval.cli evaluate-real --waveform examples/sample_waveform.csv --output-dir outputs/example
```

输出包括：

- `real_metrics.csv`
- `real_summary.json`
- `score_summary.json`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `optimization_dataset.csv`
- `run_manifest_real.json`
- `figures/`

### 单次推荐报告

```bash
python -m goa_eval.cli recommend --summary outputs/example/real_summary.json --score outputs/example/score_summary.json --metrics outputs/example/real_metrics.csv --output outputs/example/recommendations.md
```

推荐报告只给出下一轮工程复核或调参建议，不声明自动优化已经完成。

### 批量评价

```bash
python -m goa_eval.cli evaluate-batch --runs-dir runs --output-dir outputs_batch
```

批量入口扫描 `runs/run_*` 目录。每个 run 至少包含：

```text
run_001/
├── waveform.csv
└── params.yaml    # 可选，但推荐提供
```

批量输出包括：

- `all_metrics.csv`
- `all_scores.csv`
- `leaderboard.csv`
- `recommendations.md`
- `run_manifest_batch.json`

## 配置模型

默认配置文件为 `config/spec.yaml`。

### thresholds

用于定义评价阈值：

- `high_threshold`：高电平判定阈值，单位 V。
- `low_threshold`：低电平或误触发判定阈值，单位 V。
- `target_pulse_width_us`：目标扫描脉宽，单位 us。
- `pulse_width_tolerance_us`：脉宽容差，单位 us。
- `max_overlap_ratio`：相邻级最大允许重叠比例。
- `max_ripple_v`：非选通窗口最大允许纹波，单位 V。
- `max_voltage_loss_v`：保持电压损失阈值，单位 V。
- `max_delay_std_us`：级间延迟标准差阈值，单位 us。
- `min_voh_margin_v`：高电平裕量阈值，单位 V。
- `target_refresh_hz`：低频保持目标刷新率。

程序内部会把 `*_us` 转换为秒。

### cascade

用于定义级联规模和报告摘要方式：

- `stage_count`：目标级数，例如 720。
- `output_node_pattern`：输出节点命名模板，例如 `o{index}`。
- `stage_group_size`：分段摘要大小，例如每 60 级为一组。
- `sample_nodes`：大规模级联绘图时抽样展示的节点序号。

如果 CSV 实际只包含 `o1~o8`，而配置为 720 级，程序会回退到实际可识别节点做兼容评价。

### weights

用于软评分聚合：

- `function_score`
- `quality_score`
- `stability_score`
- `consistency_score`
- `cost_score`

硬约束和软评分分开记录。硬约束失败时，软评分仍保留用于分析具体短板。

## 模块职责

- `src/goa_eval/cli.py`：命令行入口。
- `src/goa_eval/waveform_io.py`：读取仿真 CSV，规范化时间列和波形列名。
- `src/goa_eval/windowing.py`：窗口检测、合法脉冲、非选通区域、端点 overlap 积分。
- `src/goa_eval/metrics.py`：逐级指标和级联摘要。
- `src/goa_eval/scorer.py`：硬约束、软评分和总体评分。
- `src/goa_eval/topology_profiles.py`：将 topology 映射到 `default` / `ota` / `comparator` / `oscillator` 评价 profile。
- `src/goa_eval/analysis_metrics.py`：读取 OP/AC/DC/TRAN companion CSV 并生成 `analysis_metrics.json`。
- `src/goa_eval/diagnosis.py`：面向人工复核的诊断语句。
- `src/goa_eval/recommendation.py`：规则化下一轮参数建议。
- `src/goa_eval/batch_eval.py`：多 run 汇总、榜单和批量推荐。
- `src/goa_eval/param_space.py`：参数文件解析与数值化辅助字段。
- `src/goa_eval/optimizer.py`：未来优化器接口占位。
- `src/goa_eval/reporter.py`：真实波形评价输出。
- `src/goa_eval/plotter.py`：PNG 图表生成。
- `src/goa_eval/schemas.py`：公共版本号、字段列表和基础 schema 校验。

## 输出设计原则

- 机器可读文件优先稳定：CSV / JSON 字段名尽量固定。
- Markdown 报告面向人工复核，只展示摘要和关键解释，避免在 720 级场景中堆满逐级明细。
- 完整逐级结果保存在 `real_metrics.csv`。
- 大规模级联使用 `block_summary`、趋势图和热力图定位风险段。
- `optimization_dataset.csv` 保留固定列和空值占位，避免下游优化流程因列缺失而中断。
- 所有仿真输出都应保留 `simulation_only` 边界。

## 非目标

当前版本不做以下声明：

- 不声明实物测试通过；
- 不声明已经完成外部仿真器闭环调度；
- 不声明已经训练可用的机器学习代理模型；
- 不把规则建议等同于自动优化结果；
- 不上传私有大型仿真 CSV、`.tr0` 或本地报告压缩包。

## 推荐开发顺序

1. 固定公开示例数据和 schema。
2. 保持 `python -m pytest -q` 可运行。
3. 对新增指标先补 schema 和测试，再接入报告。
4. 对批量评价输出保持参数字段和 provenance 字段。
5. 积累足够多参数-结果样本后，再评估候选生成、贝叶斯优化、进化算法或代理模型。
