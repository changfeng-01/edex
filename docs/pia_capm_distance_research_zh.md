# PIA-CA-LLSO 约束感知物理流形距离研究说明

## 1. 研究定位

本文件说明 PIA-CA-LLSO 中新增的 **CAPM-Distance**：

**Constraint-Aware Physics-Manifold Distance，约束感知物理流形距离**。

PIA-CA-LLSO 的统一问题定义、目标层区分、完整公式和闭环伪代码见 `docs/pia_ca_llso_formal_method_zh.md`。本文档只保留 CAPM-Distance 的研究解释和消融建议；若二者表述有差异，以正式方法定义文档为准。

它面向“无训练数据或极少训练数据”的 GOA 显示驱动电路候选筛选场景。它不是一个训练模型，也不是 SPICE 替代品，而是一个仿真前候选排序 proxy，用来把下一轮仿真预算优先分配给物理上更合理、约束风险更低、离已知 L1 区域更近的候选。

证据边界必须保持：

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- must_resimulate = true
- claim_boundary = next-run simulation suggestions

## 2. 原始物理距离的局限

PIA-CA-LLSO 原有物理距离是加权欧氏距离：

```text
D_physics(x, y) = sqrt(sum_k w_k * (phi_k(x) - phi_k(y))^2)
```

其中 `phi(x)` 是由参数推导出的 GOA 物理特征，例如：

- `cboot_cload_ratio`
- `pullup_pulldown_ratio`
- `ron_pullup_cload_proxy`
- `ron_pulldown_cload_proxy`
- `vgh_vth_margin`
- `vgl_off_margin`
- `clk_slew_proxy`

这个方法简单、稳定、可解释，但有三个不足：

1. 没有显式处理约束边界。两个点欧氏距离很近，但其中一个可能已经靠近低电压裕量或过高 RC proxy 的风险区。
2. 没有表达物理耦合。GOA 电路中 `Ron*Cload`、clock slew、bootstrap/load ratio 等不是完全独立的维度。
3. 只看候选点到 L1 点的直线距离，没有考虑从候选区域到 L1 basin 的路径是否穿过高风险区域。

## 3. CAPM-Distance 公式

CAPM-Distance 将距离拆成四项：

```text
D_capm(x, y) =
  D_tensor(x, y)
+ lambda_barrier * D_barrier(x, y)
+ lambda_graph * D_geodesic(x, y)
+ lambda_missing * D_missing(x, y)
```

### 3.1 D_tensor：各向异性物理距离

`D_tensor` 仍然比较 GOA 物理特征，但不再把所有维度当作普通坐标。

默认权重来自 GOA 物理语义：

- `cboot_cload_ratio`: bootstrap 电容与负载电容的相对裕量。
- `pullup_pulldown_ratio`: 上拉/下拉驱动平衡。
- `ron_pullup_cload_proxy`: 上拉路径对负载的等效驱动压力。
- `ron_pulldown_cload_proxy`: 下拉路径对负载的等效驱动压力。
- `vgh_vth_margin`: 高电平门压相对阈值漂移的裕量。
- `vgl_off_margin`: 低电平关断裕量。
- `clk_slew_proxy`: 时钟边沿速度 proxy。

同时加入少量耦合项，例如：

```text
(ron_pullup_cload_proxy * clk_slew_proxy)
(ron_pulldown_cload_proxy * clk_slew_proxy)
(cboot_cload_ratio * vgh_vth_margin)
```

这些耦合项用于表达“单个特征正常，但组合后可能风险变大”的情况。

### 3.2 D_barrier：软约束屏障

`D_barrier` 是仿真前风险屏障，不是失败判定。

候选如果出现以下风险，CAPM 距离会变大：

- `vgh_vth_margin` 低于最小裕量。
- `vgl_off_margin` 低于最小裕量。
- `cboot_cload_ratio` 过低。
- `ron_pullup_cload_proxy` 或 `ron_pulldown_cload_proxy` 过高。
- `pullup_pulldown_ratio` 过低或过高。
- `clk_slew_proxy` 过高。

这些风险只影响下一轮候选排序，不升级为物理验证结论。

### 3.3 D_geodesic：到 L1 basin 的图上测地距离

CAPM 不只看候选到某个 L1 样本的直线距离。

实现上会把 candidate 和 history 合成一个小型 kNN 图：

1. 节点：候选样本、历史样本。
2. 边权：CAPM pairwise distance。
3. 目标：从候选节点到任意 L1 节点的最短路径。

这样可以表达一个研究假设：

> 一个候选如果必须穿过高约束风险区域才能接近 L1 basin，那么它不应该被视为“真正接近 L1”。

### 3.4 D_missing：缺失特征惩罚

