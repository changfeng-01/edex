# CircuitPilot 历史迁移技术记录（退役后端移除前）

> 本文档仅保存 2026-05-28 的迁移前仓库快照，其中提到的专用后端、命令、
> adapter、配置和测试均已退役，不代表当前运行能力。当前架构请以
> `README.md`、`docs/multi_agent_evidence_chain.md` 和
> `docs/instrumentation_amplifier_agent_template_zh.md` 为准。

生成时间：2026-05-28  
当前工作区：`D:\EDA大赛`  
当前分支：`main` / `origin/main`  
报告用途：面向项目复盘、答辩说明、后续工程规划，以及直接粘贴给 GPT 继续讨论优化路线。

---

## 1. 一句话定位与边界

CircuitPilot / 芯智调参 是一个面向电路仿真结果的评估、诊断、候选参数生成、多轮搜索和证据编排原型。代码包名仍为 `goa_eval`，用于兼容早期 GOA / 8T1C 波形评估脚本；公开项目名使用 CircuitPilot。

它当前做的是：

- 读取仿真器或外部流程导出的 CSV / SPICE / SKY130 相关数据。
- 把波形、指标、约束、评分、诊断、候选参数和报告组织成可复核的结构化产物。
- 为下一轮仿真调参提供保守候选，而不是直接宣称芯片级或实验室级优化完成。
- 用多智能体证据链把已有评估产物、候选产物、critic 风险审查和决策报告串起来。
- 用 React dashboard 展示公开 demo 的核心指标、图表和优化快照。

必须保留的工程边界是：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

这两个标签的含义是：当前结果来自仿真 CSV、mock ngspice 或 ngspice/数据集链路，不是物理样片、量产芯片或实验室测量结论。即使本机存在 PDK/ngspice 工具链，也只能说明软件链路可以运行到某个阶段，不能自动升级为物理验证。

简言之：当前项目结论是仿真-only，不是物理验证。

---

## 2. 当前代码库和分支状态

### 2.1 主线状态

当前主线是 `main`，与 `origin/main` 对齐，最近提交为：

```text
7ed3700e Merge pull request #10 from changfeng-01/feature/evidence-index-benchmark
```

主线已经合入的主要能力包括：

- 参数候选生成、公开 demo、DeepSeek 分析、本地 `.env` runner。
- SKY130 transient / sweep / mainline 的主线门面和 mock fallback。
- profile-aware / topology-aware 评分、语义参数映射、候选规则。
- 多轮优化驱动，包括 adaptive / genetic / bayesian / surrogate / hybrid 策略入口。
- LangGraph 多智能体证据链。
- 多智能体 evidence index benchmark。
- React + Vite dashboard 和公开 demo 数据。

当前主线可视为本报告的能力基准。

### 2.2 分支摘要

本仓库存在多条历史和实验分支。报告只把 `main` 当作当前真实交付基线，其他分支用于解释演化来源和潜在风险。

| 分支 | 当前判断 | 与主线关系 |
| --- | --- | --- |
| `main` | 当前基准 | 与 `origin/main` 对齐 |
| `codex/sky130-ngspice-experiment` | SKY130/ngspice 早期实验线，含 `sky130-experiment` 和历史 GPT 报告 | 相对 `main` 独有 4 个提交，但落后主线 33 个提交 |
| `codex/langgraph-multi-agent-mvp` | LangGraph 多智能体早期 MVP | 独有 2 个提交，但落后主线 33 个提交；主线已扩展其能力 |
| `refactor/circuitpilot-structure` | 闭环候选生成和差异化评分早期结构分支 | 独有 2 个提交，但落后主线 33 个提交；主线已扩展 |
| `feature/multi-agent-mainline` | 多智能体主线集成分支 | 本地分支落后 `main` 4 个提交，主线已领先 |
| `codex/parameter-candidates` | 参数候选和公开发布硬化分支 | 主线已合入并继续前进 |
| `codex/multi-agent-evidence-benchmark` | 多智能体 benchmark 支撑分支 | 主线已合入并继续前进 |
| `codex/feature/evidence-index-benchmark` | evidence index benchmark 支撑分支 | 主线已合入并继续前进 |
| `codex/backup-local-main-d49f89f8` | 历史备份分支 | 包含大量 `frontend/node_modules`、`tools/` / PDK 类 vendor 文件风险，只作为历史参考 |

