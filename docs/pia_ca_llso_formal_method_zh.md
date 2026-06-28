# PIA-CA-LLSO 正式方法定义

本文档给出 PIA-CA-LLSO 的统一方法定义，用于论文 Methods、答辩材料和代码审计之间的术语对齐。这里的定义不改变现有实现，而是把代码库中的 `overall_score`、`objective_score`、`hard_constraint_passed`、`acquisition_score`、`simulations_to_target`、CAPM-Distance、L1/L2/L3/L4 标签和闭环停止条件组织成同一套符号体系。所有表述均保持当前证据边界：data_source = real_simulation_csv，engineering_validity = simulation_only，must_resimulate = true。由 PIA-CA-LLSO 输出的候选仍然是 next-run simulation suggestions，而不是最终物理验证结果。

## 1. 问题定义

设 GOA 显示驱动电路的设计变量为 `x in X`，其中 `X` 是由配置文件 `parameter_columns` 给出的离散或连续搜索空间。一次昂贵仿真被表示为黑盒函数 `F(x) = (m(x), S(x), H(x))`，其中 `m(x)` 是仿真得到的指标集合，`S(x)=overall_score` 是单次仿真的总体性能分数，`H(x)=hard_constraint_passed` 是硬约束是否全部通过的二值变量。对于第 `t` 轮闭环，历史仿真集记为 `D_t = {(x_i, S_i, H_i, m_i)}`，候选池记为 `C_t`，预算记为 `B`，目标阈值记为 `T = target_score`。

PIA-CA-LLSO 的论文主目标不是直接最大化仿真前的候选分数，而是在有限仿真预算下尽快发现满足目标阈值和硬约束的候选。该目标写作 `tau_T = min { t | t <= B, S(x_t) >= T, H(x_t)=1 }`，实验中对应代码列 `simulations_to_target`，数值越小表示越少仿真次数即可达到目标。如果预算内未达到目标，则报告 `best_feasible_score`、`hard_pass_rate`、`convergence_auc` 和 `target_hit_rate` 等辅助指标。

方法中存在四个不同层次的“目标”概念，论文中必须分开表述。第一层是单次仿真评分层，`S(x)` 对应 `overall_score`。第二层是 profile 加权目标层，对应评分器输出的 `objective_score`，它用于解释特定 profile 下的加权目标，但不是 PIA 选择器的唯一排序依据。第三层是候选采集层，`A(x)` 对应 `acquisition_score`，它仅表示下一轮仿真的优先级。第四层是验证实验主结果层，`tau_T` 对应 `simulations_to_target`，用于比较不同策略在有限预算下达到目标的效率。

## 2. 约束和层级标签

硬约束目标定义为 `H(x)=1` 当且仅当仿真评分器认为所有硬约束通过。`hard_constraint_passed` 是来自仿真结果和评分器的证据字段，不能由 CAPM barrier 直接替代。CAPM 中的 barrier 只是在仿真前对候选风险进行排序的 proxy，因此论文中应写为 pre-simulation risk proxy，而不是写为真实失败判定。

历史样本根据 `overall_score` 和 `hard_constraint_passed` 被标注为 L1/L2/L3/L4。L1 表示高分且硬约束通过的样本，是 PIA-CA-LLSO 所追踪的高质量可行区域。L2 表示中等分数但仍可行的样本，可作为 learner 或可行边界参考。L3 表示低分可行样本或硬约束失败样本，它对边界学习和约束风险识别仍有价值。L4 表示仿真失败、不可评估或 predicted-only 样本，不能进入外部 benchmark 的真实证据集合。

Pareto/工程多目标排序层使用 `DEFAULT_OBJECTIVES`，其中包括最小化 `Max_overlap_ratio`、`Max_ripple`、`Max_voltage_loss`、`Delay_std` 和 `not_evaluable_metric_count`，同时最大化 `overall_score`、`hard_constraint_passed`、`target_passed` 和 `LowFreqStable`。该层用于工程排序和候选风格解释，不等同于 PIA 的 `acquisition_score`，也不等同于最终验证协议中的 `simulations_to_target`。

## 3. 物理语义特征映射

