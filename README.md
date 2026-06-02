# CircuitPilot / 芯智调参
## Hybrid GOA Optimizer

`hybrid-goa-optimize` adds a GOA-first, simulation-only candidate optimizer that combines surrogate prediction, failure-guided repair, and Pareto ranking without requiring real ngspice or SKY130. See `docs/goa_hybrid_optimizer.md`.

```bash
python -m goa_eval.cli hybrid-goa-optimize \
  --leaderboard outputs/run/optimization_leaderboard.csv \
  --param-space examples/sample_params.yaml \
  --output-root outputs/hybrid_goa
```

## GOA Strategy Benchmark

`goa-strategy-benchmark` compares random, adaptive, surrogate, repair, and hybrid_goa candidate-generation strategies for GOA circuits. It is simulation-only and does not require real ngspice or SKY130. See `docs/goa_strategy_benchmark.md`.

```bash
python -m goa_eval.cli goa-strategy-benchmark \
  --leaderboard outputs/run/optimization_leaderboard.csv \
  --param-space examples/sample_params.yaml \
  --output-root outputs/goa_strategy_benchmark
```

## Multi-Agent Evidence Chain

The `multi-agent-run` command adds a local orchestration layer over the existing evidence tools. It routes tasks through Supervisor, Router, GOA/SKY130/Generic/Netlist, Evaluation, Optimization, Critic, and Report agents, then writes trace, handoff, memory, critic, decision, and optimization-loop artifacts. See `docs/multi_agent_evidence_chain.md`.

```bash
python -m goa_eval.cli multi-agent-run \
  --task examples/tasks/sky130_multi_agent_task.yaml \
  --output-dir outputs/multi_agent_sky130
```

## Evidence Metadata

CircuitPilot now writes additive evidence metadata to summary, score, manifest, mainline validation, and related SKY130 status outputs.

| Level | Meaning |
|---|---|
| Level 0 | public demo CSV. |
| Level 1 | external CSV. |
| Level 2 | mock-ngspice software-flow evidence. |
| Level 3 | real ngspice + SKY130 PDK, with no mock. |
| Level 4 | multi-round optimization with nominal rerun evidence. |
| Level 5 | validation matrix evidence. |

Machine-readable fields include `evidence_level`, `simulation_backend`, `mock_used`, `pdk_available`, `ngspice_available`, `reportable_as_real_ngspice`, and `optimizer_claim_level`. `reportable_as_real_ngspice=true` is only valid when real ngspice and a SKY130 PDK are available and no mock path was used.

Evidence-loop CLI additions:

- `sky130-mainline --require-real-ngspice` disables `--mock-ngspice` and mock fallback; missing PDK or ngspice causes the command to fail.
- `strategy-benchmark` compares `random`, `adaptive`, `genetic`, `bayesian`, `surrogate`, and `hybrid` over fixed seeds, rounds, and max runs per round.
- `random` is a baseline strategy that does not read best-candidate replay.
- Benchmark outputs now include scenario/fairness metadata, hard-constraint pass rates, not-evaluable rates, validation rollups, baseline improvement fields, and `strategy_leaderboard.csv`.
- Every generated `figures/*.png` is listed in `figures/figure_manifest.json` with `source_type=matplotlib_local`, `ai_generated=false`, `llm_used=false`, data-source labels, and evidence level.

中文名：芯智调参：基于仿真数据的电路参数智能推荐系统  
English name: CircuitPilot: Simulation-Driven Intelligent Parameter Recommendation for Circuit Design

CircuitPilot 是一个面向电路仿真结果的评价、诊断、参数候选生成和仿真调度原型。项目最早来自 8T1C / GOA 级联波形分析流程，当前已扩展到 SKY130/ngspice 数据接入、拓扑感知评分、参数扫描和多轮候选搜索。Python 包名仍保留为 `goa_eval`，用于兼容已有脚本和测试；公开项目名使用 CircuitPilot。

## 项目定位

当前版本处理的是仿真数据和仿真器输出文件，不是实物测试平台。所有真实 CSV 评价输出必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

这表示结果只能作为仿真分析、下一轮参数建议和软件链路验证依据，不能写成芯片、样机或实验室实测结论。`optimize-rounds` 能调度多轮仿真扫描并生成候选，但仍然是 simulation-only 搜索轨迹，不等同于已经完成物理验证的自动优化闭环。

## 最近更新总结

