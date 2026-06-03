# CircuitPilot / 芯智调参

中文名：芯智调参：基于仿真数据的电路参数智能推荐系统
English name: CircuitPilot: Simulation-Driven Intelligent Parameter Recommendation for Circuit Design

CircuitPilot 是一个面向电路仿真结果的评价、诊断、参数候选生成、仿真调度和展示原型。项目最早来自 8T1C / GOA 级联波形分析流程，当前主线已经扩展到上传到 dashboard、product-demo artifact 打包、只读 dashboard API、SKY130/ngspice 接入、策略 benchmark 和多智能体证据链。

Python 包名仍保留为 `goa_eval`，用于兼容已有脚本和测试；公开项目名使用 CircuitPilot。

## 项目边界

当前版本处理的是仿真数据、仿真器输出文件和基于这些文件生成的候选建议，不是实物测试平台。所有真实 CSV 评价、公开 demo、dashboard、benchmark、多智能体报告和 SKY130 相关输出都必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

这两个标签表示结果只能作为仿真分析、下一轮参数建议和软件链路验证依据。即使本机存在 PDK/ngspice 工具链，或某次运行进入 real ngspice 路径，也不能自动升级为芯片、样机、实验室实测、流片或已验证优化结论。候选参数默认是 next-run simulation suggestions，必须重新仿真后才能讨论改善。

## 5 分钟 Upload-to-Dashboard Demo

推荐的本地演示入口是上传到 dashboard 工作流：

```bash
python -m pip install -e ".[test]"
cd frontend
npm install
cd ..
python scripts/run_upload_demo.py
```

脚本会启动：

- FastAPI upload backend: `goa_eval.web.app` at `http://127.0.0.1:8000`
- Vite frontend: `http://127.0.0.1:5173`

打开页面后可以点击 **Run Built-in Demo**，后端会使用 `examples/sample_waveform.csv` 和 `examples/sample_params.yaml` 生成新的 `demo_<timestamp>_<id>` case，并跳转到 `?case_id=<case_id>` 展示 dashboard。

使用自定义数据时，上传 `waveform.csv`，可选上传 `params.yaml`，然后点击 **Run Analysis**。图片在当前 MVP 中只作为附件展示，不参与曲线识别。上传流程输出位于：

```text
outputs/web_cases/{case_id}/
```

Upload-to-Dashboard now also supports **Preview Input** before the full analysis run. Recommended demo flow: start `python scripts/run_upload_demo.py`, open the frontend, upload `waveform.csv`, click **Preview Input**, inspect the detected time column, output nodes, parameter space, netlist summary, attachments, warnings, and suggestions, then click **Run Analysis** to generate the dashboard bundle.

The preview layer checks whether uploaded inputs are readable and likely usable for evaluation. It is not simulation validation. Image attachments are currently listed for display only and are not used for OCR or curve recognition. Candidate parameters remain next-run simulation suggestions and must be rerun before any improvement claim.

Preview API endpoints:

- `POST /api/cases/preview` accepts the same multipart upload form as `POST /api/cases`, saves files under `outputs/web_cases/{case_id}/input/`, writes `input_preview.json`, and does not run the full analysis.
- `GET /api/cases/{case_id}/input-preview` returns the saved preview JSON for a validated case id.

上传分析后端与 public demo 使用同一套评价、推荐、候选生成和 product-demo 打包逻辑。输出仍然保持：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

## Dashboard 与 Product Demo

主线现在有两层 dashboard 后端：

- `goa_eval.web.app`：上传分析后端，接收 waveform/params 上传，运行分析并把 case 写入 `outputs/web_cases/{case_id}/`。
- `goa_eval.web_api`：只读 product-demo artifact adapter，读取已生成的 dashboard artifact，不重写优化算法，不伪造 validation 结果。

前端支持两种模式：

- API 模式：设置 `VITE_API_BASE_URL=http://127.0.0.1:8000`，前端从后端读取 case bundle。
- 静态模式：未设置 `VITE_API_BASE_URL` 时，前端读取 `frontend/public/data/` 中的固定 demo 数据。

只读 dashboard API 可单独启动：

```bash
python scripts/run_dashboard_api.py
```

product-demo 打包 workflow 可从已有评估产物生成 dashboard 所需的 summary、tables、figures、reports 和 manifest：

```bash
python -m goa_eval.cli product-demo \
  --input-dir examples/demo_run \
  --case-id public_demo \
  --output-dir outputs/product_demo
```

相关文档：

- `docs/reproduce_results.md`
- `docs/dashboard_api.md`
- `docs/demo_quickstart.md`
- `docs/result_reading_guide.md`

## 主要能力

### 仿真 CSV 评价与候选生成

