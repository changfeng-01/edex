from __future__ import annotations

import json
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import HTTPException

from goa_eval.io_utils import write_json
from goa_eval.product_demo.schemas import DIRECTORIES
from goa_eval.web.storage import ALLOWED_ASSET_EXTENSIONS, validate_case_id
from goa_eval.web_api.loaders import load_bundle


BLOB_TOKEN_ENV = "BLOB_READ_WRITE_TOKEN"
DEFAULT_BLOB_API_BASE = "https://blob.vercel-storage.com"
DEFAULT_BLOB_PREFIX = "web_cases"


@dataclass(frozen=True)
class BlobUpload:
    pathname: str
    url: str
    content_type: str


class VercelBlobStore:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_base_url: str = DEFAULT_BLOB_API_BASE,
        prefix: str = DEFAULT_BLOB_PREFIX,
        api_version: str = "11",
    ) -> None:
        self.token = (token or "").strip()
        self.api_base_url = api_base_url.rstrip("/")
        self.prefix = prefix.strip("/ ") or DEFAULT_BLOB_PREFIX
        self.api_version = api_version

    @classmethod
    def from_env(cls) -> "VercelBlobStore":
        return cls(
            token=os.getenv(BLOB_TOKEN_ENV),
            api_base_url=os.getenv("CIRCUITPILOT_BLOB_API_BASE", DEFAULT_BLOB_API_BASE),
            prefix=os.getenv("CIRCUITPILOT_BLOB_PREFIX", DEFAULT_BLOB_PREFIX),
            api_version=os.getenv("CIRCUITPILOT_BLOB_API_VERSION", "11"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def case_path(self, case_id: str, relative_path: str) -> str:
        case_id = validate_case_id(case_id)
        clean_relative = _validate_blob_relative_path(relative_path)
        return f"{self.prefix}/{case_id}/{clean_relative}"

    def put_file(self, pathname: str, source_path: Path, *, content_type: str | None = None) -> BlobUpload:
        if not self.enabled:
            raise RuntimeError(f"{BLOB_TOKEN_ENV} is required for Vercel Blob storage")
        content_type = content_type or _content_type_for_path(source_path)
        payload = source_path.read_bytes()
        response = self._request(
            "PUT",
            pathname,
            payload,
            {
                "content-type": content_type,
                "x-content-type": content_type,
                "x-access": "public",
                "x-add-random-suffix": "0",
            },
        )
        details = json.loads(response.decode("utf-8"))
        return BlobUpload(pathname=pathname, url=str(details.get("url") or ""), content_type=content_type)

    def put_json(self, pathname: str, payload: dict[str, Any]) -> BlobUpload:
        handle = tempfile.NamedTemporaryFile(prefix="circuitpilot_blob_", suffix=".json", delete=False)
        handle.close()
        temp_path = Path(handle.name)
        try:
            write_json(temp_path, payload)
            return self.put_file(pathname, temp_path, content_type="application/json; charset=utf-8")
        finally:
            temp_path.unlink(missing_ok=True)

    def read_json(self, pathname: str) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError(f"{BLOB_TOKEN_ENV} is required for Vercel Blob storage")
        try:
            return json.loads(self._request("GET", pathname, None, {}).decode("utf-8"))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"blob json could not be parsed: {exc}") from exc

    def _request(self, method: str, pathname: str, payload: bytes | None, headers: dict[str, str]) -> bytes:
        url = f"{self.api_base_url}/{quote(pathname.lstrip('/'), safe='/')}"
        request_headers = {
            "authorization": f"Bearer {self.token}",
            "x-api-version": self.api_version,
            **headers,
        }
        request = Request(url, data=payload, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise HTTPException(status_code=404, detail="blob object not found") from exc
            detail = exc.read().decode("utf-8", errors="replace") or exc.reason
            raise HTTPException(status_code=502, detail=f"blob request failed: {detail}") from exc
        except URLError as exc:
            raise HTTPException(status_code=502, detail=f"blob request failed: {exc.reason}") from exc


def persist_case_dir_to_blob(store: VercelBlobStore, case_dir: Path, case_id: str) -> None:
    if not store.enabled:
        return
    case_id = validate_case_id(case_id)
    uploads: dict[str, BlobUpload] = {}
    for path in sorted(case_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(case_dir).as_posix()
        blob_path = store.case_path(case_id, relative_path)
        uploads[relative_path] = store.put_file(blob_path, path)

    bundle = _build_blob_bundle(case_dir, case_id, uploads)
    if bundle is not None:
        store.put_json(store.case_path(case_id, "dashboard_bundle.json"), bundle)
    url_index = {relative_path: upload.url for relative_path, upload in uploads.items() if upload.url}
    store.put_json(store.case_path(case_id, "blob_urls.json"), {"case_id": case_id, "urls": url_index})


def load_case_json_from_blob(store: VercelBlobStore, case_id: str, relative_path: str) -> dict[str, Any]:
    return store.read_json(store.case_path(validate_case_id(case_id), relative_path))


def load_case_bundle_from_blob(store: VercelBlobStore, case_id: str) -> dict[str, Any]:
    return load_case_json_from_blob(store, case_id, "dashboard_bundle.json")


def blob_asset_url(store: VercelBlobStore, case_id: str, asset_path: str) -> str:
    asset_path = _validate_asset_path(asset_path)
    url_index = load_case_json_from_blob(store, case_id, "blob_urls.json")
    url = (url_index.get("urls") or {}).get(asset_path)
    if not url:
        raise HTTPException(status_code=404, detail="asset not found")
    return str(url)


def _build_blob_bundle(case_dir: Path, case_id: str, uploads: dict[str, BlobUpload]) -> dict[str, Any] | None:
    product_demo_root = case_dir / "product_demo"
    product_demo_case_dir = product_demo_root / case_id
    if not product_demo_case_dir.exists():
        return None
    bundle = load_bundle(product_demo_root, case_id)
    _rewrite_blob_figures(case_id, bundle, uploads)
    _rewrite_blob_reports(case_id, bundle, uploads, product_demo_case_dir)
    return bundle


def _rewrite_blob_figures(case_id: str, bundle: dict[str, Any], uploads: dict[str, BlobUpload]) -> None:
    figures = bundle.get("figures")
    if not isinstance(figures, list):
        return
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        filename = str(figure.get("file") or "")
        if not filename:
            continue
        relative_path = f"product_demo/{case_id}/{DIRECTORIES['figures']}/{filename}"
        upload = uploads.get(relative_path)
        if upload and upload.url:
            figure["url"] = upload.url


def _rewrite_blob_reports(case_id: str, bundle: dict[str, Any], uploads: dict[str, BlobUpload], product_demo_case_dir: Path) -> None:
    reports = bundle.get("reports")
    if not isinstance(reports, list):
        return
    for report in reports:
        if not isinstance(report, dict):
            continue
        filename = str(report.get("file") or report.get("name") or "")
        if not filename:
            continue
        relative_path = f"product_demo/{case_id}/{DIRECTORIES['report']}/{filename}"
        upload = uploads.get(relative_path)
        if upload and upload.url:
            report["url"] = upload.url
        report_path = product_demo_case_dir / DIRECTORIES["report"] / filename
        if report_path.exists() and report_path.is_file():
            report["content"] = report_path.read_text(encoding="utf-8")


def _validate_blob_relative_path(relative_path: str) -> str:
    candidate = Path(relative_path)
    if not relative_path or candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(status_code=400, detail="invalid blob path")
    return candidate.as_posix()


def _validate_asset_path(asset_path: str) -> str:
    value = _validate_blob_relative_path(asset_path)
    if Path(value).suffix.lower() not in ALLOWED_ASSET_EXTENSIONS:
        raise HTTPException(status_code=400, detail="invalid asset extension")
    return value


def _content_type_for_path(path: Path) -> str:
    if path.suffix.lower() == ".md":
        return "text/markdown; charset=utf-8"
    if path.suffix.lower() in {".json", ".csv", ".txt"}:
        guessed = mimetypes.guess_type(path.name)[0] or "text/plain"
        return f"{guessed}; charset=utf-8"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