本轮项目更新的重点是把早期的单次波形评价工具，扩展为更接近“仿真评价 + 参数候选 + 多轮搜索”的完整软件链路。

### 1. SKY130 / ngspice 链路

- 新增 `sky130-transient`，可从公开 SKY130 数据集 testbench 读取 SPICE，调用本机 `ngspice`，并转换为 `TIME,v(o1),...` 兼容波形。
- 新增 `sky130-sweep`，读取 `config/sky130_sweep.yaml`，改写 SPICE 参数，批量运行仿真、评价、打分和候选生成。
- 每个 SKY130 run 会保留 `source_netlist.spice`、`testbench.spice`、`waveform.csv`、`analysis_metrics.json`、`netlist_structure.json`、`sky130_metadata.json` 和状态文件。
- 根目录汇总 `sky130_runs.csv`、`sky130_sweep_runs.csv`、`sky130_sweep_leaderboard.csv`、`sky130_sweep_sensitivity.csv` 和 `next_param_space.yaml`。
- 支持 `--mock-ngspice` 和 mock 数据入口，用于没有 PDK/ngspice 时验证软件流程。

### 2. 拓扑感知评价与结构特征

- 新增 `config/sky130_eval_profiles.yaml`，内置 `default`、`ota`、`comparator`、`oscillator` profile，并支持 `two_stage_opamp`、`vco` 等别名。
- 新增 OP/AC/DC/TRAN companion metrics，写入 `analysis_metrics.json`，并在 `score_summary.json` 中形成 `profile_score`、`analysis_metric_penalties` 和 `not_evaluable_metrics`。
- OTA 关注 `dc_gain_db`、`bandwidth_3db_hz`、`unity_gain_hz`、`slew_rate_v_per_s`、`output_swing_v`、`static_power_w`。
- Comparator 关注 `switching_threshold_v`、`output_swing_v`、`static_power_w`。
- Oscillator / VCO 关注 `frequency_hz`、`period_std_s`、`output_swing_v`、`startup_time_s`、`static_power_w`。
- 新增 SPICE netlist 结构解析，提取 MOS、电容、电阻、电流源、模型和节点数量等压缩摘要字段，作为 companion metadata，不直接作为物理通过证据。

### 3. 评分、推荐和候选生成增强

- `score_summary.json` 现在更清楚地区分 `hard_constraints`、`hard_constraint_failures`、`soft_scores`、`failure_reasons`、`warning_reasons` 和 `metric_penalties`。
- `propose-candidates` 默认使用 `constrained-random`，支持单参数和两参数组合候选，并保留固定 seed 以便复现。
- 候选生成会读取 waveform penalty 和 topology-aware penalty，提高主要失效指标对应参数的搜索权重。
- Profile candidate rules 可将 `dc_gain_db`、`static_power_w`、`frequency_hz` 等 profile 指标映射到参数空间中的 `m1_width`、`m2_width`、`load_cap`、`ibias` 等候选。
- 新增 `config/circuit_profiles.yaml` 和 `config/parameter_semantics.yaml`，支持把候选生成从固定参数名匹配扩展为语义标签匹配，例如 `input_pair_width`、`bias_current`、`compensation_capacitance`。
- `All_pulses_exist`、`Seq_pass` 等硬约束失败也能生成恢复候选，例如驱动能力、负载、电平阈值复核类建议。
- `next_candidates.csv` 增加 `strategy`、`candidate_kind`、`changed_parameters`、`parameters_json`、`search_score`、`rationale`、`parameter_group`、`semantic_tags`、`must_resimulate` 等字段。

### 4. 多轮优化驱动

- 新增 `optimize-rounds`，在 `sky130-sweep` 外层运行多轮搜索，并把上一轮最佳 run 的 `next_candidates.csv` 反馈到下一轮参数空间。
- 支持 `random`、`adaptive`、`genetic`、`bayesian`、`surrogate`、`hybrid` 策略；`random` 不读取 best candidate replay，作为纯随机/多样性基线。
- `bayesian` 使用 Gaussian-process expected improvement；`surrogate` 使用 random-forest score model；`hybrid` 组合规则候选、遗传变异、模型排序和多样性回退。
- 当历史样本不足或目标分数无有效方差时，模型策略会记录 fallback 状态，并选择未尝试过的多样化网格点，避免伪装成模型已学到规律。
- 输出 `optimization_history.json`、`optimization_leaderboard.csv`、`round_summary.csv`、`final_param_space.yaml` 和 `best_next_candidates.csv`。
- Leaderboard 保留候选来源字段，包括 `candidate_source`、`source_candidate_id`、`source_candidate_trigger_metric`、`source_candidate_parameters_json` 和 `rank_status`。
- `strategy-benchmark` 在多策略横向比较中额外输出 `strategy_leaderboard.csv`，并在 summary 中记录场景、同条件比较约束、baseline 分组、相对 random 的改进率、不可评价率和仿真效率。