- 读取外部仿真导出的 CSV 波形，归一化 `XVAL` / `TIME`、`v(o1)`、`v(xs4.pu)` 等常见列名。
- 自动识别 `o1~oN` 输出节点扫描窗口，兼容 `o1~o8` 小样例和较大规模级联配置。
- 计算电压、脉宽、延迟、重叠、纹波、保持损失、误触发和级联摘要指标。
- 区分合法重复扫描脉冲和真正误触发。
- 在波形时长不足时将低频保持标为 `not_evaluable_with_current_waveform`，不强行判定通过或失败。
- 生成 CSV / JSON / Markdown / PNG 评价包、推荐报告和下一轮参数候选表。

常用命令：

```bash
python -m goa_eval.cli evaluate-real \
  --waveform examples/sample_waveform.csv \
  --output-dir outputs/evaluate_real

python -m goa_eval.cli propose-candidates \
  --summary outputs/evaluate_real/real_summary.json \
  --score outputs/evaluate_real/score_summary.json \
  --param-space examples/sample_params.yaml \
  --output-dir outputs/candidates
```

### SKY130 / ngspice 链路

- `sky130-transient` 可从 SKY130 数据链路读取 SPICE testbench，调用本机 `ngspice` 或 mock ngspice，并转换为兼容波形。
- `sky130-sweep` 读取 sweep 配置，改写 SPICE 参数，批量运行仿真、评价、打分和候选生成。
- `sky130-mainline` 是轻量主线校验入口，默认允许 mock fallback；`--require-real-ngspice` 会禁用 mock fallback，缺少 PDK 或 ngspice 时直接失败。
- `sky130-mainline --require-real-ngspice` 是真实 ngspice 路径的硬门禁，不是默认 public demo 路径。
- `reportable_as_real_ngspice=true` 只允许出现在真实 `ngspice`、SKY130 PDK 可用且 `mock_used=false` 的运行中。

示例：

```powershell
python -m goa_eval.cli sky130-mainline `
  --sweep config/sky130_candidate_sweep.yaml `
  --validation-config config/sky130_validation.yaml `
  --pdk-root tools/volare-pdks/sky130A `
  --ngspice-cmd tools/ngspice/Spice64/bin/ngspice.exe `
  --require-real-ngspice `
  --output-root outputs/sky130_mainline_real
```

### 多轮优化与 GOA 策略

- `optimize-rounds` 在 `sky130-sweep` 外层运行多轮搜索，并把上一轮最佳 run 的 `next_candidates.csv` 反馈到下一轮参数空间。
- 支持 `random`、`adaptive`、`genetic`、`bayesian`、`surrogate`、`hybrid` 等策略。
- `random` 是 no-replay baseline，不读取 best candidate replay。
- Leaderboard 保留 `candidate_source`、`source_candidate_id`、`source_candidate_trigger_metric`、`source_candidate_parameters_json` 和 `rank_status`。

GOA 专用优化与 benchmark：

```bash
python -m goa_eval.cli hybrid-goa-optimize \
  --leaderboard outputs/run/optimization_leaderboard.csv \
  --param-space examples/sample_params.yaml \
  --output-root outputs/hybrid_goa

python -m goa_eval.cli goa-strategy-benchmark \
  --leaderboard outputs/run/optimization_leaderboard.csv \
  --param-space examples/sample_params.yaml \
  --output-root outputs/goa_strategy_benchmark
```

`goa-strategy-benchmark` 比较 `random`、`adaptive`、`surrogate`、`repair` 和 `hybrid_goa` 候选生成策略。它是 simulation-only，不要求真实 ngspice 或 SKY130。详见 `docs/goa_hybrid_optimizer.md` 和 `docs/goa_strategy_benchmark.md`。

### Benchmark Surface

`strategy-benchmark` 用同一场景、同一参数空间、同一 seeds、同一预算比较多种搜索策略，重点不是单纯分数，而是工程语义：

- hard constraints before soft scores
- row-level candidate provenance
- `hard_constraint_passed`
- `not_evaluable_metric_count`
- validation rollup
- baseline deltas versus `random`
- `strategy_leaderboard.csv`

示例：

```powershell
python -m goa_eval.cli strategy-benchmark `
  --sweep config/sky130_candidate_sweep.yaml `
  --validation-config config/sky130_validation.yaml `
  --mock-ngspice `
  --seeds 1,2,3 `
  --rounds 2 `
  --max-runs-per-round 3 `
  --output-root outputs/strategy_benchmark
```

多智能体 benchmark 使用：

```bash
python -m goa_eval.cli benchmark-run \
  --suite benchmarks/multi_agent/sky130_evidence_case \
  --output-dir outputs/benchmark_multi_agent
