from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_PROFILE_PATH = Path("config/eval_profiles.yaml")


def load_eval_profiles(path: Path = DEFAULT_PROFILE_PATH) -> dict:
    if not path.exists():
        return _builtin_profiles()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = raw.get("profiles", raw)
    if "default" not in profiles:
        profiles["default"] = _builtin_profiles()["default"]
    return profiles


def resolve_topology_profile(topology: str | None, profiles: dict | None = None) -> dict:
    profiles = profiles or load_eval_profiles()
    normalized = _normalize(topology)
    for name, profile in profiles.items():
        aliases = [_normalize(name), *[_normalize(alias) for alias in profile.get("aliases", [])]]
        if normalized in aliases:
            return {"name": name, **profile}
    default = profiles.get("default", _builtin_profiles()["default"])
    return {"name": "default", **default}


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _builtin_profiles() -> dict:
    return {
        "default": {
            "aliases": [],
            "weights": {
                "function_score": 0.35,
                "quality_score": 0.25,
                "stability_score": 0.15,
                "consistency_score": 0.15,
                "cost_score": 0.10,
            },
            "metrics": {},
        }
    }
