# CircuitPilot Phase 1 GOA 分析工作台设计

**日期：** 2026-07-11  
**状态：** 已确认，待实施  
**前置阶段：** Phase 0 产品领域、SQLite Repository、Artifact Store  
**目标部署：** 本地与私有部署为完整产品基准；Vercel 保留现有 Demo/上传兼容链路

## 1. 执行摘要

Phase 1 将现有 CircuitPilot 仿真评价内核产品化为完整的 GOA 分析工作台。用户可以通过浏览器创建项目、建立设计版本、上传并预检仿真输入、执行分析、查看结构化问题、证据、图表和报告，无需使用命令行。

采用兼容迁移架构：

- 保留 src/goa_eval/web/ 的上传分析兼容入口。
- 保留 src/goa_eval/web_api/ 的只读 product-demo artifact 入口。
- 新增 src/goa_eval/product/ 应用服务层。
- 新增 src/goa_eval/product_api/ 的 /api/v1 产品接口。
- 旧 API 和新 API 最终调用同一个 AnalysisService。
- 现有 waveform、metrics、scorer、diagnosis、recommendation 和 product_demo 继续作为领域内核，不复制实现。

Phase 1 不包含候选审批、Simulation Job、PIA 多代实验、外部仿真器自动调用、用户权限系统和外部任务队列。现有候选生成只能作为只读建议显示，必须继续标记 must_resimulate=true。

## 2. 阶段目标

1. 用户可在页面创建 GOA 项目和 baseline 设计版本。
2. 用户可上传 waveform.csv、params.yaml 和可选网表。
3. 预检与正式分析使用不同状态和文案。
4. 同一输入经 CLI、旧 API 和新 API 得到一致核心结果。
5. 分析输出被整体发布到 Artifact Store。
6. SQLite 只保存元数据、状态和 Artifact 引用。
7. 每个失败约束产生结构化 Issue 或明确 unclassified 状态。
8. 所有证据保持可追溯和不可越级。
9. 新前端具备清晰、稳定、美观的工程控制台体验。
10. 旧 Demo、旧上传入口和只读 Dashboard 保持可用。

## 3. 非目标

- 不自动执行 ngspice、Spectre、HSPICE 或 Empyrean。
- 不在 Phase 1 创建正式 CandidateRecord。
- 不把只读候选建议标记为已优化。
- 不引入 Redis、Celery、Kafka 或 Kubernetes。
- 不在 V1 实现组织、邀请、细粒度权限。
- 不在 Phase 1 提供在线 Circuit Profile 编辑器。
- 不重写现有评价算法和报告生成器。
- 不把 LLM 作为核心分析成功的必要条件。
- 不在第一阶段完成 OTA、比较器和振荡器产品页面。

## 4. 固定证据边界

以下值必须原样存在于 API、Artifact、前端和报告：

~~~text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
~~~

约束：

- Preview ready 只表示文件结构可进入分析。
- Analysis completed 只表示软件分析链路完成。
- Hard constraint passed 才表示当前仿真规格检查通过。
- 只读候选建议不能成为 confirmed improvement。
- 缺失必要证据时 AnalysisRun 必须进入 evidence_incomplete。
- API 或前端不得在读取后临时补字段来伪装证据完整。
- 正常归一化继续由 product_demo.schemas.normalize_evidence_boundary 完成。

## 5. 架构决策

### 5.1 采用新产品层与旧入口兼容适配

~~~text
React Product Workspace
        |
Product API /api/v1
        |
Product Application Services
        |
Phase 0 Repository + Artifact Store
        |
Existing goa_eval Domain Kernel
~~~

旧入口：

~~~text
/api/cases
/api/cases/preview
/api/demo/sample-case
        |
Compatibility Adapter
        |
AnalysisService
~~~

旧 Demo 不强制写入产品数据库，避免公开演示数据污染正式 Project。

### 5.2 分析默认同步执行

Phase 1 不使用伪可靠的进程内后台任务。产品 API 创建 AnalysisRun，按 queued -> running -> completed/failed 更新状态，但默认在当前请求内执行分析。

优点：

- 与现有分析链路一致。
- 本地和私有部署行为可预测。
- 失败时状态和 Artifact 可完整落盘。
- 后续可替换为后台执行器而不改变 DTO。

限制：

- 长任务占用请求。
- Vercel 不作为完整后台分析运行面。
- Phase 3 才增加可恢复任务执行器。