### 5. 公开 demo、DeepSeek 分析和文档 schema

- 公开 demo 位于 `examples/demo_run/`，可由 `scripts/build_public_demo.py` 固定重建。
- `analyze-params` 可在已有 summary、score、metrics、candidates 基础上调用 DeepSeek V4 生成中文参数分析；真实 key 只应放在本地 `.env` 或当前进程环境变量中。
- `docs/schema_spec.md`、`docs/metrics_spec.md` 和 `docs/project_overview.md` 已补充 topology-aware metrics、SKY130 输出、多轮优化输出和候选字段约定。
- 单节点或少节点波形绘图逻辑已加固，避免小规模输出时图表生成失败。

## 已实现能力

- 读取外部仿真导出的 CSV 波形，归一化 `XVAL` / `TIME`、`v(o1)`、`v(xs4.pu)` 等常见列名。
- 自动识别 `o1~oN` 输出节点扫描窗口，兼容 `o1~o8` 小样例和大规模级联配置。
- 计算电压、脉宽、延迟、重叠、纹波、保持损失、误触发和级联摘要指标。
- 区分合法重复扫描脉冲和真正误触发。
- 在波形时长不足时将低频保持标为 `not_evaluable_with_current_waveform`，不强行判定通过或失败。
- 生成 CSV / JSON / Markdown / PNG 评价包。
- 输出批量榜单、推荐报告、优化数据集和下一轮参数候选表。
- 接入 SKY130/ngspice 仿真扫描，并保留 SPICE 结构摘要和 profile companion metrics。
- 调度多轮离散参数搜索，并保留候选来源、跳过原因和模型 fallback 状态。

## 仓库结构

```text
config/
├── circuit_profiles.yaml        # 通用 circuit profile、目标、硬约束和语义候选规则
├── parameter_semantics.yaml     # 参数 target、单位、语义标签、风险和参数组
├── spec.yaml                    # 默认阈值、评分权重和级联配置
├── sky130_eval_profiles.yaml    # topology profile、profile metrics 和候选规则
├── sky130_sweep.yaml            # SKY130 参数扫描示例
└── sky130_transient_spec.yaml   # SKY130 transient 评价配置
docs/
├── project_overview.md          # 项目总览、数据流和扩展边界
├── metrics_spec.md              # 指标定义、单位和判定策略
├── schema_spec.md               # 输出文件 schema 与字段约定
├── public_demo_run.md           # 固定公开 demo run 的重建说明
├── reproduce_results.md         # 复现公开结果的最短步骤
└── profile_closed_loop_example.md
examples/
├── sample_waveform.csv          # 可公开的小型示例波形
├── sample_params.yaml           # 可公开的示例参数空间
├── profile_closed_loop_params.yaml
└── demo_run/                    # 固定 demo 输出包
scripts/                         # 辅助脚本，核心逻辑不放在这里
src/goa_eval/                    # CircuitPilot 核心包
tests/                           # pytest 回归测试
```

核心模块：

```text
src/goa_eval/
├── cli.py                       # 命令行入口
├── waveform_io.py               # 仿真 CSV 读取与列名归一化
├── windowing.py                 # 脉冲窗口、重复扫描窗口、边沿区域、overlap 积分
├── metrics.py                   # 单次波形指标计算和级联摘要
├── scorer.py                    # 硬约束、软评分和 profile score
├── analysis_metrics.py          # OP/AC/DC/TRAN companion metrics
├── topology_profiles.py         # topology 到 profile 的解析
├── diagnosis.py                 # 诊断报告
├── recommendation.py            # 规则化参数建议
├── optimizer.py                 # 候选参数生成和搜索打分
├── sky130_transient.py          # SKY130 数据集/ngspice transient 接入
├── sky130_sweep.py              # SKY130 参数扫描
├── multi_round_optimizer.py     # 多轮搜索驱动
├── parsers/netlist_parser.py    # SPICE netlist 结构摘要
├── reporter.py                  # CSV / JSON / Markdown 输出
├── plotter.py                   # PNG 图表
└── schemas.py                   # schema_version、字段名和基础校验
```

