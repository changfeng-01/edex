from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, Depends, File, UploadFile

from goa_eval.product.input_service import InputFile
from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import ProductApiError, translate_domain_error
from goa_eval.product_api.schemas import success
from goa_eval.web.schemas import UploadedCaseConfig


router = APIRouter(prefix="/api/v1")


@router.post("/design-versions/{version_id}/inputs/preview")
async def preview_input(
    version_id: str,
    waveform: UploadFile = File(...),
    params: UploadFile | None = File(default=None),
    netlist: UploadFile | None = File(default=None),
    attachments: list[UploadFile] | None = File(default=None),
    container: ProductContainer = Depends(get_container),
):
    uploads = [(waveform, "waveform.csv")]
    if params is not None:
        uploads.append((params, "params.yaml"))
    if netlist is not None:
        suffix = Path(netlist.filename or "").suffix.lower()
        if suffix not in {".sp", ".spice", ".netlist"}:
            raise ProductApiError("INPUT_PREVIEW_FAILED", "Input preview failed.", 422)
        uploads.append((netlist, f"source_netlist{suffix}"))
    for attachment in attachments or []:
        uploads.append((attachment, f"attachments/{_safe_filename(attachment.filename)}"))

    try:
        with TemporaryDirectory(prefix="circuitpilot-api-input-") as temporary_name:
            temporary = Path(temporary_name)
            input_files = []
            for upload, logical_name in uploads:
                _safe_filename(upload.filename)
                target = temporary / logical_name.replace("/", "_")
                target.write_bytes(await upload.read())
                input_files.append(InputFile(logical_name, target))
            result = container.input_service.create_input_snapshot(
                design_version_id=version_id,
                files=input_files,
                preview_config=UploadedCaseConfig(case_id=f"preview_{version_id}"),
            )
        return success(result, status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


def _safe_filename(filename: str | None) -> str:
    value = str(filename or "").strip()
    if not value or "/" in value or "\\" in value or ":" in value or Path(value).name != value:
        raise ProductApiError("INPUT_PREVIEW_FAILED", "Input preview failed.", 422)
    return value
