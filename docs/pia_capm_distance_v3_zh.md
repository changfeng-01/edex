# CAPM 物理感知距离 V3

## 定位与边界

V3 是仿真前候选排序模型，不替代 SPICE、版图寄生提取或硅后验证。原有策略名保持不变，`legacy` 和 `v2` 继续用于历史复现；晶体管级配置默认使用 `capm_distance.metric_version: v3`。

所有输出保持以下边界：

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

## 数学结构：距离与风险分离

V3 的默认几何状态只含无量纲且尽量不冗余的量：上下拉过驱动/供电、上下拉 RC/时钟 slew、bootstrap 耦合、bootstrap 余量/供电以及上下拉驱动对数比。原始 SI 特征仍是 barrier 和诊断的唯一数据源，但不再同时把 `R`、`C`、`R*C` 和 `max(R*C)` 重复塞入默认距离向量。

历史向量先做稳健中心化和 `asinh` 变换，再用带 ridge 的收缩协方差构造 Mahalanobis 度量。收缩系数、精度矩阵和所用基底记录在 `capm_normalization_json` 中。V3 不再叠加依赖坐标基底的特征乘积耦合项。

几何距离与风险严格分开：

```text
Dgeo(x, x) = 0
Rpoint = lambda_barrier * barrier
       + lambda_missing * missing_coverage
       + lambda_fallback * proxy_coverage
Ddecision = Dgeo + Rpoint
```

`distance`/`geometric_distance` 只表示几何差异；`point_risk_cost` 和 `decision_cost` 单独报告。候选选择仍用 barrier 硬门控及覆盖率置信度，风险不会再污染历史距离标定。

## 连续 TFT 与 Bootstrap 自洽计算

器件配置显式声明角色、极性、W/L、迁移率、Cox、阈值、VGS/VDS、沟道调制、串联电阻以及可选观测电阻。极性归一化后的工作区判定为：

```text
VOV = VGS* - |VTH|
VOV <= 0       -> off
0 < VDS* < VOV -> linear
VDS* >= VOV    -> saturation
```

`tft_square_law_v1` 保留用于复现。晶体管级默认改为 `tft_charge_sheet_v2`：通过平滑有效漏压统一线性区与饱和区的沟道电荷电流，并在整个导通区一致地施加沟道长度调制，因此工作区边界处电流连续。可配置截止电流下限和串联电阻；观测电阻仍具有最高优先级。

```text
VDS,eff = smooth_min(VDS*, VOV)
Id = beta * (VOV*VDS,eff - 0.5*VDS,eff^2) * (1 + lambda*VDS*)
Rdevice = VDS*/Id + Rseries
Rpath = Rdevice + Rparasitic
tau = Rpath * Ceff
```

Bootstrap 不再只计算一次静态电容分压。固定点求解器把有效栅电容加入电荷分配，得到提升后的目标器件栅压，再将该偏置送回同一 TFT 模型。诊断输出迭代次数、耦合系数、提升后过驱动和 `charge_residual_v`；未收敛会显式标为 `not_converged`。

## 多 corner/PVT 与不确定性

PVT 场景键固定为 `corner|temperature_c|supply_v`。重复场景键在投影前去重；每个唯一场景可配置 `weight` 和 `distance_uncertainty`。侧车观测仍逐字段优先于代理。

非参考温度必须显式给出迁移率温度指数和阈值温漂；非参考供电必须给出供电偏置指数；代理 corner 必须完整给出 μ、Vth、R、C 四类系数。缺项时场景记为 `missing` 并列出 `missing_coefficients`，不再使用 0 或 1 静默退化为 TT。

场景距离采用加权均值与上置信 CVaR 的混合：

```text
Dup = Dgeo + z * sigma_distance
Dpvt = (1 - alpha) * weighted_mean(Dgeo) + alpha * CVaR_q(Dup)
Pviolation = sum(weight of scenarios with barrier > 0)
```

`pvt_cvar_quantile`、`pvt_cvar_weight`、`pvt_uncertainty_z` 和允许违约概率均可配置。barrier 仍取场景最大值；`pvt_violation_probability` 与 `chance_constraint_excess` 单独进入风险诊断。这样，复制某个场景不会改变统计权重，低概率坏 corner 也不会被简单平均掩盖。

## 历史输出尺度

V3 只用历史数据做 leave-one-out 到 L1 的标定，候选池不参与拟合：

```text
S = P90(positive finite history-to-L1 distances)  # 至少 5 个参考值
S = max(history-to-L1 distances)                  # 1 至 4 个参考值
Dcal = clip(Dgeo / S, 0, 1)
```

没有正参考距离时输出 `degenerate_history`，并采用确定性的零/一映射。由于标定只读取几何距离，barrier、代理状态或候选池增删不会改变同一历史几何尺度。

## 关键诊断

- `physics_feature_status_json`：逐特征的 `physical`、`observed`、`proxy_fallback` 或 `missing`。
- `capm_electrical_status_json`：器件工作区、电流模型、Bootstrap 收敛残差和寄生来源。
- `capm_pvt_status`、`capm_pvt_diagnostics_json`：唯一场景、权重、不确定性、系数缺项和观测/代理来源。
- `capm_distance_calibration_json`、`capm_calibration_status`：历史距离尺度和退化状态。

任何 V3 候选仍必须重新仿真；代理模型改进不构成工程验证通过。
