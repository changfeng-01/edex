from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
import hashlib
import json
import math
import shutil
import yaml
import zipfile

import pandas as pd


def ensure_run_dirs(out_dir: Path) -> None:
    for child in ["metrics", "figures", "reports", "logs"]:
        (out_dir / child).mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_archives(raw_dir: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    for archive in sorted(raw_dir.glob("*.zip")):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                _validate_archive_member(member.filename)
            zf.extractall(out_dir)
        extracted.append(archive)
    return extracted


def _validate_archive_member(name: str) -> None:
    normalized = name.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"Unsafe archive member path: {name}")
    if ".." in posix_path.parts:
        raise ValueError(f"Unsafe archive member path: {name}")


def copy_initial_raw_inputs(root: Path) -> None:
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name in ["v1.zip", "v8.zip", "评价指标表.html"]:
        src = root / name
        if src.exists():
            shutil.copy2(src, raw / name)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(data), ensure_ascii=False, indent=2), encoding="utf-8")


def to_jsonable(value: object) -> object:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


# ---------------------------------------------------------------------------
# 数值转换工具（统一替代各模块中的重复 _as_float / _number / _finite / _clamp）
# ---------------------------------------------------------------------------

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
    threshold = finite_float(limit)
    return v is not None and threshold is not None and v > threshold


def json_number(value: Any) -> float | None:
    """从 JSON 兼容值中提取数值。

    统一替代 strategy_benchmark.py:_json_number()、
    goa_strategy_benchmark.py:_json_number()、
    goa_hybrid_optimizer.py:_json_number()。
    """
    return as_float(value)


# ---------------------------------------------------------------------------
# 文件 I/O 工具（统一替代各模块中的 _read_json / _read_yaml / _read_csv）
# ---------------------------------------------------------------------------

def read_json(path: Path | str | None) -> dict[str, Any]:
    """安全读取 JSON 文件，不存在或解析失败时返回 {}。

    统一替代各模块中的 _read_json()。
    采用 multi_round_optimizer.py 中最健壮的版本（含错误处理 + 类型检查）。
    """
    if path is None:
        return {}
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_yaml(path: Path | str | None) -> dict[str, Any]:
    """安全读取 YAML 文件，不存在时返回 {}。

    统一替代各模块中的 _read_yaml() 和 _load_yaml()。
    采用 strategy_benchmark.py 中最健壮的版本（含类型检查）。
    """
    if path is None:
        return {}
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def read_csv(path: Path | str | None) -> "pd.DataFrame":
    """安全读取 CSV 文件，不存在时返回空 DataFrame。

    统一替代各模块中的 _read_csv()。
    """
    if path is None:
        return pd.DataFrame()
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
