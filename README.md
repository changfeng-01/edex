# CircuitPilot / 芯智调参

中文名：芯智调参：基于仿真数据的电路参数智能推荐系统  
English name: CircuitPilot: Simulation-Driven Intelligent Parameter Recommendation for Circuit Design

CircuitPilot 是一个面向电路仿真结果的评价、诊断和规则化参数推荐原型。项目从 8T1C / GOA 级联波形分析流程中抽取出可复用的软件部分，Python 包名保留为 `goa_eval`，便于兼容已有脚本和测试。

## 项目定位

当前版本处理的是仿真 CSV 文件，不是实物测试平台，也不是已经闭环接入外部 SPICE 的全自动优化系统。它完成的核心工作是：

- 读取外部仿真导出的 CSV 波形；
- 归一化 `XVAL` / `TIME`、`v(o1)`、`v(xs4.pu)` 等常见列名；
- 自动识别 `o1~oN` 输出节点的合法扫描窗口；
- 计算电压、时序、级间重叠、纹波、保持损失和误触发等指标；
- 生成 CSV / JSON / Markdown / PNG 评价包；
- 按硬约束、软评分和失败原因生成诊断结果；
- 基于当前指标给出保守的下一轮参数调整建议；
- 支持 `runs/run_001`、`runs/run_002` 形式的批量评价入口。

所有真实 CSV 评价输出必须保留以下边界标记：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

这些标记表示结果来自电路仿真 CSV，只能作为 simulation-only 工程分析依据，不能表述为物理样机或实验室测试结论。

## 为什么做这个项目

电路迭代过程中通常会产生大量波形 CSV、截图和手工记录。若只依赖人工查看，后续很难稳定比较不同参数组合，也难以把评价结果接入参数搜索或优化算法。CircuitPilot 的目标是把仿真结果整理为固定字段、固定单位、可复核的数据包，让后续的参数空间搜索、规则推荐和优化器接口可以基于结构化数据继续演进。

## 当前已实现功能

- 识别 `XVAL` / `TIME` 时间列，以及 `v(o1)`、`v(o2)`、`v(xs4.pu)` 等波形列名。
- 对 `o1~oN` 输出节点做逐级扫描窗口识别；当 CSV 只有 `o1~o8` 时按 8 级兼容评价。
- 支持 720 级级联配置接口；这表示框架可扩展，不表示示例数据已经包含 720 级真实仿真结果。
- 区分合法重复扫描脉冲和真正误触发，避免把周期性扫描误判为异常。
- overlap 使用时间区间端点交集累计，适配非均匀采样。
- ripple 在 hold / non-selected 窗口计算，并排除上升沿和下降沿区域。
- 低频保持时长不足时输出 `not_evaluable_with_current_waveform`，不硬判低频稳定性失败。
- 评分结果区分 `hard_constraints`、`soft_scores`、`failure_reasons` 和 `warning_reasons`。
- 批量评价输出 `all_metrics.csv`、`all_scores.csv`、`leaderboard.csv` 和 `recommendations.md`。
- 输出 `optimization_dataset.csv`，保留固定列和 provenance 字段，方便后续参数搜索流程读取。

## 仓库结构

```text
config/
└── spec.yaml                  # 默认阈值、权重和级联规模配置
docs/
├── project_overview.md         # 项目总览、数据流和扩展边界
├── metrics_spec.md             # 指标定义、单位和判定策略
├── schema_spec.md              # 输出文件 schema 与字段约定
└── github_upload_checklist.md  # 上传 GitHub 前的检查清单
examples/
├── sample_waveform.csv         # 可公开的小型示例波形
└── sample_params.yaml          # 可公开的示例参数
scripts/                        # 辅助脚本，核心逻辑不放在这里
src/goa_eval/                   # CircuitPilot 核心包
tests/                          # pytest 回归测试
```

核心模块：

```text
src/goa_eval/
├── cli.py              # evaluate-real / recommend / evaluate-batch
├── waveform_io.py      # 仿真 CSV 读取与列名归一化
├── windowing.py        # 脉冲窗口、重复扫描窗口、边沿区域、overlap 积分
├── metrics.py          # 单次波形指标计算和级联摘要
├── scorer.py           # 硬约束与软评分
├── diagnosis.py        # 诊断报告
├── recommendation.py   # 规则化参数建议
├── batch_eval.py       # 多 run 批量评价
├── param_space.py      # run 参数与参数空间读取
├── optimizer.py        # 后续优化器接口
├── reporter.py         # CSV / JSON / Markdown 输出
├── plotter.py          # PNG 图表
└── schemas.py          # schema_version、字段名和基础校验
```

