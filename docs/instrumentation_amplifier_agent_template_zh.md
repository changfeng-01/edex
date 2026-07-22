# 三运放仪表放大器领域 Agent 首模板

## 定位

`InstrumentationAmplifierAgent` 是“一类电路一个领域 Agent”的首个完整模板。
领域 Agent 只负责本电路的参数语义、局部状态、解析模型、约束和灵敏度；候选
去重、信赖域、证据审计、PVT 聚合、迁移协调和报告由公共框架复用。

注册 profile 为 `instrumentation_amplifier_three_opamp_compensated_v1`，别名为
`three_opamp_7r`、`instrumentation_amplifier` 和 `three_opamp_lm324`。其中 LM324
只是外部模型或 CSV 的身份标签；缺少模型参数和观测时，结果只标记为解析代理。

## 参数和电路约束

设计变量为

\[
x=[R,R_G,R_D,K_{D+},K_{D-},C_F].
\]

派生关系为

\[
R_1=R_2=R,\quad R_3=R_4=R_D,
\]

\[
R_5=K_{D+}R_D,\quad R_6=K_{D-}R_D,
\]

\[
C_5=C_F/K_{D+},\quad C_6=C_F/K_{D-}.
\]

因此两个补偿支路始终满足

\[
R_5C_5=R_6C_6=R_DC_F.
\]

只有 `kind=design`、`optimizable=true` 且为正值的参数可进入对数灵敏度和动作
投影。environment、model、variation 和 derived 参数不会被优化器误当作设计动作。

## 解析电学模型

理想回归路径保持

\[
o_1=u_1+\frac{R_1}{R_G}(u_1-u_2),\qquad
o_2=u_2+\frac{R_2}{R_G}(u_2-u_1).
\]

实际路径把三级运放、负载、电阻和补偿电容放入同一复数 MNA 系统。提供
`A0` 与 `GBW` 时，三级统一采用

\[
A(s)=\frac{A_0}{1+s/\omega_p},\qquad
\omega_p=\frac{2\pi GBW}{A_0}.
\]

差模和共模采用正交激励分别求解。CMRR 的“无穷大”由矩阵条件数和浮点分辨率
判定，不使用任意上限。带宽通过确定性对数括区和二分法寻找 -3 dB 交点；未找到
交点、奇异矩阵、非法单位和参数越界均返回显式状态。

barrier 同时检查增益误差、CMRR、带宽、输入共模范围、输出裕量和压摆率利用度。
功耗只接受外部观测或明确供电电流模型，不以电阻成本代理功耗。

## PVT、观测和标定隔离

数据优先级为：场景外部 CSV、显式运放模型、解析代理、缺失。非标称 PVT 场景
如果既无观测又无显式系数，将标记为 `missing`，不会静默退化为标称场景。

外部 CSV 使用长表，以 `sample_id` 连接；场景由 `corner`、`temperature_c`、
`supply` 唯一确定。历史标定按 agent、profile、physics version、task-head version
和 corner set 隔离，三运放历史不会污染 GOA 标定。

## 跨电路迁移

领域 Agent 先将本地状态转换为 `circuitpilot.physical-effect.v1`。所有效应方向均为
正值代表改善，例如关键时间常数用 `-delta ln(tau)`，功耗用 `-delta ln(P)`。
目标领域只接收双方都支持的效应；GOA 的 bootstrap 和 TFT 工作区效应在三运放中
明确为 `not_applicable`。

目标雅可比采用中心对数差分。匹配 baseline、场景和正负扰动对的外部 CSV 可以
逐项覆盖解析灵敏度。协调器执行带正则的加权最小二乘，并检查秩、条件数、不确定度、
对齐度和相对残差；通过后输出 0.25、0.5、1.0 三个信赖域步长，再交给唯一的
`OptimizationAgent` 做边界、耦合、barrier 和去重。

## 证据边界

外部仿真支持的候选必须保留：

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

没有外部 CSV 时只输出 `analytic_model_proxy` 诊断，不伪装成真实仿真证据。

## 运行示例

```bash
python -m goa_eval.cli multi-agent-run \
  --task examples/tasks/instrumentation_amplifier_agent_task.yaml \
  --output-dir outputs/instrumentation_amplifier_agent
```

主要新增产物为：

- `instrumentation_agent_diagnosis.json`
- `physical_effect_packet.json`
- `target_sensitivity.json`
- `transfer_projection.json`（仅接受迁移投影时生成）