### 2.3 本地忽略产物边界

主线 `.gitignore` 已明确忽略：

- `tools/`
- `outputs/`
- `output/`
- `outputs_batch/`
- `runs/`
- `.env`
- `.env.*`
- `frontend/node_modules`
- 大型仿真输出如 `*.tr0`、`*.raw`、`*.lis`、`*.out`

因此，本报告把这些目录和文件视为本地工具链、缓存或实验输出，不把它们当作主线可复现能力的一部分。主线证明以 tracked source、tracked docs、tracked examples、tracked frontend public data 和测试为准。

---

## 3. 目录结构和模块职责

### 3.1 顶层目录

```text
config/
  CircuitPilot 当前主线配置：SKY130、profile、参数语义、validation、transient spec。

configs/
  早期 GOA / 默认评估配置，包括默认阈值、metrics、cascade 配置。

docs/
  项目说明、schema、指标说明、公开 demo 复现、多智能体证据链和计划文档。

examples/
  可公开的小样例波形、参数空间、demo_run 固定产物、多智能体任务样例。

frontend/
  React + Vite dashboard，读取 frontend/public/data 下的固定 demo 数据。

scripts/
  公共 demo 构建、版本比较、真实 DeepSeek runner、profile 闭环示例等辅助脚本。

src/goa_eval/
  核心 Python 包，包含 CLI、评估、评分、候选、SKY130、多智能体、报告和可视化。

tests/
  pytest 回归测试，覆盖主线 CLI、评估、候选、SKY130、多智能体和公开 demo。
```

### 3.2 Python 包结构

`src/goa_eval` 是核心工程边界。主要模块分工如下：

| 模块 | 职责 |
| --- | --- |
| `cli.py` | 命令行入口，集中注册评估、候选、SKY130、优化、多智能体命令 |
| `real_waveform_eval.py` | 单次真实仿真 CSV 评估主流程 |
| `waveform_io.py` | 读取和归一化仿真 CSV 列名 |
| `metrics.py` | 波形指标计算，包括电压、脉宽、延迟、重叠、纹波、保持等 |
| `windowing.py` | 脉冲窗口、重复扫描、边沿和 overlap 积分辅助逻辑 |
| `scorer.py` | 硬约束、软评分、profile score、失败和 warning 原因 |
| `diagnosis.py` | 面向人工复核的诊断报告 |
| `recommendation.py` | 根据指标和评分生成调参建议 |
| `optimizer.py` | 规则候选、constrained-random 候选、语义参数候选输出 |
| `multi_round_optimizer.py` | 多轮 sweep / candidate replay / leaderboard / history 驱动 |
| `sky130_transient.py` | SKY130 数据集 / netlist / ngspice transient 接入 |
| `sky130_sweep.py` | SKY130 参数 sweep 和汇总 |
| `sky130_mainline.py` | 主线轻量校验门面，包含 preflight、mock fallback、validation summary |
| `csv_import_adapter.py` | 面向通用 CSV 输入目录的适配入口 |
| `analysis_metrics.py` | OP / AC / DC / TRAN companion metrics 提取 |
| `circuit_profiles.py` | circuit profile 加载、解析和引用校验 |
| `parameter_semantics.py` | 参数语义标签、风险、tradeoff 和影响指标映射 |
| `parsers/*` | netlist、mapping、metric table、waveform 等解析器 |
| `report/*` | manifest、summary、metrics table、Markdown 报告写入 |
| `visualization/*` | 波形、指标、版本比较图表 |
| `multi_agent/*` | 多智能体任务 schema、状态、工具、critic、evidence index、LangGraph app |

### 3.3 前端结构

前端位于 `frontend/`，技术栈是：

- React 19
- Vite 7
- TypeScript
- Vitest
- Recharts
- lucide-react
- d3-dsv

