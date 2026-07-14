# PIA-CA-LLSO 中文 IEEE 结构稿图表清单

证据边界固定为：

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

| 图号 | 文件 | 论文用途 | 支持的结论 | 不支持的结论 |
|---|---|---|---|---|
| Fig. 1 | `../pia_ca_llso_paper_figures/figures/fig01_graphical_abstract.png` / `.pdf` | 图形摘要 | 展示 history CSV、candidate pool、CAPM-Distance、PIA acquisition、simulation batch、result import 的闭环关系 | 不支持物理实测、硅验证或真实芯片优化完成 |
| Fig. 2 | `../pia_ca_llso_paper_figures/figures/fig02_closed_loop_architecture.png` / `.pdf` | 方法架构 | 展示标签、LLSO offspring、selector、result import、resume state、boundary audit 的模块关系 | 不支持所有 simulator backend 已被完整实验验证 |
| Fig. 3 | `../pia_ca_llso_paper_figures/figures/fig03_capm_physics_manifold.png` / `.pdf` | CAPM 概念图 | 解释物理语义特征、L1 basin、barrier proxy、geodesic path、missingness | 不支持 barrier proxy 等同真实 hard-constraint failure |
| Fig. 4 | `../pia_ca_llso_paper_figures/figures/fig04_acquisition_ensemble.png` / `.pdf` | acquisition 组成 | 展示 CAPM、自适应权重、分类器、多样性、不确定性和 paper-inspired 分量 | 不支持完整复现外部 paper 算法 |
| Fig. 5 | `../pia_ca_llso_paper_figures/figures/fig05_strategy_benchmark.png` / `.pdf` | 策略证据视图 | 展示当前 benchmark artifact 与边界字段 | 不支持最终方法优越性，因为 Phase 3 smoke 区分度不足 |
| Fig. 6 | `../pia_ca_llso_paper_figures/figures/fig06_ablation_and_boundary.png` / `.pdf` | 消融与边界审计 | 展示当前可用消融槽位和 boundary audit 语义 | 不支持正式数值消融结论 |
| Fig. 7 | `../pia_ca_llso_paper_figures/figures/fig07_candidate_acquisition_diagnostics.png` / `.pdf` | 候选诊断 | 解释 acquisition_score、CAPM 距离、barrier 和候选角色 | 不支持候选已经物理验证 |

所有图均已存在于 `docs/pia_ca_llso_paper_figures/figures/`。IEEE 后续排版时优先使用 PDF 或 PNG；根据 IEEE 图形指南，正式提交前应确认字体可嵌入、灰度可读、尺寸适配单栏或双栏。
