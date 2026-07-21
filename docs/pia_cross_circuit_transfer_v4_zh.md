# CAPM V4 跨电路迁移工程说明

## 1. 目标与证据边界

V4 的目标不是让不同电路共享原始列名，而是让它们共享“物理状态、局部响应和语义动作”。原有
`pia_capm_distance`、`adaptive_pia_capm`、`classifier_level_hybrid` 等入口保持不变，通过
`capm_distance.metric_version: v4` 启用新内核。`legacy`、`v2`、`v3` 仍可复现。

任何迁移推荐仍严格标记：

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

迁移模型只分配仿真预算，不把源电路结果当作目标电路的已验证结果。

## 2. 分层工程结构

```text
原始电路/侧车数据
  -> physics: 有符号器件、bootstrap 电荷、G/C 相位网络、寄生/PVT
  -> domain: 电路域描述、域距离、源域权重、语义动作解码
  -> transfer: 层次物理残差、OOD/不确定性门控、选择偏差、LOCO
  -> pia_ca_llso: CAPM V4 距离、历史标定、策略排序
  -> product/API/UI: selection_scores 与迁移审计展示
  -> 目标电路重新仿真
```

代码边界如下：

- `goa_eval.physics`：不依赖具体策略，输出带 fidelity 的物理量。
- `goa_eval.domain`：定义 `CircuitDomain`、`CanonicalAction` 和拓扑/工艺/尺度距离。
- `goa_eval.transfer`：拟合跨域残差、计算源域支持度、信任门控和 LOCO 报告。
- `goa_eval.pia_ca_llso`：只负责用上述输出形成距离、风险和 acquisition。

## 3. 底层数学与电学

### 3.1 有符号 TFT 与工作区

令极性符号 (s=+1)（N 型）或 (s=-1)（P 型），采用

\[
V_{GS}^{*}=sV_{GS},\quad V_{th}^{*}=sV_{th},\quad
V_{OV}=V_{GS}^{*}-V_{th}^{*}.
\]

阈值保持有符号，因而耗尽型器件的 (V_{th}^{*}<0) 不会被错误地绝对值化。模型区分 cutoff、
subthreshold、linear 和 saturation；负的归一化 (V_{DS}) 触发源漏交换并保留电流方向。输出同时包含
大信号电阻 (V/I)、小信号电阻 (1/g_{ds}) 和轨迹电阻，RC 延迟使用轨迹电阻，避免把静态工作点电阻
错误当成完整瞬态路径。

### 3.2 Bootstrap 电荷守恒

V4 以电荷而不是经验电压惩罚计算提升量：

\[
\Delta V_G=\frac{C_{boot}\Delta V_{clk}-Q_{leak}}
{C_{boot}+C_g+C_L+C_{loss}}.
\]

提升后的栅压重新送入目标器件模型，`bootstrap_headroom_v` 是目标器件余量，不再引用 bootstrap 开关
自身的过驱动。诊断同时给出耦合系数、charge residual 和 fidelity。

### 3.3 相位 G/C 网络

`solve_phase_network` 对每个时钟相位建立节点电导矩阵 (G) 和电容矩阵 (C)，用后向欧拉积分：

\[
(C/\Delta t+G)v_{k+1}=C v_k/\Delta t+b.
\]

这为多节点、共享寄生和非单一 `R×C` 路径提供稳定基线；完整晶体管仿真仍属于更高 fidelity。

### 3.4 V4 距离

各特征先按物理支持域变换：正值 R/C/RC 使用 log，耦合系数使用 logit，有符号余量和失衡使用
asinh。历史中位数/MAD、收缩协方差只由历史行拟合。协方差在未加权坐标上估计，最终距离再施加
特征权重，从而避免“先加权协方差、再加权距离”造成权重抵消。

历史尺度采用逐行 cross-fit：每个历史样本作为 held-out 行时，中心、尺度和精度矩阵均只由其余历史
拟合。正参考距离不少于 5 个取 P90，否则取最大值。输出映射为

\[
d_{out}=\frac{d}{d+s_{history}},
\]

因此没有候选池 min-max 漂移，也没有大距离硬截断造成的排序并列。

### 3.5 PVT 与风险语义

- `deterministic_corner` 用等权均值与最坏角混合，不解释成概率。
- `statistical_sample` 必须显式给出 probability，才计算 violation probability。
- 场景集合取历史上下文与比较双方的固定并集；缺失场景进入覆盖惩罚，不能因交集缩小而消失。
- hard constraint、validated risk、heuristic warning 分开输出。启发式 warning 可以影响预算优先级，但不能
  自动宣告物理失败。

## 4. 跨域表示和迁移模型

`CircuitDomain` 至少描述拓扑族、器件/工艺族、供电、时钟周期、负载和角色签名。连续尺度使用 log-ratio，
类别使用显式不匹配，角色使用 Jaccard 差异。多个源电路按 softmax 域距离生成权重。

学习目标采用

\[
y=f_{physics}(x)+r_{shared}(z)+b_{domain}+b_{fidelity}+\epsilon,
\]

