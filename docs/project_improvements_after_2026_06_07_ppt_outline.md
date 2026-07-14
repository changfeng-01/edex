# 6月7日后项目改进导师汇报 PPT 大纲

> 目标：用于导师组会或阶段性汇报。重点讲“做了什么、相比之前改进了什么、当前证据能支持什么、还有哪些问题未解决”。不按文件清单汇报，也不把 smoke/local fixture、selection-only 或论文数字化证据说成真实物理仿真结论。

## 建议汇报定位

- 建议时长：12-15 分钟。
- 建议页数：14 页正文 + 2 页备用页。
- 叙事主线：从“算法想法”推进到“闭环优化系统”和“发表级验证框架”。
- 汇报口径：强调工程可信度、实验可复现性、证据边界和下一步真实仿真补强。
- 设计风格：少文字、多流程图和对比图；每页只讲一个核心判断。

## 一句话主线

6月7日后，我把项目从“能给候选建议的优化器”推进到“能闭环演化、能协议化验证、能审计证据边界、能支撑论文讨论的 PIA-CA-LLSO 研究框架”，但真实物理性能结论仍需要后续真实仿真 case pack 补强。

## Slide 1. 标题页

**标题**

6月7日后项目阶段性改进汇报：PIA-CA-LLSO 闭环优化与可信验证框架

**页面重点**

- 时间范围：2026-06-07 之后
- 汇报对象：导师阶段性讨论
- 主题：做了什么、改进了什么、还缺什么

**视觉建议**

- 用一张横向流程背景图：候选生成 -> 仿真批次 -> 结果导入 -> 闭环演化 -> 验证审计 -> 论文证据。
- 颜色建议：深蓝/石墨灰做技术底色，绿色表示“已完成”，橙色表示“待补强证据”。

**口头讲法**

> 这次汇报不按代码提交讲，而是按研究能力讲：我这段时间主要补了闭环、验证、证据边界和论文材料四个层面。

## Slide 2. 汇报总览：从工具到研究框架

**核心信息**

项目阶段发生了三个层级的变化。

**页面内容**

- 之前：候选推荐、离线分析、局部 benchmark。
- 现在：闭环演化 + 协议化验证 + 证据审计。
- 下一步：真实仿真 case pack + formal validation + 论文 claim 确认。

**视觉建议**

三段式阶梯图：

1. Candidate suggestion
2. Closed-loop validation framework
3. Publication-ready evidence package

**口头讲法**

> 最大变化不是新增一个评分公式，而是把候选生成到证据封装这条链路补起来，让后续实验更可复现、更适合写论文。

## Slide 3. 原来的关键问题

**核心信息**

6月7日前，项目的主要短板不是“没有算法”，而是“证据链不够闭环”。

**页面内容**

- 算法建议和仿真结果之间缺少闭环状态管理。
- 实验比较缺少统一 protocol，容易变成单次 smoke。
- 公开论文/专利数据容易被误解为真实仿真证据。
- 论文材料缺少 claim boundary 和 source lock。

**视觉建议**

用“风险矩阵”展示四类风险：

- 可复现性
- 仿真接口
- 方法公平比较
- 论文证据边界

**口头讲法**

> 所以后续我没有继续堆新 ranking，而是优先补可信度：怎么跑、怎么比较、怎么审计、哪些话能写进论文。

## Slide 4. 改进一：PIA-CA-LLSO 方法本体更清楚

**核心信息**

PIA-CA-LLSO 的算法结构已经从散点式模块整理成可解释的方法体系。

**做了什么**

- 建立候选选择基础：raw distance、physics distance、CAPM distance、memory attention。
- 加入约束修复：adaptive PIA CAPM repair、constraint ledger。
- 加入混合调度：classifier-level hybrid、evaluation scheduler。
- 引入文献先验：literature ensemble hybrid。
- 形成中文方法定义和创新点总结。

**改进了什么**

- 从“能算分”变成“能解释为什么这样选候选”。
- 从单一距离度量变成物理先验、约束修复、分类器调度的组合策略。

**视觉建议**

画三层方法结构图：

- 底层：物理/结构先验
- 中层：约束修复和候选生成
- 上层：分类器/文献混合调度

**证据边界**

- 这是方法和工程框架改进。
- 还不能单独证明真实物理性能优越。

