# CircuitPilot 路线 C 产品设计

**日期：** 2026-07-11  
**状态：** 已确认产品路线，待实施  
**路线：** GOA 首发、底层通用  
**产品内核：** 现有 `goa_eval` 评价、诊断、候选生成、PIA 闭环、证据和报告能力

## 1. 执行摘要

CircuitPilot 将从“仿真 CSV 评价与算法演示原型”发展为“仿真驱动的电路分析与优化协作平台”。产品第一阶段围绕 GOA、8T1C 和大规模级联扫描驱动形成完整体验；底层通过 circuit profile、parameter semantics、metric plugin、simulation contract 和 simulator adapter 保持对 OTA、比较器、振荡器及其他模拟电路的扩展能力。

产品不替代 SPICE 或商业 EDA 仿真器。它位于仿真器上层，负责把设计规格、参数、网表信息、仿真结果和优化历史组织成可评价、可诊断、可比较、可重放、可审计的工程闭环。

核心用户旅程为：

```text
建立项目与规格
  -> 导入设计版本和仿真结果
  -> 输入预检
  -> 自动评价与约束诊断
  -> 生成并审批下一轮候选
  -> 导出或执行仿真批次
  -> 校验并导入重仿真结果
  -> 比较版本、更新最优设计
  -> 生成工程报告和证据包
```

## 2. 设计目标

### 2.1 产品目标

1. 让 GOA 工程师无需命令行即可完成一次完整的仿真审查。
2. 让每个失败约束都能追溯到具体指标、节点、窗口、输入文件和配置版本。
3. 让候选参数从“静态建议文件”升级为可审批、可重仿真、可比较的实验对象。
4. 让 PIA-CA-LLSO 和其他策略通过统一实验接口进入产品，而不是形成平行系统。
5. 让新增电路类型主要通过 profile、parameter semantics 和 metric adapter 完成，而不是修改核心产品流程。
6. 保持 CLI、API、前端和离线 artifact bundle 的结果一致。

### 2.2 非目标

首轮产品化不做以下事项：

- 不替代 local-simulator、Spectre、HSPICE、Empyrean 或其他仿真器。
- 不自动宣称候选参数已经改善电路。
- 不把仿真证据升级为芯片、样机、流片或实验室实测证据。
- 不在 V1 同时覆盖所有模拟电路拓扑。
- 不在 V1 引入复杂微服务、Kubernetes 或事件总线。
- 不重写现有 `goa_eval` 算法和报告链路。
- 不让 LLM 直接绕过规则、约束和仿真证据决定最终结论。

## 3. 不可破坏的工程边界

所有现有和新增产品输出必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

语义规则如下：

- `data_source = real_simulation_csv` 表示输入来自仿真 CSV，不表示来自物理样机。
- `engineering_validity = simulation_only` 表示工程结论仅适用于仿真范围。
- `must_resimulate = true` 表示候选参数必须重新仿真才能讨论改善。
- 只有导入了与候选、配置和仿真任务匹配的结果后，单个候选的状态才可从 `proposed` 变为 `resimulated`。
- 只有评价器对重仿真结果完成硬约束和指标检查后，才可显示 `confirmed_improvement`。
- mock、local fixture、论文数字化和 selection-only benchmark 不得进入“确认改善”统计。

现有 `src/goa_eval/product_demo/schemas.py` 中的 evidence normalization 继续作为边界字段的单一来源；产品层消费统一结果，不在 API 或前端临时补字段。

## 4. 产品定位与首发范围

### 4.1 产品定位

产品名称继续使用 CircuitPilot，中文描述为“仿真驱动的电路分析与优化协作平台”。

对用户的核心表达：

> 从仿真波形到可复核的设计决策。

### 4.2 GOA 首发范围

GOA 首发体验覆盖：

- 8T1C / GOA / 级联扫描驱动项目模板。
- 1 至 720 级输出节点识别与分段汇总。
- VOH、延迟、脉宽、纹波、电压损失、重叠、误触发和保持类指标。
- 最差级、首个失败级、异常区段和趋势定位。
- 参数空间、GOA 语义标签和候选生成。
- 单次分析、版本比较和多轮调参实验。
- 手动仿真批次导出/结果导入。
- PIA-CA-LLSO 闭环与验证协议的产品化入口。