核心页面 `frontend/src/App.tsx` 读取 `frontend/public/data`，并组合以下组件：

- `StatusOverview` / `CommandScreen`：展示运行概览和边界状态。
- `ConstraintPanel`：展示硬约束、失败原因和风险。
- `MetricTrends`：展示指标趋势。
- `FigureGallery`：展示公开 demo 中的 PNG 图表。
- `OptimizationSnapshot`：展示优化数据集或候选快照。

前端当前是公开 demo dashboard，不是在线运行后端仿真的交互式调参平台。

---

## 4. 核心数据流和 CLI 入口

### 4.1 主数据流

```text
仿真 CSV / SKY130 数据 / mock 数据
        |
        v
读取与归一化
  - waveform_io.py
  - parsers/*
  - csv_import_adapter.py
  - sky130_transient.py
        |
        v
指标计算
  - metrics.py
  - windowing.py
  - analysis_metrics.py
        |
        v
评分与诊断
  - scorer.py
  - diagnosis.py
  - recommendation.py
        |
        v
候选生成与多轮搜索
  - optimizer.py
  - multi_round_optimizer.py
  - sky130_sweep.py
  - sky130_mainline.py
        |
        v
报告、图表、benchmark、多智能体证据链
  - report/*
  - visualization/*
  - multi_agent/*
  - frontend/
```

### 4.2 主要 CLI 命令

当前 `python -m goa_eval.cli` 提供以下关键命令：

| 命令 | 作用 |
| --- | --- |
| `evaluate-real` | 读取单个仿真 CSV，生成指标、评分、图表、报告和 manifest |
| `recommend` | 根据 summary / score / metrics 生成 Markdown 调参建议 |
| `evaluate-batch` | 批量扫描多个 run，生成 leaderboard 和汇总 |
| `propose-candidates` | 根据推荐和参数空间生成下一轮候选参数 |
| `validate-config` | 校验 profile 和参数语义配置引用 |
| `analyze-params` | 调用或 mock DeepSeek 参数分析，生成中文分析报告 |
| `ai-profile-assistant` | 根据电路描述、指标和参数信息辅助生成 profile 建议 |
| `csv-import` | 将通用 CSV 输入目录适配成标准评估输出 |
| `simulate-run` | 统一适配单次 `csv-import` 或 `sky130-transient` |
| `simulate-sweep` | 统一适配批量 `csv-import` 或 `sky130-sweep` |
| `sky130-transient` | 从 SKY130 数据链路生成 transient 评估产物 |
| `sky130-sweep` | 对 SKY130 参数空间进行 sweep |
| `optimize-rounds` | 在 sweep 外层运行多轮搜索和 candidate replay |
| `sky130-mainline` | 主线轻量 SKY130 校验入口，支持 mock fallback 和 validation summary |
| `multi-agent-run` | 运行 LangGraph 多智能体证据链 |
| `benchmark-run` | 运行多智能体 benchmark suite |

旧的 `extract`、`parse`、`evaluate`、`all` 入口仍存在，主要用于早期设计目录、netlist、mapping 和 mock waveform 的兼容流程。

---

## 5. 评估、评分、诊断和候选生成方法

### 5.1 波形评估

`evaluate-real` 是当前最核心的单次评估入口。它完成：

- 读取 CSV 并归一化 `TIME` / `XVAL`、`v(o1)`、`o1` 等常见列名。
- 根据配置或自动探测识别输出节点，例如 `o1` 到 `oN`。
- 如果配置要求 720 级但样例 CSV 只有少量节点，会按当前 CSV 可识别节点兼容评价，并在 notes 中说明。
- 计算逐级指标、汇总指标、block summary 和全局指标。
- 提取可选 internal waveform 图表。
- 写出机器可读和人工可读产物。

主要输出包括：

- `real_metrics.csv`
- `real_summary.json`
- `score_summary.json`
- `analysis_metrics.json`
- `optimization_dataset.csv`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `run_manifest_real.json`
- `figures/*.png`

跨流程产物还包括 `optimization_*`、`multi_agent_*` 和 dashboard 数据与图表。

### 5.2 指标体系

当前指标覆盖：

