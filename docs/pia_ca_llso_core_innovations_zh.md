# PIA-CA-LLSO 核心创新点总结

本文档用于论文写作、导师汇报和答辩材料整理。当前创新点的主线应聚焦在 **物理语义距离驱动的昂贵仿真闭环候选选择**，而不是泛泛表述为“使用距离”或“融合多个优化算法”。

正式的方法定义、完整公式和伪代码以 `docs/pia_ca_llso_formal_method_zh.md` 为准。论文写作中应保持四个层级的术语区分：`overall_score` 是单次仿真评分层，`objective_score` 是 profile 加权目标层，`acquisition_score` 是候选采集层，`simulations_to_target` 是实验主结果层。

## 1. 总体论文定位

PIA-CA-LLSO 面向 GOA 显示驱动电路优化中的小样本、昂贵仿真、硬约束和证据边界问题。核心思想是：将候选解从原始参数空间映射到电路物理语义空间，在该空间中定义约束感知物理流形距离，并用它指导下一轮仿真候选选择。

推荐的论文主张：

> 本文提出一种面向 GOA 显示驱动电路的 Physics-Informed Adaptive CA-LLSO 框架。该框架通过约束感知物理流形距离 CAPM-Distance，将候选选择从原始参数空间推进到电路物理语义空间，并在昂贵仿真预算下实现可审计的闭环候选推荐、仿真调度与验证报告。

必须保持的证据边界：

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- must_resimulate = true

## 2. 主创新一：物理语义特征空间

传统参数距离直接比较原始设计变量，容易把不同物理含义的量混在一起。PIA-CA-LLSO 先构造物理语义特征 `phi(x)`，再计算候选间距离。

GOA profile 中的代表性物理特征包括：

- `pullup_w_l`：上拉 TFT 驱动能力 proxy
- `pulldown_w_l`：下拉 TFT 驱动能力 proxy
- `pullup_pulldown_ratio`：上下拉驱动平衡
- `cboot_cload_ratio`：bootstrap 电容与负载电容裕量
- `ron_pullup_cload_proxy`：上拉路径负载驱动压力
- `ron_pulldown_cload_proxy`：下拉路径负载驱动压力
- `clk_slew_proxy`：时钟边沿速度 proxy
- `vgh_vth_margin`：高电平门压相对阈值漂移裕量
- `vgl_off_margin`：低电平关断裕量
- `holding_droop_proxy`：保持能力 proxy

论文表述重点：

> 创新不在于简单使用距离，而在于把距离定义在由电路物理机制构成的语义空间中，使候选选择更接近电路设计中的真实约束关系。

## 3. 主创新二：CAPM-Distance 约束感知物理流形距离

CAPM-Distance 是当前最核心、最适合作为论文方法贡献的创新点。

CAPM-Distance 可表述为：

```text
D_capm(x, y) =
  D_tensor(x, y)
+ lambda_barrier * D_barrier(x, y)
+ lambda_graph * D_geodesic(x, y)
+ lambda_missing * D_missing(x, y)
```

四个组成部分的含义：

| 组成项 | 作用 | 论文意义 |
|---|---|---|
| `D_tensor` | 在物理语义特征上计算各向异性距离 | 替代原始参数空间欧氏距离 |
| `D_barrier` | 对低裕量、高 RC 压力、不平衡驱动等风险加入软约束惩罚 | 将硬约束风险前置到仿真前候选排序 |
| `D_geodesic` | 构建 candidate + history 的小型 kNN 图，计算到 L1 basin 的最短路径 | 避免只看直线距离而忽略高风险路径 |
| `D_missing` | 对缺失关键物理输入加入可信度惩罚 | 防止缺失特征被错误视为零距离 |

论文表述重点：

> CAPM-Distance 将 CA-LLSO 的 L1 邻域思想从 raw parameter space 扩展到 constraint-aware physics manifold，使候选选择关注“是否接近高质量可行区域”，而不是仅关注参数数值是否接近。

## 4. 主创新三：L1-basin 引导的候选选择