### 4.3 通用扩展边界

通用扩展通过以下接口完成：

- `config/circuit_profiles.yaml`：电路类型、目标、指标集合和别名。
- `config/parameter_semantics.yaml`：参数的物理含义、单位、范围和方向。
- `src/goa_eval/topology_profiles.py`：拓扑到评价 profile 的映射。
- `src/goa_eval/analysis_metrics.py`：OP/AC/DC/TRAN companion 指标。
- `src/goa_eval/pia_ca_llso/simulation_contract.py`：算法与仿真执行之间的稳定协议。
- `src/goa_eval/pia_ca_llso/simulator_adapter.py`：外部仿真器命令边界。
- `src/goa_eval/empyrean/`：外部 EDA 离线适配的现有先例。

## 5. 用户与权限角色

### 5.1 设计工程师

- 创建项目和设计版本。
- 上传输入并执行评价。
- 查看诊断、候选和前后对比。
- 审批候选并导入重仿真结果。

### 5.2 审核者

- 查看项目整体状态和证据完整性。
- 审核候选、重仿真结果和报告结论。
- 标记结论为接受、退回或证据不足。

### 5.3 算法研究者

- 配置策略、seed、budget、ablation 和 validation protocol。
- 运行 PIA/benchmark 实验。
- 查看收敛曲线、公平性和泄漏审计。

### 5.4 工作区管理员

- 管理成员、项目权限、存储、profile 和仿真器配置。
- 查看任务失败、审计日志和系统健康状态。

V1 只实现 `owner` 与 `editor` 两种轻量角色；更细角色在项目闭环稳定后增加。

## 6. 信息架构

```text
Workspace
├── Projects
│   └── Project
│       ├── Overview
│       ├── Inputs
│       ├── Design Versions
│       ├── Analysis Runs
│       ├── Comparisons
│       ├── Optimization Experiments
│       ├── Simulation Jobs
│       ├── Evidence
│       └── Reports
├── Circuit Profiles
├── Simulator Connections
└── Settings
```

前端主导航按“项目 -> 分析 -> 优化 -> 证据”组织，不按底层 Python 模块组织。

## 7. 核心领域模型

### 7.1 Workspace

表示一个独立协作空间，包含项目、成员、profile 和仿真器连接。

关键字段：

- `workspace_id`
- `name`
- `created_at`
- `schema_version`

### 7.2 Project

表示一个连续设计任务，例如“720 级 GOA 扫描驱动优化”。

关键字段：

- `project_id`
- `workspace_id`
- `name`
- `circuit_profile_id`
- `spec_revision_id`
- `status`
- `created_at`

### 7.3 DesignVersion

表示一个可复核的参数/网表版本，而不是一次评价结果。

关键字段：

- `design_version_id`
- `project_id`
- `label`
- `parent_version_id`
- `parameter_set_ref`
- `netlist_ref`
- `source_candidate_id`
- `created_at`

### 7.4 AnalysisRun

表示对一个设计版本的一次评价。

关键字段：

- `analysis_run_id`
- `design_version_id`
- `input_manifest_ref`
- `spec_revision_id`
- `profile_revision_id`
- `status`
- `artifact_bundle_ref`
- `evidence_boundary`
- `started_at`
- `completed_at`

### 7.5 Issue

将现有 diagnosis 文本结构化为问题卡片。

关键字段：

- `issue_id`
- `analysis_run_id`
- `constraint_key`
- `severity`
- `affected_nodes`
- `metric_refs`
- `possible_causes`
- `recommended_actions`
- `evidence_refs`

### 7.6 Candidate

表示一个待验证的参数方案。

关键字段：

- `candidate_id`
- `experiment_id`
- `parent_design_version_id`
- `parameter_changes`
- `strategy`
- `reason_codes`
- `predicted_or_selection_scores`
- `approval_status`
- `must_resimulate`
- `simulation_job_id`
- `result_design_version_id`

### 7.7 OptimizationExperiment

表示具有固定目标、参数空间、策略和预算的一组优化活动。

关键字段：