PIA-CA-LLSO 不直接在原始参数空间计算核心距离，而是先构造物理语义特征映射 `phi: X -> R^d`。对于 GOA profile，`phi(x)` 包含 `cboot_cload_ratio`、`pullup_pulldown_ratio`、`ron_pullup_cload_proxy`、`ron_pulldown_cload_proxy`、`vgh_vth_margin`、`vgl_off_margin`、`clk_slew_proxy` 和 `holding_droop_proxy` 等特征。这些特征由设计参数派生，表达 bootstrap/负载关系、上下拉驱动平衡、等效负载压力、门压裕量和时钟边沿压力等电路语义。

为避免标签泄漏，`phi_k(x)` 不能包含仿真结果列或评分结果列。禁止泄漏列包括 `overall_score`、`objective_score`、`hard_constraint_passed`、`delay`、`power`、`waveform_score`、`output_high`、`output_low`、`overshoot`、`undershoot` 和其他 imported-result metrics。该约束保证 CAPM-Distance 是仿真前候选排序方法，而不是把真实仿真结果泄漏进距离计算。

## 4. CAPM-Distance

CAPM-Distance 是 Constraint-Aware Physics-Manifold Distance，即约束感知物理流形距离。它的 pairwise 距离由物理张量项、物理耦合项、约束风险项和缺失特征惩罚项组成。张量与耦合距离写作 `D_tensor(x,y) = sqrt( sum_k w_k (phi_k(x)-phi_k(y))^2 + sum_(a,b) rho_ab (phi_a(x)phi_b(x)-phi_a(y)phi_b(y))^2 )`，其中 `w_k` 是物理特征权重，`rho_ab` 是特征耦合权重。耦合项用于表达 GOA 电路中 `Ron*Cload`、bootstrap/load margin、clock slew 和电压裕量之间的组合风险。

约束 barrier 写作 `B(phi(x)) = sum_j p_j(phi_j(x); theta_j)`。其中 `p_j` 是配置中的 penalty function，可以是 linear、quadratic 或 exponential penalty，`theta_j` 是仿真前筛选阈值。该 barrier 只描述候选的先验风险，例如低 `vgh_vth_margin`、低 `vgl_off_margin`、低 `cboot_cload_ratio`、高 `ron_pullup_cload_proxy`、高 `ron_pulldown_cload_proxy`、不平衡 `pullup_pulldown_ratio` 或过高 `clk_slew_proxy`。

CAPM pairwise 距离写作 `D_pair(x,y) = D_tensor(x,y) + lambda_barrier * max(B(phi(x)), B(phi(y))) + lambda_missing * M(x,y)`，其中 `M(x,y)` 是缺失关键物理特征的惩罚。候选到 L1 basin 的图上距离写作 `D_geodesic(x,L1) = min_{z in L1} shortest_path_G(x,z)`，图 `G` 由 candidate 和 history 节点构成，边权为 `D_pair`，邻接数量由 `k_neighbors` 控制。实现中同时保留 direct nearest-L1 距离和 kNN 图上最短路径距离，并输出 `capm_distance_to_l1`、`capm_geodesic_distance_to_l1`、`capm_barrier_score`、`capm_missing_penalty` 和 `capm_status`。

## 5. 候选采集函数

`pia_capm_distance` 的采集函数将 L1 basin 接近度、候选多样性、硬风险门控和缺失特征可信度合并为下一轮仿真优先级。其形式写作 `A_capm(x) = alpha_d (1 - norm(D_geodesic(x,L1))) + alpha_v diversity(x) + alpha_h I[B(phi(x))=0] + alpha_m (1 - M(x))`。在当前实现中，`capm_hard_risk_passed`、`capm_distance_to_l1_normalized`、`diversity_score` 和 `candidate_id` 共同决定稳定排序。

`adaptive_pia_capm` 保留 CAPM 的物理先验，但根据历史仿真结果调整特征权重和 acquisition 权重。当历史样本显示某些物理维度与 `overall_score` 或 `hard_constraint_passed` 更相关时，这些维度的权重会提高；当硬约束通过率较低时，约束风险项会获得更高权重。该策略的论文表述应是数据反馈驱动的物理先验自适应，而不是黑盒 surrogate 替代仿真。

