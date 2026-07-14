from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable, Protocol


@dataclass(frozen=True)
class ArtifactRef:
    uri: str
    key: str
    size_bytes: int
    sha256: str


class ArtifactStoreError(ValueError):
    pass


class InvalidArtifactKey(ArtifactStoreError):
    pass


class ArtifactSourceError(ArtifactStoreError):
    pass


class ArtifactAlreadyExists(ArtifactStoreError):
    pass


class ArtifactIntegrityError(ArtifactStoreError):
    pass


class ArtifactStore(Protocol):
    def put_bytes(self, key: str, data: bytes) -> ArtifactRef: ...

    def put_file(self, key: str, source: Path) -> ArtifactRef: ...

    def publish_directory(self, prefix: str, source: Path) -> list[ArtifactRef]: ...

    def resolve(self, ref: ArtifactRef) -> Path: ...

    def exists(self, ref: ArtifactRef) -> bool: ...


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, data: bytes) -> ArtifactRef:
        return self._publish_file(key, lambda handle: handle.write(data))

    def put_file(self, key: str, source: Path) -> ArtifactRef:
        source = source.resolve()
        if not source.exists() or not source.is_file() or source.is_symlink():
            raise ArtifactSourceError(f"artifact source is not a regular file: {source}")

        def copy_source(handle: BinaryIO) -> None:
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)

        return self._publish_file(key, copy_source)

    def publish_directory(self, prefix: str, source: Path) -> list[ArtifactRef]:
        normalized_prefix = self._normalize_key(prefix)
        source = source.resolve()
        if not source.exists() or not source.is_dir() or source.is_symlink():
            raise ArtifactSourceError(f"artifact source is not a regular directory: {source}")

        files = self._validated_source_files(source, normalized_prefix)
        destination = self._resolve_key(normalized_prefix)
        if destination.exists():
            raise ArtifactAlreadyExists(f"artifact prefix already exists: {normalized_prefix}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".artifact-staging-", dir=destination.parent)).resolve()
        self._require_under_root(staging)
        try:
            for source_file, relative in files:
                staging_file = staging.joinpath(*relative.parts)
                staging_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, staging_file)
            if destination.exists():
                raise ArtifactAlreadyExists(f"artifact prefix already exists: {normalized_prefix}")
            os.rename(staging, destination)
        except Exception:
            if staging.exists():
                self._require_under_root(staging)
                shutil.rmtree(staging)
            raise

        return [
            self._build_ref(
                f"{normalized_prefix}/{relative.as_posix()}",
                destination.joinpath(*relative.parts),
            )
            for _, relative in files
        ]

    def resolve(self, ref: ArtifactRef) -> Path:
        path = self._resolve_key(ref.key)
        if not path.exists() or not path.is_file():
            raise ArtifactSourceError(f"artifact does not exist: {ref.key}")
        if path.stat().st_size != ref.size_bytes or self._sha256(path) != ref.sha256:
            raise ArtifactIntegrityError(f"artifact integrity check failed: {ref.key}")
        return path

    def exists(self, ref: ArtifactRef) -> bool:
        try:
            self.resolve(ref)
        except (ArtifactSourceError, ArtifactIntegrityError, InvalidArtifactKey):
            return False
        return True

    def ref_from_uri(self, uri: str, expected_sha256: str | None = None) -> ArtifactRef:
        prefix = "artifact://"
        if not isinstance(uri, str) or not uri.startswith(prefix):
            raise InvalidArtifactKey(f"invalid artifact URI: {uri!r}")
        key = self._normalize_key(uri.removeprefix(prefix))
        path = self._resolve_key(key)
        if not path.is_file():
            raise ArtifactSourceError(f"artifact does not exist: {key}")
        ref = self._build_ref(key, path)
        if expected_sha256 is not None and ref.sha256 != expected_sha256:
            raise ArtifactIntegrityError(f"artifact checksum does not match evidence: {key}")
        return ref

    def _publish_file(self, key: str, writer: Callable[[BinaryIO], object]) -> ArtifactRef:
        normalized = self._normalize_key(key)
        destination = self._resolve_key(normalized)
        if destination.exists():
            raise ArtifactAlreadyExists(f"artifact already exists: {normalized}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                writer(handle)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise ArtifactAlreadyExists(f"artifact already exists: {normalized}") from exc
        finally:
            temporary.unlink(missing_ok=True)

        return self._build_ref(normalized, destination)

    def _validated_source_files(self, source: Path, prefix: str) -> list[tuple[Path, PurePosixPath]]:
        files: list[tuple[Path, PurePosixPath]] = []
        for entry in source.rglob("*"):
            if entry.is_symlink():
                raise ArtifactSourceError(f"artifact directories cannot contain symlinks: {entry}")
            if entry.is_dir():
                continue
            if not entry.is_file():
                raise ArtifactSourceError(f"artifact source contains a non-file entry: {entry}")
            relative = PurePosixPath(entry.relative_to(source).as_posix())
            self._normalize_key(f"{prefix}/{relative.as_posix()}")
            files.append((entry, relative))
        return sorted(files, key=lambda item: item[1].as_posix())

    def _normalize_key(self, key: str) -> str:
        value = key.strip() if isinstance(key, str) else ""
        if not value or value == "." or "\\" in value or ":" in value:
            raise InvalidArtifactKey(f"invalid artifact key: {key!r}")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise InvalidArtifactKey(f"invalid artifact key: {key!r}")
        return path.as_posix()

    def _resolve_key(self, key: str) -> Path:
        normalized = self._normalize_key(key)
        path = self.root.joinpath(*PurePosixPath(normalized).parts).resolve()
        self._require_under_root(path)
        return path

    def _require_under_root(self, path: Path) -> None:
        if path == self.root or self.root not in path.parents:
            raise InvalidArtifactKey(f"artifact path escapes storage root: {path}")

    def _build_ref(self, key: str, path: Path) -> ArtifactRef:
        return ArtifactRef(
            uri=f"artifact://{key}",
            key=key,
            size_bytes=path.stat().st_size,
            sha256=self._sha256(path),
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