## Slide 5. 改进二：从候选推荐走向闭环演化

**核心信息**

PIA 现在不只是输出候选参数，而是能按 generation 组织闭环演化。

**做了什么**

- 建立 `pia-evolve` 闭环入口。
- 建立 evolution state schema。
- 支持 LLSO offspring generation。
- 支持仿真批次 contract 和结果导入。
- 支持 resume from pending generation。
- 增加 local fixture 和 simulator adapter 边界。

**改进了什么**

- 从“一次性推荐”变成“可持续迭代”。
- 从手工拼接仿真结果变成有 contract 的输入输出流。
- 从中断后重跑变成可恢复运行。

**视觉建议**

闭环流程图：

History + Candidate Pool -> Select -> Simulation Batch -> Simulator/Fixture -> Result Import -> Update State -> Next Generation

**口头讲法**

> 这一步是工程上最关键的变化：PIA 开始具备真正闭环优化系统的形态。

## Slide 6. 改进三：仿真接口边界更明确

**核心信息**

仿真不再只是“将来接一下”，而是已经定义了批次、结果、adapter 和日志边界。

**做了什么**

- 定义 simulation batch contract。
- 定义 simulation result schema。
- 建立 result import 和 schema validation。
- 建立 external simulator adapter boundary。
- 对 local fixture 做清晰定位。

**改进了什么**

- 算法输出和仿真执行之间有明确协议。
- 能区分测试 fixture、导入 CSV 和真实外部仿真。
- 后续接 Empyrean/外部仿真器时接口歧义更少。

**视觉建议**

画“算法侧”和“仿真侧”的接口边界图，中间是 batch/result contract。

**证据边界**

- local fixture 只用于确定性测试和 smoke，不是物理仿真器。
- 候选输出仍是 next-run simulation suggestions。

## Slide 7. 改进四：实验验证从 smoke 变成 protocol

**核心信息**

验证体系从单次运行升级为 `pia-validate` 协议化验证框架。

**做了什么**

- 建立 validation protocol schema。
- 建立 scenario registry。
- 建立 ablation config builder。
- 建立 validation runner、statistics、report。
- 接入 `pia-validate` 统一验证入口。

**改进了什么**

- 从“跑一次看结果”变成“按协议比较方法”。
- 从单个场景变成可扩展的 scenario 管理。
- 从人工整理结果变成自动统计和报告。

**视觉建议**

用 pipeline 图：

Validation Protocol -> Scenario Registry -> Method/Ablation Runs -> Statistics -> Report

**口头讲法**

> 这部分解决的是导师最可能问的“怎么公平比较”和“别人怎么复现”的问题。

## Slide 8. 改进五：多预算、多 seed、多场景评估

**核心信息**

验证不再只看一个 top-k，而是支持 scenario × seed × budget × method。

**做了什么**

- 支持多 budget replay。
- 支持多 seed 汇总。
- 支持多场景比较。
- 引入 best-so-far curve。
- 输出 pairwise win rates。
- 增加 sklearn surrogate baseline 等对照。

**改进了什么**

- 能观察不同仿真预算下是否更快命中目标。
- 能减少单次随机结果或单场景结果带来的误导。
- 能为论文结果表和消融图提供结构化来源。

**视觉建议**

用三维矩阵图或小 multiples：

- 横轴 budget
- 纵轴 method
- 分面 scenario/seed

也可以展示一张简化 best-so-far 曲线示意图。

**证据边界**

- 目前框架已经具备。
- 强性能 claim 仍依赖真实 case pack 的完整运行结果。

## Slide 9. 改进六：证据封装和 strict validation

**核心信息**

发表前最容易被质疑的是证据来源，现在已建立 case pack 和 strict evidence validation。

**做了什么**

- 定义 real simulation case pack。
- 建立 evidence case pack contract。
- 建立 strict evidence validation。
- 检查候选和结果是否对齐。
- 检查结果泄漏和证据缺失。
- 支持 publication evidence inventory/report。

**改进了什么**

- 从只给 summary table 变成能追溯每个实验来源。
- 从“相信结果”变成先检查证据完整性。
- 从后期补材料变成一开始就锁定实验证据。

**视觉建议**

画 case pack 六块拼图：

- scenario
- history
- candidate pool
- simulation results
- scoring config
- provenance

