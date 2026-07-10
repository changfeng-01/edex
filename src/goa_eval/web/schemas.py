from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from goa_eval.product_demo.schemas import (
    DATA_SOURCE,
    ENGINEERING_VALIDITY,
    MUST_RESIMULATE,
    default_evidence_boundary,
)


def evidence_boundary() -> dict[str, Any]:
    return default_evidence_boundary()


class WebApiSettings(BaseModel):
    web_cases_root: Path = Field(default=Path("outputs/web_cases"))
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    blob_storage_enabled: bool = False
    write_api_key: str | None = None
    require_write_auth: bool = False
    max_waveform_bytes: int = 64 * 1024 * 1024
    max_netlist_bytes: int = 64 * 1024 * 1024
    max_param_bytes: int = 2 * 1024 * 1024
    max_image_bytes: int = 16 * 1024 * 1024
    max_request_bytes: int = 128 * 1024 * 1024
    max_attachments: int = 10

    @classmethod
    def from_env(cls) -> "WebApiSettings":
        root = Path(os.getenv("CIRCUITPILOT_WEB_CASES_ROOT", "outputs/web_cases"))
        origins = [
            origin.strip()
            for origin in os.getenv(
                "CIRCUITPILOT_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]
        blob_storage_enabled = bool(os.getenv("BLOB_READ_WRITE_TOKEN"))
        return cls(
            web_cases_root=root,
            cors_origins=origins,
            blob_storage_enabled=blob_storage_enabled,
            write_api_key=os.getenv("CIRCUITPILOT_WRITE_API_KEY") or None,
            require_write_auth=_env_bool("CIRCUITPILOT_REQUIRE_WRITE_AUTH", False),
            max_waveform_bytes=_env_int("CIRCUITPILOT_MAX_WAVEFORM_BYTES", 64 * 1024 * 1024),
            max_netlist_bytes=_env_int("CIRCUITPILOT_MAX_NETLIST_BYTES", 64 * 1024 * 1024),
            max_param_bytes=_env_int("CIRCUITPILOT_MAX_PARAM_BYTES", 2 * 1024 * 1024),
            max_image_bytes=_env_int("CIRCUITPILOT_MAX_IMAGE_BYTES", 16 * 1024 * 1024),
            max_request_bytes=_env_int("CIRCUITPILOT_MAX_REQUEST_BYTES", 128 * 1024 * 1024),
            max_attachments=_env_int("CIRCUITPILOT_MAX_ATTACHMENTS", 10),
        )


class UploadedCaseConfig(BaseModel):
    case_id: str
    circuit_profile: str | None = None
    topology: str | None = None
    stage_count: int | None = None
    output_node_pattern: str = "o{index}"
    generate_candidates: bool = True
    run_llm_analysis: bool = False


class CaseRunResult(BaseModel):
    case_id: str
    status: str
    case_dir: str
    input_dir: str
    analysis_dir: str
    product_demo_case_dir: str | None = None
    bundle_url: str | None = None
    error: str | None = None
    evidence_boundary: dict[str, Any] = Field(default_factory=evidence_boundary)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)