## 6. Phase 0 能力复用

Phase 1 直接复用：

- ProductSettings
- WorkspaceRecord
- ProjectRecord
- DesignVersionRecord
- AnalysisRunRecord
- EvidenceRecord
- AuditEventRecord
- AnalysisStatus 状态机
- SqlAlchemyProductRepository
- LocalArtifactStore
- ArtifactRef 与 SHA-256 校验
- Alembic product core migration

Phase 1 只增加必要查询、服务和 API，不重做 Phase 0。

## 7. 信息架构

~~~text
Workspace
└── Projects
    └── GOA Project
        ├── Overview
        ├── Design Versions
        │   └── Design Version
        │       ├── Input Snapshot
        │       └── Analysis Runs
        ├── Latest Issues
        ├── Evidence
        └── Reports
~~~

Phase 1 前端路由：

~~~text
/workspaces/:workspaceId/projects
/projects/new
/projects/:projectId/overview
/projects/:projectId/versions/:versionId
/analysis/:runId
/demo
~~~

## 8. ProjectService

新增：

~~~text
src/goa_eval/product/project_service.py
~~~

接口：

~~~python
create_workspace(name)
create_project(
    workspace_id,
    name,
    circuit_profile_id,
    spec_revision_id,
)
create_design_version(
    project_id,
    label,
    parameter_set_ref=None,
    netlist_ref=None,
    parent_version_id=None,
)
get_project_overview(project_id)
~~~

Repository 增加：

~~~python
get_workspace(workspace_id)
list_workspaces()
list_design_versions(project_id)
list_analysis_runs(project_id=None, design_version_id=None)
get_latest_analysis_run(project_id)
~~~

项目创建时：

1. 校验 workspace。
2. 使用 resolve_circuit_profile 校验 Profile。
3. 规范化 Profile 内容。
4. 写入不可变 profile_snapshot.json Artifact。
5. 创建 ProjectRecord。
6. 创建项目 EvidenceRecord。
7. 写入 project.created 审计事件。

Project overview 只返回小型摘要，不读取大型波形、CSV 或 PNG。

## 9. Input Snapshot

新增：

~~~text
src/goa_eval/product/input_service.py
~~~

Phase 1 不增加 input_snapshots 数据库表。Input Snapshot 是 Artifact Store 中的不可变 manifest。

输入：

- waveform.csv，必需。
- params.yaml，可选。
- source_netlist.spice、.sp 或 .netlist，可选。
- PNG/JPG 附件，可选且仅展示。

流程：

1. API 保存到受控临时目录。
2. 复用 web.input_inspector。
3. 生成预检摘要。
4. 生成 input_manifest.json。
5. 将临时目录整体发布到 Artifact Store。
6. 返回 input_snapshot_id 和 manifest_ref。
7. AnalysisRun 只接受 manifest_ref，不接受客户端绝对路径。

manifest 至少包含：

~~~json
{
  "input_snapshot_id": "input_xxx",
  "design_version_id": "version_xxx",
  "profile_revision_id": "profile_xxx",
  "created_at": "UTC timestamp",
  "preview_status": "preview_ready",
  "preview": {},
  "files": [
    {
      "logical_name": "waveform.csv",
      "artifact_uri": "artifact://...",
      "size_bytes": 0,
      "sha256": "..."
    }
  ]
}
~~~

状态：

- preview_ready
- preview_ready_with_warnings
- preview_failed

预检失败的临时文件不得发布为正式 Input Snapshot。

## 10. AnalysisService

新增：

~~~text
src/goa_eval/product/analysis_service.py
~~~

输入：

~~~python
run_analysis(
    analysis_run,
    input_manifest_ref,
    circuit_profile,
    topology,
    stage_count,
    output_node_pattern,
    generate_readonly_suggestions=True,
    run_llm_analysis=False,
)
~~~

输出：

~~~python
AnalysisExecutionResult(
    analysis_run_id,
    status,
    artifact_bundle_ref,
    dashboard_bundle_ref,
    issue_manifest_ref,
    evidence_ids,
    error=None,
)
~~~

编排顺序：

1. 读取并校验 Input Snapshot。
2. 将 AnalysisRun 更新为 running。
3. 调用 run_real_waveform_evaluation。
4. 调用 recommendation。
5. 可选生成只读候选建议。
6. LLM 默认关闭；LLM 失败不得使核心分析失败。
7. 调用 run_product_demo。
8. 生成 Issue manifest。
9. 在临时目录完成所有输出。
10. 整体发布到 Artifact Store。
11. 建立 EvidenceRecord。
12. 更新 AnalysisRun 为 completed 或 evidence_incomplete。
13. 失败时更新为 failed，并保留结构化错误与可用日志。