**口头讲法**

> 我把实验材料做成可审计包，这样导师和评审可以看到结果从哪里来，不只是看最终平均数。

## Slide 10. 改进七：fairness/leakage/source-lock 审计

**核心信息**

formal validation 进一步补了公平比较、数据泄漏和证据漂移风险。

**做了什么**

- 加入 fairness audit。
- 加入 leakage audit。
- 加入 method registry。
- 加入 source lock。
- 记录 scenario、method、budget、seed、输入和输出来源。

**改进了什么**

- 避免不同方法比较时预算或 seed 不一致。
- 避免 candidate pool 或 surrogate baseline 意外使用结果列。
- 避免论文复现实验时输入和结果版本漂移。

**视觉建议**

用“审计检查清单”图示：

- Fair comparison?
- No leakage?
- Same budget?
- Source locked?
- Claim boundary preserved?

**证据强度分级**

- 高可信：框架、协议、审计机制已实现。
- 中等可信：smoke/local fixture 证明流程可运行。
- 低可信/待补：真实物理性能优越性。

## Slide 11. 改进八：论文和答辩材料开始成型

**核心信息**

工程成果已开始转化为论文方法、创新点、图示和答辩讲法。

**做了什么**

- 形成中文方法定义。
- 形成核心创新点总结。
- 形成论文图包思路。
- 形成 IEEE 中文稿草稿。
- 形成证据 appendix 和 claim boundary checklist。
- 形成答辩讲稿框架。

**改进了什么**

- 从“代码做了很多”变成“能和导师讨论论文结构”。
- 从“实验结果先写强结论”变成“先确认 claim boundary”。

**视觉建议**

不要列文件。用“论文材料工作台”示意图：

Method -> Figures -> Evidence Appendix -> Claim Boundary -> Manuscript -> Defense Q&A

**口头讲法**

> 我现在把论文材料写得比较保守，重点是框架和证据链成立，真实性能提升等强结论等真实仿真补齐后再写。

## Slide 12. 当前最重要的证据边界

**核心信息**

当前能证明的是“框架可运行、验证可审计”，还不能证明“真实物理场景全面优越”。

**可以讲**

- PIA-CA-LLSO 已有闭环优化框架。
- 已有协议化验证体系。
- 已有 evidence case pack 和 strict validation。
- 已有 fairness/leakage/source-lock 审计思路。
- 已有论文和答辩材料雏形。

**不能强讲**

- 真实电路物理仿真中全面优于所有 baseline。
- local fixture 等同真实 simulator。
- paper/patent digitized 数据等同真实仿真 CSV。
- selection-only 场景等同完整闭环验证。
- 候选建议等同已验证设计。

**必须保留的边界词**

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

**视觉建议**

左右对比：

- 左：Supported now
- 右：Need more evidence

## Slide 13. 仍未完成的问题

**核心信息**

下一阶段的瓶颈不是再发明一个新算法，而是真实仿真证据和 formal validation 完整闭环。

**未完成 1：真实仿真 case pack 不足**

- 需要 5-8 个真实或可复现实验 case pack。
- 每个 case pack 需要完整 scenario、history、candidate pool、simulation results、scoring config、provenance。

**未完成 2：外部 simulator 证据不足**

- 需要保存 simulator invocation、stdout、stderr。
- 需要把外部仿真结果纳入 strict evidence 路径。

**未完成 3：强性能 claim 还不能定稿**

- 需要真实 case pack 运行后再决定提升幅度、优势范围和论文表述强度。

**未完成 4：论文材料还需与证据同步**

- 图、表、结论必须跟真实验证结果同步更新。
- claim boundary checklist 需要随实验结果复核。

**视觉建议**

用四象限“待解决问题地图”：

- 数据证据
- 仿真接口
- 统计验证
- 论文 claim

## Slide 14. 下一步计划

**核心信息**

下一步按“真实证据 -> formal validation -> 导师确认 claim -> 论文定稿”推进。

**行动 1：补真实仿真 case pack**

- 优先选择 5-8 个代表性 GOA 场景。
- 每个场景补齐输入、结果和 provenance。

**行动 2：跑完整 formal validation**

- 生成 validation summary。
- 生成 best-so-far curve。
- 生成 pairwise win rates。
- 生成 fairness/leakage/source-lock 报告。