其中 `HierarchicalPhysicsResidual` 只拟合物理基线的结构化残差。历史若来自主动选择，使用
inverse-propensity weighting；未知 propensity 必须报告 `not_fitted`，不能假定随机采样。

搜索动作使用 `(role, parameter, operation, magnitude)`，例如
`(pullup, width, log_scale, 0.2)`。每个目标电路通过 `role_parameter_map` 解码为实际参数列并执行边界裁剪，
避免把某个拓扑的 `M1_W` 直接迁移到另一个拓扑。

## 5. 信任门控

迁移同时检查五个维度：域距离、特征 OOD、预测标准差、有效源样本数和物理特征覆盖率。任一维度越界，
状态变为 `target_only_exploration`；系统仍可推荐目标域探索点，但不使用跨域残差提升其可信度。
候选 CSV、产品 `selection_scores` 和前端表格均保留 `capm_transfer_trust_score`、
`capm_transfer_status` 与 `capm_transfer_diagnostics`。

## 6. 数据契约

训练表新增以下可选列：

- `circuit_domain_id`、`topology_family`、`technology_family`、`process_family`；
- `fidelity_level`（F0–F4；真实电路仿真默认为 F3）；
- `selection_propensity`（用于逆倾向加权）。

PVT 侧车仍为长表，以 `sample_id + corner + temperature_c + supply_v` 连接。浮点键按显式 tolerance 匹配；
部分观测只覆盖对应字段，共享 mobility/threshold/bias 列在一个场景内只缩放一次。寄生状态按每个 R/C
分量记录，不能因某一列已观测就把整张寄生网络标为 physical。

## 7. 验证与验收

核心协议是 leave-one-circuit-out（LOCO）：完整目标电路不得进入拟合、标准化、源权重校准或早停选择。
每个 held-out 电路至少报告 MAE/RMSE、校准、hard-pass、negative-transfer rate、仿真到目标次数，并与
target-only、V3、随机和原有策略比较。

必须执行的消融包括：无域距离、无局部灵敏度、无层次残差、无 propensity、无信任门控、无 PVT、
无寄生、无 bootstrap 守恒和仅 target-only。只有当多个 held-out 电路上相对 target-only 的收益稳定，且
negative-transfer rate 未恶化时，才可声称“具备经验证的跨电路迁移能力”；当前代码落地的是可审计的
能力框架，任何具体电路族仍需真实仿真数据完成上述验收。

完整配置模板见 `config/pia_ca_llso_transfer_v4.yaml`。

## 8. 跨电路参数空间与任务头

跨电路迁移不要求 GOA、OTA、像素存储驱动等电路共享原始参数列。每个
`circuit_profile` 同时声明两类电路本地契约：

- `metrics + objective`：定义该电路真正关心的输出指标、方向、阈值和权重；
- `parameter_profile`：定义本地参数列到 `role.property` 的语义映射、单位、变量类型、可优化性、边界、量化和耦合组。

参数被明确分成 `design`、`environment`、`model`、`parasitic` 和 `derived`。
只有 `design && optimizable=true` 可以被搜索器修改；供电、温度、负载、工艺模型和提取寄生不得作为普通设计旋钮被误扰动。LLSO offspring 从同一 learner
继承这些条件列，并对设计变量执行 profile 边界和量化。`keep_ratio` 与
`must_change_together` 参数组使用同一乘性步长，量化或边界导致组约束无法满足时丢弃该 offspring。

同一个规范物理状态会分别送入目标电路任务头。例如 GOA 可提高
`voh_min_v`、bootstrap 余量和时序权重，OTA 可提高增益、相位裕度、带宽与功耗权重；任务分数不会被误当成通用物理距离，而是作为可配置 acquisition 分量。

局部灵敏度在无量纲变换坐标中计算：正值输入/输出使用 log，有符号量使用 asinh。
对目标电路任务头，参数重要度为

\[
I_j \propto \sum_k w_k\,(1+\text{violation}_k)
\left|\frac{\partial \tilde y_k}{\partial \tilde x_j}\right|.
\]

源电路的动作优先迁移为期望物理效应向量，而不是参数名或固定百分比。目标电路根据自己的局部 Jacobian 求带岭项的最小二乘投影：

\[
\Delta \tilde x^*=\arg\min_{\Delta \tilde x}
\|W^{1/2}(J_t\Delta\tilde x-\Delta\tilde y)\|_2^2
+\lambda\|\Delta\tilde x\|_2^2.
\]

实现使用可处理秩亏 Jacobian 的 least-squares 求解，并在边界/量化后重新计算实际效应。只有效应方向余弦和相对残差同时通过门限时，参数动作才可执行；否则退化为 `state_transfer_only`，继续推荐目标域探索点但不迁移动作。

选择结果新增 `capm_parameter_profile_status`、`capm_parameter_coverage`、
`capm_optimizable_parameter_coverage`、`capm_action_transfer_status`、
`capm_task_head_status`、`capm_task_alignment_score` 以及对应 JSON 诊断。示例配置通过
`transfer.target_circuit_profile: transistor_level_goa` 同时选择 GOA 参数空间和任务头；切换电路应新增或选择另一个 profile，而不是修改共享 CAPM/transfer 内核。
