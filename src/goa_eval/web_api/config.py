from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class DashboardApiSettings(BaseModel):
    product_demo_root: Path = Field(default=Path("outputs/product_demo"))
    enable_build_api: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    @classmethod
    def from_env(cls) -> "DashboardApiSettings":
        root = Path(os.getenv("CIRCUITPILOT_PRODUCT_DEMO_ROOT", "outputs/product_demo"))
        origins = [
            origin.strip()
            for origin in os.getenv(
                "CIRCUITPILOT_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]
        return cls(
            product_demo_root=root,
            enable_build_api=_env_bool(os.getenv("CIRCUITPILOT_ENABLE_BUILD_API")),
            cors_origins=origins,
        )


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}

