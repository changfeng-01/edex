from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def read_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        return {}
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def ensure_output_dir(path: str | Path) -> Path:
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def read_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def write_json(path: str | Path, data: dict[str, Any] | list[Any]) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: str | Path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def write_csv(path: str | Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False)
