# CircuitPilot 工程泛化升级设计方案

日期：2026-05-25

## 1. 背景

CircuitPilot 当前已经从最初的 8T1C / GOA 级联波形评价，扩展到 retired foundry-specific local-simulator 数据接入、topology-aware profile 评分、参数扫描、多轮候选搜索和 DeepSeek 参数分析。现有能力证明了软件链路可行，但仍存在一个工程化瓶颈：核心流程虽然逐步泛化，入口、配置和参数推荐仍带有较强的 retired foundry flow 或特定电路痕迹。

下一阶段目标不是继续堆叠某几个新电路规则，而是把项目升级为可面向真实工程场景的“通用电路仿真评价与 AI 交互式参数推荐框架”。

该方案继续保持项目边界：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

所有输出都只表示仿真分析、下一轮参数建议和软件链路验证，不声明芯片实测通过，不声明自动物理优化闭环已经完成。

## 2. 总目标

将 CircuitPilot 从“针对特定电路的仿真后处理工具”升级为：

> 一个 profile-driven、adapter-based、AI-interactive 的模拟/混合信号电路仿真评价、诊断、候选参数生成和多轮搜索框架。

具体含义：

- **profile-driven**：不同电路类型通过 profile 配置描述评价目标、指标、权重、硬约束和调参规则。
- **adapter-based**：不同仿真器、PDK、数据来源通过 adapter 接入，核心评价逻辑只消费统一中间数据。
- **AI-interactive**：AI 不替代评分器和仿真器，而是作为工程助手，与用户交互完成目标澄清、profile 生成、结果解释、候选筛选和下一轮计划。
- **engineering-first**：优先保证可复现、可审计、可降级、可人工复核，而不是追求看起来自动化但不可解释的黑盒优化。

## 3. 非目标

本阶段不做以下事情：

- 不宣称完成物理验证或流片级验证。
- 不把 AI 输出当作指标真值。
- 不让 AI 直接无约束修改 netlist。
- 不自动下载、打包或提交 PDK。
- 不把所有电路一次性支持完整。
- 不重写现有 8T1C、retired foundry flow、profile-aware、optimizer 逻辑。
- 不把当前包名 `goa_eval` 立即改名，避免破坏已有脚本和测试。

## 4. 核心设计思路

### 4.1 三层泛化架构

下一阶段架构分为三层：

```text
User / AI interaction
        |
        v
Circuit Profile + Parameter Semantics + Objective
        |
        v
Simulation Adapter + Unified Artifacts
        |
        v
Existing evaluator / scorer / recommendation / optimizer
```

第一层负责人与 AI 的交互和工程意图表达。

第二层负责把“这个电路该怎么评价、哪些参数能调、目标是什么”结构化。

第三层负责接入不同仿真来源，并继续复用现有评价、评分、推荐和优化模块。

### 4.2 从 topology 到 circuit profile

现有 `topology_profile` 主要解决“OTA / comparator / oscillator 该看哪些 companion metrics”。下一阶段应升级为更完整的 `circuit_profile`。

建议新增配置文件：

```text
config/circuit_profiles.yaml
```

保留 `config/retired_foundry_flow_eval_profiles.yaml` 作为兼容入口，逐步迁移到通用 profile。

示例结构：

```yaml
profiles:
  ota_general:
    aliases: ["ota", "opamp", "two_stage_opamp", "amplifier"]
    required_analyses: ["op", "ac", "tran"]
    optional_analyses: ["dc", "noise"]
    hard_constraints:
      output_swing_v:
        minimum: 1.0
      static_power_w:
        maximum: 0.01
    objectives:
      dc_gain_db:
        goal: maximize
        minimum: 40.0
        weight: 0.25
      unity_gain_hz:
        goal: maximize
        minimum: 10000000.0
        weight: 0.20
      phase_margin_deg:
        goal: target
        target: 60.0
        tolerance: 15.0
        weight: 0.15
      static_power_w:
        goal: minimize
        maximum: 0.01
        weight: 0.20
      slew_rate_v_per_s:
        goal: maximize
        minimum: 10000000.0
        weight: 0.20
    fallback_policy:
      missing_required_analysis: "not_evaluable"
      missing_optional_analysis: "warn"
    candidate_rules:
      dc_gain_db:
        - semantic_tags: ["input_pair_width", "gain_device_width", "device_width"]
          direction: increase
          priority: 92
          rationale: "Increase effective transconductance for gain recovery."
      static_power_w:
        - semantic_tags: ["bias_current"]
          direction: decrease
          priority: 96
          rationale: "Reduce bias current when static power dominates."
```

