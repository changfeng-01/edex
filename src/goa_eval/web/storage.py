from __future__ import annotations

import re
import shutil
import uuid
import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, UploadFile

from goa_eval.io_utils import write_json
from goa_eval.web.schemas import UploadedCaseConfig, evidence_boundary

if TYPE_CHECKING:
    from goa_eval.web.schemas import WebApiSettings


CASE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
ALLOWED_WAVEFORM_EXTENSIONS = {".csv"}
ALLOWED_PARAM_EXTENSIONS = {".yaml", ".yml"}
ALLOWED_NETLIST_EXTENSIONS = {".spice", ".sp", ".netlist"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_WAVEFORM_EXTENSIONS | ALLOWED_PARAM_EXTENSIONS | ALLOWED_NETLIST_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS
ALLOWED_ASSET_EXTENSIONS = {".json", ".csv", ".md", ".png", ".jpg", ".jpeg", ".webp", ".txt"}


def generate_case_id() -> str:
    return f"case_{uuid.uuid4().hex[:12]}"


def generate_demo_case_id() -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"demo_{timestamp}_{uuid.uuid4().hex[:6]}"


def validate_case_id(case_id: str) -> str:
    value = case_id.strip()
    if not CASE_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid case_id")
    return value


def validate_filename(filename: str, allowed_extensions: set[str] = ALLOWED_UPLOAD_EXTENSIONS) -> str:
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


def resolve_under(root: Path, *parts: str) -> Path:
    root_resolved = root.resolve()
    path = root_resolved.joinpath(*parts).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise HTTPException(status_code=400, detail="path escapes case directory")
    return path


def prepare_case_dir(root: Path, case_id: str) -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    case_dir = resolve_under(root, validate_case_id(case_id))
    if case_dir.exists():
        raise HTTPException(status_code=409, detail=f"case_id already exists: {case_id}")
    (case_dir / "input").mkdir(parents=True, exist_ok=True)
    (case_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (case_dir / "product_demo").mkdir(parents=True, exist_ok=True)
    return case_dir


async def save_uploads(
    case_dir: Path,
    files: list[UploadFile],
    settings: "WebApiSettings | None" = None,
) -> dict[str, Path]:
    from goa_eval.web.schemas import WebApiSettings

    settings = settings or WebApiSettings()
    input_dir = case_dir / "input"
    saved: dict[str, Path] = {}
    attachments_dir = input_dir / "attachments"
    total_bytes = 0
    attachment_count = 0
    for upload in files:
        filename = validate_filename(upload.filename or "")
        target_name = _target_name(upload, filename, saved)
        if target_name.startswith("attachments/"):
            attachment_count += 1
            if attachment_count > settings.max_attachments:
                raise HTTPException(status_code=413, detail=f"attachment count exceeds {settings.max_attachments}")
            attachments_dir.mkdir(parents=True, exist_ok=True)
        target = resolve_under(input_dir, *target_name.split("/"))
        file_limit = _upload_limit(target_name, settings)
        file_bytes = 0
        try:
            with target.open("wb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    file_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if file_bytes > file_limit:
                        raise HTTPException(status_code=413, detail=f"{target_name} exceeds upload limit")
                    if total_bytes > settings.max_request_bytes:
                        raise HTTPException(status_code=413, detail="upload request exceeds total limit")
                    handle.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        saved[target_name] = target
    if "waveform.csv" not in saved:
        raise HTTPException(status_code=400, detail="waveform.csv is required")
    return saved


def _upload_limit(target_name: str, settings: "WebApiSettings") -> int:
    if target_name == "waveform.csv":
        return settings.max_waveform_bytes
    if target_name == "params.yaml":
        return settings.max_param_bytes
    if target_name.startswith("attachments/"):
        return settings.max_image_bytes
    return settings.max_netlist_bytes


def copy_sample_inputs(case_dir: Path, waveform_path: Path, params_path: Path | None = None) -> dict[str, Path]:
    if not waveform_path.exists():
        raise HTTPException(status_code=500, detail=f"sample waveform not found: {waveform_path}")
    input_dir = case_dir / "input"
    saved = {"waveform.csv": resolve_under(input_dir, "waveform.csv")}
    shutil.copyfile(waveform_path, saved["waveform.csv"])
    if params_path is not None:
        if not params_path.exists():
            raise HTTPException(status_code=500, detail=f"sample params not found: {params_path}")
        saved["params.yaml"] = resolve_under(input_dir, "params.yaml")
        shutil.copyfile(params_path, saved["params.yaml"])
    return saved


def build_config(fields: dict[str, Any]) -> UploadedCaseConfig:
    case_id = validate_case_id(str(fields.get("case_id") or generate_case_id()))
    return UploadedCaseConfig(
        case_id=case_id,
        circuit_profile=_optional_str(fields.get("circuit_profile")),
        topology=_optional_str(fields.get("topology")),
        stage_count=_optional_int(fields.get("stage_count")),
        output_node_pattern=_optional_str(fields.get("output_node_pattern")) or "o{index}",
        generate_candidates=_optional_bool(fields.get("generate_candidates"), default=True),
        run_llm_analysis=_optional_bool(fields.get("run_llm_analysis"), default=False),
    )


def write_status(case_dir: Path, payload: dict[str, Any]) -> None:
    payload.setdefault("evidence_boundary", evidence_boundary())
    write_json(case_dir / "case_status.json", payload)


def read_status(root: Path, case_id: str) -> dict[str, Any]:
    path = resolve_under(root, validate_case_id(case_id), "case_status.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="case status not found")
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def resolve_asset(root: Path, case_id: str, asset_path: str) -> Path:
    if not asset_path or asset_path.startswith(("/", "\\")) or ".." in Path(asset_path).parts:
        raise HTTPException(status_code=400, detail="invalid asset path")
    case_dir = resolve_under(root, validate_case_id(case_id))
    path = resolve_under(case_dir, *Path(asset_path).parts)
    if path.suffix.lower() not in ALLOWED_ASSET_EXTENSIONS:
        raise HTTPException(status_code=400, detail="invalid asset extension")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return path


def _target_name(upload: UploadFile, filename: str, saved: dict[str, Path]) -> str:
    suffix = Path(filename).suffix.lower()
    field_name = upload.filename or filename
    form_name = getattr(upload, "name", "")
    if form_name == "waveform" or filename == "waveform.csv":
        return "waveform.csv"
    if form_name == "params" or filename == "params.yaml" or suffix in ALLOWED_PARAM_EXTENSIONS:
        return "params.yaml"
    if suffix in ALLOWED_NETLIST_EXTENSIONS:
        return f"source_netlist{suffix}"
    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        return f"attachments/{_unique_attachment_name(filename, saved)}"
    if suffix in ALLOWED_WAVEFORM_EXTENSIONS and "waveform.csv" not in saved and "waveform" in field_name.lower():
        return "waveform.csv"
    raise HTTPException(status_code=400, detail=f"unsupported upload file: {filename}")


def _unique_attachment_name(filename: str, saved: dict[str, Path]) -> str:
    if f"attachments/{filename}" not in saved:
        return filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 2
    while f"attachments/{stem}_{index}{suffix}" in saved:
        index += 1
    return f"{stem}_{index}{suffix}"


def _optional_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_int(value: Any) -> int | None:
    text = _optional_str(value)
    return int(text) if text else None


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
