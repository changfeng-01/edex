# CircuitPilot Multi-Agent Evidence Chain

CircuitPilot 是一个面向电路仿真结果的本地 multi-agent 证据链原型。它读取已有仿真 CSV、评分摘要、leaderboard、参数空间和 netlist 文件，通过确定性 Agent 完成任务路由、证据读取、候选生成、风险审查、优化闭环记录和报告输出。

当前仓库不做 WebUI、数据库、RAG、远程服务或自动物理验证。它的目标是把一次本地运行整理成可复查、可答辩、可继续 rerun 的工程证据包。

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

这两个字段是项目边界：结果来自仿真 CSV，只能作为 simulation-only 工程分析依据，不能表述为流片验证、实物芯片验证或完整工业级自动优化。

## 快速运行

安装测试与 Agent 依赖：

```powershell
python -m pip install -e ".[test,agent]"
```

运行 SKY130 multi-agent 最小流程：

```powershell
python -m goa_eval.cli multi-agent-run `
  --task examples/tasks/sky130_multi_agent_task.yaml `
  --output-dir outputs/multi_agent_sky130
```

验证四类路由：

```powershell
python -m goa_eval.cli multi-agent-run --task examples/tasks/goa_multi_agent_task.yaml --output-dir outputs/multi_agent_goa
python -m goa_eval.cli multi-agent-run --task examples/tasks/sky130_multi_agent_task.yaml --output-dir outputs/multi_agent_sky130
python -m goa_eval.cli multi-agent-run --task examples/tasks/generic_multi_agent_task.yaml --output-dir outputs/multi_agent_generic
python -m goa_eval.cli multi-agent-run --task examples/tasks/netlist_multi_agent_task.yaml --output-dir outputs/multi_agent_netlist
```

如果未安装 LangGraph，命令会返回清晰错误，并提示安装 `.[agent]`。

## Agent 角色

| Agent | 职责 | 允许工具 |
| --- | --- | --- |
| SupervisorAgent | 初始化共享状态和运行边界 | `inspect_task_inputs` |
| RouterAgent | 根据 `task_type`、`profile`、输入文件进行可解释路由 | `inspect_task_inputs` |
| GOAAgent | 输出 GOA / 8T1C 级联诊断，关注 stage、overlap、ripple、voltage loss、false trigger | `inspect_real_metrics`, `inspect_score_summary`, `inspect_leaderboard` |
| SKY130Agent | 输出 SKY130 诊断，关注 timing、load_cap、drive_resistance、hard constraints、参数风险 | `inspect_real_metrics`, `inspect_score_summary`, `inspect_leaderboard`, `inspect_candidates` |
| GenericWaveformAgent | 汇总通用 waveform-derived 评估文件 | `inspect_real_metrics`, `inspect_score_summary`, `inspect_leaderboard` |
| NetlistAgent | 检查 netlist 最小完整性和 parser 可见结构 | `inspect_netlist_integrity` |
| EvaluationAgent | 汇总已存在评估结果，不重算核心指标 | `inspect_leaderboard`, `inspect_score_summary`, `inspect_real_metrics` |
| OptimizationAgent | 通过现有 optimizer wrapper 生成 `next_candidates.csv` | `generate_candidates`, `inspect_candidates` |
| CriticAgent | 审查边界、schema、硬约束、异常指标、工具越权、candidate 风险和 netlist 完整性 | `check_schema_and_boundary`, `inspect_candidates`, `inspect_netlist_integrity` |
| ReportAgent | 写出最终报告、优化闭环记录和决策证据卡 | `write_multi_agent_report` |

每个 Agent 都有显式 contract：`role`、`allowed_tools`、`input_schema`、`output_schema`、`handoff_policy`、`failure_policy`。运行时的工具调用进入 trace，CriticAgent 会检查是否发生越权调用。

## 路由规则

RouterAgent 的路由是可解释的：

- `profile` 或 `task_type` 指向 GOA / 8T1C 时，进入 `GOAAgent`。
- `profile` 或 `task_type` 指向 SKY130 时，进入 `SKY130Agent`。
- 没有明确领域 profile，但输入包含 `waveform`、`real_metrics`、`score_summary` 或 `leaderboard` 时，进入 `GenericWaveformAgent`。
- 只有 netlist 输入且没有 waveform 评估文件时，进入 `NetlistAgent`。
- 输入不足或不支持时，交给 `CriticAgent` 生成失败/警告证据。

路由结果会写入 `multi_agent_plan.json`、`multi_agent_trace.jsonl`、`multi_agent_handoff_trace.jsonl` 和 `multi_agent_decision_report.md`。

## 证据链输出

一次 `multi-agent-run` 会在输出目录生成：

| 文件 | 内容 |
| --- | --- |
| `multi_agent_plan.json` | 任务元信息、选中的 Agent、路由原因、Agent contracts、边界字段和预期输出 |
| `multi_agent_trace.jsonl` | 每个 Agent 步骤、工具调用、状态、输入摘要、输出摘要和时间戳 |
| `multi_agent_handoff_trace.jsonl` | Agent 之间的 handoff、原因、传递的状态字段和状态 |
| `critic_report.json` | Critic verdict、severity、risk_type、risk_summary、top_risks、warning/failure 和边界 |
| `multi_agent_memory.json` | 本次运行的 Agent、工具、best candidate、候选摘要、warning/failure 和后续动作 |
| `multi_agent_decision_report.md` | 完整人读报告，包含目标、路由、工具调用、领域诊断、候选依据、闭环链接、netlist 检查、Critic 结果和边界说明 |
| `optimization_loop_record.json` | 优化闭环机器可读记录：baseline、next_candidates、rerun instruction、rerun results、comparison、decision |
| `optimization_decision_card.md` | 面向比赛展示和答辩的决策证据卡 |

