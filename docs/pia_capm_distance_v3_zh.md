# CAPM 物理感知距离 V3

## 定位与兼容性

V3 是仿真前候选排序模型，不替代 SPICE、版图寄生提取或硅后验证。原有策略名保持不变，`legacy` 和 `v2` 继续保留用于历史复现；晶体管级配置默认使用 `capm_distance.metric_version: v3`。

所有输出保持以下边界：

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

## 统一电学特征

V3 的基础距离、耦合项和 barrier 只读取同一组 SI 特征：器件过驱动、等效电阻、有效负载、上拉/下拉/临界 RC、bootstrap 耦合与余量、驱动平衡和 clock-slew/RC 比。

器件配置显式声明角色、极性、W/L、迁移率、Cox、阈值、VGS/VDS 和可选观测电阻。对极性归一化后的电压：

```text
VOV = VGS* - |VTH|
VOV <= 0              -> off
0 < VDS* < VOV        -> linear
VDS* >= VOV           -> saturation
```

`tft_square_law_v1` 仅是可配置的预仿真代理。缺少偏置时回退到 V2 风格导通代理，并把工作区记为 `unknown`；不能将该状态描述为完整器件模型。

```text
Rpath = Rdevice + Rparasitic
tau = Rpath * Ceff
kboot = Cboot / (Cboot + Ceff + Cbootstrap_loss)
```

寄生数据优先级是：PVT 观测值、行内角色级 R/C、经 `net_role_map` 映射的 Empyrean `ParasiticSummary`、旧 `C_parasitic`、显式零值回退。内部统一换算为 F、ohm 和 s；未知单位会产生 `missing` 诊断，不会静默套用。

## 多 corner/PVT

PVT 场景键固定为 `corner|temperature_c|supply_v`。侧车 CSV 以 `sample_id` 和场景键连接；匹配的观测字段优先于代理值。缺少观测时，只有在配置提供 corner 系数、迁移率温度指数、阈值温漂和供电缩放所需参数后才投影该场景；缺少 corner 模型时场景记为 `missing`，不会当作 TT。

每个场景独立计算统一电学向量。默认距离聚合为场景等权的 `0.5 * mean + 0.5 * worst`，barrier 取最大值。代理和缺失场景覆盖率进入 `capm_proxy_fallback_penalty` 与 `capm_missing_penalty`。

## 历史输出尺度

V3 不再对当前候选池执行 min-max。系统对历史记录计算 leave-one-out 的到 L1 距离，排除 L1 样本自身：

```text
S = P90(positive finite history-to-L1 distances)  # 至少 5 个参考值
S = max(history-to-L1 distances)                  # 1 到 4 个参考值
Dcal = clip(Draw / S, 0, 1)
```

没有正参考距离时输出 `degenerate_history`，并使用确定性的零/一映射。`capm_distance_calibration_json.candidate_pool_fitted` 固定为 `false`，用于审计候选池没有参与标定。

## 关键诊断字段

- `physics_feature_status_json`：逐特征的 `physical`、`observed`、`proxy_fallback` 或 `missing`。
- `capm_electrical_status_json`：器件区域、极性、寄生来源和统一特征状态。
- `capm_pvt_status`、`capm_pvt_diagnostics_json`：场景覆盖与观测/代理来源。
- `capm_distance_calibration_json`、`capm_calibration_status`：历史距离尺度及退化状态。

任何 V3 候选仍必须重新仿真；代理改善不构成工程验证通过。
