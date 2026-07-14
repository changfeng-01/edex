# CAPM 物理感知距离 V2

## 定位

CAPM V2 是仿真前候选排序代价，不替代 SPICE，也不把风险代理解释为真实失效证据。默认策略名保持 `pia_capm_distance`、`adaptive_pia_capm` 和 `classifier_level_hybrid`；历史复现可配置 `capm_distance.metric_version: legacy`。

证据边界保持：

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

## 电学特征

在原有驱动比、bootstrap/load 比、时钟边沿和阈值裕量基础上，V2 增加：

```text
C_eff = C_load + C_parasitic
G_pu = mu_pu * C_ox * (W/L)_pu * max(VGH - Vth_shift, epsilon)
G_pd = mu_pd * C_ox * (W/L)_pd * max(|VGL| - |Vth_shift|, epsilon)
tau_pu = C_eff / max(G_pu, epsilon)
tau_pd = C_eff / max(G_pd, epsilon)
Q_boot = C_boot * CLK_amp
k_boot = C_boot / (C_boot + C_eff)
V_boot = CLK_amp * k_boot
```

可选输入为 `mu_pullup_cm2_v_s`、`mu_pulldown_cm2_v_s`、`cox_f_per_cm2` 和 `C_parasitic`。缺少工艺参数时使用单位驱动因子，缺少寄生时使用零寄生，并通过 `physics_feature_status_json` 标记 `proxy_fallback`，不得描述为完整器件模型。

## 数学定义

归一化只使用历史记录拟合：

```text
scale_k = max(1.4826 * MAD_k, 0.05 * |median_k|, epsilon)
z_k(x) = clip(asinh((phi_k(x) - median_k) / scale_k), -8, 8)
```

严格相似性部分满足同一点距离为零：

```text
D_sim(x,y)^2 = sum_k w_k * (z_k(x)-z_k(y))^2
             + coupling_budget * sum_(a,b) rho_ab
               * (z_a(x)z_b(x)-z_a(y)z_b(y))^2
```

风险和数据可信度作为独立通行代价：

```text
R_path(x,y) = [B(phi(x)) + 4B((phi(x)+phi(y))/2) + B(phi(y))] / 6
C(x,y) = D_sim(x,y)
       + lambda_barrier * R_path(x,y)
       + lambda_missing * M(x,y)
       + lambda_fallback * F(x,y)
```

`M` 是按物理特征权重计算的缺失比例，`F` 是代理回退比例。完整 `C` 应称为风险感知通行代价，而不是严格数学度量。

## L1 流形

历史样本单独构建对称 kNN 图，候选只连接历史节点，避免候选池组成改变既有候选的距离。到 L1 的距离对最近三个可达 L1 使用质量加权 soft-min；无可达路径时回退直接距离。

## 消融和复现

- `no_capm_barrier`
- `no_capm_geodesic`
- `no_capm_coupling`
- `no_missing_penalty`
- `no_capm_normalization`
- `no_capm_softmin`
- `no_capm_electrical_features`

V2 与 legacy 的排序结果不能直接混写为同一方法结果。所有性能结论仍需在相同预算、seed、scenario 和真实仿真结果下比较。
