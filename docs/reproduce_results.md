# 如何复现结果

本文档用于快速复现仓库内置的公开 demo 结果。它只使用公开样例数据，不需要私有波形文件，也不需要 DeepSeek API key。

## 1. 安装依赖

在仓库根目录执行：

```bash
python -m pip install -e ".[test]"
```

前端 dashboard 如需本地构建，再进入 `frontend/` 安装依赖：

```bash
npm install
```

## 1a. 一键 Upload-to-Dashboard 演示

推荐使用仓库根目录的一键脚本启动上传演示：

```bash
python scripts/run_upload_demo.py
```

脚本会检查 `goa_eval.web.app` 是否可导入、`frontend/package.json` 是否存在、`frontend/node_modules` 是否已安装，然后启动：

- FastAPI upload backend: `http://127.0.0.1:8000`
- Vite frontend: `http://127.0.0.1:5173`

打开页面后可以点击 **Run Built-in Demo**，后端会使用 `examples/sample_waveform.csv` 和 `examples/sample_params.yaml` 生成一个新的 `demo_<timestamp>_<id>` case，并自动跳转到 `?case_id=<case_id>` 展示 dashboard。

上传自定义数据时，`waveform.csv` 是必需输入，`params.yaml` 可选。图片在当前 MVP 中只作为附件展示，不参与曲线识别。

该流程仍然保持：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

这些结果不是 physical validation、silicon validation 或已验证优化结论；候选参数只是下一轮仿真建议。

如果要手动演示网页上传流程，可分别启动 FastAPI 后端和前端作为 fallback：

```bash
python -m uvicorn goa_eval.web.app:app --reload --host 127.0.0.1 --port 8000
```

## 2. 重新生成 demo 结果

在仓库根目录执行：

```bash
python scripts/build_public_demo.py
```

该命令会重建：

- `examples/demo_run/`：完整公开 demo 输出包
- `frontend/public/data/`：前端 dashboard 使用的数据快照

## 2a. 可选：网页上传到 Dashboard

启动后端后，在另一个终端启动前端：

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

打开前端页面后执行最短上传演示：

```text
1. 上传 examples/sample_waveform.csv。
2. 可选上传 examples/sample_params.yaml。
3. 点击 Preview Input。
4. 检查时间列、输出节点、参数空间、netlist 摘要、附件、warnings 和 suggestions。
5. 点击 Run Analysis。
6. 等待后端生成 outputs/web_cases/{case_id}/analysis/ 和 product_demo/{case_id}/。
7. 页面自动跳转到 ?case_id={case_id} 并展示 dashboard。
```

Preview Input 只是输入可评价性检查，不是仿真验证。图片当前只作为附件展示，不参与 OCR 或曲线识别。候选参数仍然是下一轮仿真建议，必须重新仿真验证。

上传流程与 public demo 使用同一套评估、推荐、候选生成和 product-demo
打包逻辑。结果仍然必须保持：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

## 3. 检查关键输出

生成后重点查看：

- `examples/demo_run/real_summary.json`
- `examples/demo_run/score_summary.json`
- `examples/demo_run/real_metrics.csv`
- `examples/demo_run/next_candidates.csv`
- `examples/demo_run/llm_parameter_analysis.md`
- `examples/demo_run/figures/`
- `examples/demo_run/figures/figure_manifest.json`

结果边界必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

## Evidence-Gated Reproduction

Public demo output is Level 0 / Level 1 evidence. Real SKY130 acceptance must use local PDK plus ngspice and can be enforced with:

```powershell
python -m goa_eval.cli sky130-mainline `
  --sweep config/sky130_candidate_sweep.yaml `
  --validation-config config/sky130_validation.yaml `
  --pdk-root tools/volare-pdks/sky130A `
  --ngspice-cmd tools/ngspice/Spice64/bin/ngspice.exe `
  --require-real-ngspice `
  --output-root outputs/sky130_mainline_real
```

If PDK or ngspice is missing, `--require-real-ngspice` fails instead of falling back to mock mode. Only runs with no mock and available PDK/ngspice may set `reportable_as_real_ngspice=true`.

Strategy benchmark reproduction:

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

The benchmark writes `strategy_benchmark.csv`, `strategy_leaderboard.csv`, `strategy_benchmark_summary.json`, and `strategy_benchmark_report.md`. The summary includes scenario, fairness, baseline groups, not-evaluable rate, validation rollup, and improvement fields versus the `random` no-replay baseline.

这表示结果只来自仿真 CSV，不是实物测试结论，也不表示已经完成自动优化闭环。

## 4. 验证复现是否成功

运行后端测试：

```bash
python -m pytest tests/test_public_demo_run.py -q
```

如需完整回归：

```bash
python -m pytest -q
```

如需检查前端 dashboard：

```bash
cd frontend
npm test -- --run
npm run build
```

## 5. 可选：接入真实 DeepSeek API

真实 API key 不要写进代码，也不要发到聊天里。按下面方式放在本机私密 `.env` 文件中：

```powershell
Copy-Item .env.example .env
notepad .env
```

把 `.env` 改成：

```text
DEEPSEEK_API_KEY=你的真实key
```

然后运行：

```powershell
.\scripts\run_real_deepseek.ps1
```

脚本会读取本地 `.env`，只在当前进程里设置 `DEEPSEEK_API_KEY`，调用真实 DeepSeek API，并写出：

- `examples/demo_run/llm_parameter_analysis_real.md`
- `examples/demo_run/llm_parameter_analysis_real.json`

DeepSeek 回复会优先按结构化 JSON 解析，并由本地代码校验候选 ID、指标名和证据边界。Markdown 报告仍然是给人阅读的最终报告；JSON 中的 `structured_analysis` 和 `validation` 用于校验、归档和 dashboard/报告脚本读取。

提交前不要提交 `.env`，也不要误提交真实 API 输出，除非你已经确认内容适合公开。

## 6. 预期结论

公开 demo 当前使用三节点小波形样例，因此会展示完整流程可复现：波形评价、评分诊断、候选参数生成、mock DeepSeek 参数分析和 dashboard 数据刷新。它不用于证明 720 级真实波形性能；只有输入波形实际包含对应节点时，才应期待更大级联规模的真实结果。
