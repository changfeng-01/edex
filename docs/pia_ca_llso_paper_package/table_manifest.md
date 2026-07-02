# PIA-CA-LLSO 中文 IEEE 结构稿表格清单

| 表号 | 标题 | 数据来源 | 论文用途 | 边界说明 |
|---|---|---|---|---|
| Table I | 方法组件与创新角色 | `docs/pia_ca_llso_formal_method_zh.md`、`docs/pia_ca_llso_core_innovations_zh.md`、`docs/pia_capm_distance_research_zh.md` | 概括 CAPM-Distance、classifier_level_hybrid、active_uncertainty_diversity、active_influence_on_demand、`pia-evolve` 和 boundary audit 的角色 | 方法表，不是性能表 |
| Table II | 实验协议与证据边界 | `outputs/pia_phase3_smoke/experimental_validation_report.md`、`paper_reproduction_report.md` | 说明当前 smoke 和 paper-baseline reproduction 协议 | 仅代表当前已有证据，不代表 full validation |
| Table III | 当前 Phase 3 smoke 结果摘要 | `outputs/pia_phase3_smoke/validation_summary.csv`、`pairwise_win_rates.csv` | 如实报告 84 个 smoke run 的统一结果和无区分度 | 不能支持方法显著优于 random |
| Table IV | Paper-baseline reproduction 结果 | `outputs/pia_phase3_smoke/paper_baseline_summary.csv` | 展示 classifier_level_hybrid、paper_ca_llso 和两个 paper-inspired baseline 的侧面比较 | 明确不是原论文 benchmark 复现 |
| Table V | 局限性与投稿前补强实验 | 当前论文证据审计 | 约束结论强度并给出投稿前实验路线 | 防止越界声明 |

表格使用 Markdown 作为当前主稿载体。后续转换为 IEEE LaTeX/Word 时，应将表格标题改为 IEEE 样式的表题，并确保所有缩写在表注或正文首次出现处定义。