缺失物理特征不能被简单填 0 后参与距离计算。

CAPM 会记录：

- `capm_missing_penalty`
- `capm_status`

当关键物理输入缺失时，候选会被降低可信度，而不是被误判为与 L1 样本接近。

## 4. 新策略 pia_capm_distance

新增 selector 策略：

```bash
python -m goa_eval.cli pia-suggest \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --output-dir outputs/pia_capm_suggest \
  --strategy pia_capm_distance \
  --top-k 3
```

`pia_capm_distance` 不依赖：

- `p_l1`
- `predicted_score`
- `p_hard_pass`
- torch
- 大规模训练集

排序依据是：

1. `capm_hard_risk_passed`
2. `capm_distance_to_l1_normalized`
3. `diversity_score`
4. `candidate_id`

输出新增诊断字段：

- `capm_distance_to_l1`
- `capm_geodesic_distance_to_l1`
- `capm_barrier_score`
- `capm_missing_penalty`
- `capm_hard_risk_passed`
- `acquisition_components_json`
- `diagnostic_status = capm_physics_manifold_no_training`

## 5. 配置入口

GOA profile 中新增：

```yaml
capm_distance:
  lambda_barrier: 1.0
  lambda_graph: 1.0
  lambda_missing: 1.0
  k_neighbors: 4
  min_vgh_vth_margin: 0.2
  min_vgl_off_margin: 0.2
  min_cboot_cload_ratio: 0.35
  max_ron_pullup_cload_proxy: 2.0
  max_ron_pulldown_cload_proxy: 2.0
  min_pullup_pulldown_ratio: 0.5
  max_pullup_pulldown_ratio: 2.0
  max_clk_slew_proxy: 2.0
  coupling_weight: 0.25
```

这些参数用于研究消融和导师汇报，不应被描述为真实电路硬阈值。它们是仿真前筛选 proxy 的可调配置。

## 6. 消融实验设计

推荐比较四个策略：

```text
random
ca_llso_raw_distance
pia_physics_distance
pia_capm_distance
```

运行示例：

```bash
python -m goa_eval.cli pia-benchmark \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --output-dir outputs/pia_capm_benchmark \
  --strategies random,ca_llso_raw_distance,pia_physics_distance,pia_capm_distance \
  --target-score 80
```

核心指标：

- `best_feasible_score_under_budget`
- `first_feasible_eval`
- `hard_constraint_pass_rate`
- `not_evaluable_rate`
- `candidate_hit_rate`
- `l1_discovery_count`

建议的 CAPM 内部消融：

- 去掉 barrier：验证约束屏障是否有价值。
- 去掉 geodesic：验证图上路径是否优于直线距离。
- 去掉 coupling：验证物理耦合项是否提升排序。
- 只保留 static physics distance：回到原始加权欧氏基线。

## 7. 论文贡献表述

可以在论文或答辩中表述为：

1. 提出一种面向 GOA 显示驱动电路的无训练物理距离 CAPM-Distance。
2. 将 CA-LLSO 的 L1 邻域思想从 raw parameter space 扩展到 constraint-aware physics manifold。
3. 在 simulation-only 离线 replay 中验证其对小样本昂贵仿真候选筛选的改进潜力。

严禁表述为：

- 已完成真实物理优化。
- 已替代 SPICE 仿真。
- 已获得硅验证或实测验证。
- `capm_barrier_score` 证明候选真实失败。

## 8. 代码位置

主要实现位置：

- `src/goa_eval/pia_ca_llso/physics_distance.py`
- `src/goa_eval/pia_ca_llso/selector.py`
- `src/goa_eval/pia_ca_llso/acquisition.py`
- `src/goa_eval/pia_ca_llso/benchmark.py`
- `config/pia_ca_llso_goa_profile.yaml`

主要测试：

- `tests/test_pia_physics_distance.py`
- `tests/test_pia_selector.py`
- `tests/test_pia_benchmark.py`
- `tests/test_pia_report.py`

## 9. 当前验证结果

本功能的验证命令包括：

```bash
python -m pytest tests/test_cli_command_registration.py tests -k pia -q
python -m ruff check src/goa_eval/pia_ca_llso src/goa_eval/cli_commands/pia_ca_llso.py tests/test_pia_physics_distance.py tests/test_pia_selector.py tests/test_pia_benchmark.py tests/test_pia_report.py
```

示例命令已能生成：

- `outputs/pia_capm_suggest/pia_selected_candidates.csv`
- `outputs/pia_capm_suggest/pia_candidate_report.md`
- `outputs/pia_capm_benchmark/pia_ablation_summary.json`
- `outputs/pia_capm_benchmark/pia_capm_distance_selected_candidates.csv`

所有生成报告仍需保留：

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- must_resimulate = true
