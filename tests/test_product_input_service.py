import hashlib
import json
from pathlib import Path

import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.input_service import InputFile, InputPreviewFailed, InputService
from goa_eval.product.project_service import ProductNotFoundError, ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.web.schemas import UploadedCaseConfig


@pytest.fixture
def input_context(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    project_service = ProjectService(repository, artifact_store)
    workspace = project_service.create_workspace("GOA team")
    project_result = project_service.create_project(
        workspace.workspace_id,
        "GOA",
        "goa_8k",
        "spec_v1",
    )
    version = project_service.create_design_version(project_result.project.project_id, "baseline")
    return InputService(repository, artifact_store), repository, artifact_store, version


def test_create_input_snapshot_from_public_sample(input_context):
    service, _, _, version = input_context

    result = service.create_input_snapshot(
        design_version_id=version.design_version_id,
        files=[
            InputFile("waveform.csv", Path("examples/sample_waveform.csv")),
            InputFile("params.yaml", Path("examples/sample_params.yaml")),
        ],
        preview_config=UploadedCaseConfig(case_id="preview"),
    )

    assert result.input_snapshot_id.startswith("input_")
    assert result.preview_status == "preview_ready"
    assert result.manifest_ref.uri.startswith("artifact://")
    assert result.preview["ready_for_analysis"] is True


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([InputFile("params.yaml", Path("examples/sample_params.yaml"))], "waveform.csv is required"),
        (
            [
                InputFile("waveform.csv", Path("examples/sample_waveform.csv")),
                InputFile("waveform.csv", Path("examples/sample_waveform.csv")),
            ],
            "duplicate logical name",
        ),
        ([InputFile("C:/waveform.csv", Path("examples/sample_waveform.csv"))], "unsafe logical name"),
        ([InputFile("notes.txt", Path("examples/sample_waveform.csv"))], "unsupported logical name"),
    ],
)
def test_input_files_are_strictly_validated(input_context, files, message):
    service, _, _, version = input_context

    with pytest.raises(ValueError, match=message):
        service.create_input_snapshot(
            design_version_id=version.design_version_id,
            files=files,
            preview_config=UploadedCaseConfig(case_id="preview"),
        )


def test_unknown_design_version_is_rejected(input_context):
    service, _, _, _ = input_context

    with pytest.raises(ProductNotFoundError, match="version_missing"):
        service.create_input_snapshot(
            design_version_id="version_missing",
            files=[InputFile("waveform.csv", Path("examples/sample_waveform.csv"))],
            preview_config=UploadedCaseConfig(case_id="preview"),
        )


def test_preview_failure_does_not_publish_snapshot(input_context, tmp_path: Path):
    service, _, artifact_store, version = input_context
    malformed = tmp_path / "malformed.csv"
    malformed.write_text("unsupported\n1\n2\n", encoding="utf-8")
    before = sorted(path.relative_to(artifact_store.root) for path in artifact_store.root.rglob("*") if path.is_file())

    with pytest.raises(InputPreviewFailed) as error:
        service.create_input_snapshot(
            design_version_id=version.design_version_id,
            files=[InputFile("waveform.csv", malformed)],
            preview_config=UploadedCaseConfig(case_id="preview"),
        )

    assert error.value.preview["ready_for_analysis"] is False
    after = sorted(path.relative_to(artifact_store.root) for path in artifact_store.root.rglob("*") if path.is_file())
    assert after == before


def test_warning_only_preview_is_published_with_warning_status(input_context, tmp_path: Path):
    service, _, _, version = input_context
    warning_waveform = tmp_path / "warning.csv"
    warning_waveform.write_text("time,signal\n0,0\n1,1\n", encoding="utf-8")

    result = service.create_input_snapshot(
        design_version_id=version.design_version_id,
        files=[InputFile("waveform.csv", warning_waveform)],
        preview_config=UploadedCaseConfig(case_id="preview"),
    )

    assert result.preview_status == "preview_ready_with_warnings"
    assert result.preview["ready_for_analysis"] is True
    assert result.preview["warnings"]


def test_image_attachment_remains_display_only(input_context, tmp_path: Path):
    service, _, artifact_store, version = input_context
    image = tmp_path / "plot.png"
    image.write_bytes(b"not-decoded-by-input-service")

    result = service.create_input_snapshot(
        design_version_id=version.design_version_id,
        files=[
            InputFile("waveform.csv", Path("examples/sample_waveform.csv")),
            InputFile("params.yaml", Path("examples/sample_params.yaml")),
            InputFile("attachments/plot.png", image),
        ],
        preview_config=UploadedCaseConfig(case_id="preview"),
    )
    manifest = json.loads(artifact_store.resolve(result.manifest_ref).read_text(encoding="utf-8"))

    assert result.preview["attachments_summary"]["image_count"] == 1
    assert result.preview["image_analysis_enabled"] is False
    image_entry = next(entry for entry in manifest["files"] if entry["logical_name"] == "attachments/plot.png")
    assert image_entry["display_only"] is True


def test_manifest_contains_immutable_file_refs_and_exact_boundary(input_context):
    service, _, artifact_store, version = input_context
    waveform = Path("examples/sample_waveform.csv")
    params = Path("examples/sample_params.yaml")
    waveform_before = waveform.read_bytes()
    params_before = params.read_bytes()

    result = service.create_input_snapshot(
        design_version_id=version.design_version_id,
        files=[InputFile("waveform.csv", waveform), InputFile("params.yaml", params)],
        preview_config=UploadedCaseConfig(case_id="preview"),
    )
    manifest = json.loads(artifact_store.resolve(result.manifest_ref).read_text(encoding="utf-8"))

    assert manifest["input_snapshot_id"] == result.input_snapshot_id
    assert manifest["design_version_id"] == version.design_version_id
    assert manifest["created_at"].endswith("+00:00")
    assert manifest["preview_status"] == "preview_ready"
    assert manifest["preview"] == result.preview
    assert manifest["profile_revision_id"].startswith("artifact://")
    assert manifest["evidence_boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }
    entries = {entry["logical_name"]: entry for entry in manifest["files"]}
    assert set(entries) == {"params.yaml", "waveform.csv"}
    for logical_name, source in (("waveform.csv", waveform), ("params.yaml", params)):
        entry = entries[logical_name]
        assert entry["artifact_uri"].startswith("artifact://")
        assert entry["size_bytes"] == source.stat().st_size
        assert entry["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert waveform.read_bytes() == waveform_before
    assert params.read_bytes() == params_before