`classifier_level_hybrid` 将分类器概率、预测分数、CAPM 距离、硬风险门控和多样性合并。其形式写作 `A_hybrid(x) = beta_1 p_L1(x) + beta_2 p_hard(x) + beta_3 pred_score(x) + beta_4 (1 - norm(D_geodesic)) + beta_5 hard_mask(x) + beta_6 diversity(x)`。其中 `p_L1(x)` 对应 `p_l1`，`p_hard(x)` 对应 `p_hard_pass`，`pred_score(x)` 对应 `predicted_score`，`hard_mask(x)` 对应 `capm_hard_risk_passed`。

`literature_ensemble_hybrid` 是可审计的扩展 acquisition layer，其形式写作 `A_lit(x) = sum_r omega_r A_r(x)`。这里的 `r` 对应 DEAOE、HRCEA、AIEA、CESAEA 和 ECCoEA-ASAA 启发式子分量，包括 on-demand priority、rectification score、influence score、relaxed classifier vote 和 adaptive aggregation trust。该层用于吸收相关工作思想并支持消融分析，不应写成对五篇论文算法的完整复现。

## 6. Algorithm 1: PIA-CA-LLSO 闭环优化主流程

```text
Input:
  history_csv, candidate_csv, config, budget B, target score T,
  selector strategy, top_k, resume state, simulation mode.

Output:
  selected_candidates, all_scored_candidates, generation_state,
  simulation_batch, boundary_audit, validation_summary.

1. Load configuration and verify boundary fields:
   data_source = real_simulation_csv,
   engineering_validity = simulation_only,
   must_resimulate = true.
2. Load D_t from history_csv and validate required columns:
   candidate/sample id, overall_score, hard_constraint_passed.
3. Load candidate pool C_t from candidate_csv and remove result leakage
   columns from pre-simulation candidate features.
4. Extract physics features phi(x) for D_t and C_t according to the
   configured profile.
5. Assign L1/L2/L3/L4 labels to D_t using overall_score and
   hard_constraint_passed.
6. Generate LLSO offspring from L1 teachers and L2/L3 learners when
   the strategy and ablation allow offspring generation.
7. Merge imported candidates, repair candidates, and LLSO offspring
   into the active candidate pool.
8. For each candidate x in C_t, compute the strategy-specific
   acquisition score A(x):
     CAPM distance, adaptive CAPM, classifier hybrid, or literature
     ensemble hybrid.
9. Sort candidates by acquisition score and strategy-specific tie
   breakers, select top_k candidates, and assign candidate roles:
   exploitation_best, l1_center, boundary_learning,
   diversity_exploration.
10. Emit selected candidates and a simulation batch. Each selected
    candidate remains a next-run simulation suggestion.
11. If simulation mode is offline, stop and wait for external results.
    If import_results mode is active, import the result CSV. If external
    command mode is active, invoke the simulator adapter and collect
    simulator invocation evidence.
12. Append imported simulation results to D_t and update generation
    state. Preserve data_source, engineering_validity, and
    must_resimulate in generated artifacts.
13. Stop when S(x) >= T and H(x)=1, when budget B is exhausted, or when
    patience/min-improvement rules are triggered.
14. Write evolution summary, run manifest, generation state, validation
    summary, and boundary audit.
```

## 7. Algorithm 2: CAPM-Distance 与 L1 basin 距离计算

```text
Input:
  candidate physics features phi(C_t), history physics features phi(D_t),
  L1 samples, feature weights w, coupling weights rho,
  barrier configuration theta, k_neighbors.

Output:
  capm_distance_to_l1, capm_geodesic_distance_to_l1,
  capm_barrier_score, capm_missing_penalty, capm_status.

1. Remove forbidden leakage columns including overall_score,
   objective_score, hard_constraint_passed, waveform metrics, and
   imported result metrics.
2. For every pair of candidate/history points, compute D_tensor(x,y)
   from weighted physical feature differences and enabled coupling
   products.
3. Compute B(phi(x)) and B(phi(y)) from configured soft barrier
   penalties.
4. Compute missing-feature penalty M(x,y).
5. Build D_pair(x,y) = D_tensor(x,y) +
   lambda_barrier * max(B(phi(x)), B(phi(y))) +
   lambda_missing * M(x,y).
6. Construct a kNN graph G over candidate and history records using
   D_pair as edge weight.
7. Identify L1 history nodes and compute D_geodesic(x,L1) as the
   shortest path from each candidate node to any L1 node.
8. If the graph path is unavailable, fall back to direct nearest-L1
   CAPM distance and mark capm_status accordingly.
9. Normalize geodesic distances for acquisition and emit CAPM
   diagnostic fields.
```

