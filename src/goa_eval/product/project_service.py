from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from goa_eval.parameter_semantics import DEFAULT_PARAMETER_SEMANTICS_PATH
from goa_eval.product.artifact_store import ArtifactRef, ArtifactStore
from goa_eval.product.models import (
    AuditEventRecord,
    DesignVersionRecord,
    EvidenceBoundary,
    EvidenceRecord,
    ProjectOverview,
    ProjectRecord,
    WorkspaceRecord,
    new_id,
)
from goa_eval.product_demo.schemas import normalize_evidence_boundary
from goa_eval.product.profile_service import ProfileService, ProfileServiceError


class ProjectServiceError(ValueError):
    pass


class ProductNotFoundError(ProjectServiceError):
    pass


class InvalidCircuitProfile(ProjectServiceError):
    pass


@dataclass(frozen=True)
class ProjectCreationResult:
    project: ProjectRecord
    profile_snapshot: ArtifactRef
    spec_snapshot: ArtifactRef
    evidence: tuple[EvidenceRecord, ...]


class ProjectService:
    def __init__(
        self,
        repository: Any,
        artifact_store: ArtifactStore,
        *,
        circuit_profile_path: Path = Path("config/circuit_profiles.yaml"),
        parameter_semantics_path: Path = DEFAULT_PARAMETER_SEMANTICS_PATH,
        default_spec_path: Path = Path("config/spec.yaml"),
        profile_service: ProfileService | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._circuit_profile_path = Path(circuit_profile_path)
        self._default_spec_path = Path(default_spec_path)
        self._profile_service = profile_service or ProfileService(
            artifact_store,
            profile_path=self._circuit_profile_path,
            semantics_path=parameter_semantics_path,
        )

    def create_workspace(self, name: str, actor_id: str = "user_local") -> WorkspaceRecord:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("workspace name is required")
        workspace = WorkspaceRecord(workspace_id=new_id("workspace"), name=normalized_name)
        self._repository.add_workspace(workspace)
        self._repository.append_audit_event(
            AuditEventRecord(
                event_id=new_id("event"),
                actor_id=actor_id,
                action="workspace.created",
                subject_type="workspace",
                subject_id=workspace.workspace_id,
                details={"name": workspace.name},
            )
        )
        return workspace

    def create_project(
        self,
        workspace_id: str,
        name: str,
        circuit_profile_id: str,
        spec_revision_id: str,
        spec_path: Path | None = None,
        actor_id: str = "user_local",
    ) -> ProjectCreationResult:
        if self._repository.get_workspace(workspace_id) is None:
            raise ProductNotFoundError(f"workspace was not found: {workspace_id}")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("project name is required")
        if not spec_revision_id.strip():
            raise ValueError("spec_revision_id is required")

        profile = self._resolve_profile(circuit_profile_id)
        spec = self._load_spec(spec_path or self._default_spec_path)
        project = ProjectRecord(
            project_id=new_id("project"),
            workspace_id=workspace_id,
            name=normalized_name,
            circuit_profile_id=str(profile["profile_id"]),
            spec_revision_id=spec_revision_id,
        )
        prefix = f"workspaces/{workspace_id}/projects/{project.project_id}/config"
        snapshot = profile["snapshot_ref"]
        profile_ref = ArtifactRef(
            uri=str(snapshot["uri"]),
            key=str(snapshot["key"]),
            size_bytes=int(snapshot["size_bytes"]),
            sha256=str(snapshot["sha256"]),
        )
        spec_ref = self._artifact_store.put_bytes(
            f"{prefix}/spec_snapshot.json",
            _canonical_json(spec),
        )

        self._repository.add_project(project)
        boundary = EvidenceBoundary()
        evidence = (
            EvidenceRecord(
                evidence_id=new_id("evidence"),
                subject_type="project",
                subject_id=project.project_id,
                evidence_type="profile_snapshot",
                source_ref=profile_ref.uri,
                checksum=profile_ref.sha256,
                boundary=boundary,
            ),
            EvidenceRecord(
                evidence_id=new_id("evidence"),
                subject_type="project",
                subject_id=project.project_id,
                evidence_type="spec_snapshot",
                source_ref=spec_ref.uri,
                checksum=spec_ref.sha256,
                boundary=boundary,
            ),
        )
        for record in evidence:
            self._repository.add_evidence(record)
        self._repository.append_audit_event(
            AuditEventRecord(
                event_id=new_id("event"),
                actor_id=actor_id,
                action="project.created",
                subject_type="project",
                subject_id=project.project_id,
                details={
                    "workspace_id": workspace_id,
                    "circuit_profile_id": project.circuit_profile_id,
                    "profile_snapshot": profile_ref.uri,
                    "spec_snapshot": spec_ref.uri,
                },
            )
        )
        return ProjectCreationResult(
            project=project,
            profile_snapshot=profile_ref,
            spec_snapshot=spec_ref,
            evidence=evidence,
        )

    def create_design_version(
        self,
        project_id: str,
        label: str,
        parameter_set_ref: str | None = None,
        netlist_ref: str | None = None,
        parent_version_id: str | None = None,
        source_candidate_id: str | None = None,
        actor_id: str = "user_local",
    ) -> DesignVersionRecord:
        if self._repository.get_project(project_id) is None:
            raise ProductNotFoundError(f"project was not found: {project_id}")
        if parent_version_id is not None:
            parent = self._repository.get_design_version(parent_version_id)
            if parent is None:
                raise ProductNotFoundError(f"design version was not found: {parent_version_id}")
            if parent.project_id != project_id:
                raise ValueError("parent design version must belong to the same project")
        normalized_label = label.strip()
        if not normalized_label:
            raise ValueError("design version label is required")

        version = DesignVersionRecord(
            design_version_id=new_id("version"),
            project_id=project_id,
            label=normalized_label,
            parameter_set_ref=parameter_set_ref,
            netlist_ref=netlist_ref,
            parent_version_id=parent_version_id,
            source_candidate_id=source_candidate_id,
        )
        self._repository.add_design_version(version)
        self._repository.append_audit_event(
            AuditEventRecord(
                event_id=new_id("event"),
                actor_id=actor_id,
                action="design_version.created",
                subject_type="design_version",
                subject_id=version.design_version_id,
                details={"project_id": project_id, "parent_version_id": parent_version_id},
            )
        )
        return version

    def get_project_overview(self, project_id: str) -> ProjectOverview:
        project = self._repository.get_project(project_id)
        if project is None:
            raise ProductNotFoundError(f"project was not found: {project_id}")
        versions = tuple(self._repository.list_design_versions(project_id))
        runs = self._repository.list_analysis_runs(project_id=project_id)
        latest = self._repository.get_latest_analysis_run(project_id)
        evidence = self._repository.list_evidence("project", project_id)
        return ProjectOverview(
            project=project,
            design_versions=versions,
            version_count=len(versions),
            analysis_count=len(runs),
            latest_analysis_run=latest,
            latest_analysis_status=latest.status if latest else None,
            evidence_count=len(evidence),
            evidence_types=tuple(record.evidence_type for record in evidence),
        )

    def _resolve_profile(self, circuit_profile_id: str) -> dict[str, Any]:
        if not _normalized_identifier(circuit_profile_id):
            raise InvalidCircuitProfile("circuit profile is required")
        try:
            return self._profile_service.get_profile(circuit_profile_id)
        except ProfileServiceError as exc:
            raise InvalidCircuitProfile(str(exc)) from exc

    @staticmethod
    def _load_spec(path: Path) -> dict[str, Any]:
        source = Path(path)
        if not source.exists() or not source.is_file():
            raise ProductNotFoundError(f"spec was not found: {source}")
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, Mapping):
            raise ValueError("spec must contain a mapping")
        normalized = _normalized_mapping(raw)
        normalized["evidence_boundary"] = normalize_evidence_boundary()
        return _normalized_mapping(normalized)


def _normalized_identifier(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _normalized_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), sort_keys=True, ensure_ascii=False))


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