- 高电平和低电平阈值。
- 输出脉冲是否存在。
- 脉宽与目标脉宽偏差。
- 相邻级延迟。
- 相邻级 overlap ratio。
- 非选通窗口纹波。
- 保持电压损失。
- false trigger 风险。
- 大规模 cascade 的 block stability 和趋势图。
- profile companion metrics，如 `dc_gain_db`、`bandwidth_3db_hz`、`static_power_w`、`frequency_hz` 等。

重要策略是：在波形长度或证据不足时，部分指标应标记为 not evaluable，而不是强行判定通过或失败。

### 5.3 评分方法

评分分为硬约束和软评分：

- 硬约束用于判断基础仿真检查是否通过。
- 软评分用于定位质量、稳定性、一致性和代价等短板。
- `score_summary.json` 记录 `hard_constraints`、`hard_constraint_failures`、`soft_scores`、`failure_reasons`、`warning_reasons`、`metric_penalties`、`profile_score` 等信息。
- 对 SKY130 类输出，`ripple_mode = diagnostic_only` 时，纹波可以保留为诊断证据，但不一定作为硬失败项。

### 5.4 诊断和推荐

`diagnosis.py` 和 `recommendation.py` 把指标短板转换为面向人工复核的文字建议。典型建议包括：

- overlap 偏高时复核输入脉冲间隔、驱动能力、负载和时序。
- delay 偏高时复核 driver resistance、NMOS/PMOS width、负载电容。
- ripple 或保持问题偏高时复核存储电容、负载、选通窗口和测量方式。
- missing pulse 或 sequence order 失败时复核驱动、阈值、负载和级联连接。

推荐报告仍然是下一轮仿真的建议，不是自动完成的工程优化结论。

### 5.5 候选参数生成

`propose-candidates` 支持两类主策略：

- `rule`：基于规则映射，输出确定性候选。
- `constrained-random`：在参数空间中生成单参数或组合参数候选，并按推荐和风险排序。

候选表字段包括：

- `candidate_id`
- `priority`
- `parameter`
- `direction`
- `candidate_value`
- `strategy`
- `candidate_kind`
- `changed_parameters`
- `parameters_json`
- `search_score`
- `parameter_group`
- `semantic_tags`
- `affected_metrics`
- `risk_tags`
- `risk_level`
- `expected_tradeoff`
- `requires_user_confirmation`
- `must_resimulate`
- `provenance`

其中 `must_resimulate = true` 是重要边界：候选参数必须进入下一轮仿真才能证明是否改善。

### 5.6 多轮优化

`optimize-rounds` 和 `multi_round_optimizer.py` 提供多轮搜索外壳：

- 每一轮运行 SKY130 sweep。
- 从上一轮 best run 或 candidate table 中生成下一轮参数空间。
- 输出 history、leaderboard、round summary、final param space 和 best next candidates。
- 支持 adaptive、genetic、bayesian、surrogate、hybrid 策略入口。
- 当样本不足、方差不足或模型无法可靠学习时，应记录 fallback，而不是假装模型已经学到规律。

当前多轮优化是 simulation-only 搜索轨迹，不是物理闭环。

---

## 6. SKY130/ngspice 与 mainline 校验能力

### 6.1 SKY130 transient

`sky130-transient` 面向 SKY130 数据链路，核心能力包括：

- 从公开数据集或 mock dataset JSON 读取 netlist / testbench。
- 调用本机 `ngspice` 或使用 `--mock-ngspice`。
- 转换为标准 CSV 波形。
- 保留 source netlist、testbench、metadata、netlist structure 和评估产物。
- 复用 `evaluate-real` 的指标、评分、诊断、候选和图表链路。

### 6.2 SKY130 sweep

`sky130-sweep` 读取 `config/sky130_sweep.yaml`，批量改写参数并运行多次 transient 评估。输出包括：

- `sky130_runs.csv`
- `sky130_sweep_runs.csv`
- `sky130_sweep_leaderboard.csv`
- `sky130_sweep_sensitivity.csv`
- `next_param_space.yaml`
- 每个 run 下的 waveform、summary、score、metrics、analysis 和 netlist 结构信息。