## 安装

建议使用 Python 3.10 或更高版本。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[test]"
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[test]"
```

SKY130 数据集入口需要额外依赖：

```bash
python -m pip install -e ".[test,sky130]"
```

可执行入口：

```bash
python -m goa_eval.cli --help
circuitpilot --help
```

## 快速开始

### 单次仿真 CSV 评价

```bash
python -m goa_eval.cli evaluate-real \
  --waveform examples/sample_waveform.csv \
  --output-dir outputs/example
```

常见输出：

- `real_metrics.csv`
- `real_summary.json`
- `score_summary.json`
- `analysis_metrics.json`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `optimization_dataset.csv`
- `run_manifest_real.json`
- `figures/`

### 生成推荐报告

```bash
python -m goa_eval.cli recommend \
  --summary outputs/example/real_summary.json \
  --score outputs/example/score_summary.json \
  --metrics outputs/example/real_metrics.csv \
  --output outputs/example/recommendations.md
```

### 生成下一轮候选参数

```bash
python -m goa_eval.cli propose-candidates \
  --summary outputs/example/real_summary.json \
  --score outputs/example/score_summary.json \
  --metrics outputs/example/real_metrics.csv \
  --param-space examples/sample_params.yaml \
  --strategy constrained-random \
  --max-candidates 10 \
  --seed 42 \
  --output-csv outputs/example/next_candidates.csv \
  --output-md outputs/example/next_candidates.md
```

`--strategy rule` 只输出规则映射的单参数候选；`constrained-random` 会生成单参数和两参数组合候选。

### 语义标签驱动候选参数

当电路已经有 circuit profile 和参数语义配置时，可以让候选生成优先按工程含义匹配，而不是只按参数名匹配：

```bash
python -m goa_eval.cli propose-candidates \
  --summary outputs/example/real_summary.json \
  --score outputs/example/score_summary.json \
  --param-space config/parameter_semantics.yaml \
  --profile-file config/circuit_profiles.yaml \
  --params config/parameter_semantics.yaml \
  --strategy rule \
  --output-csv outputs/example/next_candidates.csv \
  --output-md outputs/example/next_candidates.md
```

例如 `dc_gain_db` 低于 profile 目标时，`ota_general` 的规则会匹配 `input_pair_width` / `gm_control` 等语义标签，并生成 `input_pair` 参数组候选。候选仍然只是下一轮仿真建议，`must_resimulate=true`，不表示参数已经被物理验证。

配置校验入口：

```bash
python -m goa_eval.cli validate-config \
  --profile-file config/circuit_profiles.yaml \
  --params config/parameter_semantics.yaml
```

### 批量评价多个 run

```bash
python -m goa_eval.cli evaluate-batch --runs-dir runs --output-dir outputs_batch
```

输入目录约定：

```text
runs/
├── run_001/
│   ├── waveform.csv
│   └── params.yaml
└── run_002/
    ├── waveform.csv
    └── params.yaml
```

批量输出包括 `all_metrics.csv`、`all_scores.csv`、`leaderboard.csv`、`recommendations.md` 和 `run_manifest_batch.json`。

## SKY130 / ngspice 使用

### transient 数据接入

```bash
python -m goa_eval.cli sky130-transient \
  --split train \
  --max-rows 5 \
  --output-root outputs/sky130_smoke
```

该命令读取 Hugging Face `pphilip/analog-circuits-sky130` 的 `with_testbench` 配置，调用本机 `ngspice`，导出兼容 CSV，并继续运行评价、打分、推荐和候选生成。

如果只验证软件链路：

```bash
python -m goa_eval.cli sky130-transient \
  --split train \
  --max-rows 2 \
  --mock-ngspice \
  --output-root outputs/sky130_mock
```

### 参数扫描

```bash
python -m goa_eval.cli sky130-sweep \
  --sweep config/sky130_sweep.yaml \
  --pdk-root /path/to/sky130/pdk \
  --split train \
  --max-rows 1 \
  --max-runs 20 \
  --output-root outputs/sky130_sweep