关键变化：

- profile 不再只是 topology 名字映射。
- profile 直接定义硬约束和优化目标。
- profile 明确 required / optional analysis。
- profile candidate rules 优先引用参数语义标签，而不是写死参数名。

## 5. 参数语义层

### 5.1 问题

真实工程项目中，同一个物理含义的参数可能有不同命名：

```text
m1_width
M1_W
W_IN_N
input_pair_w
wn
```

如果推荐系统只靠固定参数名匹配，就很难迁移到新电路、新团队和新 PDK。

### 5.2 设计

建议扩展参数空间配置，给每个参数增加语义字段：

```yaml
parameters:
  m1_width:
    target: XM1.W
    values: ["0.8", "1.0", "1.2"]
    unit: "um"
    semantic_tags:
      - device_width
      - input_pair_width
      - gm_control
    affects:
      - dc_gain_db
      - bandwidth_3db_hz
      - static_power_w
    risk:
      - area
      - capacitance

  ibias:
    target: IBIAS.dc_value
    values: ["5u", "10u", "20u"]
    unit: "A"
    semantic_tags:
      - bias_current
      - speed_power_tradeoff
    affects:
      - slew_rate_v_per_s
      - bandwidth_3db_hz
      - static_power_w
    risk:
      - power
```

### 5.3 推荐逻辑变化

旧逻辑：

```text
metric penalty -> candidate rule -> parameter name match
```

新逻辑：

```text
metric penalty -> candidate rule -> semantic tag match -> concrete parameter candidates
```

优点：

- 新电路只要标注参数语义，就能复用已有候选规则。
- AI 可以辅助生成语义标签，但最终写入配置前必须给出可审计解释。
- 参数推荐从“认名字”升级为“认工程含义”。

## 6. Adapter 层

### 6.1 问题

当前 `retired_foundry_flow-transient` 和 `retired_foundry_flow-sweep` 对公开 retired foundry-specific local-simulator 数据集非常有效，但真实工程中输入来源更复杂：

- local-simulator
- HSPICE
- Spectre
- Xyce
- 已有 CSV / log / mt0 / lis / raw 文件
- 本地 testbench
- PDK 私有路径
- 多 corner、多温度、多负载仿真结果

核心评价逻辑不应关心这些来源细节。

### 6.2 统一中间产物

建议定义 adapter 输出目录规范：

```text
run_dir/
  source_netlist.spice
  testbench.spice
  waveform.csv
  analysis_metrics.json
  simulation_metadata.json
  netlist_structure.json
  adapter_status.json
  run_manifest_real.json
```

其中：

- `waveform.csv`：统一时域波形输入。
- `analysis_metrics.json`：统一 OP / DC / AC / TRAN / NOISE / PSS companion metrics。
- `simulation_metadata.json`：仿真器、PDK、corner、temperature、supply、command、source 等。
- `adapter_status.json`：adapter 是否成功、是否跳过、失败原因、缺失数据。

### 6.3 Adapter 类型

建议先支持四类 adapter：

| Adapter | 作用 | 优先级 |
|---|---|---|
| `csv-import` | 直接导入已有 waveform/metrics 文件 | P0 |
| `local-simulator-local` | 本地 local-simulator + SPICE testbench | P1 |
| `retired_foundry_flow-dataset` | 现有 retired foundry flow 数据集入口兼容层 | P1 |
| `external-simulator-import` | 导入 HSPICE/Spectre 等外部结果 | P2 |

### 6.4 CLI 设计

新增通用命令：

```powershell
python -m goa_eval.cli simulate-run `
  --adapter csv-import `
  --input outputs/external_run `
  --profile ota_general `
  --params config/my_params.yaml `
  --output-dir outputs/general_run
```

```powershell
python -m goa_eval.cli simulate-sweep `
  --adapter local-simulator-local `
  --sweep config/my_circuit_sweep.yaml `
  --profile comparator_general `
  --output-root outputs/general_sweep