- `experiment_id`
- `project_id`
- `baseline_design_version_id`
- `objective_spec`
- `parameter_space_ref`
- `strategy_config`
- `budget`
- `seed`
- `state`
- `best_confirmed_design_version_id`

### 7.8 SimulationJob

表示一次可追踪的仿真任务或手动仿真交接。

关键字段：

- `simulation_job_id`
- `candidate_id`
- `adapter_type`
- `input_manifest_ref`
- `command_manifest_ref`
- `status`
- `result_manifest_ref`
- `logs_ref`
- `attempt`

### 7.9 EvidenceRecord

表示一条可引用的证据，不把证据只嵌在报告文本中。

关键字段：

- `evidence_id`
- `subject_type`
- `subject_id`
- `evidence_type`
- `source_ref`
- `checksum`
- `boundary`
- `created_at`

## 8. 系统架构

### 8.1 架构原则

采用“模块化单体 + 后台任务执行器”，不在第一阶段拆微服务。

```text
React Product UI
      |
Product API (FastAPI)
      |
Product Application Services
      |
Existing goa_eval Domain Kernel
      |
Artifact Store + Metadata Store + Job Runner
      |
CSV Import / local-simulator / Empyrean / Future Adapters
```

### 8.2 保留的现有内核

以下能力继续作为领域内核，不重写：

- `waveform_io.py`、`windowing.py`、`metrics.py`：波形与指标。
- `scorer.py`、`diagnosis.py`、`recommendation.py`：约束、诊断和建议。
- `real_waveform_eval.py`、`reporter.py`、`plotter.py`：评价与 artifact 输出。
- `product_demo/`：Dashboard bundle 和报告聚合。
- `pia_ca_llso/`：候选、演化、simulation contract、resume、验证和审计。
- `multi_agent/`：路由、critic、evidence index 和 decision report。
- `circuit_profiles.py`、`topology_profiles.py`：通用电路扩展。

### 8.3 保持分离的现有 Web 角色

- `src/goa_eval/web/` 继续负责上传分析和当前兼容 API。
- `src/goa_eval/web_api/` 继续负责只读 product-demo artifact 适配。
- 新增 `src/goa_eval/product_api/` 作为项目化产品 API，调用共享 application services。
- 不把 `web/` 和 `web_api/` 直接合并；旧端点保留兼容期。

### 8.4 新增产品应用层

新增 `src/goa_eval/product/`，包含：

- `models.py`：领域实体和枚举。
- `repositories.py`：元数据持久化接口。
- `artifact_store.py`：artifact 引用和校验和。
- `project_service.py`：项目与设计版本。
- `analysis_service.py`：输入预检和评价编排。
- `comparison_service.py`：版本比较。
- `experiment_service.py`：候选和实验状态机。
- `simulation_job_service.py`：任务导出、结果导入和重试。
- `evidence_service.py`：证据索引与边界检查。
- `report_service.py`：产品报告聚合。

应用层只编排现有内核，不复制指标和优化算法。

## 9. 存储设计

### 9.1 元数据

第一阶段使用 SQLite + SQLAlchemy/Alembic，支持本地和单实例部署。数据库保存项目、版本、状态、引用、权限和审计元数据，不保存大型波形内容。

### 9.2 Artifact 存储

大型输入和输出继续使用文件/object storage：

```text
storage/
└── workspaces/{workspace_id}/
    └── projects/{project_id}/
        ├── inputs/{input_id}/
        ├── runs/{analysis_run_id}/
        ├── experiments/{experiment_id}/
        ├── jobs/{simulation_job_id}/
        └── reports/{report_id}/
```

Vercel Blob 作为 Web 部署适配器保留；本地文件系统作为开发和私有部署默认实现。所有 artifact 通过 store interface 访问，业务代码不拼接任意用户路径。

### 9.3 数据一致性

- 数据库先创建 pending 记录，再执行长任务。
- artifact 写入临时目录，通过校验后原子发布。
- 数据库记录 artifact URI、大小、SHA-256 和 schema version。
- 删除项目采用软删除；artifact 清理由显式维护任务完成。

## 10. 关键工作流

### 10.1 新建 GOA 项目

1. 用户选择 GOA 模板。
2. 系统加载 GOA circuit profile 和默认 parameter semantics。
3. 用户确认 stage count、节点命名、规格和参数空间。
4. 系统冻结 spec/profile revision。
5. 创建 baseline design version。

