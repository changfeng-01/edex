# PIA-CA-LLSO 中文 IEEE 结构论文包

本目录包含基于当前项目证据生成的中文 IEEE 结构科研论文稿。该稿按当前用户要求直接使用已有证据成稿，不先运行新的多场景验证。

## 文件

| 文件 | 作用 |
|---|---|
| `manuscript_ieee_zh.md` | 中文 IEEE 结构主稿 |
| `figure_manifest.md` | Fig. 1 至 Fig. 7 的来源、用途和证据边界 |
| `table_manifest.md` | Table I 至 Table V 的来源和用途 |
| `evidence_appendix.md` | 方法、结果、文献和不可支持结论的证据附录 |
| `claim_boundary_checklist.md` | 结论边界、禁止声明和投稿前补强检查 |
| `references_ieee.md` | IEEE 编号格式参考文献 |

## 主稿口径

主稿固定为 simulation-only 证据，不声称物理实测、硅验证、流片验证或无需重仿真的真实电路改进。必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

## 当前结果解释

Phase 3 smoke 结果可以证明验证链路、统计输出和 boundary audit 可运行，但由于所有方法在 sample_goa 上均达到 target_hit_rate=1.0、best_score_mean=92.0，且 win_rate_vs_random=0.0，不能用于强方法优越性结论。Paper-baseline reproduction 可作为统一协议侧面比较，但不是外部论文 benchmark 表格复现。

## 后续投稿转换

若要提交 IEEE 期刊，应将 `manuscript_ieee_zh.md` 转入目标 IEEE LaTeX 或 Word 模板，补充作者、单位、资助、数据可用性、利益冲突、正式 source lock 和多场景 full validation。图形优先使用 `docs/pia_ca_llso_paper_figures/figures/*.pdf`，并按 IEEE 图形指南检查字体、灰度可读性和单栏/双栏尺寸。