```

保留现有命令：

```text
retired_foundry_flow-transient
retired_foundry_flow-sweep
optimize-rounds
evaluate-real
analyze-params
```

但长期方向是让 `retired_foundry_flow-*` 成为通用命令的预设或 wrapper。

## 7. AI 交互设计

### 7.1 AI 的定位

AI 是工程助手，不是仿真器，不是评分器，不是物理验证器。

AI 可以做：

- 读取 profile、summary、score、metrics、candidates。
- 解释当前失败原因。
- 与用户确认设计目标。
- 帮用户生成或修订 profile。
- 帮用户标注参数语义。
- 帮用户筛选下一轮候选。
- 生成下一轮仿真计划。
- 识别缺失数据和不可信结论。

AI 不应该做：

- 在没有仿真证据时宣称性能提升。
- 把候选参数当成最终答案。
- 绕过硬约束直接推荐高风险改动。
- 自动修改 PDK 或私有模型。
- 输出不可追踪的“经验结论”。

### 7.2 交互入口

建议新增一个 AI 会话命令：

```powershell
python -m goa_eval.cli ai-assist `
  --workspace outputs/general_sweep `
  --profile config/circuit_profiles.yaml `
  --params config/my_params.yaml `
  --mode review
```

支持模式：

| Mode | 用途 |
|---|---|
| `onboard` | 新电路接入向导 |
| `profile` | 生成或审阅 circuit profile |
| `review` | 解释一次仿真或一轮 sweep 结果 |
| `candidate` | 审阅下一轮候选参数 |
| `plan` | 生成下一轮仿真计划 |
| `report` | 生成汇报用说明 |

### 7.3 新电路接入向导

AI 应按固定问题流引导用户，而不是一次性自由发挥。

建议流程：

1. 识别电路类型：

```text
这是哪类电路？
- OTA / OpAmp
- Comparator
- Oscillator / VCO
- LDO / regulator
- Bandgap / reference
- Charge pump
- Digital timing chain
- Custom
```

2. 识别仿真数据：

```text
你现在有什么仿真结果？
- 只有 transient waveform
- 有 OP + transient
- 有 OP + DC + AC + transient
- 有 sweep / corner 结果
- 只有外部 CSV / log
```

3. 识别工程目标：

```text
这轮最重要的目标是什么？
- 先满足功能硬约束
- 提高速度 / 带宽
- 降低功耗
- 提高摆幅 / 裕量
- 提高稳定性
- 做多目标折中
```

4. 识别可调参数：

```text
哪些参数可以调？
- 器件宽长
- 偏置电流
- 负载电容
- 补偿电容
- 电源电压
- 阈值/参考电压
- testbench 条件
```

5. 生成草案：

```text
AI 输出:
- 建议 profile
- 参数语义标注
- 必需仿真类型
- 当前无法评价的指标
- 第一轮 sweep 建议
```

### 7.4 AI 输出格式

AI 交互结果必须结构化保存，不能只存在聊天文本里。

建议输出：

```text
ai_assist/
  interaction_summary.md
  profile_draft.yaml
  parameter_semantics_draft.yaml
  next_simulation_plan.md
  ai_assist.json
```

`ai_assist.json` 示例：

```json
{
  "schema_version": "1.0",
  "mode": "profile",
  "model": "deepseek-v4-pro",
  "boundary": {
    "data_source": "real_simulation_csv",
    "engineering_validity": "simulation_only"
  },
  "input_files": [
    "real_summary.json",
    "score_summary.json",
    "analysis_metrics.json",
    "next_candidates.csv",
    "params.yaml"
  ],
  "user_confirmed_goals": [
    "increase dc_gain_db",
    "keep static_power_w under 10 mW"
  ],
  "recommendations": [
    {
      "type": "profile_change",
      "status": "draft",
      "reason": "OTA profile lacks phase_margin_deg but AC data can provide it."
    }
  ],
  "warnings": [
    "phase_margin_deg is not currently available; do not use it as a hard constraint until AC parser supports it."
  ]
}
```

### 7.5 AI 与确定性逻辑的边界

AI 只能生成草案和解释，确定性模块负责落地：

| 任务 | AI | 确定性代码 |
|---|---|---|
| 解释失败原因 | 可以 | 评分器提供事实来源 |
| 生成 profile 草案 | 可以 | schema 校验必须通过 |
| 标注参数语义 | 可以 | 参数必须存在于参数空间 |
| 生成候选参数 | 可以建议 | optimizer 最终生成可运行候选 |
| 判断 pass/fail | 不可以替代 | scorer / hard checks |
| 宣称工程有效 | 不可以 | 只能保持 simulation-only |

## 8. Objective 设计

现有多轮优化已经支持不同策略，但目标函数仍需要进一步 profile 化。

建议新增 `objective` 结构：

```yaml
objective:
  priority_order:
    - hard_constraints
    - profile_score
    - overall_score
    - risk_penalty
  hard_constraint_policy: "must_pass_before_optimize"
  scalarization:
    method: weighted_sum
    missing_metric_policy: not_evaluable
  weights:
    dc_gain_db: 0.25
    unity_gain_hz: 0.20
    static_power_w: 0.20
    output_swing_v: 0.15
    slew_rate_v_per_s: 0.20
