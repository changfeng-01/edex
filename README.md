# CircuitPilot / 芯智调参

中文名：芯智调参：基于仿真数据的电路参数智能推荐系统

English name: CircuitPilot: Simulation-Driven Intelligent Parameter Recommendation for Circuit Design

CircuitPilot 是一个面向电路仿真结果的评价、诊断、候选参数生成、多轮仿真调度和 dashboard 展示原型。Python 包名仍保留为 `goa_eval`，用于兼容已有脚本和测试；公开项目名使用 CircuitPilot。

## Project Boundary

当前版本处理的是仿真数据和仿真器输出文件，不是实物测试平台。所有真实 CSV 评价、上传 dashboard、product-demo、benchmark、多智能体报告和 SKY130 相关输出都必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

这两个标签表示结果只能作为仿真分析、下一轮参数建议和软件链路验证依据。候选参数默认是 next-run simulation suggestions，必须重新仿真后才能讨论改善。即使某次运行进入真实 ngspice/SKY130 路径，也不能自动升级为芯片、样机、实验室实测、流片或已验证优化结论。

## Quick Start

Install the Python package and test extras:

```bash
python -m pip install -U pip
python -m pip install -e ".[test]"
```

Run a single CSV waveform evaluation:

```bash
python -m goa_eval.cli evaluate-real \
  --waveform examples/sample_waveform.csv \
  --output-dir outputs/example
```

Generate recommendations and next candidates:

```bash
python -m goa_eval.cli recommend \
  --summary outputs/example/real_summary.json \
  --score outputs/example/score_summary.json \
  --metrics outputs/example/real_metrics.csv \
  --output outputs/example/recommendations.md

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

Typical evaluation artifacts include `real_metrics.csv`, `real_summary.json`, `score_summary.json`, `analysis_metrics.json`, `diagnosis_report.md`, `real_waveform_report.md`, `optimization_dataset.csv`, `run_manifest_real.json`, and `figures/`.

## Upload To Dashboard

Recommended local browser demo:

```bash
cd frontend
npm install
cd ..
python scripts/run_upload_demo.py
```

The launcher starts:

- Upload-analysis backend: `goa_eval.web.app` at `http://127.0.0.1:8000`
- Vite frontend: `http://127.0.0.1:5173`

The frontend supports a built-in demo and custom uploads. Custom analysis accepts `waveform.csv`, optional `params.yaml`, and display-only attachments. Upload case outputs are written under:

```text
outputs/web_cases/{case_id}/
```

The preview endpoint checks whether uploaded inputs are readable and likely usable. It is not simulation validation; image attachments are listed for display only and are not used for OCR or curve recognition.

## Dashboard And Product Demo

There are two backend surfaces:

- `goa_eval.web.app`: upload-analysis backend. It accepts user files, runs the existing evaluation/recommendation/candidate/product-demo pipeline, and writes cases under `outputs/web_cases/{case_id}/`.
- `goa_eval.web_api`: read-only product-demo artifact adapter. It reads generated dashboard artifacts and does not rewrite optimization or fabricate validation.

Create a product-demo package from existing artifacts:

```bash
python -m goa_eval.cli product-demo \
  --input-dir examples/demo_run \
  --case-id public_demo \
  --output-dir outputs/product_demo
```

Start only the read-only dashboard API:

```bash
python scripts/run_dashboard_api.py
```

Frontend modes:

- API mode: set `VITE_API_BASE_URL=http://127.0.0.1:8000`.
- Static mode: when `VITE_API_BASE_URL` is absent, the frontend reads checked-in demo data under `frontend/public/`.

## Optimization And Benchmarks

CircuitPilot has two benchmark surfaces with different evidence boundaries.

### GOA Candidate-Quality Proxy

`goa-strategy-benchmark` compares candidate-generation strategies for GOA evidence without requiring real ngspice or SKY130. It is a candidate-quality proxy benchmark, not a real-simulation validation benchmark.

```bash
python -m goa_eval.cli goa-strategy-benchmark \
  --leaderboard outputs/run/optimization_leaderboard.csv \
  --param-space examples/sample_params.yaml \
  --output-root outputs/goa_strategy_benchmark \
  --strategies random,adaptive,surrogate,repair,hybrid_goa \
  --max-candidates 30 \
  --seeds 1,2,3 \
  --top-k 10
```

GOA benchmark outputs include `goa_strategy_benchmark.csv`, `goa_strategy_benchmark_summary.json`, `goa_strategy_leaderboard.csv`, `goa_strategy_benchmark_report.md`, and per-strategy candidate CSVs.

### SKY130 Strategy Benchmark

`strategy-benchmark` compares multi-round SKY130/ngspice-style strategies under the same sweep, seeds, budget, and validation config. It is still simulation-only.

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

`physics_guided_hybrid` is additive orchestration: replay existing candidates first, then physics-prior ranking, then existing surrogate/model ranking, then diversity fallback. Physics-prior metrics are pre-simulation selection evidence, not a SPICE replacement.

Benchmark rules and schema details live in:

- `docs/algorithm_benchmark.md`
- `docs/schema_spec.md`
- `docs/goa_hybrid_optimizer.md`
- `docs/physics_guided_optimizer.md`

## PIA-CA-LLSO Experimental Optimizer Module