AnalysisService 不复制：

- waveform_io
- windowing
- metrics
- scorer
- diagnosis
- recommendation
- candidate algorithm
- product_demo builder

## 11. 旧 API 兼容

src/goa_eval/web/runners.py 调整为兼容适配器。

要求：

- CaseRunResult 字段不变。
- /api/cases 行为不变。
- /api/cases/preview 行为不变。
- /api/demo/sample-case 行为不变。
- 旧输出目录和 bundle URL 不变。
- 旧测试全部通过。
- 同一输入的 summary、score 和 evidence 与新 AnalysisService 一致。
- 旧 Demo 可使用临时 service context，不创建正式项目。

## 12. IssueService

新增：

~~~text
src/goa_eval/product/issue_service.py
~~~

Phase 1 不增加 Issue 表。问题写入 issues.json Artifact。

Issue：

~~~json
{
  "issue_id": "issue_xxx",
  "constraint_key": "FAIL_RIPPLE",
  "category": "waveform_quality",
  "severity": "high",
  "affected_nodes": [],
  "metric_refs": ["max_ripple"],
  "possible_causes": [],
  "recommended_actions": [],
  "evidence_refs": [],
  "classification": "known"
}
~~~

规则：

- 已知失败映射为稳定类别。
- 未知失败必须产生 unclassified Issue。
- possible_causes 是可能原因，不是确认根因。
- severity 不覆盖 hard constraint 状态。
- Markdown diagnosis 继续保留并可下载。

## 13. EvidenceService

新增：

~~~text
src/goa_eval/product/evidence_service.py
~~~

接口：

~~~python
index_analysis_artifacts(run_id, artifact_refs, raw_evidence)
validate_boundary(evidence)
can_confirm_improvement(candidate, result_run)
summarize_completeness(run_id)
~~~

索引：

- input manifest
- profile snapshot
- spec revision
- real summary
- score summary
- metrics CSV
- figure manifest
- report files
- dashboard bundle
- issue manifest

Phase 1 中 can_confirm_improvement 对所有只读建议返回 false。

## 14. Product API

新增：

~~~text
src/goa_eval/product_api/
├── __init__.py
├── app.py
├── schemas.py
├── dependencies.py
├── errors.py
└── routes/
    ├── workspaces.py
    ├── projects.py
    ├── inputs.py
    └── analyses.py
~~~

API：

### Workspace

~~~text
POST /api/v1/workspaces
GET  /api/v1/workspaces/{workspace_id}/projects
~~~

### Project

~~~text
POST /api/v1/projects
GET  /api/v1/projects/{project_id}
GET  /api/v1/projects/{project_id}/overview
~~~

### Design Version

~~~text
POST /api/v1/projects/{project_id}/design-versions
GET  /api/v1/projects/{project_id}/design-versions
GET  /api/v1/design-versions/{version_id}
~~~

### Input

~~~text
POST /api/v1/design-versions/{version_id}/inputs/preview
~~~

### Analysis

~~~text
POST /api/v1/design-versions/{version_id}/analysis-runs
GET  /api/v1/analysis-runs/{run_id}
GET  /api/v1/analysis-runs/{run_id}/bundle
GET  /api/v1/analysis-runs/{run_id}/issues
GET  /api/v1/analysis-runs/{run_id}/evidence
~~~

成功响应：

~~~json
{
  "schema_version": "1.0",
  "data": {}
}
~~~

错误响应：

~~~json
{
  "error_code": "INPUT_SNAPSHOT_NOT_FOUND",
  "message": "Input snapshot was not found.",
  "details": {},
  "retryable": false,
  "artifact_refs": []
}
~~~

错误码：

- WORKSPACE_NOT_FOUND
- PROJECT_NOT_FOUND
- DESIGN_VERSION_NOT_FOUND
- CIRCUIT_PROFILE_INVALID
- INPUT_PREVIEW_FAILED
- INPUT_SNAPSHOT_NOT_FOUND
- ANALYSIS_STATE_CONFLICT
- ANALYSIS_EXECUTION_FAILED
- EVIDENCE_BOUNDARY_INVALID
- ARTIFACT_NOT_FOUND

