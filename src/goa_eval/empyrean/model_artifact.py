from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from goa_eval.empyrean.schemas import STATUS_NOT_PROVIDED, STATUS_PASSED, base_versions
from goa_eval.io_utils import write_json


MODEL_EXTENSIONS = {".sp", ".spi", ".mod", ".model", ".txt"}


def summarize_model_artifacts(paths: list[Path], output_path: Path) -> dict[str, Any]:
    artifacts = [summarize_model_artifact(path) for path in paths if path.exists()]
    summary = {
        **base_versions(),
        "status": STATUS_PASSED if artifacts else STATUS_NOT_PROVIDED,
        "artifacts": artifacts,
    }
    write_json(output_path, summary)
    return summary


def summarize_model_artifact(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lower = text.lower()
    return {
        "path": str(path),
        "file_name": path.name,
        "size_bytes": path.stat().st_size,
        "model_names": _model_names(text),
        "contains_model_statement": ".model" in lower,
        "contains_subckt": ".subckt" in lower,
        "contains_tft_keyword": "tft" in lower,
        "contains_oled_keyword": "oled" in lower,
        "usable_for_simulation_hint": bool(".model" in lower or ".subckt" in lower),
    }


def _model_names(text: str) -> list[str]:
    names = []
    for pattern in [r"(?im)^\s*\.model\s+([^\s]+)", r"(?im)^\s*\.subckt\s+([^\s]+)"]:
        names.extend(match.group(1) for match in re.finditer(pattern, text))
    return sorted(set(names))