```

`--pdk-root` 优先，其次读取 `PDK_ROOT` 或 `SKYWATER_PDK_ROOT`。项目只检测和传递外部 PDK 路径，不下载、不打包、不改写 PDK 模型文件。

### 多轮搜索

```bash
python -m goa_eval.cli optimize-rounds \
  --sweep config/sky130_sweep.yaml \
  --pdk-root /path/to/sky130/pdk \
  --split train \
  --max-rows 1 \
  --strategy hybrid \
  --rounds 3 \
  --max-runs-per-round 5 \
  --output-root outputs/sky130_multi_round
```

可选策略：

- `adaptive`：默认策略，基于上一轮最佳候选收窄参数空间。
- `genetic`：对离散合法参数值做变异和组合。
- `bayesian`：在离散网格上用 Gaussian-process expected improvement 排序。
- `surrogate`：用 random-forest score model 排序。
- `hybrid`：组合规则候选、遗传变异、模型排序和多样性回退。

所有策略都只在 sweep YAML 给出的合法离散值上采样，不生成自由形式 SPICE 参数。

## 拓扑感知闭环示例

项目内置一个不依赖外部 PDK 的 profile-aware 示例：

```bash
python scripts/run_profile_closed_loop_example.py
```

默认输出：

```text
outputs/profile_closed_loop_example/
```

该示例会运行 `evaluate-real --topology two_stage_opamp`，写出 `analysis_metrics.json`、`score_summary.json`、`recommendations.md`、`next_candidates.csv` 和 `closed_loop_validation.json`。它证明 profile metrics 可以驱动下一轮候选生成，但仍是 simulation-only 软件链路验证。

## 公开 Demo Run

仓库内置一套可复现的公开 demo，位于 `examples/demo_run/`。它只使用 `examples/sample_waveform.csv` 和 `examples/sample_params.yaml`，并用固定 mock DeepSeek 输出生成参数分析，不需要 `DEEPSEEK_API_KEY`。

重新生成 demo 和前端 dashboard 数据：

```bash
python scripts/build_public_demo.py
```

最短复现步骤见 `docs/reproduce_results.md`，完整说明见 `docs/public_demo_run.md`。

### Upload-to-Dashboard MVP

本地网页上传原型在 public demo 之外新增一条主流程：上传 `waveform.csv`
和可选 `params.yaml` 后，后端同步运行现有评价、推荐、候选生成和
product-demo 打包逻辑，再由前端跳转到对应 `case_id` 的 dashboard。

启动后端：

```bash
python -m uvicorn goa_eval.web.app:app --reload --host 127.0.0.1 --port 8000
```

启动前端：

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

最短演示路径：

```text
1. 启动后端。
2. 启动前端并打开 Vite 输出的网址。
3. 上传 examples/sample_waveform.csv。
4. 可选上传 examples/sample_params.yaml。
5. 点击 Run Analysis。
6. 页面自动跳转到 ?case_id=<生成的 case_id> 并展示 dashboard。
```

上传 case 默认写入 `outputs/web_cases/{case_id}/`。该流程仍然只处理仿真
文件，结果边界保持：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

## DeepSeek V4 参数分析

`analyze-params` 可以把已有结构化输出交给 DeepSeek V4，生成面向汇报和人工复核的中文参数分析。该功能不会替代硬指标、评分器或规则推荐器。

真实调用前设置 API key：

```powershell
$env:DEEPSEEK_API_KEY = "your_deepseek_api_key"
```

示例：

```powershell
python -m goa_eval.cli analyze-params `
  --summary outputs/example/real_summary.json `
  --score outputs/example/score_summary.json `
  --metrics outputs/example/real_metrics.csv `
  --candidates outputs/example/next_candidates.csv `
  --params examples/sample_params.yaml `
  --model deepseek-v4-pro `
  --output-md outputs/example/llm_parameter_analysis.md `
  --output-json outputs/example/llm_parameter_analysis.json