PIA-CA-LLSO 的距离目标不是任意历史样本，而是高质量可行的 L1 区域。候选如果在物理流形上更接近 L1 basin，并且约束 barrier 更低，就更值得进入下一轮昂贵仿真。

该机制解决的问题：

- 原始参数距离无法表达电路物理等价性。
- 分类器概率高的候选不一定物理合理。
- 离某个 L1 样本直线距离近，不代表沿物理路径接近 L1 basin。
- 小样本情况下训练复杂 surrogate 容易不稳定。

论文表述重点：

> 本文将候选选择从“预测分数最大化”转为“高质量可行区域接近度 + 约束风险 + 多样性”的综合调度。

## 5. 主创新四：自适应物理先验

`adaptive_pia_capm` 在 CAPM-Distance 基础上，根据历史仿真样本学习特征权重和 acquisition 权重。

它的价值在于：

- 保留电路物理先验，不完全依赖黑盒模型。
- 根据历史结果动态强化与得分、硬约束通过率相关的物理维度。
- 当硬约束通过率较低时，提高约束风险项的重要性。
- 保持 `pia_capm_distance` 作为可对照 baseline，便于消融实验。

论文表述重点：

> 自适应 CAPM 将静态物理先验扩展为数据反馈驱动的物理先验，使小样本闭环优化可以在保守物理约束和历史仿真反馈之间动态平衡。

## 6. 主创新五：分类器、距离、约束风险的混合 acquisition

`classifier_level_hybrid` 将以下信息统一到候选评分中：

- `p_l1`：候选成为 L1 高质量样本的概率
- `p_hard_pass`：候选通过硬约束的概率
- `predicted_score`：预测性能分数
- `capm_distance`：到 L1 basin 的物理距离
- `capm_hard_risk_passed`：CAPM 约束风险门控
- `diversity_score`：候选多样性

这使方法不只是距离排序，也不是纯分类器排序，而是一个多证据融合的 candidate acquisition function。

论文表述重点：

> 本文将 surrogate 分类结果、物理语义距离、硬约束风险和多样性统一为候选 acquisition score，用于昂贵仿真预算下的下一轮候选调度。

## 7. 五篇论文借鉴的扩展层

最新加入的 `literature_ensemble_hybrid` 是对五篇导师相关论文思想的工程化吸收。它不是替代 CAPM-Distance，而是在 CAPM-Distance 之上增加可审计的 acquisition layer。

| 借鉴来源 | 吸收的思想 | 当前落地方式 |
|---|---|---|
| DEAOE | on-demand evaluation、约束优先评估 | `deaoe_on_demand_priority`、`deaoe_constraint_urgency` |
| HRCEA | 回归/分类协同、alpha-cut 可行性门控 | `hrcea_rectification_score`、`hrcea_alpha_gate_passed` |
| AIEA | influence degree、不确定性优先 | `aiea_influence_score`、`aiea_uncertainty_need` |
| CESAEA | 分类器集成和松弛投票 | `cesaea_relaxed_vote_score` |
| ECCoEA-ASAA | 自适应样本权重和模型聚合可信度 | `eccoea_asaa_sample_weight`、`eccoea_asaa_aggregation_trust`、`eccoea_asaa_weighted_score` |

论文定位建议：

> CAPM-Distance 是主创新；`literature_ensemble_hybrid` 是基于相关工作的可审计扩展 acquisition layer，用于增强候选选择、支持消融实验和论文对照。

`active_influence_on_demand` 将其中最适合当前低数据昂贵仿真的三类思想提升为正式主动采集策略：AIEA 的邻域 influence、DEAOE/HRCEA 的按需约束确认、以及分布式代理集成的保守 trust。它不是 `literature_ensemble_hybrid` 的替代，而是把 `active_uncertainty_diversity` 的 batch selection 扩展为可消融的预算调度策略。

需要注意：

- 目前该层仍是启发式工程融合。
- 如果作为强创新点，需要补充分量消融和权重敏感性实验。
- 论文中不宜直接声称其完整复现了 DEAOE、HRCEA、AIEA、CESAEA 或 ECCoEA-ASAA。

## 8. 主创新六：昂贵仿真闭环优化骨架

