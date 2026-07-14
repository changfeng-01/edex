# 消除重复代码 —— 实施计划

## 一、概述

将分散在 18 个文件中的重复工具函数（`_as_float`、`_number`、`_finite`、`_clamp`、`_gt`、`_greater`、`_read_json`、`_read_yaml`、`_read_csv`、`_json_number`）统一提取到 `io_utils.py`，消除约 150 行重复代码，建立单一事实来源。

## 二、当前状态分析

### 2.1 重复函数清单

| 类别 | 函数 | 出现次数 | 涉及文件 |
|------|------|---------|---------|
| 数值转换 | `_as_float` | 9 次 | strategy_benchmark, sky130_mainline, goa_hybrid_optimizer, multi_round_optimizer, physics_engine, product_demo/figures, paper_digitization/build_ml_dataset, paper_digitization/quality_check, eclipse_benchmark/metrics |
| 数值转换 | `_number` / `_finite` | 4 次 | scorer, recommendation, analysis_metrics, multi_agent/optimization_loop |
| 数值转换 | `_clamp` | 1 次 | scorer |
| 比较 | `_gt` / `_greater` | 4 次 | scorer, recommendation, metrics, diagnosis |
| 文件 I/O | `_read_json` | 10 次 | strategy_benchmark, llm_analysis, multi_round_optimizer, web/runners, web_api/loaders, paper_digitization/build_ml_dataset, paper_digitization/build_leaderboard, product_demo/artifact_collector, csv_import_adapter, multi_agent/critic |
| 文件 I/O | `_read_yaml` / `_load_yaml` | 5 次 | strategy_benchmark, llm_analysis, paper_digitization/build_leaderboard, ai_profile_assistant, sky130_mainline |
| 文件 I/O | `_read_csv` | 3 次 | strategy_benchmark, paper_digitization/build_ml_dataset, product_demo/artifact_collector |
| JSON 辅助 | `_json_number` | 3 次 | strategy_benchmark, goa_strategy_benchmark, goa_hybrid_optimizer |

### 2.2 目标模块

`src/goa_eval/io_utils.py` 已被 35 个文件导入，是放置共享工具函数的自然位置。当前仅包含 `write_json`、`to_jsonable`、`ensure_run_dirs` 等写入/文件操作函数，缺少对应的读取函数和数值工具函数。

### 2.3 不纳入合并的例外

| 文件 | 函数 | 原因 |
|------|------|------|
| `evaluation/scoring.py` | `_finite()` | 语义不同——不转换为 float，仅检查 nan 并返回原始值 |
| `web_api/loaders.py` | `_read_json()` | 返回 `tuple[Any, str]` 而非 `dict`，签名不同 |
| `multi_agent/optimization_loop.py` | `_number()` | 位于 `multi_agent` 子包，属于不同逻辑边界，本次暂不处理 |

## 三、具体变更

### 步骤 1：扩展 `io_utils.py` —— 新增共享工具函数

**文件**：`src/goa_eval/io_utils.py`

在文件末尾追加以下函数（保持现有函数不变）：

#### 1.1 数值转换函数

```python
def as_float(value: Any, *, default: float | None = None) -> float | None:
    """安全地将值转换为 float，处理 None、pd.isna、类型错误。
    
    统一替代各模块中的 _as_float()。
    """
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def finite_float(value: Any) -> float | None:
    """安全转换为 float，额外排除 math.nan。
    
    统一替代 scorer.py:_finite() 和 analysis_metrics.py:_number()。
    """
    number = as_float(value)
    if number is not None and math.isnan(number):
        return None
    return number


def safe_float(value: Any) -> float | None:
    """安全转换为 float，不检查 math.nan。
    
    统一替代 recommendation.py:_number()。
    """
    return as_float(value)


def clamp_0_100(value: float) -> float:
    """将值钳制到 [0, 100] 范围。
    
    统一替代 scorer.py:_clamp()。
    """
    return float(max(0.0, min(100.0, value)))


def gt(value: Any, limit: Any) -> bool:
    """安全的大于比较，处理 None/nan。
    
    统一替代 scorer.py:_gt()、recommendation.py:_gt()、
    metrics.py:_gt()、diagnosis.py:_greater()。
    """
    v = finite_float(value)
    l = finite_float(limit)
    return v is not None and l is not None and v > l


def json_number(value: Any) -> float | None:
    """从 JSON 兼容值中提取数值。
    
    统一替代 strategy_benchmark.py:_json_number()、
    goa_strategy_benchmark.py:_json_number()、
    goa_hybrid_optimizer.py:_json_number()。
    """
    return as_float(value)
```

**需要的 import 补充**（在文件顶部添加）：
```python
import math
import pandas as pd
```