### 6.3 SKY130 mainline

`sky130-mainline` 是主线轻量门面，目标是给公开或 CI 风格流程提供可运行、可降级的验证入口：

- preflight 检查 PDK root、ngspice 命令、sweep 配置、validation 配置、mock dataset。
- 如果缺少 PDK/ngspice 且允许 fallback，则使用 mock ngspice。
- 调用 `run_multi_round_optimization`。
- 运行轻量 validation matrix。
- 写出 `mainline_validation.json`、`sky130_mainline_report.md`、`validation_summary.csv`。

这个入口的关键价值不是证明物理正确，而是让主线有一个稳定、可复核、不会因本机工具链缺失而完全失效的 SKY130 评估通道。

### 6.4 实验分支关系

`codex/sky130-ngspice-experiment` 上存在早期 `sky130-experiment` 入口和历史 GPT 报告。它相对主线独有 4 个提交，但落后主线 33 个提交。当前主线已经采用更丰富的 `sky130-transient`、`sky130-sweep`、`optimize-rounds`、`sky130-mainline` 路线，因此该实验分支只作为演化证据和历史参考，不应直接覆盖主线。

---

## 7. 多智能体证据链和 benchmark

### 7.1 设计定位

多智能体层不是替代评估器、评分器、优化器或 SKY130 sweep 的新核心算法，而是现有证据工具之上的编排层。它负责：

- 根据任务类型选择 domain agent。
- 读取已有 artifact。
- 记录 handoff 和 trace。
- 运行 critic 检查。
- 写出决策报告、memory 和 optimization loop record。

它仍然保持：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

### 7.2 Agent 分工

| Agent | 职责 |
| --- | --- |
| `SupervisorAgent` | 初始化共享状态、计划元数据和边界上下文 |
| `RouterAgent` | 根据 task type、profile 和 inputs 选择 domain path |
| `GOAAgent` | 解释 GOA / 8T1C 波形、overlap、ripple、voltage loss 和 false-trigger 风险 |
| `SKY130Agent` | 解释 SKY130/ngspice 证据、score summary、timing risk 和候选上下文 |
| `GenericWaveformAgent` | 处理非特定电路族的 waveform-derived artifact |
| `NetlistAgent` | 做轻量 netlist integrity 检查并说明 parser 限制 |
| `EvaluationAgent` | 读取 leaderboard、score summary、real metrics 等证据 |
| `OptimizationAgent` | 调用现有 optimizer wrapper 创建受限 next candidates |
| `CriticAgent` | 检查 schema、边界标签、硬约束、缺失指标、风险和禁止的物理验证表述 |
| `ReportAgent` | 写最终决策报告和优化证据卡 |

### 7.3 输入和输出

可读取的证据包括：

- `real_summary.json`
- `real_metrics.csv`
- `score_summary.json`
- `analysis_metrics.json`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `next_candidates.csv`
- `best_next_candidates.csv`
- `optimization_history.json`
- `optimization_leaderboard.csv`
- `validation_summary.csv`
- `run_manifest_real.json`
- `sky130_mainline_report.md`

典型输出包括：

- `multi_agent_plan.json`
- `multi_agent_trace.jsonl`
- `multi_agent_handoff_trace.jsonl`
- `critic_report.json`
- `multi_agent_memory.json`
- `multi_agent_decision_report.md`
- `optimization_loop_record.json`
- `optimization_decision_card.md`

### 7.4 benchmark

主线包含 `benchmark-run` 和 `benchmarks/multi_agent/sky130_evidence_case`，用于对多智能体证据链输出进行固定任务验证。它验证的是证据读取、风险整理、决策记录和输出契约，不是验证物理电路。

---

## 8. 前端 dashboard 与公开 demo

### 8.1 公开 demo

公开 demo 位于 `examples/demo_run/`，输入基于：

- `examples/sample_waveform.csv`
- `examples/sample_params.yaml`

构建脚本是：

```text
scripts/build_public_demo.py
```

它会依次运行：

