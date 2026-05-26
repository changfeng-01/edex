from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
import hashlib
import json
import shutil
import zipfile


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