如果提供了 `param_space` 和 leaderboard，OptimizationAgent 会通过现有 `goa_eval.optimizer` wrapper 生成 `next_candidates.csv`。这只是下一轮仿真候选，不是自动闭环优化完成证明。

## 优化闭环语义

优化闭环记录遵循：

```text
next_candidates -> rerun -> comparison -> decision
```

如果 task 没有提供 rerun 结果，`optimization_loop_record.json` 会写出：

```text
status = awaiting_rerun_results
decision = await_rerun_results
```

这表示系统已经给出下一轮候选和 rerun 指令，但还没有真实 rerun artifact，不能宣称优化完成。

如果 task 提供 `rerun_leaderboard`、`rerun_score_summary` 或 `rerun_real_metrics`，系统会进入 `decision_ready`，并基于 baseline best candidate 与 rerun best candidate 的 `overall_score` 做 comparison。分数提升时输出 `accept_rerun_candidate`，未提升时输出 `reject_rerun_candidate`，缺少可比字段时输出 `review_required`。

可选 rerun 输入字段：

```yaml
inputs:
  baseline_run_dir: outputs/multi_agent_sky130
  rerun_run_dir: outputs/rerun_001
  rerun_leaderboard: outputs/rerun_001/leaderboard.csv
  rerun_score_summary: outputs/rerun_001/score_summary.json
  rerun_real_metrics: outputs/rerun_001/real_metrics.csv
```

## CriticAgent 风险分级

CriticAgent 保留旧的 `verdict` 字段，同时新增：

- `severity`: `info | warning | major | critical`
- `risk_type`: `boundary | hard_constraint | not_evaluable | false_trigger | overlap | candidate_risk | netlist_integrity | tool_permission | rerun_missing | decision_blocked`
- `risks`: 每个具体问题的风险类型和严重度
- `risk_summary`: 按风险类型和严重度聚合
- `top_risks`: 适合报告展示的主要风险

主要检查项包括：

- `hard_constraint_passed = false` 或硬约束失败原因。
- `not_evaluable`、`not_evaluable_with_current_waveform`、`missing`、`nan` 等不可评估指标。
- `FalseTrigger` 或 `FalseTriggerCount > 0`。
- `OverlapRatio` 超过默认或任务指定阈值。
- 缺失 `schema_version`、`result_version`、`data_source`、`engineering_validity`。
- Agent 调用了 contract 中未允许的工具。
- 候选参数值超出 `param_space` 或单个候选修改参数数过多。
- netlist 缺少 `.END`、`.SUBCKT` 未闭合、`.ENDS` 不匹配、缺少 MOS 器件或电压源等最小完整性问题。
- 生成了 `next_candidates` 但没有 rerun 结果时，记录 `rerun_missing`。
- 报告文字是否越界声称 silicon validation、physical validation 或 industrial-grade full automation。

## Task YAML

任务文件保持轻量，基础字段如下：

```yaml
task_name: sky130_multi_agent_mvp
task_type: sky130_eda_optimization
profile: sky130_inverter_chain

inputs:
  leaderboard: examples/multi_agent/sample_sky130_leaderboard.csv
  score_summary: examples/multi_agent/sample_score_summary.json
  real_metrics: examples/multi_agent/sample_real_metrics.csv
  param_space: examples/sample_params.yaml

objectives:
  primary: pass_hard_constraints

limits:
  max_candidates: 10
  max_parameter_changes_per_candidate: 2

validity:
  data_source: real_simulation_csv
  engineering_validity: simulation_only
```

现有示例任务位于 `examples/tasks/`。这些任务复用 `examples/multi_agent/` 中已有样例文件，不需要继续增加样例数据。

## 与核心评估逻辑的关系

Multi-agent 层只做编排、审查、闭环记录和报告：

- 不重写 `metrics.py`。
- 不重写 `scorer.py`。
- 不重写 `optimizer.py`。
- 不重写 `reporter.py`。
- 不直接调度远程服务或外部数据库。

已有入口仍然可用：

```powershell
python -m goa_eval.cli evaluate-real --waveform examples/sample_waveform.csv --output-dir outputs/example
python -m goa_eval.cli recommend --summary outputs/example/real_summary.json --score outputs/example/score_summary.json --metrics outputs/example/real_metrics.csv --output outputs/example/recommendations.md
python -m goa_eval.cli evaluate-batch --runs-dir runs --output-dir outputs_batch
```

## 测试

定向测试：

```powershell
python -m pytest tests -k multi_agent -q
```

全量回归：

```powershell
python -m pytest -q
```

如果本机缺少某些私有 fixture 或外部工具，优先看 multi-agent 定向测试和错误信息，不要把工具链可用性误写成物理验证结论。