- `evaluate-real`
- `recommend`
- `propose-candidates`
- `analyze-params`，使用固定 mock response，避免公开 demo 依赖真实 API key
- 同步 dashboard 所需数据到 `frontend/public/data`

### 8.2 demo_run 当前产物

`examples/demo_run/` 包含：

- `diagnosis_report.md`
- `llm_parameter_analysis.json`
- `llm_parameter_analysis.md`
- `llm_parameter_analysis_real.json`
- `llm_parameter_analysis_real.md`
- `next_candidates.csv`
- `next_candidates.md`
- `optimization_dataset.csv`
- `real_metrics.csv`
- `real_summary.json`
- `real_waveform_report.md`
- `recommendations.md`
- `run_manifest_real.json`
- `score_summary.json`
- `figures/`

这些文件是主线公开展示和 dashboard 的固定样例结果。它们适合证明软件输出格式和展示链路，不适合证明某个真实芯片或真实工艺优化已经完成。

### 8.3 dashboard

`frontend/public/data` 存放 dashboard 静态数据：

- `real_summary.json`
- `score_summary.json`
- `real_metrics.csv`
- `optimization_dataset.csv`
- `figures/*.png`

前端当前读取这些静态文件展示状态、指标、图表和优化快照。它不是一个在线编辑参数、实时触发仿真、实时写回后端的工作台。

---

## 9. 已生成结果和可复现路径

### 9.1 单次公开 demo 复现

推荐复现入口：

```powershell
python scripts/build_public_demo.py
```

该脚本会重建 `examples/demo_run`，并同步 `frontend/public/data`。

也可以手动执行：

```powershell
python -m goa_eval.cli evaluate-real `
  --waveform examples/sample_waveform.csv `
  --output-dir outputs/example

python -m goa_eval.cli recommend `
  --summary outputs/example/real_summary.json `
  --score outputs/example/score_summary.json `
  --metrics outputs/example/real_metrics.csv `
  --output outputs/example/recommendations.md

python -m goa_eval.cli propose-candidates `
  --summary outputs/example/real_summary.json `
  --score outputs/example/score_summary.json `
  --metrics outputs/example/real_metrics.csv `
  --param-space examples/sample_params.yaml `
  --strategy constrained-random `
  --max-candidates 10 `
  --seed 42 `
  --output-csv outputs/example/next_candidates.csv `
  --output-md outputs/example/next_candidates.md
```

### 9.2 SKY130 mainline 复现

轻量入口：

```powershell
python -m goa_eval.cli sky130-mainline `
  --output-root outputs/sky130_mainline `
  --mock-if-unavailable
```

如果本机有 PDK/ngspice，可以显式传入：

```powershell
python -m goa_eval.cli sky130-mainline `
  --pdk-root tools/volare-pdks/sky130A `
  --ngspice-cmd tools/ngspice/Spice64/bin/ngspice.exe `
  --output-root outputs/sky130_mainline `
  --no-mock-if-unavailable
```

注意：工具链可用只说明可以尝试真实 ngspice 路径，不说明物理验证完成。

### 9.3 多智能体运行

```powershell
python -m goa_eval.cli multi-agent-run `
  --task examples/tasks/sky130_multi_agent_task.yaml `
  --output-dir outputs/multi_agent_sky130