```

更安全的本地运行方式是复制 `.env.example` 为 `.env`，填入 `DEEPSEEK_API_KEY`，再运行：

```powershell
.\scripts\run_real_deepseek.ps1
```

`.env` 不应提交到公开仓库。

## 关键输出文件

### 单次评价输出

| 文件 | 说明 |
|---|---|
| `real_metrics.csv` | 逐级指标表，每行对应一个输出节点或级。 |
| `real_summary.json` | 整体摘要、最差级、分段摘要和关键统计值。 |
| `score_summary.json` | 硬约束、软评分、惩罚项、profile score 和失败/警告原因。 |
| `analysis_metrics.json` | OP/AC/DC/TRAN companion metrics 与不可评价原因。 |
| `diagnosis_report.md` | 面向人工复核的诊断报告。 |
| `real_waveform_report.md` | 波形评价 Markdown 报告。 |
| `optimization_dataset.csv` | 面向后续搜索的一行结构化数据。 |
| `next_candidates.csv` | 下一轮参数候选表。 |
| `run_manifest_real.json` | 输入文件、阈值、命令、版本和边界记录。 |
| `figures/` | 波形总览、趋势图、热力图和内部节点图。 |

### 多轮搜索输出

| 文件 | 说明 |
|---|---|
| `round_001/`, `round_002/`, ... | 每轮 `sky130-sweep` 输出目录。 |
| `optimization_history.json` | 机器可读的轮次摘要和 run 历史。 |
| `optimization_leaderboard.csv` | 所有尝试 run 的统一榜单。 |
| `round_summary.csv` | 每轮最佳分数、最佳 run 和停止原因。 |
| `final_param_space.yaml` | 最后一轮使用的参数空间。 |
| `best_next_candidates.csv` | 从最佳 run 复制出的候选参数表。 |

字段细节见 `docs/schema_spec.md`，指标定义见 `docs/metrics_spec.md`。

## 配置说明

默认配置位于 `config/spec.yaml`。

- `thresholds`：高低电平阈值、目标脉宽、最大 overlap ratio、最大 ripple、电压损失、延迟一致性和目标刷新率。
- `cascade`：级数、输出节点命名模式、分段大小和抽样绘图节点。
- `weights`：功能、质量、稳定性、一致性和成本评分权重。

命令行可覆盖部分阈值和级联配置：

```bash
python -m goa_eval.cli evaluate-real \
  --waveform examples/sample_waveform.csv \
  --output-dir outputs/example \
  --stage-count 8 \
  --output-node-pattern "o{index}"
```

如果配置要求 720 级但当前 CSV 只包含 `o1~o8`，程序会按实际可识别输出节点兼容评价，并在报告中记录说明。

## 当前边界和非目标

当前版本可以做：

- 仿真 CSV 评价、打分和报告生成；
- 公开 SKY130/ngspice 数据接入；
- 规则化推荐和下一轮候选生成；
- 离散参数扫描与多轮搜索调度；
- DeepSeek V4 辅助解释。

当前版本不做以下声明：

- 不声明实物测试通过；
- 不声明芯片或样机验证完成；
- 不自动下载或打包 SKY130 PDK；
- 不把 DeepSeek 分析当作指标真值；
- 不把规则候选当作已经完成的自动优化结果；
- 不把 `PASS_BASIC_SIMULATION_CHECK` 写成物理验证通过；
- 不上传私有大型仿真 CSV、`.tr0`、PDK 文件或本地报告压缩包。

## 测试

```bash
python -m pytest -q
```

公开仓库上传前建议同时检查：

```bash
python scripts/build_public_demo.py
python scripts/run_profile_closed_loop_example.py
```

GitHub 上传清单见 `docs/github_upload_checklist.md`。

## Roadmap

- 继续固定输出 schema 和公开示例数据。
- 增加更多 topology profile 和更细的 OP/AC/DC/TRAN companion metrics。
- 扩展 PVT、Monte Carlo、负载变化和功耗指标。
- 在积累足够多参数-结果数据后，再评估更稳健的代理模型和优化策略。
- 增加外部仿真器调度接口，同时保持仿真结果与实物验证边界清晰。

## SKY130 Candidate Validation

This workflow keeps PDK files and private simulation inputs out of the repository while focusing on local, simulation-only SKY130/ngspice evidence. It does not download or commit a PDK. By default the local PDK path is `tools/volare-pdks/sky130A`, and `--pdk-root` can override it.

Run the current two-round candidate validation with:

```powershell
python -m goa_eval.cli optimize-rounds `
  --sweep config/sky130_candidate_sweep.yaml `
  --validation-config config/sky130_validation.yaml `
  --pdk-root tools/volare-pdks/sky130A `
  --source-dataset local_external_ngspice `
  --strategy adaptive `
  --rounds 2 `
  --max-runs-per-round 3 `
  --output-root outputs/sky130_candidate_validation
