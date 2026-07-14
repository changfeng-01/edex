# CAPM-Distance 三点优化实现计划

## 摘要

针对 CAPM-Distance 的三个已知劣势进行优化：
1. **物理耦合覆盖不全面**：将耦合对从 3 对扩展到 8 对，每对可独立配置权重和启用/禁用
2. **惩罚函数过于简单**：从固定二次惩罚改为默认指数惩罚，支持 YAML 按特征配置惩罚类型和陡峭度
3. **diversity_score 与 CAPM 距离不一致**：为 `compute_diversity` 和 `_attach_diversity` 新增 `distance_fn` 参数，CAPM 策略传入 `compute_capm_distance`

## 当前状态分析

### 涉及的核心文件

| 文件 | 路径 | 角色 |
|------|------|------|
| physics_distance.py | `src/goa_eval/pia_ca_llso/physics_distance.py` | CAPM 距离计算核心 |
| selector.py | `src/goa_eval/pia_ca_llso/selector.py` | 候选选择器 |
| acquisition.py | `src/goa_eval/pia_ca_llso/acquisition.py` | 采集函数和 diversity |
| pia_ca_llso_default.yaml | `config/pia_ca_llso_default.yaml` | 默认 YAML 配置 |
| pia_ca_llso_goa_profile.yaml | `config/pia_ca_llso_goa_profile.yaml` | GOA 专用 YAML 配置 |
| test_pia_physics_distance.py | `tests/test_pia_physics_distance.py` | 物理距离测试 |
| test_pia_selector.py | `tests/test_pia_selector.py` | 选择器测试 |

### 现有数据流

```
YAML config -> _capm_config() 合并 CAPM_DEFAULT_CONFIG
  -> compute_capm_distance() 使用 coupling_weight (全局单一值)
    -> _coupling_distance() 遍历 CAPM_COUPLINGS (3对固定元组)
  -> constraint_barrier_score()
    -> _low_margin_penalty() / _high_proxy_penalty() (固定二次惩罚)
```

### 现有问题定位

- **耦合**：`CAPM_COUPLINGS`（第60-64行）是硬编码的 3 对 `tuple[tuple[str,str],...]`，`coupling_weight`（第33行）是全局单一浮点数
- **惩罚**：`_low_margin_penalty`（第265行）和 `_high_proxy_penalty`（第273行）硬编码为 `(delta/threshold)²`
- **diversity**：`_attach_diversity`（selector.py 第158行）和 `compute_diversity`（acquisition.py 第60行）始终使用原始欧氏距离

---

## 优化点 1：物理耦合扩展

### 改动文件

#### 1.1 `physics_distance.py` — 修改 `CAPM_COUPLINGS` 常量（第60-64行）

**现状**：
```python
CAPM_COUPLINGS = (
    ("ron_pullup_cload_proxy", "clk_slew_proxy"),
    ("ron_pulldown_cload_proxy", "clk_slew_proxy"),
    ("cboot_cload_ratio", "vgh_vth_margin"),
)
```

**改为**：从 `tuple[tuple[str,str],...]` 改为 `list[dict]`，每对包含 `left/right/weight/enabled` 四个字段，扩展为 8 对：

```python
CAPM_COUPLINGS = [
    {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
    {"left": "ron_pulldown_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
    {"left": "cboot_cload_ratio", "right": "vgh_vth_margin", "weight": 0.25, "enabled": True},
    {"left": "ron_pullup_cload_proxy", "right": "vgh_vth_margin", "weight": 0.15, "enabled": True},
    {"left": "ron_pulldown_cload_proxy", "right": "vgl_off_margin", "weight": 0.15, "enabled": True},
    {"left": "cboot_cload_ratio", "right": "holding_droop_proxy", "weight": 0.15, "enabled": True},
    {"left": "pullup_pulldown_ratio", "right": "clk_slew_proxy", "weight": 0.10, "enabled": True},
    {"left": "vgh_vth_margin", "right": "vgl_off_margin", "weight": 0.10, "enabled": True},
]
```

