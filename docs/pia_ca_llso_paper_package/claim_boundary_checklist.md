# Claim Boundary Checklist

## 必须保留的原文标签

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

## 已在主稿中保守处理的声明

| 声明类型 | 主稿处理 |
|---|---|
| 候选输出 | 写为 next-run simulation suggestions |
| CAPM barrier | 写为 pre-simulation risk proxy |
| Phase 3 smoke | 写为流程和审计链路验证，不写为 superiority evidence |
| Paper-baseline reproduction | 写为统一协议侧面实验，不写为原论文表格复现 |
| 结论 | 写为 simulation-only 研究原型，不写为物理优化完成 |

## 禁止写入正式投稿稿的声明

- 已完成真实物理优化。
- 已完成硅验证、实测验证、样品验证或 tapeout 验证。
- CAPM-Distance 可替代 SPICE 仿真。
- `capm_barrier_score` 可证明候选真实硬约束失败。
- 当前 Phase 3 smoke 已证明 PIA-CA-LLSO 显著优于所有 baseline。
- 当前候选无需重新仿真即可作为最终优化结果。

## 投稿前必须补强的检查

| 检查项 | 当前状态 | 投稿前动作 |
|---|---|---|
| 多场景验证 | 未完成，当前仅 sample_goa smoke | 运行至少 3 个 scenario |
| 多预算验证 | 当前 smoke 仅 budget=8 | 增加 20、50、100 |
| 多 seed 统计 | 当前每组合 2 个 seed | 增加到至少 5 个 seed |
| CAPM 内部消融 | 当前主稿仅说明建议 | 补 no barrier、no geodesic、no coupling、no missing penalty |
| 图 5/图 6 | 当前为 sample/smoke 可视化 | 用正式 validation CSV 更新 |
| source lock | 当前主稿引用已有路径 | 生成正式 source_lock.json 并记录 hash、命令、commit |