#### 1.2 文件 I/O 函数

```python
def read_json(path: Path | None) -> dict[str, Any]:
    """安全读取 JSON 文件，不存在或解析失败时返回 {}。
    
    统一替代各模块中的 _read_json()。
    采用 multi_round_optimizer.py 中最健壮的版本（含错误处理 + 类型检查）。
    """
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_yaml(path: Path | None) -> dict[str, Any]:
    """安全读取 YAML 文件，不存在时返回 {}。
    
    统一替代各模块中的 _read_yaml() 和 _load_yaml()。
    采用 strategy_benchmark.py 中最健壮的版本（含类型检查）。
    """
    if path is None or not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def read_csv(path: Path | None) -> "pd.DataFrame":
    """安全读取 CSV 文件，不存在时返回空 DataFrame。
    
    统一替代各模块中的 _read_csv()。
    """
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
```

**需要的 import 补充**：
```python
import json
import yaml
```

### 步骤 2：逐文件替换 —— 删除本地定义，改为从 io_utils 导入

按依赖关系从简单到复杂排序，每个文件的操作模式为：
1. 在文件顶部的 import 区域添加 `from goa_eval.io_utils import ...`
2. 删除文件底部的本地重复函数定义
3. 将文件内所有对本地函数的调用替换为导入的函数名

#### 批次 A：仅定义未导出给外部的文件（无跨文件引用风险）

| 序号 | 文件 | 删除的本地函数 | 新增导入 |
|------|------|-------------|---------|
| A1 | `src/goa_eval/analysis_metrics.py` | `_number()` (L426-435) | `from goa_eval.io_utils import finite_float as _number` |
| A2 | `src/goa_eval/recommendation.py` | `_number()` (L415-421), `_gt()` (L424-427) | `from goa_eval.io_utils import safe_float as _number, gt as _gt` |
| A3 | `src/goa_eval/diagnosis.py` | `_greater()` (L66-67) | `from goa_eval.io_utils import gt as _greater` |
| A4 | `src/goa_eval/physics_engine.py` | `_as_float()` (L313-319) | `from goa_eval.io_utils import as_float as _as_float` |
| A5 | `src/goa_eval/llm_analysis.py` | `_read_json()` (L290-293), `_read_yaml()` (L296-299) | `from goa_eval.io_utils import read_json as _read_json, read_yaml as _read_yaml` |
| A6 | `src/goa_eval/ai_profile_assistant.py` | `_read_yaml()` (L188-191) | `from goa_eval.io_utils import read_yaml as _read_yaml` |
| A7 | `src/goa_eval/csv_import_adapter.py` | `_read_json()` (L213-217) | `from goa_eval.io_utils import read_json as _read_json` |
| A8 | `src/goa_eval/product_demo/artifact_collector.py` | `_read_json()` (L125-129), `_read_csv()` (L134-138) | `from goa_eval.io_utils import read_json as _read_json, read_csv as _read_csv` |
| A9 | `src/goa_eval/product_demo/figures.py` | `_as_float()` (L205-211) | `from goa_eval.io_utils import as_float as _as_float` |
| A10 | `src/goa_eval/paper_digitization/build_ml_dataset.py` | `_read_csv()` (L339-343), `_read_json()` (L345-349), `_as_float()` (L368-374) | `from goa_eval.io_utils import read_csv as _read_csv, read_json as _read_json, as_float as _as_float` |
| A11 | `src/goa_eval/paper_digitization/build_leaderboard.py` | `_read_yaml()` (L141-145), `_read_json()` (L147-151) | `from goa_eval.io_utils import read_yaml as _read_yaml, read_json as _read_json` |
| A12 | `src/goa_eval/paper_digitization/quality_check.py` | `_as_float()` (L135-141) | `from goa_eval.io_utils import as_float as _as_float` |
| A13 | `src/goa_eval/eclipse_benchmark/metrics.py` | `_as_float()` (L316-322) | `from goa_eval.io_utils import as_float as _as_float` |
| A14 | `src/goa_eval/web/runners.py` | `_read_json()` (L139-143) | `from goa_eval.io_utils import read_json as _read_json` |
| A15 | `src/goa_eval/multi_agent/critic.py` | `_read_json()` (L193-197) | `from goa_eval.io_utils import read_json as _read_json` |

#### 批次 B：scorer.py —— 有内部交叉引用

**文件**：`src/goa_eval/scorer.py`

- 删除：`_finite()` (L470-479)、`_clamp()` (L482-483)、`_gt()` (L464-467)
- 新增导入：
  ```python
  from goa_eval.io_utils import finite_float as _finite, clamp_0_100 as _clamp, gt as _gt
  ```