新增 5 对耦合的物理含义：

| 编号 | left_key | right_key | 物理含义 |
|------|----------|-----------|----------|
| 4 | `ron_pullup_cload_proxy` | `vgh_vth_margin` | 上拉 Ron 与 VGH 阈值裕度耦合 |
| 5 | `ron_pulldown_cload_proxy` | `vgl_off_margin` | 下拉 Ron 与 VGL 关断裕度耦合 |
| 6 | `cboot_cload_ratio` | `holding_droop_proxy` | 自举电容比与保持跌落耦合 |
| 7 | `pullup_pulldown_ratio` | `clk_slew_proxy` | 上下拉比与时钟斜率耦合 |
| 8 | `vgh_vth_margin` | `vgl_off_margin` | VGH/VGL 裕度对称性耦合 |

#### 1.2 `physics_distance.py` — 修改 `CAPM_DEFAULT_CONFIG`（第20-34行）

移除 `"coupling_weight": 0.25`，新增 `"couplings"` 键（从 `CAPM_COUPLINGS` 派生默认值）：

```python
CAPM_DEFAULT_CONFIG = {
    "lambda_barrier": 1.0,
    "lambda_graph": 1.0,
    "lambda_missing": 1.0,
    "k_neighbors": 4,
    "min_vgh_vth_margin": 0.2,
    "min_vgl_off_margin": 0.2,
    "min_cboot_cload_ratio": 0.35,
    "max_ron_pullup_cload_proxy": 2.0,
    "max_ron_pulldown_cload_proxy": 2.0,
    "min_pullup_pulldown_ratio": 0.5,
    "max_pullup_pulldown_ratio": 2.0,
    "max_clk_slew_proxy": 2.0,
    "couplings": [dict(c) for c in CAPM_COUPLINGS],
    "penalty_config": {},
}
```

#### 1.3 `physics_distance.py` — 新增 `_resolve_couplings(config)` 函数

从配置中解析启用的耦合对及其权重，兼容旧的 `coupling_weight` 全局配置：

```python
def _resolve_couplings(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Resolve enabled coupling pairs with per-pair weights from config.
    
    Supports both new per-pair config and legacy global coupling_weight.
    """
    couplings_cfg = config.get("couplings", [])
    if not couplings_cfg:
        # Legacy fallback: use CAPM_COUPLINGS with global coupling_weight
        legacy_weight = float(config.get("coupling_weight", 0.25))
        return [
            {"left": c["left"], "right": c["right"], "weight": legacy_weight, "enabled": True}
            for c in CAPM_COUPLINGS
        ]
    # New per-pair config
    resolved = []
    for entry in couplings_cfg:
        if not isinstance(entry, dict):
            continue
        if not entry.get("enabled", True):
            continue
        resolved.append({
            "left": str(entry["left"]),
            "right": str(entry["right"]),
            "weight": float(entry.get("weight", 0.25)),
        })
    return resolved
```

#### 1.4 `physics_distance.py` — 修改 `_coupling_distance` 函数（第281-291行）

将函数签名从 `(phi_a, phi_b, coupling_weight: float)` 改为 `(phi_a, phi_b, couplings: list[dict])`，内部遍历 `couplings` 列表而非 `CAPM_COUPLINGS` 元组。

#### 1.5 `physics_distance.py` — 修改 `compute_capm_distance` 中的调用（第129行）

将：
```python
tensor_total += _coupling_distance(phi_a, phi_b, float(cfg["coupling_weight"]))
```

改为：
```python
couplings = _resolve_couplings(cfg)
tensor_total += _coupling_distance(phi_a, phi_b, couplings)
```

#### 1.6 YAML 配置文件更新