```

如果未安装 `langgraph`，该命令会按可用性检查失败；`pyproject.toml` 中的 optional dependency 是 `agent = ["langgraph"]`。

### 9.4 前端运行

```powershell
cd frontend
npm install
npm test
npm run dev
```

前端读取 `frontend/public/data`，所以要先确保公开 demo 数据存在或已由 `scripts/build_public_demo.py` 同步。

---

## 10. 做到的程度、没做到的事情、主要风险

### 10.1 已做到

项目已经从早期单点波形评估，扩展为一条较完整的软件证据链：

- 能读取真实仿真 CSV 并生成稳定输出。
- 能按阈值、窗口和 profile 计算指标。
- 能把硬约束、软评分、失败原因和 warning 原因结构化。
- 能生成人工诊断报告和下一轮候选参数。
- 能基于 profile 和 semantic tags 做更工程化的候选映射。
- 能做 SKY130 transient / sweep / mainline 轻量链路。
- 能做多轮搜索和 candidate replay。
- 能将证据交给多智能体链路进行 routing、critic 和报告。
- 能用 benchmark 检查多智能体证据输出。
- 能用 React dashboard 展示固定公开 demo。
- 有较大规模 pytest 和前端测试覆盖。

### 10.2 尚未做到

不能把当前项目描述为以下状态：

- 已完成真实芯片验证。
- 已完成实验室硬件测试。
- 已完成 tape-out 级 signoff。
- 已形成工业级自动调参闭环。
- 已训练出稳定可泛化的机器学习代理模型。
- 已证明候选参数在真实工艺、PVT、load、corner 和版图寄生条件下稳定改善。
- 已把前端做成在线调参工作台。

### 10.3 主要风险

当前主要风险不是“没有功能”，而是容易过度表述功能：

- 把 simulation-only 写成 physical validation。
- 把 mock ngspice 或 preflight 写成真实工程证明。
- 把候选参数写成已经优化完成的参数。
- 把 ignored `outputs/` 或本机 `tools/` 当成 tracked repo 能力。
- 把落后主线的实验分支内容当成当前主线。
- 把多智能体证据链写成会自动创造新仿真证据的 AI 系统。
- 把 dashboard 写成在线仿真平台。

### 10.4 历史分支风险

`codex/backup-local-main-d49f89f8` 曾出现大量 vendor/tool 文件，包括 `frontend/node_modules` 和 `tools/` / PDK 类内容。这类内容会污染 diff、放大仓库、引入授权和复现风险。当前主线已经通过 `.gitignore` 和 tracked-file 状态把这些内容排除在外；后续发布时仍应检查：

```powershell
git ls-files tools frontend/node_modules
git check-ignore tools frontend/node_modules outputs .env
```

---

## 11. 后续路线图

### 11.1 近期优先级

1. 保持主线健康：继续让 `python -m pytest -q` 和 `npm test` 成为发布前检查。
2. 固化公开 demo：确保 `scripts/build_public_demo.py` 能稳定重建 `examples/demo_run` 和 `frontend/public/data`。
3. 完善 SKY130 mainline：继续收敛 `sky130-mainline` 的 validation matrix、fallback 原因和报告解释。
4. 强化候选复跑闭环：把 `next_candidates.csv` 到下一轮 sweep 的 replay 路径做成更明确、更可追踪的工作流。
5. 强化 profile-aware 配置：让 OTA、comparator、oscillator、VCO 等 profile 的指标、候选规则和参数语义更完整。

### 11.2 中期目标

1. 引入更真实的样本库：积累多轮、多 profile、多参数空间的仿真结果。
2. 扩展 benchmark：增加失败样例、缺失指标样例、overclaim 样例和 replay 样例。
3. 改进前端：从静态 demo dashboard 升级到可选择数据包、比较 run、查看候选 lineage 的评审工具。
4. 改进多智能体：让 agent 输出更严格依赖 evidence index，减少自由文本解释空间。
5. 增强 schema：把 artifact 版本、输入 hash、候选 provenance 和 validation 状态做成更统一的契约。

### 11.3 长期目标

1. 真正闭合仿真优化循环：候选生成、仿真复跑、结果回灌、排行榜更新、停止条件判断。
2. 在样本足够后评估 ML / surrogate model，而不是过早宣称代理模型能力。
3. 接入 PVT、corner、load、版图寄生等更真实约束。
4. 将物理验证作为独立阶段记录，不能和 simulation-only 输出混写。
5. 建立可发布的公开数据包、实验协议和结果审计流程。

---

## 12. 可直接粘贴给 GPT 的上下文提示词

### 12.1 项目总览提示词

```text
你现在协助分析 CircuitPilot / 芯智调参 项目。

这是一个基于仿真数据的电路评估、诊断、候选参数生成、多轮搜索和证据编排原型。Python 包名是 goa_eval，公开项目名是 CircuitPilot。

