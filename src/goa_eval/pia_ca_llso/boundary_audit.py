"""Evidence-boundary audit for PIA closed-loop outputs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


BOUNDARY_DATA_SOURCE = "real_simulation_csv"
BOUNDARY_VALIDITY = "simulation_only"
SUGGESTION_FILES = {
    "simulation_batch.csv",
    "pia_selected_candidates.csv",
    "offspring_candidates.csv",
}
IMPORTED_FILES = {
    "imported_results.csv",
    "evolution_history.csv",
}
OVERCLAIM_PHRASES = [
    "physical validation complete",
    "silicon validation complete",
    "lab validation complete",
    "tapeout validation complete",
    "validated in silicon",
    "validated on hardware",
]


def audit_evolution_outputs(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    issues: list[dict[str, Any]] = []
    checked_files: list[str] = []
    for path in sorted(root.rglob("*.csv")):
        checked_files.append(str(path.relative_to(root)))
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            issues.append(_issue(path, root, f"could not read CSV: {exc}"))
            continue
        _audit_frame(path, root, frame, issues)

    for path in sorted(root.rglob("*.md")):
        checked_files.append(str(path.relative_to(root)))
        text = path.read_text(encoding="utf-8", errors="ignore")
        lower = text.lower()
        for phrase in OVERCLAIM_PHRASES:
            idx = lower.find(phrase)
            if idx == -1:
                continue
            context = lower[max(0, idx - 120): idx + len(phrase)]
            if "not " in context or "do not" in context or "does not" in context:
                continue
            issues.append(_issue(path, root, f"overclaiming report text: {phrase}"))

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "checked_files": checked_files,
    }


def _audit_frame(path: Path, root: Path, frame: pd.DataFrame, issues: list[dict[str, Any]]) -> None:
    if frame.empty:
        return
    if "engineering_validity" not in frame.columns:
        issues.append(_issue(path, root, "missing engineering_validity"))
    else:
        bad = frame["engineering_validity"].fillna("").astype(str) != BOUNDARY_VALIDITY
        if bad.any():
            issues.append(_issue(path, root, "engineering_validity must be simulation_only"))

    if path.name in SUGGESTION_FILES:
        if "must_resimulate" not in frame.columns:
            issues.append(_issue(path, root, "suggestion rows missing must_resimulate = true"))
        else:
            must = frame["must_resimulate"].map(_as_bool)
            if not must.all():
                issues.append(_issue(path, root, "suggestion rows must keep must_resimulate = true"))

    if path.name in IMPORTED_FILES and "source" in frame.columns:
        imported = frame["source"].fillna("").astype(str) == "simulation_result"
        if imported.any():
            if "data_source" not in frame.columns:
                issues.append(_issue(path, root, "imported rows missing data_source = real_simulation_csv"))
            else:
                bad_source = frame.loc[imported, "data_source"].fillna("").astype(str) != BOUNDARY_DATA_SOURCE
                if bad_source.any():
                    issues.append(_issue(path, root, "imported rows must keep data_source = real_simulation_csv"))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _issue(path: Path, root: Path, message: str) -> dict[str, Any]:
    return {
        "file": str(path.relative_to(root)),
        "message": message,
    }