- 注意：`_gt()` 在 scorer.py 内部调用 `_finite()`，替换后 `gt()` 内部已调用 `finite_float()`，行为一致

#### 批次 C：metrics.py

**文件**：`src/goa_eval/metrics.py`

- 删除：`_gt()` (L592-595)
- 新增导入：`from goa_eval.io_utils import gt as _gt`
- 注意：metrics.py 的 `_gt()` 直接使用 `float()` 而非 `_finite()`，替换为统一 `gt()` 后行为更安全（增加了 None/nan 保护）

#### 批次 D：strategy_benchmark.py —— 定义最多重复函数

**文件**：`src/goa_eval/strategy_benchmark.py`

- 删除：`_read_csv()` (L321-324)、`_read_json()` (L327-332)、`_read_yaml()` (L335-339)、`_as_float()` (L342-348)、`_json_number()` (L351-353)
- 新增导入：
  ```python
  from goa_eval.io_utils import read_csv as _read_csv, read_json as _read_json, read_yaml as _read_yaml, as_float as _as_float, json_number as _json_number
  ```

#### 批次 E：sky130_mainline.py

**文件**：`src/goa_eval/sky130_mainline.py`

- 删除：`_load_yaml()` (L475-479)、`_as_float()` (L587-593)
- 新增导入：
  ```python
  from goa_eval.io_utils import read_yaml as _load_yaml, as_float as _as_float
  ```

#### 批次 F：goa_hybrid_optimizer.py

**文件**：`src/goa_eval/goa_hybrid_optimizer.py`

- 删除：`_as_float()` (L910-916)、`_json_number()` (L919-921)
- 新增导入：
  ```python
  from goa_eval.io_utils import as_float as _as_float, json_number as _json_number
  ```

#### 批次 G：multi_round_optimizer.py

**文件**：`src/goa_eval/multi_round_optimizer.py`

- 删除：`_read_json()` (L599-606)、`_as_float()` (L931-937)
- 新增导入：
  ```python
  from goa_eval.io_utils import read_json as _read_json, as_float as _as_float
  ```

#### 批次 H：goa_strategy_benchmark.py

**文件**：`src/goa_eval/goa_strategy_benchmark.py`

- 删除：`_json_number()` (L687-693)
- 新增导入：`from goa_eval.io_utils import json_number as _json_number`

### 步骤 3：运行测试验证

在所有文件修改完成后，运行以下测试确保无回归：

```bash
# 核心评价管线
pytest tests/test_scorer_breakdown.py -v
pytest tests/test_recommendation.py -v
pytest tests/test_llm_analysis.py -v

# 优化引擎
pytest tests/test_multi_round_optimizer.py -v
pytest tests/test_goa_hybrid_optimizer.py -v
pytest tests/test_physics_engine.py -v

# 策略基准
pytest tests/test_goa_strategy_benchmark.py -v
pytest tests/test_strategy_benchmark.py -v

# 其他受影响模块
pytest tests/test_sky130_mainline.py -v
pytest tests/test_analysis_metrics.py -v  # 如果存在
pytest tests/test_diagnosis.py -v  # 如果存在
pytest tests/test_io_utils.py -v

# 全量回归（最终确认）
pytest tests/ -v --tb=short
```

## 四、假设与决策

1. **使用别名保持向后兼容**：所有替换使用 `from io_utils import new_name as old_name` 模式，文件内部调用无需修改，降低风险。
2. **io_utils.py 是唯一目标**：不新建 `utils.py`，因为 io_utils 已被 35 个文件导入，是自然聚集点。
3. **`paper_digitization/build_ml_dataset.py` 的 `_as_float(default=...)` 参数**：统一后的 `as_float()` 已支持 `default` 关键字参数，该文件调用 `_as_float(value, default=0.0)` 可直接替换。
4. **`web_api/loaders.py` 不纳入**：其 `_read_json()` 返回 `tuple[Any, str]`，签名不同，保持原样。
5. **`evaluation/scoring.py` 不纳入**：其 `_finite()` 语义不同（不转换 float），保持原样。
6. **`multi_agent/optimization_loop.py` 不纳入**：位于独立子包，本次暂不处理。
7. **metrics.py 的 `_gt()` 行为变化**：原版直接用 `float()`，替换后使用 `finite_float()` 增加了 None/nan 保护，这是行为改进而非破坏。

## 五、验证步骤

1. **单元测试**：运行上述全部受影响模块的测试，确保全部通过
2. **类型检查**：确认 io_utils.py 新增函数的类型注解正确
3. **导入检查**：确认所有修改后的文件 import 语句无循环依赖
4. **手动抽查**：随机选取 3 个修改后的文件，确认本地函数定义已删除、导入正确
5. **全量回归**：运行 `pytest tests/` 确保无意外破坏
