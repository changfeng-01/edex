import hashlib
from pathlib import Path

import pytest

from goa_eval.product.artifact_store import (
    ArtifactAlreadyExists,
    ArtifactRef,
    ArtifactSourceError,
    InvalidArtifactKey,
    LocalArtifactStore,
)


def test_put_bytes_returns_resolvable_content_addressed_reference(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    payload = b"t,v\n0,0\n"

    ref = store.put_bytes(
        "workspace_a/project_a/inputs/input_a/waveform.csv",
        payload,
    )

    assert ref.uri == "artifact://workspace_a/project_a/inputs/input_a/waveform.csv"
    assert ref.size_bytes == len(payload)
    assert ref.sha256 == hashlib.sha256(payload).hexdigest()
    assert store.resolve(ref).read_bytes() == payload
    assert store.exists(ref) is True


def test_put_file_copies_source_without_modifying_it(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    source = tmp_path / "source.csv"
    source.write_text("time,v\n0,1\n", encoding="utf-8")

    ref = store.put_file("workspace_a/project_a/inputs/source.csv", source)

    assert store.resolve(ref).read_text(encoding="utf-8") == "time,v\n0,1\n"
    assert source.read_text(encoding="utf-8") == "time,v\n0,1\n"


@pytest.mark.parametrize(
    "key",
    ["", ".", "../escape.csv", "/absolute.csv", "C:/escape.csv", "workspace\\escape.csv"],
)
def test_put_bytes_rejects_unsafe_keys(tmp_path: Path, key: str):
    store = LocalArtifactStore(tmp_path / "artifacts")

    with pytest.raises(InvalidArtifactKey):
        store.put_bytes(key, b"unsafe")

    assert not (tmp_path / "escape.csv").exists()


def test_resolve_revalidates_reference_key(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    forged = ArtifactRef(
        uri="artifact://../escape.csv",
        key="../escape.csv",
        size_bytes=0,
        sha256=hashlib.sha256(b"").hexdigest(),
    )

    with pytest.raises(InvalidArtifactKey):
        store.resolve(forged)


def test_publish_directory_preserves_nested_files_and_returns_refs(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    source = tmp_path / "bundle"
    (source / "figures").mkdir(parents=True)
    (source / "summary.json").write_text('{"status":"ok"}', encoding="utf-8")
    (source / "figures" / "plot.txt").write_text("figure", encoding="utf-8")

    refs = store.publish_directory("workspace_a/project_a/runs/run_a", source)

    assert [ref.key for ref in refs] == [
        "workspace_a/project_a/runs/run_a/figures/plot.txt",
        "workspace_a/project_a/runs/run_a/summary.json",
    ]
    assert all(store.exists(ref) for ref in refs)
    assert store.resolve(refs[0]).read_text(encoding="utf-8") == "figure"


def test_publish_directory_refuses_existing_prefix_without_deleting_data(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    existing = store.put_bytes("workspace_a/project_a/runs/run_a/keep.txt", b"existing")
    unrelated = store.put_bytes("workspace_a/project_b/keep.txt", b"unrelated")
    source = tmp_path / "bundle"
    source.mkdir()
    (source / "new.txt").write_text("new", encoding="utf-8")

    with pytest.raises(ArtifactAlreadyExists):
        store.publish_directory("workspace_a/project_a/runs/run_a", source)

    assert store.resolve(existing).read_bytes() == b"existing"
    assert store.resolve(unrelated).read_bytes() == b"unrelated"
    assert not (store.root / "workspace_a/project_a/runs/run_a/new.txt").exists()


def test_publish_directory_validates_source_before_creating_destination(tmp_path: Path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    missing = tmp_path / "missing"

    with pytest.raises(ArtifactSourceError):
        store.publish_directory("workspace_a/project_a/runs/run_a", missing)

    assert not (store.root / "workspace_a/project_a/runs/run_a").exists()