`config/pia_ca_llso_default.yaml` 和 `config/pia_ca_llso_goa_profile.yaml` 中，将 `capm_distance` 段下的 `coupling_weight: 0.25` 替换为：

```yaml
capm_distance:
  # ... 其他配置保持不变 ...
  couplings:
    - {left: ron_pullup_cload_proxy, right: clk_slew_proxy, weight: 0.25, enabled: true}
    - {left: ron_pulldown_cload_proxy, right: clk_slew_proxy, weight: 0.25, enabled: true}
    - {left: cboot_cload_ratio, right: vgh_vth_margin, weight: 0.25, enabled: true}
    - {left: ron_pullup_cload_proxy, right: vgh_vth_margin, weight: 0.15, enabled: true}
    - {left: ron_pulldown_cload_proxy, right: vgl_off_margin, weight: 0.15, enabled: true}
    - {left: cboot_cload_ratio, right: holding_droop_proxy, weight: 0.15, enabled: true}
    - {left: pullup_pulldown_ratio, right: clk_slew_proxy, weight: 0.10, enabled: true}
    - {left: vgh_vth_margin, right: vgl_off_margin, weight: 0.10, enabled: true}
```

---

## 优化点 2：惩罚函数非线性化

### 设计决策

- **默认惩罚类型**：`exponential`（`exp(alpha * |delta| / threshold) - 1`），alpha 默认 2.0
- **可配置性**：通过 YAML `penalty_config` 按特征名指定 `type`（linear/quadratic/exponential）和 `alpha`
- **向后兼容**：`_low_margin_penalty` 和 `_high_proxy_penalty` 保持原有签名，内部委托给 `_quadratic_penalty`

### 改动文件

#### 2.1 `physics_distance.py` — 新增三个惩罚函数

在 `_high_proxy_penalty` 之后新增：

```python
def _linear_penalty(delta: float, threshold: float) -> float:
    """Linear penalty: |delta| / threshold."""
    if threshold <= 0:
        return 0.0
    return float(abs(delta) / threshold)


def _quadratic_penalty(delta: float, threshold: float) -> float:
    """Quadratic penalty: (delta / threshold)^2."""
    if threshold <= 0:
        return 0.0
    return float((delta / threshold) ** 2)


def _exponential_penalty(delta: float, threshold: float, alpha: float = 2.0) -> float:
    """Exponential penalty: exp(alpha * |delta| / threshold) - 1."""
    if threshold <= 0:
        return 0.0
    return float(np.exp(alpha * abs(delta) / threshold) - 1.0)
```

#### 2.2 `physics_distance.py` — 新增 `_apply_penalty` 调度函数

```python
PENALTY_FUNCTIONS = {
    "linear": _linear_penalty,
    "quadratic": _quadratic_penalty,
    "exponential": _exponential_penalty,
}

DEFAULT_PENALTY_TYPE = "exponential"
DEFAULT_PENALTY_ALPHA = 2.0


def _apply_penalty(
    value: float | None,
    threshold: float,
    direction: str,
    penalty_config: Mapping[str, Any] | None = None,
    feature_name: str = "",
) -> float:
    """Apply configured penalty function for a feature constraint.
    
    Args:
        value: The observed value.
        threshold: The constraint threshold.
        direction: "low" (value must be >= threshold) or "high" (value must be <= threshold).
        penalty_config: Per-feature penalty configuration from YAML.
        feature_name: Name of the feature (used to look up per-feature config).
    
    Returns:
        Penalty score (0.0 if constraint is satisfied).
    """
    if value is None or threshold <= 0:
        return 0.0
    
    if direction == "low":
        if value >= threshold:
            return 0.0
        delta = threshold - value
    elif direction == "high":
        if value <= threshold:
            return 0.0
        delta = value - threshold
    else:
        return 0.0
    
    # Resolve penalty type and alpha for this feature
    pcfg = (penalty_config or {}).get(feature_name, {}) if penalty_config else {}
    penalty_type = str(pcfg.get("type", DEFAULT_PENALTY_TYPE)).lower()
    alpha = float(pcfg.get("alpha", DEFAULT_PENALTY_ALPHA))
    
    if penalty_type not in PENALTY_FUNCTIONS:
        penalty_type = DEFAULT_PENALTY_TYPE
    
    fn = PENALTY_FUNCTIONS[penalty_type]
    if penalty_type == "exponential":
        return fn(delta, threshold, alpha)
    return fn(delta, threshold)
```