### 10.2 输入预检与分析

1. 上传 waveform、params、netlist/附件。
2. `input_inspector` 只检查可读性、列、单位和节点覆盖。
3. 预检通过后创建 `AnalysisRun(status=queued)`。
4. 后台调用现有 `run_real_waveform_evaluation()`。
5. 生成 score、diagnosis、figures 和 product-demo bundle。
6. application service 将摘要写入数据库并建立 evidence index。
7. 前端展示分析结果，原始 artifact 仍可下载复核。

### 10.3 候选审批与重仿真

1. 用户从失败问题或实验页生成候选。
2. 现有规则、PIA 或组合策略生成候选及原因。
3. 所有候选初始状态为 `proposed` 且 `must_resimulate=true`。
4. 用户批准候选后生成 simulation contract。
5. 用户手动下载批次或选择已配置 adapter。
6. 结果导入时校验 candidate ID、schema、参数、行数和边界。
7. 通过后生成新的 design version 和 analysis run。
8. comparison service 比较 baseline 和 result。
9. 仅对重仿真且评价通过的结果设置确认改善状态。

### 10.4 PIA 多代闭环

1. 产品层创建 experiment，并将配置映射到现有 PIA config/protocol。
2. `run_evolution_loop()` 继续负责 generation 和 resume。
3. 产品层将每代 artifact、候选、job 和状态映射到领域模型。
4. pending generation 显示为“等待仿真结果”，不伪造下一代。
5. benchmark、fairness、source lock 和 boundary audit 作为实验报告附件。

## 11. 状态机

### 11.1 AnalysisRun

```text
draft -> previewed -> queued -> running -> completed
                                  |         |
                                  v         v
                                failed   evidence_incomplete
```

### 11.2 Candidate

```text
proposed -> approved -> simulation_pending -> resimulated -> evaluated
    |          |              |                               |
    v          v              v                               v
 rejected   edited        simulation_failed        improved / regressed / neutral
```

### 11.3 OptimizationExperiment

```text
draft -> ready -> running -> waiting_for_simulation -> running -> completed
                    |                   |                          |
                    v                   v                          v
                  paused             failed                   terminated
```

状态转换由 application service 控制，不由前端直接写任意字符串。

## 12. API 设计

新增 API 使用 `/api/v1`：

### Workspace 与 Project

- `POST /api/v1/workspaces`
- `GET /api/v1/workspaces/{workspace_id}`
- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `GET /api/v1/projects/{project_id}/overview`

### Design 与 Analysis

- `POST /api/v1/projects/{project_id}/design-versions`
- `POST /api/v1/design-versions/{version_id}/preview`
- `POST /api/v1/design-versions/{version_id}/analysis-runs`
- `GET /api/v1/analysis-runs/{run_id}`
- `GET /api/v1/analysis-runs/{run_id}/bundle`
- `POST /api/v1/comparisons`

### Optimization

- `POST /api/v1/projects/{project_id}/experiments`
- `POST /api/v1/experiments/{experiment_id}/candidates:generate`
- `POST /api/v1/candidates/{candidate_id}:approve`
- `POST /api/v1/candidates/{candidate_id}:reject`
- `POST /api/v1/experiments/{experiment_id}:resume`

### Simulation Jobs

- `POST /api/v1/candidates/{candidate_id}/simulation-jobs`
- `GET /api/v1/simulation-jobs/{job_id}`
- `GET /api/v1/simulation-jobs/{job_id}/export`
- `POST /api/v1/simulation-jobs/{job_id}/results`
- `POST /api/v1/simulation-jobs/{job_id}:retry`

### Evidence 与 Reports

- `GET /api/v1/projects/{project_id}/evidence`
- `GET /api/v1/evidence/{evidence_id}`
- `POST /api/v1/projects/{project_id}/reports`
- `GET /api/v1/reports/{report_id}`

现有 `/api/cases` 与 `/api/demo/sample-case` 保留，并在兼容层内部逐步调用新的 analysis service。

## 13. 前端设计

### 13.1 路由

