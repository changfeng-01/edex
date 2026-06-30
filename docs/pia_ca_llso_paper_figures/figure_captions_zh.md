# PIA-CA-LLSO 论文图注草稿

**图 1. PIA-CA-LLSO 图形摘要。** 该图概述从历史仿真 CSV 与候选设计出发，经物理语义特征映射、CAPM-Distance、PIA 采集选择、下一轮仿真批次和结果导入形成闭环的流程。图中所有结果边界限定为 `data_source = real_simulation_csv`、`engineering_validity = simulation_only`、`must_resimulate = true`。

**图 2. PIA-CA-LLSO 闭环架构。** 该图展示 L1/L2/L3/L4 标签、LLSO offspring、候选修复、PIA selector、仿真批次、结果导入、resume state 与 boundary audit 的模块关系。

**图 3. CAPM-Distance 物理语义流形示意。** 原始设计变量通过 `phi(x)` 映射到物理特征空间，候选点到 L1 basin 的距离由 tensor/coupling 距离、soft barrier、missing penalty 和图上 geodesic 共同刻画。barrier 仅是仿真前风险 proxy，不等同于真实硬约束失败。

**图 4. 候选采集集成层。** CAPM 距离、自适应物理权重、分类器概率、多样性、不确定性和五篇论文启发式子分量共同形成 `A(x)`，用于排序下一轮仿真建议；该层不是对五篇论文算法的完整复现。

**图 5. 策略基准证据视图。** 若本地存在 Phase 3 `validation_summary.csv`，该图展示正式验证汇总；否则展示已有 sample/smoke benchmark artifact 中可审计的方法和边界字段，不作为最终优越性证据。

**图 6. 消融与边界审计。** 该图汇总可用的验证指标或在正式验证缺失时显式标记待补指标，同时展示 `real_simulation_csv / simulation_only / must_resimulate` 等边界字段。

**图 7. 候选采集诊断。** 该图基于 `pia_selected_candidates.csv` 或样例候选池展示 `acquisition_score`、CAPM 距离、barrier 和候选角色，用于解释下一轮仿真建议，不代表最终真实性能证据。