当前主线能力包括：
- evaluate-real：读取仿真 CSV，生成 real_metrics.csv、real_summary.json、score_summary.json、analysis_metrics.json、diagnosis_report.md、real_waveform_report.md、optimization_dataset.csv、run_manifest_real.json 和 figures。
- recommend：根据 summary / score / metrics 生成调参建议。
- propose-candidates：根据推荐和参数空间生成下一轮候选参数，支持 rule 和 constrained-random。
- sky130-transient / sky130-sweep / sky130-mainline：接入 SKY130/ngspice 或 mock ngspice 的仿真评估链路。
- optimize-rounds：运行多轮 sweep / candidate replay / leaderboard / history。
- multi-agent-run / benchmark-run：运行 LangGraph 多智能体证据链和 benchmark。
- frontend：React + Vite dashboard，读取 frontend/public/data 的公开 demo 数据。

所有结论必须保留：
data_source = real_simulation_csv
engineering_validity = simulation_only

请不要把它描述成物理芯片验证、实验室验证、tape-out signoff 或工业级自动调参闭环。候选参数只是下一轮仿真建议，必须复跑仿真才能确认改善。
```

### 12.2 优化路线讨论提示词

```text
请基于 CircuitPilot 当前状态设计下一阶段优化路线。

优先考虑：
1. 如何把 next_candidates.csv 安全地 replay 到下一轮 sky130-sweep。
2. 如何设计 optimization_leaderboard.csv、optimization_history.json 和 validation_summary.csv 的字段，使候选来源、复跑结果和是否达标清晰可追踪。
3. 如何避免把 simulation-only 结果误写成 physical validation。
4. 如何在样本不足时保持 bayesian / surrogate / hybrid 策略的 fallback 诚实。
5. 如何为 OTA、comparator、oscillator、VCO profile 扩展参数语义和 candidate rules。

请输出工程实施顺序、schema 变更、测试计划和风险控制，不要直接建议大规模重写。
```

### 12.3 报告审阅提示词

```text
请审阅 CircuitPilot 的技术报告，重点检查是否存在过度声明。

必须检查：
- 是否所有仿真结论都保留 data_source = real_simulation_csv 和 engineering_validity = simulation_only。
- 是否把 PDK/ngspice 可用性误写成物理验证。
- 是否把候选参数误写成已经完成的优化结果。
- 是否混淆 main 分支、实验分支、本地 ignored outputs 和 tracked source。
- 是否把 React dashboard 误写成在线仿真平台。
- 是否把多智能体证据链误写成能自动产生新仿真证据的系统。

请以“问题 / 风险 / 建议改法”的格式输出。
```

---

## 13. 验证快照

本报告生成前的只读摸底已经确认：

- 当前分支：`main`
- 主线与 `origin/main` 对齐。
- 目标报告文件在生成前不存在。
- 主线 tracked 文件数量约 272。
- `tools/`、`outputs/`、`.env`、`frontend/node_modules` 被忽略。
- Python 回归测试覆盖约 199 个用例。
- 前端 Vitest 覆盖 2 个测试文件、5 个用例。

报告生成后已执行：

```powershell
git diff --check -- docs/PROJECT_TECHNICAL_REPORT_FOR_GPT.md
python -m pytest -q
cd frontend
npm test
```

实际结果：

- `git diff --check -- docs/PROJECT_TECHNICAL_REPORT_FOR_GPT.md`：无输出，格式检查通过。
- UTF-8 读取检查：`ReplacementChars = 0`。
- 内容检查：命中 `data_source = real_simulation_csv`、`engineering_validity = simulation_only`、`仿真-only，不是物理验证`、`codex/backup-local-main-d49f89f8`、`optimization_*`、`multi_agent_*`。
- `python -m pytest -q`：`199 passed, 3 warnings in 160.52s`；warning 为 `tests/test_real_waveform_eval.py` 中 pandas `to_datetime(unit=...)` 的 FutureWarning。
- `npm test` in `frontend/`：`Test Files 2 passed (2)`，`Tests 5 passed (5)`。

因此，这份报告可以作为 2026-05-28 当前主线状态的可信说明；其结论仍严格限定在 simulation-only 边界内。