## 安装

建议使用 Python 3.10 或更高版本。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[test]"
```

Windows PowerShell 可使用：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[test]"
```

运行测试：

```bash
python -m pytest -q
```

## 快速开始

运行公开示例波形：

```bash
python -m goa_eval.cli evaluate-real --waveform examples/sample_waveform.csv --output-dir outputs/example
```

生成单次推荐报告：

```bash
python -m goa_eval.cli recommend \
  --summary outputs/example/real_summary.json \
  --score outputs/example/score_summary.json \
  --metrics outputs/example/real_metrics.csv \
  --output outputs/example/recommendations.md
```

Windows PowerShell：

```powershell
python -m goa_eval.cli recommend `
  --summary outputs/example/real_summary.json `
  --score outputs/example/score_summary.json `
  --metrics outputs/example/real_metrics.csv `
  --output outputs/example/recommendations.md
```

批量评价多个 run：

```bash
python -m goa_eval.cli evaluate-batch --runs-dir runs --output-dir outputs_batch
```

## 单次评价输出

`evaluate-real` 会在指定输出目录中生成：

- `real_metrics.csv`：逐级指标表，每行对应一个输出节点或级。
- `real_summary.json`：整次评价摘要，包括通过状态、最差级、分段摘要和关键统计值。
- `score_summary.json`：硬约束、软评分、失败原因和警告原因。
- `diagnosis_report.md`：面向人工复核的诊断报告。
- `real_waveform_report.md`：波形评价 Markdown 报告。
- `optimization_dataset.csv`：面向后续参数搜索的一行结构化数据。
- `run_manifest_real.json`：输入文件、配置、阈值、版本和有效性边界记录。
- `figures/`：波形总览、趋势图、热力图和内部节点图。

字段细节见 [docs/schema_spec.md](docs/schema_spec.md)，指标定义见 [docs/metrics_spec.md](docs/metrics_spec.md)。

## 批量评价约定

批量入口读取 `runs/run_xxx` 目录。每个 run 至少需要一个 `waveform.csv`，可选 `params.yaml`。

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

`evaluate-batch` 主要输出：

- `all_metrics.csv`：所有 run 的逐级指标合并表，并附带参数字段。
- `all_scores.csv`：所有 run 的评分摘要。
- `leaderboard.csv`：按 `overall_score` 排序的候选结果表。
- `recommendations.md`：按 run 分组的下一轮参数建议。
- `run_manifest_batch.json`：批量评价元数据。

## 配置说明

默认配置位于 [config/spec.yaml](config/spec.yaml)。其中：

- `thresholds` 定义高低电平阈值、目标脉宽、最大 overlap ratio、最大 ripple、电压损失、延迟一致性和目标刷新率。
- `cascade` 定义级数、输出节点命名模式、分段大小和抽样绘图节点。
- `weights` 定义功能、质量、稳定性、一致性和成本评分权重。

命令行可覆盖部分阈值和级联配置，例如：

```bash
python -m goa_eval.cli evaluate-real \
  --waveform examples/sample_waveform.csv \
  --output-dir outputs/example \
  --stage-count 8 \
  --output-node-pattern "o{index}"
```

如果配置要求 720 级但当前 CSV 只包含 `o1~o8`，程序会按实际可识别输出节点兼容评价，并在报告中记录说明。

## 当前边界

CircuitPilot 当前只处理仿真数据。推荐器是规则系统，不训练深度学习模型，不直接调度外部 SPICE，也不声明已经完成全自动闭环优化。建议内容用于指导下一轮仿真设计和指标复核。

公开仓库不应上传私有或大体积仿真数据。上传前请查看 [docs/github_upload_checklist.md](docs/github_upload_checklist.md) 和 `.gitignore`。

## Roadmap

- 固定更多输出 schema 与公开示例数据。
- 扩展参数空间定义和候选生成策略。
- 增加 PVT、Monte Carlo、负载变化和功耗指标。
- 在积累足够多参数-结果数据后，再评估贝叶斯优化、进化算法或机器学习模型。
- 增加外部仿真器调度接口，同时保持仿真结果与实物验证边界清晰。

## License

MIT License. See [LICENSE](LICENSE).

## Acknowledgement

This project started from an 8T1C / GOA circuit simulation review workflow. The open-source version preserves the reusable software parts: simulation-data parsing, metric extraction, structured reporting, diagnosis, and conservative rule-based recommendations.
