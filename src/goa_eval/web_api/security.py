from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException


CASE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
ALLOWED_FIGURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_REPORT_EXTENSIONS = {".md"}


def validate_case_id(case_id: str) -> str:
    if not CASE_ID_RE.fullmatch(case_id) or case_id in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid case_id")
    return case_id


def validate_filename(filename: str, allowed_extensions: set[str]) -> str:
    candidate = Path(filename)
    if (
        not filename
        or candidate.name != filename
        or candidate.is_absolute()
        or ".." in filename
        or "/" in filename
        or "\\" in filename
        or candidate.suffix.lower() not in allowed_extensions
    ):
        raise HTTPException(status_code=400, detail="invalid filename")
    return filename


def resolve_case_dir(root: Path, case_id: str) -> Path:
    validate_case_id(case_id)
    return resolve_under(root, case_id)


def resolve_under(root: Path, *parts: str) -> Path:
    root_resolved = root.resolve()
    path = root_resolved.joinpath(*parts).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise HTTPException(status_code=400, detail="path escapes product-demo root")
    return path


def validate_repo_relative_path(value: str, repo_root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or any(part in {"..", ""} for part in candidate.parts):
        raise HTTPException(status_code=400, detail="path must be repository-relative")
    resolved = repo_root.resolve().joinpath(candidate).resolve()
    repo_resolved = repo_root.resolve()
    if resolved != repo_resolved and repo_resolved not in resolved.parents:
        raise HTTPException(status_code=400, detail="path escapes repository root")
    return resolved