PIA-CA-LLSO 已经从单次候选排序扩展成闭环流程：

1. 读取历史仿真 CSV。
2. 按 `overall_score` 和 `hard_constraint_passed` 生成 L1/L2/L3/L4 标签。
3. 基于 L1 teacher 和 L2/L3 learner 生成 LLSO offspring。
4. 使用 PIA selector 选择下一轮候选。
5. 生成 simulation batch。
6. 离线等待、导入仿真结果，或调用外部 simulator。
7. 将结果追加回 history。
8. 根据预算、target score、patience 停止。
9. 输出 evolution summary、generation state 和 boundary audit。

论文表述重点：

> 本文不是只提出一个距离公式，而是将该距离嵌入可恢复、可审计、预算受限的昂贵仿真闭环中。

## 9. 主创新七：证据边界和发表级复现机制

当前工程中已经包含面向论文证据整理的机制：

- `boundary_audit`：检查输出是否保持 `simulation_only` 和 `must_resimulate`。
- `case_pack`：定义真实仿真 CSV case 的输入结构。
- `case_pack_validation`：生成 publication summary、win rates、evidence inventory、source lock。
- `validation_statistics`：输出 target hit rate、best score、simulations to target、hard pass rate、pairwise win rate。
- `source_lock.json`：锁定输入文件 hash、命令参数、git commit。

论文价值：

> 该机制使算法实验从“跑出一个结果”升级为“可复现、可审计、可限定证据边界的 simulation-only 研究流程”。

## 10. 建议写入论文的四条贡献

建议论文最终只写 4 条贡献，避免过散：

1. **提出 CAPM-Distance**：一种面向 GOA 显示驱动电路的约束感知物理流形距离，将候选选择从原始参数空间扩展到物理语义可行区域接近度。

2. **提出 PIA-CA-LLSO 候选选择框架**：融合 L1-basin proximity、物理约束 barrier、层级分类器、多样性和不确定性，实现小样本昂贵仿真预算下的候选 acquisition。

3. **构建可恢复的闭环仿真优化流程**：将 LLSO offspring、PIA selector、simulation batch、结果导入、resume 和 boundary audit 连接成端到端 workflow。

4. **建立 simulation-only 证据包与复现机制**：通过 case pack、source lock、publication report、pairwise win rate 和 boundary audit 支持保守、可审计的论文实验。

## 11. 不建议过度声称的内容

以下表述目前不宜写入论文结论：

- 已完成真实物理优化。
- 已替代 SPICE 仿真。
- 已完成硅验证、实测验证或 tapeout 验证。
- CAPM barrier 可以证明候选真实失败。
- `literature_ensemble_hybrid` 已严格复现五篇论文算法。
- 仅凭 smoke/local fixture 结果证明算法优于所有 baseline。

更稳妥的表述：

> 当前结果属于 simulation-only evidence。候选推荐仍是 next-run simulation suggestions，所有被选候选必须经过下一轮仿真确认。

## 12. 后续最关键实验

为了让创新点更适合投稿，需要补齐以下实验：

1. **CAPM 消融**：完整 CAPM vs 无 barrier vs 无 geodesic vs 无 coupling vs 无 missing penalty。
2. **策略对比**：random、ca_llso_raw_distance、pia_physics_distance、pia_capm_distance、adaptive_pia_capm、classifier_level_hybrid、active_uncertainty_diversity、active_influence_on_demand、literature_ensemble_hybrid。
3. **预算敏感性**：不同 simulation budget 下的 best score、target hit rate、simulations to target。
4. **约束效果**：hard pass rate、mean constraint violation、被 barrier 降权候选的后续仿真表现。
5. **小样本鲁棒性**：不同初始 history size 下的性能。
6. **真实 case-pack 复现**：使用固定输入、固定 seed、固定配置生成 publication summary 和 source lock。

## 13. 一句话总结

PIA-CA-LLSO 的核心创新不是简单使用距离，而是：

> 用 GOA 电路物理语义重新定义候选距离，并将该距离作为昂贵仿真闭环中的约束感知候选选择、预算调度和可审计验证核心。