**行动 3：和导师确认论文 claim**

- 哪些可以现在讲。
- 哪些只能弱化讲。
- 哪些必须等真实仿真后再讲。

**行动 4：同步论文图表**

- 根据真实验证结果更新图表和结论。
- 保持 simulation-only 边界不被误写。

**视觉建议**

路线图：

Case Pack -> Formal Validation -> Evidence Review -> Claim Decision -> Manuscript Update

## Slide 15. 总结页

**核心信息**

这段时间的主要成果是把项目推进到“可以被验证和被审计”的阶段。

**三点总结**

1. 方法层面：PIA-CA-LLSO 已形成物理先验、约束修复、混合调度和闭环演化框架。
2. 验证层面：已形成 `pia-validate`、多预算多场景验证、case pack、fairness/leakage/source-lock 审计。
3. 论文层面：已形成方法、创新点、图示和答辩材料雏形，但真实性能 claim 仍需真实仿真补证。

**最后一句**

> 当前阶段可以向导师汇报为：框架和验证体系已经搭好，下一阶段重点转向真实仿真证据补强和论文 claim 定稿。

**视觉建议**

用一张“已完成 vs 下一步”的双栏总结图。

## 备用页 A. 如果导师追问“为什么不直接声称效果提升？”

**回答逻辑**

- 当前证据主要证明流程可运行、验证可审计。
- smoke/local fixture 不是物理 simulator。
- 公开论文/专利数字化是弱证据。
- selection-only 场景不能替代完整闭环验证。
- 强 claim 需要真实 case pack 和 formal validation 支撑。

**建议口头回答**

> 我现在刻意没有把结论写强，因为这样更符合论文证据边界。等真实仿真 case pack 补齐后，才能决定性能提升写到什么程度。

## 备用页 B. 如果导师追问“下一步最优先做什么？”

**建议回答**

第一优先级是补真实仿真 case pack，不是继续加新 ranking。

**原因**

- 算法和验证框架已有。
- 当前最缺的是真实仿真证据。
- case pack 一旦补齐，就能直接进入 `pia-validate` 和 formal audit。
- 这会直接决定论文能写多强的实验结论。

## 图示和可视化建议

为避免文字堆叠，建议实际做 PPT 时优先画以下 6 类图：

1. **总流程图**：候选生成 -> 仿真批次 -> 结果导入 -> 演化状态 -> 验证审计。
2. **方法三层图**：物理先验 -> 约束修复 -> 混合调度。
3. **验证 pipeline 图**：protocol -> scenario -> method/ablation -> statistics -> report。
4. **case pack 拼图图**：六个证据组成块。
5. **证据强度阶梯图**：framework implemented -> smoke runnable -> real validation pending。
6. **下一步路线图**：case pack -> formal validation -> claim review -> paper update。

## 汇报时应避免的说法

- 避免：“已经证明 PIA 全面优于 baseline。”
- 改为：“已经建立可公平比较 PIA 与 baseline 的验证框架，真实优越性需要更多真实仿真 case pack 支撑。”

- 避免：“local fixture 就是真实仿真。”
- 改为：“local fixture 是确定性测试支撑，用于证明流程可跑，不作为物理仿真结论。”

- 避免：“论文数字化数据就是仿真数据。”
- 改为：“论文/专利数字化数据是弱证据和场景来源，真实工程结论仍需自跑或导入仿真结果。”

- 避免：“候选建议就是优化成功。”
- 改为：“候选建议是 next-run simulation suggestions，必须重新仿真确认。”

## 15 分钟时间分配

- 0:00-1:30：Slide 1-3，讲背景变化和原问题。
- 1:30-6:30：Slide 4-8，讲方法、闭环和验证体系。
- 6:30-10:30：Slide 9-12，讲证据、审计和论文边界。
- 10:30-13:30：Slide 13-14，讲未完成问题和下一步。
- 13:30-15:00：Slide 15，总结并引导导师讨论 claim。

## 给导师的结尾问题

建议最后主动问导师三个问题：

1. 当前论文主 claim 是否应先定位为“闭环优化与验证框架”，而不是“已证明全面性能提升”？
2. 下一阶段真实仿真 case pack 应优先选哪几类 GOA 场景？
3. formal validation 中哪些 baseline 和 ablation 是导师认为必须保留的？
