from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from goa_eval.product.artifact_store import ArtifactRef, ArtifactStore
from goa_eval.product.models import InputPreviewStatus, new_id, utc_now_iso
from goa_eval.product.project_service import ProductNotFoundError
from goa_eval.product_demo.schemas import normalize_evidence_boundary
from goa_eval.web.input_inspector import inspect_uploaded_case_input
from goa_eval.web.schemas import UploadedCaseConfig


NETLIST_LOGICAL_NAMES = {
    "source_netlist.sp",
    "source_netlist.spice",
    "source_netlist.netlist",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


class InputServiceError(ValueError):
    pass


class InputPreviewFailed(InputServiceError):
    def __init__(self, preview: dict[str, Any]) -> None:
        super().__init__("input preview failed")
        self.preview = preview


@dataclass(frozen=True)
class InputFile:
    logical_name: str
    source_path: Path


@dataclass(frozen=True)
class InputSnapshotResult:
    input_snapshot_id: str
    design_version_id: str
    preview_status: str
    manifest_ref: ArtifactRef
    preview: dict[str, Any]


class InputService:
    def __init__(self, repository: Any, artifact_store: ArtifactStore) -> None:
        self._repository = repository
        self._artifact_store = artifact_store

    def create_input_snapshot(
        self,
        *,
        design_version_id: str,
        files: list[InputFile],
        preview_config: UploadedCaseConfig | None = None,
    ) -> InputSnapshotResult:
        version = self._repository.get_design_version(design_version_id)
        if version is None:
            raise ProductNotFoundError(f"design version was not found: {design_version_id}")
        project = self._repository.get_project(version.project_id)
        if project is None:
            raise ProductNotFoundError(f"project was not found: {version.project_id}")

        validated = self._validate_files(files)
        input_snapshot_id = new_id("input")
        prefix = (
            f"workspaces/{project.workspace_id}/projects/{project.project_id}/"
            f"design_versions/{design_version_id}/inputs/{input_snapshot_id}"
        )

        with TemporaryDirectory(prefix="circuitpilot-input-") as temporary_name:
            case_dir = Path(temporary_name)
            input_dir = case_dir / "input"
            input_dir.mkdir(parents=True)
            for logical_name, source in validated:
                destination = input_dir.joinpath(*PurePosixPath(logical_name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)

            preview = inspect_uploaded_case_input(case_dir, preview_config)
            if not preview.get("ready_for_analysis", False):
                raise InputPreviewFailed(preview)
            preview_status = (
                InputPreviewStatus.READY_WITH_WARNINGS
                if preview.get("warnings")
                else InputPreviewStatus.READY
            )
            manifest = {
                "input_snapshot_id": input_snapshot_id,
                "design_version_id": design_version_id,
                "profile_revision_id": self._profile_revision_id(project.project_id, project.circuit_profile_id),
                "created_at": utc_now_iso(),
                "preview_status": preview_status.value,
                "preview": preview,
                "evidence_boundary": normalize_evidence_boundary(),
                "files": self._manifest_files(prefix, input_dir, validated),
            }
            (case_dir / "input_manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            refs = self._artifact_store.publish_directory(prefix, case_dir)

        manifest_key = f"{prefix}/input_manifest.json"
        manifest_ref = next(ref for ref in refs if ref.key == manifest_key)
        return InputSnapshotResult(
            input_snapshot_id=input_snapshot_id,
            design_version_id=design_version_id,
            preview_status=preview_status.value,
            manifest_ref=manifest_ref,
            preview=preview,
        )

    @staticmethod
    def _validate_files(files: list[InputFile]) -> list[tuple[str, Path]]:
        validated: list[tuple[str, Path]] = []
        seen: set[str] = set()
        for item in files:
            logical_name = item.logical_name.strip()
            if logical_name in seen:
                raise ValueError(f"duplicate logical name: {logical_name}")
            if not _is_safe_logical_name(logical_name):
                raise ValueError(f"unsafe logical name: {logical_name}")
            if not _is_supported_logical_name(logical_name):
                raise ValueError(f"unsupported logical name: {logical_name}")
            source = Path(item.source_path).resolve()
            if not source.exists() or not source.is_file() or source.is_symlink():
                raise ValueError(f"input source is not a regular file: {item.source_path}")
            seen.add(logical_name)
            validated.append((logical_name, source))
        if "waveform.csv" not in seen:
            raise ValueError("waveform.csv is required")
        return sorted(validated, key=lambda item: item[0])

    @staticmethod
    def _manifest_files(
        prefix: str,
        input_dir: Path,
        files: list[tuple[str, Path]],
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for logical_name, _ in files:
            staged = input_dir.joinpath(*PurePosixPath(logical_name).parts)
            entries.append(
                {
                    "logical_name": logical_name,
                    "artifact_uri": f"artifact://{prefix}/input/{logical_name}",
                    "size_bytes": staged.stat().st_size,
                    "sha256": _sha256(staged),
                    "display_only": logical_name.startswith("attachments/"),
                }
            )
        return entries

    def _profile_revision_id(self, project_id: str, fallback: str) -> str:
        evidence = self._repository.list_evidence("project", project_id)
        profile = next((record for record in evidence if record.evidence_type == "profile_snapshot"), None)
        return profile.source_ref if profile else fallback


def _is_safe_logical_name(logical_name: str) -> bool:
    if not logical_name or "\\" in logical_name or ":" in logical_name:
        return False
    path = PurePosixPath(logical_name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _is_supported_logical_name(logical_name: str) -> bool:
    if logical_name in {"waveform.csv", "params.yaml", *NETLIST_LOGICAL_NAMES}:
        return True
    path = PurePosixPath(logical_name)
    return (
        len(path.parts) == 2
        and path.parts[0] == "attachments"
        and Path(path.name).suffix.lower() in IMAGE_EXTENSIONS
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
