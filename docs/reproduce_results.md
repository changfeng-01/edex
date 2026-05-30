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

## 2. 重新生成 demo 结果

在仓库根目录执行：

```bash
python scripts/build_public_demo.py
```

该命令会重建：

- `examples/demo_run/`：完整公开 demo 输出包
- `frontend/public/data/`：前端 dashboard 使用的数据快照

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

The benchmark writes `strategy_benchmark.csv`, `strategy_benchmark_summary.json`, and `strategy_benchmark_report.md`.

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

提交前不要提交 `.env`，也不要误提交真实 API 输出，除非你已经确认内容适合公开。

## 6. 预期结论

公开 demo 当前使用三节点小波形样例，因此会展示完整流程可复现：波形评价、评分诊断、候选参数生成、mock DeepSeek 参数分析和 dashboard 数据刷新。它不用于证明 720 级真实波形性能；只有输入波形实际包含对应节点时，才应期待更大级联规模的真实结果。