## 8. Algorithm 3: 候选采集与角色分配

```text
Input:
  candidate pool C_t, labeled history D_t, selector strategy, top_k,
  method configuration.

Output:
  selected candidates, all scored candidates, explanation report.

1. If strategy is random, sample candidates with a fixed seed.
2. If strategy is ca_llso_raw_distance, rank candidates by raw
   parameter distance to L1 samples and attach generic acquisition
   fields.
3. If strategy is pia_physics_distance, rank by weighted physics
   distance to L1 and diversity.
4. If strategy is pia_capm_distance, compute A_capm(x) and sort by
   hard-risk gate, normalized CAPM distance, diversity, and candidate id.
5. If strategy is adaptive_pia_capm, learn feature/acquisition weights
   from history and then compute A_capm(x).
6. If strategy is classifier_level_hybrid, ensure p_l1, p_hard_pass,
   predicted_score, uncertainty, and model_status exist; then compute
   A_hybrid(x).
7. If strategy is literature_ensemble_hybrid, compute the DEAOE,
   HRCEA, AIEA, CESAEA, and ECCoEA-ASAA inspired sub-scores and combine
   them as A_lit(x).
8. Select the top_k candidates and assign roles in rank order:
   exploitation_best, l1_center, boundary_learning,
   diversity_exploration, additional_candidate.
9. Generate selection_reason text and explanation_report with
   claim_boundary = next-run simulation suggestions.
```

## 9. Algorithm 4: 验证协议

```text
Input:
  validation protocol with methods, ablations, seeds, budgets,
  scenarios, target_score, and boundary fields.

Output:
  validation_runs.csv, validation_summary.csv,
  pairwise_win_rates.csv, validation_summary.json,
  experimental_validation_report.md.

1. Validate that primary_outcome is simulations_to_target.
2. Validate that the protocol contains required methods, ablations,
   seeds, budgets, scenarios, and the fixed boundary fields.
3. Expand the Cartesian product of scenarios, methods, ablations,
   seeds, and budgets into run specifications.
4. For each run specification, execute the configured PIA workflow,
   import simulation evidence, and collect run_manifest, run_summary,
   and boundary_audit.
5. Compute simulations_to_target as the first imported result position
   where S(x) >= target_score. Report missing target time as not reached.
6. Compute target_hit_rate, best_score, hard_pass_rate,
   convergence_auc, and auxiliary acquisition statistics.
7. Aggregate runs by scenario, method, ablation, budget, and seed.
8. Compute pairwise win rates using simulations_to_target first and
   feasible score metrics as secondary evidence.
9. Preserve data_source = real_simulation_csv,
   engineering_validity = simulation_only, and must_resimulate = true
   in aggregate outputs and reports.
```

## 10. 与代码字段的统一映射

| 论文符号 | 代码字段或模块 | 作用层级 |
|---|---|---|
| `x` | `parameter_columns` | 设计变量 |
| `D_t` | history CSV / imported results | 历史仿真集 |
| `C_t` | candidate CSV / offspring / repair candidates | 候选池 |
| `S(x)` | `overall_score` | 单次仿真评分 |
| `J_profile(x)` | `objective_score` | profile 加权目标 |
| `H(x)` | `hard_constraint_passed` | 硬约束门控 |
| `A(x)` | `acquisition_score` | 下一轮仿真采集优先级 |
| `tau_T` | `simulations_to_target` | 论文实验主结果 |
| `phi(x)` | `extract_physics_features` | 物理语义特征 |
| `D_geodesic(x,L1)` | `capm_geodesic_distance_to_l1` | 到 L1 basin 的 CAPM 图上距离 |
| `B(phi(x))` | `capm_barrier_score` | 仿真前约束风险 proxy |
| `M(x)` | `capm_missing_penalty` | 缺失物理特征惩罚 |

这一映射应作为后续论文写作和代码报告的唯一术语来源。若后续新增 selector 或验证指标，应优先判断它属于单次仿真评分层、profile 目标层、候选采集层还是实验主结果层，避免把多个目标函数混写为同一个概念。