ProductContainer 负责组装 settings、engine、repository、artifact store 和 services。测试必须注入临时容器。

## 15. 前端视觉方向

### 15.1 核心方向

采用“工程证据控制台 / Evidence Cockpit”风格：

- 深海军蓝背景。
- 青色用于主操作和信息状态。
- 琥珀色用于证据警告。
- 红色只用于明确失败。
- 绿色只用于已验证通过。
- 使用细网格、微弱径向光和克制阴影保留工程感。
- 避免营销落地页式大面积渐变、玻璃卡片堆叠和夸张动画。
- 视觉重点放在项目上下文、约束、证据和异常。

现有 styles.css 的深色背景和网格可保留，但产品页面需要从“单页演示海报”转向稳定的应用框架。

### 15.2 布局

桌面：

- 左侧导航宽度 232px。
- 顶部项目上下文栏 64px。
- 内容区最大宽度 1600px。
- 12 列网格。
- 页面水平边距 24 至 32px。
- 8px 基础间距系统。
- 核心卡片圆角 12px。
- 数据表和图表优先获得横向空间。

平板：

- 左侧导航收起为图标栏或抽屉。
- 内容使用 8 列网格。
- KPI 卡片两列。

移动端：

- 单列布局。
- 表格允许横向滚动。
- 主操作固定在可见区域，但不得遮挡证据声明。
- 不要求在移动端完成复杂波形研究，但必须可查看状态和报告。

目标断点：

- 390px
- 768px
- 1024px
- 1280px
- 1440px
- 1920px

### 15.3 视觉层级

每个产品页固定为：

1. Breadcrumb 与项目上下文。
2. 页面标题和主要操作。
3. 状态摘要。
4. 核心工作区。
5. 证据与辅助信息。
6. Artifact 和技术细节。

标题不再使用 Demo 页的 6xl 大标题。产品页建议：

- 页面标题：28 至 36px。
- 区块标题：16 至 18px。
- 数据值：20 至 28px。
- 正文：14px。
- 辅助文本：12 至 13px。

### 15.4 状态色

- info / running：cyan
- warning / evidence incomplete：amber
- pass / verified：emerald
- fail / blocked：red
- neutral / missing：slate

颜色不能作为唯一信息来源，所有状态同时显示图标和文字。

### 15.5 组件规范

新增基础组件：

- AppSidebar
- ProjectContextBar
- PageHeader
- SectionPanel
- MetricCard
- EmptyState
- ErrorState
- LoadingSkeleton
- DataTableShell
- ArtifactList
- IssueCard
- EvidenceSummary

现有组件继续复用：

- OverviewCards
- EvidenceBoundaryCard
- ConstraintStatusPanel
- FiguresGallery
- ReportsPanel

现有组件需要通过 props 和容器适配产品布局，不复制代码。

### 15.6 动效

- 页面进入动画不超过 240ms。
- 只对导航、展开、状态切换使用动效。
- 图表不得为了装饰自动循环动画。
- 支持 prefers-reduced-motion。
- Loading 使用骨架屏，不使用持续旋转的大型 Logo。

### 15.7 图表与数据密度

- 图表标题必须包含指标与单位。
- Pass/Fail 使用稳定语义色。
- 波形和趋势图保留缩放或大图入口。
- 720 级数据优先使用热力图、趋势和异常区段摘要。
- 表格表头在长列表中保持可见。
- 数字按统一精度和工程单位格式化。
- 不用大量彩色 KPI 卡片稀释真正异常。

## 16. 前端页面

### ProjectListPage

- 工作区名称与项目数。
- 搜索和创建项目。
- 项目卡或紧凑表格。
- Profile、版本数、最近分析、硬约束和证据状态。
- 空状态提供“创建首个 GOA 项目”和“打开公开 Demo”。

### NewProjectPage

- 两步向导：基础信息、GOA 配置。
- GOA reference profile 为推荐默认值。
- 显示 Profile 来源和 simulation-only 边界。
- 校验错误靠近字段展示。

### ProjectOverviewPage

- 项目摘要和 Profile。
- 最新设计版本。
- 最近分析状态。
- 硬约束和证据摘要。
- 设计版本时间线。
- 创建新版本和进入最新分析的主操作。

### DesignVersionPage

- 文件上传。
- Input Preview。
- 参数、节点和网表摘要。
- 警告与错误。
- 分析历史。
- 执行分析按钮。