- `/workspaces/:workspaceId/projects`
- `/projects/:projectId/overview`
- `/projects/:projectId/inputs`
- `/projects/:projectId/versions`
- `/analysis/:runId`
- `/comparisons/:comparisonId`
- `/experiments/:experimentId`
- `/jobs/:jobId`
- `/projects/:projectId/evidence`
- `/projects/:projectId/reports`

### 13.2 复用现有组件

以下组件继续复用并接入新路由：

- `OverviewCards`
- `EvidenceBoundaryCard`
- `ConstraintStatusPanel`
- `CandidateRankingTable`
- `BeforeAfterPanel`
- `FiguresGallery`
- `ReportsPanel`
- `UploadWorkspace` 和输入预检组件

现有 `App.tsx` 从单页条件渲染改为路由壳；组件的数据类型逐步从 demo bundle 类型扩展为版本化 API DTO。

### 13.3 关键交互原则

- “预检通过”与“分析通过”必须使用不同状态和颜色。
- “候选评分”与“重仿真结果”必须分区展示。
- `must_resimulate=true` 在候选详情和审批动作附近持续可见。
- 所有改善标签必须链接到 comparison 和对应 analysis run。
- 错误提示必须包含可操作的修复建议和相关 artifact/log 链接。

## 14. 错误处理

定义稳定错误结构：

```json
{
  "error_code": "RESULT_CANDIDATE_MISMATCH",
  "message": "Imported results do not match the simulation job candidate set.",
  "details": {},
  "retryable": false,
  "artifact_refs": []
}
```

重点错误：

- `INPUT_UNREADABLE`
- `TIME_COLUMN_MISSING`
- `UNIT_AMBIGUOUS`
- `NODE_COVERAGE_INSUFFICIENT`
- `PROFILE_VALIDATION_FAILED`
- `ANALYSIS_EXECUTION_FAILED`
- `SIMULATOR_UNAVAILABLE`
- `SIMULATION_TIMEOUT`
- `RESULT_SCHEMA_INVALID`
- `RESULT_CANDIDATE_MISMATCH`
- `EVIDENCE_BOUNDARY_INVALID`
- `EXPERIMENT_STATE_CONFLICT`

失败时保留输入、日志和部分 artifact；不得把失败 job 更新为 completed。

## 15. 安全与隔离

- 上传文件使用已有路径穿越保护，并增加总大小、单文件大小和类型限制。
- 解压文件继续拒绝目录穿越和符号链接逃逸。
- 外部 simulator command 不接受任意前端 shell 字符串，只能使用管理员配置的 adapter 模板。
- artifact 下载使用资源 ID 解析，不接受任意绝对路径。
- 工作区数据按 workspace ID 隔离。
- API token、PDK 路径和仿真器凭据不进入报告或 artifact bundle。
- 审计日志记录创建、审批、导入、重试和报告确认动作。

## 16. 可观测性

每个请求和后台任务携带：

- `request_id`
- `workspace_id`
- `project_id`
- `analysis_run_id` 或 `simulation_job_id`
- `schema_version`

系统健康页至少展示：

- API 状态；
- 数据库状态；
- artifact store 状态；
- 队列深度；
- 最近失败任务；
- local-simulator/PDK/adapter 可用性，但不得因“检测到路径”直接声明真实证据。

## 17. 测试策略

### 17.1 单元测试

- 状态机和非法转换。
- repository 和 artifact 引用。
- evidence normalization 与 claim gating。
- comparison 分类。
- profile/schema 校验。

### 17.2 集成测试

- 新建项目到完成一次分析。
- 候选审批、批次导出、结果导入和比较。
- PIA pending generation 与 resume。
- API、数据库和 artifact store 一致性。

### 17.3 前端测试

- 项目导航和空状态。
- 上传/预检/分析状态区分。
- 候选审批和 `must_resimulate` 可见性。
- 失败 job 和证据不足状态。

### 17.4 端到端测试

- 固定公开 GOA 示例项目。
- 临时目录中的本地文件 artifact store。
- deterministic local simulator 只验证流程，不计入真实仿真证据。
- 可选的 real retired local-simulator/foundry flow 测试由明确环境开关启用并 fail closed。

## 18. 迁移策略