```

排序规则：

1. 硬约束失败数量更少者优先。
2. `not_evaluable` 指标更少者优先。
3. profile objective score 更高者优先。
4. overall score 更高者优先。
5. 参数改动风险更低者优先。

这样不同电路可以共享优化器，但使用不同目标定义。

## 9. 输出 schema 升级

### 9.1 新增或扩展文件

建议新增：

```text
circuit_profile_resolved.json
parameter_semantics.json
objective_summary.json
adapter_status.json
ai_assist.json
```

### 9.2 `score_summary.json` 扩展

保留现有字段，追加：

```json
{
  "circuit_profile": "ota_general",
  "profile_source": "config/circuit_profiles.yaml",
  "objective_score": 82.4,
  "objective_breakdown": {
    "hard_constraint_score": 100.0,
    "profile_metric_score": 78.0,
    "risk_penalty": 3.0
  },
  "not_evaluable_required_metrics": [],
  "not_evaluable_optional_metrics": ["noise_density"]
}
```

### 9.3 `next_candidates.csv` 扩展

保留现有字段，追加：

```text
semantic_tags
affected_metrics
risk_tags
expected_tradeoff
ai_review_status
requires_user_confirmation
```

示例：

```text
candidate_id,parameter,direction,semantic_tags,affected_metrics,risk_tags,expected_tradeoff
cand_001,ibias,increase,bias_current;slew_control,slew_rate_v_per_s;bandwidth_3db_hz;static_power_w,power,"May improve speed but increase static power."
```

## 10. 用户工作流

### 10.1 新电路第一次接入

```text
准备 netlist / waveform / metrics
        |
        v
ai-assist --mode onboard
        |
        v
生成 profile_draft.yaml + parameter_semantics_draft.yaml
        |
        v
用户确认或修改
        |
        v
simulate-run / evaluate-real
        |
        v
score_summary + recommendations + next_candidates
        |
        v
ai-assist --mode review / candidate
```

### 10.2 工程调参循环

```text
Run simulation
        |
        v
Extract waveform and companion metrics
        |
        v
Evaluate by circuit profile
        |
        v
Score hard constraints and objectives
        |
        v
Generate deterministic candidates
        |
        v
AI reviews tradeoffs and asks user to choose
        |
        v
