# PIA-CA-LLSO 论文证据附录

## 方法来源

| 路径 | 证据角色 | 在论文中的用途 |
|---|---|---|
| `docs/pia_ca_llso_formal_method_zh.md` | 术语、公式和伪代码的主来源 | 问题定义、CAPM-Distance、闭环流程和验证协议 |
| `docs/pia_ca_llso_core_innovations_zh.md` | 创新点整理 | 引言贡献、讨论和限制 |
| `docs/pia_capm_distance_research_zh.md` | CAPM-Distance 说明 | 方法章节和 CAPM 组件解释 |
| `docs/pia_ca_llso.md` | 模块概述 | 系统边界和实现入口 |

## 当前结果来源

| 路径 | 当前读数 | 支持的结论 |
|---|---|---|
| `outputs/pia_phase3_smoke/experimental_validation_report.md` | run_count=84，target_score=80，方法 6 类，消融 7 类，场景 sample_goa | Phase 3 smoke runner、报告和边界审计链路可运行 |
| `outputs/pia_phase3_smoke/validation_summary.csv` | 所有方法/消融在 sample_goa 下 target_hit_rate=1.0、best_score_mean=92.0、best_score_std=0.0 | 当前 smoke 数据无方法区分度 |
| `outputs/pia_phase3_smoke/pairwise_win_rates.csv` | 各方法相对 random 的 win_rate_vs_random=0.0，comparison_count=2 | 不能声称 PIA 系列在该 smoke 中优于 random |
| `outputs/pia_phase3_smoke/paper_reproduction_report.md` | classifier_level_hybrid 与 paper_ca_llso 均 simulations_to_target=1；两个 paper-inspired baseline 为 2 | 侧面支持 classifier_level_hybrid 在统一协议下表现不弱于 paper_ca_llso |
| `outputs/pia_phase3_smoke/paper_baseline_summary.csv` | classifier_level_hybrid: hit 1.0, AUC 282.0, best 94.0；paper_ca_llso: hit 1.0, AUC 280.5, best 94.0；另两个 baseline: hit 0.75, best 91.0 | 可写入 Table IV，但必须标注非原论文 benchmark 复现 |
| `config/pia_ca_llso_validation_protocol.yaml` | 当前协议新增 `active_uncertainty_diversity` 方法 | 说明主动采样策略已接入下一轮验证，但旧 smoke 数值不能回填为该策略结果 |

## 文献来源

| 路径 | 论文 | DOI | 用途 |
|---|---|---|---|
| `papers/you2024_10t2c_scan_driver/paper_metadata.yaml` | Y. You et al., 2024, *Electronics* | `10.3390/electronics13122254` | GOA/scan-driver 主参考 |
| `papers/song2022_dual_gated_sr/paper_metadata.yaml` | R. Song et al., 2022, *Micromachines* | `10.3390/mi13101696` | dual-gated shift-register 辅助参考 |
| `papers/zhou2025_31inch_goa/paper_metadata.yaml` | X. Zhou et al., 2025, *Micromachines* | `10.3390/mi16121325` | 大尺寸 AMOLED GOA 参考 |

## 不能支持的结论

当前证据不能支持以下说法：

- PIA-CA-LLSO 已完成真实物理优化。
- CAPM-Distance 替代 SPICE 或其他电路仿真器。
- 当前候选已经过硅验证、实验台验证、样品验证或 tapeout 验证。
- Phase 3 smoke 已证明 PIA-CA-LLSO 显著优于 random。
- active_uncertainty_diversity 已经通过真实仿真证明优于 classifier_level_hybrid。
- paper-baseline reproduction 是外部论文 benchmark 表格的完整复现。

## 可支持的保守结论

当前证据支持以下说法：

- PIA-CA-LLSO 已形成方法定义、代码接口、图表包、smoke validation 和 paper-baseline reproduction 的一致证据链。
- CAPM-Distance 是 next-run simulation suggestions 的仿真前候选排序 proxy。
- active_uncertainty_diversity 是 low-data active acquisition 的候选采样扩展，会输出 next-run simulation suggestions，仍需要后续真实仿真确认。
- Phase 3 smoke 证明验证链路和 boundary audit 可以运行，但不能给出强优越性结论。
- Paper-baseline reproduction 在统一 GOA/PIA simulation-only 协议下显示 classifier_level_hybrid 与 paper_ca_llso 均能以 1 次仿真达到目标，两个 paper-inspired baseline 为 0.75 hit rate 和 2 次到目标。