```

Benchmark 规则详见 `docs/algorithm_benchmark.md`；输出 schema 详见 `docs/schema_spec.md`。

### Multi-Agent Evidence Chain

`multi-agent-run` 是本地编排层，运行在现有评价器、评分器、优化器、SKY130 sweep 和报告 artifact 之上。它不会替代底层算法，而是整理证据、路由任务、生成诊断、评审风险和记录下一步优化状态。

```bash
python -m goa_eval.cli multi-agent-run \
  --task examples/tasks/sky130_multi_agent_task.yaml \
  --output-dir outputs/multi_agent_sky130
```

主要输出包括：

- `evidence_index.json`
- trace / handoff / memory artifacts
- critic verdict and risk summary
- optimization-loop record
- decision card
- benchmark case outputs when used through `benchmark-run`

当 rerun artifact 不存在时，优化证据链应报告等待复跑结果，而不是把候选建议写成已完成优化。

## Evidence Metadata

CircuitPilot 会把 additive evidence metadata 写入 summary、score、manifest、mainline validation、figure manifest 和相关 SKY130 status 输出。

| Level | Meaning |
|---|---|
| Level 0 | public demo CSV |
| Level 1 | external CSV |
| Level 2 | mock-ngspice software-flow evidence |
| Level 3 | real ngspice + SKY130 PDK, with no mock |
| Level 4 | multi-round optimization with nominal rerun evidence |
| Level 5 | validation matrix evidence |

常见机器字段：

- `evidence_level`
- `simulation_backend`
- `mock_used`
- `pdk_available`
- `ngspice_available`
- `reportable_as_real_ngspice`
- `optimizer_claim_level`
- `must_resimulate`

`figures/figure_manifest.json` 会记录本地图表来源，例如 `source_type=matplotlib_local`、`ai_generated=false`、`llm_used=false`、data-source labels 和 evidence level。

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
├── algorithm_benchmark.md       # benchmark 工程规则
├── dashboard_api.md             # 只读 dashboard API
├── reproduce_results.md         # 复现公开结果的最短步骤
├── schema_spec.md               # 输出文件 schema 与字段约定
├── metrics_spec.md              # 指标定义、单位和判定策略
└── result_reading_guide.md      # 结果阅读边界
examples/
├── sample_waveform.csv          # 可公开的小型示例波形
├── sample_params.yaml           # 可公开的示例参数空间
├── tasks/                       # multi-agent task 示例
└── demo_run/                    # 固定 demo 输出包
frontend/                        # React + Vite dashboard
scripts/                         # 本地演示和辅助脚本
src/goa_eval/                    # CircuitPilot 核心包
tests/                           # pytest 回归测试
```

核心模块：

```text
src/goa_eval/
├── cli.py                       # 命令行入口
├── waveform_io.py               # 仿真 CSV 读取与列名归一化
├── metrics.py                   # 单次波形指标计算和级联摘要
├── scorer.py                    # 硬约束、软评分和 profile score
├── optimizer.py                 # 候选参数生成和搜索打分
├── multi_round_optimizer.py     # 多轮搜索驱动
├── product_demo/                # product-demo artifact 打包
├── web/                         # 上传分析后端
├── web_api/                     # 只读 dashboard artifact adapter
├── sky130_transient.py          # SKY130 数据集/ngspice transient 接入
├── sky130_sweep.py              # SKY130 参数扫描
├── goa_hybrid_optimizer.py      # GOA hybrid optimizer
├── goa_strategy_benchmark.py    # GOA strategy benchmark
├── multi_agent/                 # 多智能体证据链
└── parsers/netlist_parser.py    # SPICE netlist 结构摘要
```

## 安装

建议使用 Python 3.10 或更高版本。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[test]"
```

Windows PowerShell:

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

## 复现与验证

重建公开 demo：

```bash
python scripts/build_public_demo.py
```

运行后端测试：

```bash
python -m pytest tests/test_public_demo_run.py -q
```

完整回归：

```bash
python -m pytest -q
```

前端检查：

```bash
cd frontend
npm test -- --run
npm run build
```

## DeepSeek 参数分析

`analyze-params` 可在已有 summary、score、metrics 和 candidates 基础上调用 DeepSeek 生成中文参数分析。真实 API key 不要写进代码，也不要提交到仓库；只应放在本地 `.env` 或当前进程环境变量中。

```powershell
Copy-Item .env.example .env
notepad .env
.\scripts\run_real_deepseek.ps1
```

公开 demo 默认不需要真实 DeepSeek API key。

## 文档入口

- `docs/reproduce_results.md`：公开 demo、上传演示和测试复现。
- `docs/schema_spec.md`：输出文件、字段和 evidence metadata 约定。
- `docs/algorithm_benchmark.md`：benchmark 规则和报告边界。
- `docs/dashboard_api.md`：只读 dashboard API。
- `docs/goa_hybrid_optimizer.md`：GOA hybrid optimizer。
- `docs/goa_strategy_benchmark.md`：GOA strategy benchmark。
- `docs/result_reading_guide.md`：如何阅读 simulation-only 结果。