### AnalysisRunPage

- 总体状态与证据边界。
- 约束面板。
- Issue 列表。
- 指标与图表。
- 只读候选建议。
- 报告。
- Artifact 明细。

### DemoPage

- 保留现有公开 Demo。
- 调整为产品导航下的独立入口。
- 不与正式 Project 混淆。

## 17. 前端状态设计

必须区分：

| 状态 | 文案与行为 |
|---|---|
| 文件已选择 | 尚未上传或预检 |
| Preview ready | 输入结构可进入分析 |
| Preview warning | 可分析但存在风险 |
| Preview failed | 阻止分析并显示错误 |
| Analysis running | 指标计算中 |
| Analysis completed | 软件链路完成 |
| Hard constraint failed | 分析完成但设计不满足规格 |
| Evidence incomplete | 输出存在但证据不完整 |
| Resource failed | 部分图表或报告不可用 |

禁止使用一个“成功”同时表示 Preview、Analysis 和 Hard Constraint。

## 18. 可访问性

- 键盘可访问所有主操作。
- Focus ring 清晰可见。
- 状态不只依赖颜色。
- 表格具有 caption 或 aria-label。
- 图表具有文本摘要。
- 对比度满足 WCAG AA 的常用文本要求。
- 错误消息与对应字段关联。
- Reduced motion 生效。

## 19. 错误处理

ProductError 字段：

- error_code
- message
- details
- retryable
- artifact_refs

规则：

- Domain 层不抛 FastAPI HTTPException。
- Product API 统一映射 HTTP 状态。
- 核心分析失败必须更新 AnalysisRun。
- LLM 失败只产生 warning。
- Artifact 发布失败不得留下 completed 状态。
- 未知 Issue 不丢失。
- 前端保留 error_code 和可操作建议。
- Resource 加载失败不应让整个分析页空白。

## 20. 测试设计

### 后端

- Repository 查询扩展。
- ProjectService。
- Profile 快照。
- Input Snapshot。
- AnalysisService 成功与失败。
- 旧 API parity。
- Issue 映射。
- Evidence 完整性。
- Product API DTO 和错误。

### 一致性

使用 examples/sample_waveform.csv 和 examples/sample_params.yaml，经 CLI、旧 API、新 API 比较：

- overall status
- overall score
- hard constraints
- stage count
- core metrics
- exact evidence boundary

### 前端

- 路由。
- 项目空状态。
- 新建项目。
- 上传和 Preview。
- 分析状态。
- Issue 和 Evidence。
- 旧 Demo 兼容。
- 390/768/1280 宽度下关键布局。
- reduced motion。
- 键盘 focus。

### 视觉验收

实施前端任务时必须调用 @frontend-skill，并使用 @playwright 或等价浏览器验证：

- 1440x900 桌面截图。
- 1024x768 平板截图。
- 390x844 移动截图。
- 无横向页面溢出。
- 关键 CTA、证据边界和错误状态可见。
- 页面视觉层级与本设计一致。
- 不出现 Demo 大标题挤压工作区。
- 不出现空白、截断或低对比度文字。

## 21. 实施拆分

建议八个任务：

1. Repository 查询扩展。
2. ProjectService 与 Profile 快照。
3. InputService 与 Input Snapshot。
4. AnalysisService。
5. 旧 API 兼容适配。
6. IssueService 与 EvidenceService。
7. Product API。
8. React 产品工作区与视觉系统。

评审批次：

- 批次 A：任务 1 至 3。
- 批次 B：任务 4 至 6。
- 批次 C：任务 7 至 8。

每个任务执行 TDD，并独立提交。

## 22. Phase 1 完成条件

- 页面可创建 GOA 项目。
- 页面可创建 baseline 设计版本。
- 页面可上传并预检输入。
- Preview 与 Analysis 状态明确分离。
- 页面可完成一次 GOA 分析。
- 分析结果包含约束、Issue、图表、报告和证据。
- 所有正式输入输出进入 Artifact Store。
- SQLite 不保存大型文件。
- CLI、旧 API 和新 API 核心结果一致。
- 旧 Demo 和 Dashboard 可运行。
- 只读候选不会显示为确认改善。
- 三个证据边界字段完整。
- Python 完整回归通过。
- 前端测试与生产构建通过。
- 三种视口完成浏览器视觉验收。
- 页面达到工程控制台的视觉一致性和可读性要求。