PIA-CA-LLSO is an experimental candidate-selection module under `src/goa_eval/pia_ca_llso/`. It improves the CA-LLSO raw Euclidean-distance selection idea with physics features and attention-metric diagnostics. The current implementation runs through CSV/offline benchmark inputs and emits next-run simulation suggestions.

The boundary remains:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

Minimal commands:

```bash
python -m goa_eval.cli pia-label \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --output-dir outputs/pia_label

python -m goa_eval.cli pia-suggest \
  --history-csv outputs/pia_label/labeled_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --strategy pia_physics_distance \
  --top-k 4 \
  --output-dir outputs/pia_suggest

python -m goa_eval.cli pia-benchmark \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --strategies random,ca_llso_raw_distance,pia_physics_distance \
  --output-dir outputs/pia_benchmark
```

## SKY130 / ngspice

Run a transient smoke path:

```bash
python -m goa_eval.cli sky130-transient \
  --split train \
  --max-rows 2 \
  --mock-ngspice \
  --output-root outputs/sky130_mock
```

Run a multi-round search:

```bash
python -m goa_eval.cli optimize-rounds \
  --sweep config/sky130_sweep.yaml \
  --strategy hybrid \
  --rounds 3 \
  --max-runs-per-round 5 \
  --mock-ngspice \
  --output-root outputs/sky130_multi_round
```

For a real local ngspice/SKY130 check, use `sky130-mainline --require-real-ngspice` with explicit `--pdk-root` and `--ngspice-cmd`. Missing PDK or ngspice should fail instead of silently claiming real evidence.

## Multi-Agent Evidence Chain

`multi-agent-run` is a local orchestration layer over existing evaluators, scorers, optimizers, SKY130 sweep outputs, and report artifacts. It does not replace the underlying algorithms.

```bash
python -m goa_eval.cli multi-agent-run \
  --task examples/tasks/sky130_multi_agent_task.yaml \
  --output-dir outputs/multi_agent_sky130
```

Main outputs include `evidence_index.json`, trace artifacts, handoff records, memory artifacts, critic verdicts, optimization-loop records, and decision reports. If rerun artifacts do not exist, the chain should report that it is waiting for rerun results instead of describing suggestions as completed optimization.

## Generalized Import

Import a simulator-export directory containing `waveform.csv`:

```bash
python -m goa_eval.cli simulate-run \
  --adapter csv-import \
  --input-dir path/to/csv_run \
  --output-dir outputs/csv_run \
  --circuit-profile ota_general \
  --profile-file config/circuit_profiles.yaml \
  --params config/parameter_semantics.yaml
```

Supported optional inputs include `op_metrics.csv`, `ac_metrics.csv`, `dc_metrics.csv`, `tran_metrics.csv`, `source_netlist.spice`, and `simulation_metadata.json/yaml`. Screenshots and raw binary simulator files are not parsed by this path.

Empyrean-exported offline cases use:

```bash
python -m goa_eval.cli empyrean-import \
  --input-dir examples/empyrean_case \
  --output-dir outputs/empyrean_case \
  --case-id demo \
  --generate-candidates
```

## Project Layout

```text
config/                           # evaluation, SKY130, profile, and parameter semantics configs
docs/                             # schema, benchmark, dashboard, and reproduction documentation
examples/                         # public sample waveform, params, tasks, and demo artifacts
frontend/                         # React + Vite dashboard and upload UI
scripts/                          # local launchers and utility scripts
src/goa_eval/                     # CircuitPilot Python package
tests/                            # pytest regression tests
```

Important packages:

- `src/goa_eval/product_demo/`: product-demo artifact packaging.
- `src/goa_eval/web/`: upload-analysis backend.
- `src/goa_eval/web_api/`: read-only dashboard API.
- `src/goa_eval/multi_agent/`: evidence-chain orchestration and inspection tools.
- `src/goa_eval/multi_round_optimizer.py`: multi-round search entrypoint.
- `src/goa_eval/multi_round_strategy.py`: strategy classification helpers for multi-round search.

## Development Checks

CodeGraph is available through the project-local wrapper:

```bash
npm run codegraph:status
npm run codegraph:sync
```

Lightweight Python lint:

```bash
python -m ruff check src tests scripts
```

Focused backend checks:

```bash
python -m pytest tests/test_goa_strategy_benchmark.py tests/test_strategy_benchmark.py tests/test_goa_hybrid_optimizer.py -q
python -m pytest tests/test_multi_round_optimizer.py tests/test_multi_agent_tools.py tests/test_cli_command_registration.py -q
python -m pytest tests/test_web_api.py tests/test_dashboard_api.py tests/test_demo_mainline.py -q
```

Frontend checks:

```bash
cd frontend
npm test -- --run
npm run build
```

Full regression:

```bash
python -m pytest -q
```

## Public Demo And Docs

Rebuild the public demo bundle:

```bash
python scripts/build_public_demo.py
```

Core documentation:

- `docs/reproduce_results.md`
- `docs/schema_spec.md`
- `docs/metrics_spec.md`
- `docs/algorithm_benchmark.md`
- `docs/dashboard_api.md`
- `docs/result_reading_guide.md`
- `docs/goa_hybrid_optimizer.md`
- `docs/physics_guided_optimizer.md`

## License

MIT License. See `LICENSE`.