#### 2.3 `physics_distance.py` — 修改 `constraint_barrier_score`（第78-97行）

将所有 `_low_margin_penalty` / `_high_proxy_penalty` 调用替换为 `_apply_penalty`，传入 `penalty_config` 和 `feature_name`：

```python
def constraint_barrier_score(
    phi: Mapping[str, Any] | pd.Series,
    config: Mapping[str, Any] | None = None,
) -> float:
    cfg = _capm_config(config)
    penalty_config = cfg.get("penalty_config", {})
    total = 0.0
    total += _apply_penalty(_numeric(phi.get("vgh_vth_margin")), float(cfg["min_vgh_vth_margin"]), "low", penalty_config, "vgh_vth_margin")
    total += _apply_penalty(_numeric(phi.get("vgl_off_margin")), float(cfg["min_vgl_off_margin"]), "low", penalty_config, "vgl_off_margin")
    total += _apply_penalty(_numeric(phi.get("cboot_cload_ratio")), float(cfg["min_cboot_cload_ratio"]), "low", penalty_config, "cboot_cload_ratio")
    total += _apply_penalty(_numeric(phi.get("ron_pullup_cload_proxy")), float(cfg["max_ron_pullup_cload_proxy"]), "high", penalty_config, "ron_pullup_cload_proxy")
    total += _apply_penalty(_numeric(phi.get("ron_pulldown_cload_proxy")), float(cfg["max_ron_pulldown_cload_proxy"]), "high", penalty_config, "ron_pulldown_cload_proxy")
    total += _apply_penalty(_numeric(phi.get("clk_slew_proxy")), float(cfg["max_clk_slew_proxy"]), "high", penalty_config, "clk_slew_proxy")
    ratio = _numeric(phi.get("pullup_pulldown_ratio"))
    if ratio is not None:
        total += _apply_penalty(ratio, float(cfg["min_pullup_pulldown_ratio"]), "low", penalty_config, "pullup_pulldown_ratio")
        total += _apply_penalty(ratio, float(cfg["max_pullup_pulldown_ratio"]), "high", penalty_config, "pullup_pulldown_ratio")
    return float(total)
```

#### 2.4 `physics_distance.py` — 保持 `_low_margin_penalty` 和 `_high_proxy_penalty` 向后兼容

将这两个函数改为内部委托给 `_quadratic_penalty`（保持原有行为）：

```python
def _low_margin_penalty(value: float | None, threshold: float) -> float:
    if value is None or threshold <= 0:
        return 0.0
    if value >= threshold:
        return 0.0
    return _quadratic_penalty(threshold - value, threshold)


def _high_proxy_penalty(value: float | None, threshold: float) -> float:
    if value is None or threshold <= 0:
        return 0.0
    if value <= threshold:
        return 0.0
    return _quadratic_penalty(value - threshold, threshold)
```

#### 2.5 YAML 配置文件更新

在 `capm_distance` 段中新增 `penalty_config`：

```yaml
capm_distance:
  # ... 其他配置保持不变 ...
  penalty_config:
    vgh_vth_margin:
      type: exponential
      alpha: 2.0
    vgl_off_margin:
      type: exponential
      alpha: 2.0
    cboot_cload_ratio:
      type: exponential
      alpha: 2.0
    ron_pullup_cload_proxy:
      type: exponential
      alpha: 2.0
    ron_pulldown_cload_proxy:
      type: exponential
      alpha: 2.0
    clk_slew_proxy:
      type: exponential
      alpha: 2.0
    pullup_pulldown_ratio:
      type: quadratic
      alpha: 2.0
```

