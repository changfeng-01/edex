from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from goa_eval.circuit_profiles import (
    DEFAULT_CIRCUIT_PROFILE_PATH,
    load_circuit_profiles,
    resolve_circuit_profile,
    validate_profile_references,
)
from goa_eval.parameter_semantics import DEFAULT_PARAMETER_SEMANTICS_PATH, load_parameter_semantics
from goa_eval.product.artifact_store import ArtifactAlreadyExists, ArtifactStore
from goa_eval.product_demo.schemas import normalize_evidence_boundary


class ProfileServiceError(ValueError):
    pass


class ProfileNotFoundError(ProfileServiceError):
    pass


class ProfileValidationError(ProfileServiceError):
    pass


class ProfileService:
    """Read-only, artifact-backed circuit profile revision service."""

    def __init__(
        self,
        artifact_store: ArtifactStore,
        *,
        profile_path: Path = DEFAULT_CIRCUIT_PROFILE_PATH,
        semantics_path: Path = DEFAULT_PARAMETER_SEMANTICS_PATH,
    ) -> None:
        self.artifact_store = artifact_store
        self._profile_path = Path(profile_path)
        self._semantics_path = Path(semantics_path)

    def list_profiles(self) -> list[dict[str, Any]]:
        profiles = self._validated_profiles()
        return [self._freeze_revision(name, profile) for name, profile in sorted(profiles.items())]

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        profiles = self._validated_profiles()
        wanted = _normalize_identifier(profile_id)
        matches = {
            _normalize_identifier(alias): name
            for name, profile in profiles.items()
            for alias in (name, *(profile.get("aliases", []) or []))
        }
        profile_name = matches.get(wanted)
        if not wanted or profile_name is None:
            raise ProfileNotFoundError(f"circuit profile was not found: {profile_id}")
        return self._freeze_revision(profile_name, resolve_circuit_profile(profile_name, profiles))

    def validate(self) -> dict[str, Any]:
        try:
            revisions = self.list_profiles()
        except ValueError as exc:
            return {"valid": False, "errors": [str(exc)], "profiles": []}
        return {
            "valid": True,
            "errors": [],
            "profiles": [
                {"profile_id": item["profile_id"], "revision_id": item["revision_id"]}
                for item in revisions
            ],
        }

    def _validated_profiles(self) -> dict[str, dict[str, Any]]:
        try:
            profiles = load_circuit_profiles(self._profile_path)
            validate_profile_references(
                profile_file=self._profile_path,
                semantics_file=self._semantics_path,
            )
        except ValueError as exc:
            raise ProfileValidationError(str(exc)) from exc
        return profiles

    def _freeze_revision(self, profile_name: str, profile: Mapping[str, Any]) -> dict[str, Any]:
        normalized_profile = _json_mapping(profile)
        normalized_profile.pop("profile_source", None)
        normalized_profile["name"] = profile_name
        normalized_profile["boundary"] = normalize_evidence_boundary(normalized_profile.get("boundary"))
        semantics = load_parameter_semantics(self._semantics_path)
        source_hash = _sha256_json(normalized_profile)
        semantics_hash = _sha256_json(semantics)
        revision_id = f"profile_{_sha256_bytes(f'{source_hash}:{semantics_hash}'.encode('ascii'))[:24]}"
        required_analyses = sorted(
            {_normalize_identifier(item) for item in normalized_profile.get("required_analyses", []) or []}
        )
        supported_analyses = sorted(
            {
                *required_analyses,
                *{
                    _normalize_identifier(item)
                    for item in normalized_profile.get("optional_analyses", []) or []
                },
            }
        )
        metrics = normalized_profile.get("metrics", {}) or {}
        required_metrics = sorted(
            metric
            for metric, rule in metrics.items()
            if not required_analyses
            or _normalize_identifier(rule.get("source_analysis")) in required_analyses
        )
        frozen = {
            "schema_version": "1.0",
            "profile_id": profile_name,
            "revision_id": revision_id,
            "source_hash": source_hash,
            "semantics_hash": semantics_hash,
            "supported_analyses": supported_analyses,
            "required_metrics": required_metrics,
            "node_rules": _json_mapping(normalized_profile.get("node_rules", {})),
            "units": {metric: str(rule.get("unit", "")) for metric, rule in sorted(metrics.items())},
            "validation": {"valid": True, "errors": []},
            "boundary": normalized_profile["boundary"],
            "profile": normalized_profile,
        }
        payload = _canonical_json(frozen)
        key = f"profiles/{profile_name}/{revision_id}.json"
        try:
            ref = self.artifact_store.put_bytes(key, payload)
        except ArtifactAlreadyExists:
            resolver = getattr(self.artifact_store, "ref_from_uri", None)
            if resolver is None:
                raise
            ref = resolver(f"artifact://{key}")
        return {
            **frozen,
            "snapshot_ref": {
                "uri": ref.uri,
                "key": ref.key,
                "size_bytes": ref.size_bytes,
                "sha256": ref.sha256,
            },
        }


def _json_mapping(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return json.loads(json.dumps(dict(value), sort_keys=True, ensure_ascii=False))


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_json(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_json(value))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_identifier(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")