Next sweep / next run
```

### 10.3 AI 交互示例

用户：

```text
这是一个两级 OTA，我现在有 OP、AC、TRAN 结果，目标是增益大于 60 dB，UGB 大于 20 MHz，静态功耗小于 5 mW。
```

AI 应输出：

```text
我会把它按 ota_general profile 处理。当前需要确认三个点：
1. phase margin 是否也是硬约束；
2. slew rate 是否有目标；
3. 哪些参数允许改动。
```

用户补充：

```text
phase margin 大于 55 度，允许调输入对宽度、负载电容、偏置电流。
```

AI 生成：

```text
- profile_draft.yaml
- parameter_semantics_draft.yaml
- first_sweep_plan.md
```

并明确：

```text
这些是下一轮仿真建议，不是性能已经达标的结论。
```

## 11. 实施路线

### Phase 1：Profile 泛化和参数语义层

目标：不大改仿真入口，先让评价和推荐脱离固定参数名。

任务：

- 新增 `config/circuit_profiles.yaml`。
- 让 `topology_profiles.py` 兼容加载新 profile 格式。
- 新增参数语义解析，支持 `semantic_tags`、`affects`、`risk`。
- 修改 candidate rule 匹配逻辑：优先 semantic tag，保留 parameter name fallback。
- 扩展 `score_summary.json` 和 `next_candidates.csv`。
- 添加 OTA / comparator / oscillator / generic transient chain 示例。

验收：

- 旧 retired foundry flow 示例不破坏。
- 无语义标签时仍能按旧参数名匹配。
- 有语义标签时可以跨参数名生成候选。
- `simulation_only` 边界字段保持稳定。

### Phase 2：AI profile assistant

目标：让 AI 能与用户交互生成 profile 和参数语义草案。

任务：

- 新增 `ai-assist --mode profile`。
- 复用现有 `analyze-params` 的安全 key 处理方式。
- 生成 `profile_draft.yaml`、`parameter_semantics_draft.yaml`、`ai_assist.json`。
- 加入 schema 校验和风险提示。
- AI 输出只作为 draft，不自动覆盖正式配置。

验收：

- 没有 API key 时可走 mock 输出。
- 有 API key 时输出结构化结果。
- AI 生成的 YAML 能被校验器发现缺失字段或非法字段。
- 文档明确 AI 不是指标真值。

### Phase 3：通用 adapter 与 simulate-run

目标：把 retired foundry flow 入口下沉为 adapter，建立通用仿真输入规范。

任务：

- 新增 adapter registry。
- 新增 `csv-import` adapter。
- 新增 `simulate-run`。
- 把 `retired_foundry_flow-transient` 输出对齐 adapter run_dir 规范。
- 新增 `simulation_metadata.json` 和 `adapter_status.json`。

验收：

- 已有 waveform CSV 可通过 `csv-import` 进入完整评价流程。
- retired foundry flow 路径仍可运行。
- adapter 失败时输出可读失败原因。

### Phase 4：通用 simulate-sweep 与 profile objective

目标：让多轮搜索真正围绕 profile objective 工作。

任务：

- 新增 `simulate-sweep`。
- 支持 profile objective score。
- 优化 leaderboard 排序规则。
- 输出 `objective_summary.json`。
- 让 `optimize-rounds` 可以接收通用 sweep config。

验收：

- OTA / comparator / oscillator 至少各有一个 simulation-only 示例。
- leaderboard 显示 hard constraint、not_evaluable、profile objective、overall score。
- 不同 profile 的 run 不混淆指标语义。

## 12. 风险与控制

### 12.1 风险：泛化过度导致现有路径变脆

控制：

- 所有新字段追加，不删除旧字段。
- 保留 `retired_foundry_flow-*` 命令。
- 保留旧 profile 文件兼容读取。
- 测试覆盖旧 demo、retired foundry flow mock、profile closed-loop。

### 12.2 风险：AI 输出过度自信

控制：

- AI 输出必须带 `engineering_validity = simulation_only`。
- AI 只能输出 draft。
- profile 和参数语义必须 schema 校验。
- candidate 最终由确定性代码生成。

### 12.3 风险：参数语义标注错误

控制：

- AI 标注必须给出 rationale。
- 高风险候选标记 `requires_user_confirmation = true`。
- leaderboard 保留 candidate provenance。
- 用户可以关闭 AI 语义建议，只用手写配置。

### 12.4 风险：不同仿真器输出格式差异过大

控制：

- 第一阶段只定义统一中间产物。
- 优先实现 `csv-import`，绕开仿真器解析复杂度。
- HSPICE/Spectre 作为后续 import adapter，不先做原生仿真调度。

## 13. 推荐的第一步

建议下一次实际开发只做 Phase 1：

> 新增通用 `circuit_profiles.yaml` 和参数语义层，让 candidate generation 从“参数名匹配”升级为“语义标签匹配”，同时保持所有现有 retired foundry flow / 8T1C / public demo 路径兼容。

这是最符合真实工程泛化能力的第一步，因为它解决的是迁移到新电路时最核心的问题：评价目标和可调参数如何从硬编码变成可配置、可解释、可复用。

第一步完成后，再做 AI profile assistant。这样 AI 交互会建立在稳定 schema 上，而不是让 AI 直接生成没有约束的文本建议。