```

The first round runs the initial SKY130 sweep. The second round replays the top runnable candidates from the previous best run's `next_candidates.csv` before falling back to exploration. Candidate-sourced rows keep `candidate_source=next_candidates`, `source_candidate_id`, `source_candidate_trigger_metric`, and `source_candidate_parameters_json` in both `optimization_history.json` and `optimization_leaderboard.csv`.

The validation target is configured in `config/sky130_validation.yaml`. The current primary target is `Max_overlap_ratio < 0.1`; rows that do not have enough output nodes are marked `not_evaluable` instead of being treated as improvements. Extended validation entries for long hold and PVT/load coverage are recorded in `validation_summary.csv`; they are skipped until the primary target passes.

The local fixture `examples/sky130_candidate_chain_row.json` provides a three-output SKY130 chain-style testbench so overlap can be evaluated. During preparation, the workflow generates a small local `sky130_minimal.lib.spice` per run that references the real SKY130 1.8 V nfet/pfet model files without loading the full PDK library.

### Lightweight SKY130 Mainline

For a faster end-to-end check, use the lightweight mainline facade. It keeps the
default run small, writes a compact validation bundle, and only enables the full
validation matrix when requested:

```powershell
python -m goa_eval.cli sky130-mainline `
  --sweep config/sky130_candidate_sweep.yaml `
  --validation-config config/sky130_validation.yaml `
  --pdk-root tools/volare-pdks/sky130A `
  --source-dataset local_external_ngspice `
  --rounds 1 `
  --max-runs-per-round 3 `
  --output-root outputs/sky130_mainline
```

If the local PDK or `ngspice` is unavailable, the command defaults to
`--mock-if-unavailable` and falls back to a mock smoke run so the software chain
can still be exercised. Add `--full-validation` to run the configured extended
validation cases such as PVT/load coverage; without it, full-matrix cases are
recorded as skipped by lightweight policy.

Mainline outputs include `mainline_validation.json`,
`sky130_mainline_report.md`, `optimization_leaderboard.csv`,
`best_next_candidates.csv`, and `validation_summary.csv`. These artifacts remain
`engineering_validity=simulation_only` and are not physical, lab, or silicon
evidence.

## License

MIT License. See `LICENSE`.

## Generalized CSV Adapter and AI Profile Assistant

This repository also provides generalized facades above the older SKY130-named
entrypoints. They keep the same boundary:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

Import an existing simulator-export directory:

```bash
python -m goa_eval.cli simulate-run \
  --adapter csv-import \
  --input-dir path/to/csv_run \
  --output-dir outputs/csv_run \
  --circuit-profile ota_general \
  --profile-file config/circuit_profiles.yaml \
  --params config/parameter_semantics.yaml
```

The input directory must contain `waveform.csv` and may include
`op_metrics.csv`, `ac_metrics.csv`, `dc_metrics.csv`, `tran_metrics.csv`,
`source_netlist.spice`, and `simulation_metadata.json/yaml`. The output run
keeps the normal evaluation artifacts and adds `adapter_status.json` plus
`simulation_metadata.json`.

Batch import child directories with:

```bash
python -m goa_eval.cli simulate-sweep \
  --adapter csv-import \
  --input-root path/to/csv_runs \
  --output-root outputs/csv_sweep \
  --circuit-profile ota_general \
  --profile-file config/circuit_profiles.yaml \
  --params config/parameter_semantics.yaml
```

The sweep facade writes `simulate_sweep_runs.csv` and
`simulate_sweep_leaderboard.csv`.

Generate auditable AI profile drafts with:

```bash
python -m goa_eval.cli ai-profile-assistant \
  --description docs/my_circuit_description.md \
  --profile-file config/circuit_profiles.yaml \
  --params config/parameter_semantics.yaml \
  --mock-response '{"analysis":"draft only"}' \
  --output-dir outputs/ai_profile_assistant
```

The assistant writes `profile_draft.yaml`,
`parameter_semantics_draft.yaml`, `ai_profile_assistant.json`, and
`ai_profile_assistant.md`. Drafts must pass `validate-config` before they are
used by scoring or candidate generation. AI output is advisory and does not
replace the evaluator, simulator, or human review.

Profile metric outputs now include additive `metric_provenance` metadata in
`analysis_metrics.json`, `score_summary.json`, and `optimization_dataset.csv`.
The metadata records units, source files, source columns, parser names, and
normalization notes for auditability.

## Acknowledgement

This project started from an 8T1C / GOA circuit simulation review workflow. The open-source version preserves the reusable software parts: simulation-data parsing, metric extraction, structured reporting, diagnosis, conservative rule-based recommendations, and simulation-only parameter search.