---

## 优化点 3：diversity 与 CAPM 距离统一

### 设计决策

- 为 `compute_diversity` 和 `_attach_diversity` 新增可选参数 `distance_fn: Callable[[pd.Series, pd.Series], float] | None`
- 当 `distance_fn=None` 时保持原始欧氏距离（向后兼容）
- CAPM 策略传入一个包装了 `compute_capm_distance` 的 lambda

### 改动文件

#### 3.1 `acquisition.py` — 修改 `compute_diversity` 函数签名（第60行）

新增 `distance_fn` 参数：

```python
from typing import Callable

def compute_diversity(
    candidate: pd.Series,
    selected_candidates: pd.DataFrame,
    feature_cols: Sequence[str],
    distance_fn: Callable[[pd.Series, pd.Series], float] | None = None,
) -> float:
    if selected_candidates.empty or not feature_cols:
        return 1.0
    distances = []
    for _, row in selected_candidates.iterrows():
        if distance_fn is not None:
            distances.append(distance_fn(candidate, row))
        else:
            distances.append(
                float(np.sqrt(sum(
                    (float(candidate.get(col, 0.0)) - float(row.get(col, 0.0))) ** 2
                    for col in feature_cols
                )))
            )
    return float(min(np.mean(distances), 1.0))
```

#### 3.2 `selector.py` — 修改 `_attach_diversity` 函数签名（第158行）

新增 `distance_fn` 参数并透传给 `compute_diversity`：

```python
from typing import Callable

def _attach_diversity(
    frame: pd.DataFrame,
    feature_cols: Sequence[str],
    distance_fn: Callable[[pd.Series, pd.Series], float] | None = None,
) -> pd.DataFrame:
    output = frame.copy()
    selected = pd.DataFrame()
    scores = []
    for _, row in output.iterrows():
        score = compute_diversity(row, selected, feature_cols, distance_fn=distance_fn)
        scores.append(score)
        selected = pd.concat([selected, row.to_frame().T], ignore_index=True)
    output["diversity_score"] = scores
    return output
```

#### 3.3 `selector.py` — 修改 `select_capm_distance` 中的调用（第94行）

将：
```python
output = _attach_diversity(output, feature_cols)
```

改为：
```python
def _capm_distance_fn(a: pd.Series, b: pd.Series) -> float:
    result = compute_capm_distance(a, b, config=config)
    return float(result.get("distance", float("inf")))

output = _attach_diversity(output, feature_cols, distance_fn=_capm_distance_fn)
```

#### 3.4 `selector.py` — 新增 import

在文件顶部 import 中新增 `compute_capm_distance`：

```python
from goa_eval.pia_ca_llso.physics_distance import (
    FORBIDDEN_DISTANCE_COLUMNS,
    compute_capm_distance,  # 新增
    distance_to_l1_physics,
    normalize_distance,
    physics_geodesic_distance_to_l1,
)
```

---

## 测试用例更新

### `tests/test_pia_physics_distance.py` — 新增 7 个测试

1. **`test_coupling_extension_with_eight_pairs`**：验证 8 对耦合全部启用时 tensor_distance >= 仅 3 对时的值
2. **`test_coupling_per_pair_weight`**：验证每对耦合的独立权重生效（高权重 > 低权重）
3. **`test_coupling_disabled_via_config`**：验证 `enabled: false` 可禁用耦合对
4. **`test_legacy_coupling_weight_backward_compatible`**：验证旧的 `coupling_weight` 全局配置仍然有效
5. **`test_penalty_function_types`**：验证 linear/quadratic/exponential 三种惩罚函数的行为差异（exponential > quadratic > linear 对相同 delta）
6. **`test_penalty_config_per_feature`**：验证通过 `penalty_config` 按特征配置惩罚类型和 alpha
7. **`test_penalty_no_violation_returns_zero`**：验证未违反约束时 barrier_score 返回 0