1. 不删除或改名现有 CLI。
2. 不改变 `examples/demo_run` 和 product-demo bundle 的读取能力。
3. 为现有 case bundle 提供只读导入器，转换为 Project/DesignVersion/AnalysisRun 元数据。
4. 新 API 先与旧 API 并存；前端按页面逐步迁移。
5. 现有 PIA artifact 通过 adapter 映射为 Experiment/Candidate/SimulationJob，不修改历史文件格式。
6. schema 变化必须带版本和向后读取测试。

## 19. 阶段路线图

### Phase 0：产品内核与数据一致性

- 建立 product domain models、repository 和 artifact store。
- 建立项目、版本、分析和证据的最小 API。
- 将现有上传分析编排封装为 application service。
- 建立公开示例项目导入。

出口条件：CLI、旧上传 API 和新产品 API 对同一输入生成一致核心指标与边界。

### Phase 1：GOA 分析工作台

- 项目列表、项目概览和设计版本。
- 输入预检、分析任务和结果页。
- 结构化 issue、图表、报告和证据页。
- 两个设计版本的比较。

出口条件：用户无需命令行完成一次 GOA 仿真审查和版本比较。

### Phase 2：候选与人工闭环

- 参数空间和候选策略配置。
- 候选解释、审批和拒绝。
- simulation contract 导出。
- 结果导入、校验、重评价和确认比较。

出口条件：能够完成至少三轮人工仿真闭环，且任何未重仿真候选不会显示为确认改善。

### Phase 3：PIA 与自动执行

- PIA experiment 映射和 generation 可视化。
- resume、budget、stop condition 和 benchmark。
- retired local-simulator/foundry flow adapter 任务执行。
- 审计、重试、日志和实验报告。

出口条件：在明确配置的真实仿真环境中完成可恢复闭环，证据字段和 claim level 正确。

### Phase 4：通用电路扩展

- Profile 管理和校验界面。
- OTA、比较器和振荡器参考模板。
- 通用 metric/parameter/simulator adapter 开发接口。
- 新 profile 的一致性和回归测试。

出口条件：新增一种支持的电路类型不需要修改项目、版本、实验和证据核心模型。

## 20. 完成度指标

不使用营收指标，使用以下产品指标：

- 示例项目首次完成时间小于 10 分钟。
- 同一输入从 CLI、旧 API、新 API 得到一致的核心指标。
- 每个硬约束失败都产生结构化 issue 或明确“无法诊断”状态。
- 100% 候选保留策略、父版本、参数差异和 `must_resimulate`。
- 100% 确认改善都能追溯到匹配的重仿真结果。
- 中断的 PIA generation 可恢复，不重复消费已导入结果。
- mock/local fixture 的 `reportable_as_real_local-simulator` 始终为 false。
- 新 profile 的引入有 schema、语义和端到端 fixture 测试。

## 21. 主要风险与控制

### 风险 1：产品层复制算法逻辑

控制：application service 只调用现有内核，指标、评分和候选算法保持单一实现。

### 风险 2：项目模型一次设计过重

控制：V1 只实现 Workspace、Project、DesignVersion、AnalysisRun、EvidenceRecord；Experiment 和 Job 在 Phase 2 增加。

### 风险 3：前端先做大量页面但后端状态不稳定

控制：每个阶段先固定 schema、状态机和 API contract，再增加页面。

### 风险 4：自动仿真扩大安全面

控制：Phase 2 先做手动导出/导入；自动执行只允许管理员注册的 adapter。

### 风险 5：通用化稀释 GOA 体验

控制：GOA 作为首个 reference profile；通用能力必须通过同一 GOA 回归套件验证。

## 22. 设计决策总结

1. 采用路线 C：GOA 首发、底层通用。
2. 采用模块化单体，不立即拆微服务。
3. 保留 `goa_eval` 为领域内核，在其上新增 product application layer。
4. 保持 `web/` 上传分析与 `web_api/` 只读 artifact 适配的现有分工。
5. 使用 SQLite + 文件/object artifact store 作为第一阶段存储。
6. 先交付完整分析工作台，再交付候选与仿真闭环，最后自动化仿真和扩展其他电路。
7. 证据边界和重仿真要求是领域规则，不是 UI 提示。