### `tests/test_pia_selector.py` — 新增 2 个测试

1. **`test_capm_diversity_uses_capm_distance`**：验证 CAPM 策略的 diversity_score 在 [0, 1] 范围内且正常计算
2. **`test_physics_distance_diversity_backward_compatible`**：验证非 CAPM 策略的 diversity 仍然使用原始欧氏距离

---

## 实施顺序

```
Phase 1: 优化点2（惩罚函数非线性化）
  ├── 新增 _linear_penalty, _quadratic_penalty, _exponential_penalty
  ├── 新增 _apply_penalty 调度函数
  ├── 修改 constraint_barrier_score 使用 _apply_penalty
  ├── 重构 _low_margin_penalty / _high_proxy_penalty 内部委托
  └── 更新 YAML 配置 (penalty_config)

Phase 2: 优化点1（物理耦合扩展）
  ├── 修改 CAPM_COUPLINGS 常量（3→8对）
  ├── 新增 _resolve_couplings 函数
  ├── 修改 _coupling_distance 接受 couplings 列表
  ├── 修改 compute_capm_distance 中的调用
  └── 更新 YAML 配置 (couplings)

Phase 3: 优化点3（diversity 与 CAPM 距离统一）
  ├── 修改 compute_diversity 新增 distance_fn 参数
  ├── 修改 _attach_diversity 新增 distance_fn 参数
  ├── 修改 select_capm_distance 传入 CAPM distance_fn
  └── 更新 selector.py 的 import

Phase 4: 测试更新
  ├── test_pia_physics_distance.py 新增 7 个测试
  └── test_pia_selector.py 新增 2 个测试
```

Phase 1 和 Phase 2 可独立进行，Phase 3 依赖 Phase 1 和 Phase 2 完成后的 `compute_capm_distance` 签名稳定。

---

## 假设与决策

1. **向后兼容**：`_resolve_couplings` 保留 `coupling_weight` 全局配置回退逻辑；`_low_margin_penalty` 和 `_high_proxy_penalty` 保持原有签名
2. **`_capm_config` 嵌套解析**：`couplings` 和 `penalty_config` 放在 `capm_distance` 段下，与现有 `_capm_config` 的 `config["capm_distance"]` 嵌套路径一致
3. **新增耦合对的特征依赖**：第 6 对 `holding_droop_proxy` 仅在 GOA profile 下生成，generic profile 下 `_coupling_distance` 中的 `None` 检查会自动跳过
4. **性能**：`_attach_diversity` 在 CAPM 策略中每次迭代调用 `compute_capm_distance`（O(n²)），对于大量候选可能较慢，后续可考虑批量计算优化

---

## 验证步骤

1. 运行现有测试确保向后兼容：`python -m pytest tests/test_pia_physics_distance.py tests/test_pia_selector.py -q`
2. 运行新增测试：`python -m pytest tests/test_pia_physics_distance.py tests/test_pia_selector.py -q -k "coupling or penalty or diversity"`
3. 运行完整 PIA 测试套件：`python -m pytest tests/ -k pia -q`
4. 运行消融 benchmark 验证四种策略仍可正常执行：`python -m goa_eval.cli pia-benchmark --history-csv examples/pia_ca_llso/sample_history.csv --candidate-csv examples/pia_ca_llso/sample_candidates.csv --config config/pia_ca_llso_goa_profile.yaml --output-dir outputs/pia_capm_benchmark --strategies random,ca_llso_raw_distance,pia_physics_distance,pia_capm_distance --target-score 80`
5. 代码风格检查：`python -m ruff check src/goa_eval/pia_ca_llso/physics_distance.py src/goa_eval/pia_ca_llso/selector.py src/goa_eval/pia_ca_llso/acquisition.py`
