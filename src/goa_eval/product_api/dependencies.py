from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import Request

from goa_eval.product.analysis_service import AnalysisService
from goa_eval.product.artifact_store import ArtifactRef, LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.input_service import InputService
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.product.settings import ProductSettings


@dataclass
class ProductContainer:
    settings: ProductSettings
    repository: SqlAlchemyProductRepository
    artifact_store: LocalArtifactStore
    project_service: ProjectService
    input_service: InputService
    analysis_service: AnalysisService

    @classmethod
    def from_settings(
        cls,
        settings: ProductSettings,
        *,
        create_tables: bool = False,
    ) -> "ProductContainer":
        engine = make_engine(settings.database_url)
        if create_tables:
            create_schema(engine)
        repository = SqlAlchemyProductRepository(engine)
        artifact_store = LocalArtifactStore(settings.artifact_root)
        return cls(
            settings=settings,
            repository=repository,
            artifact_store=artifact_store,
            project_service=ProjectService(repository, artifact_store),
            input_service=InputService(repository, artifact_store),
            analysis_service=AnalysisService(repository, artifact_store),
        )

    def ref_from_uri(self, uri: str, checksum: str) -> ArtifactRef:
        prefix = "artifact://"
        if not uri.startswith(prefix):
            raise ValueError("artifact URI is invalid")
        key = PurePosixPath(uri.removeprefix(prefix)).as_posix()
        path = self.artifact_store.root.joinpath(*PurePosixPath(key).parts).resolve()
        root = self.artifact_store.root
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(uri)
        return ArtifactRef(uri=uri, key=key, size_bytes=path.stat().st_size, sha256=checksum)


def get_container(request: Request) -> ProductContainer:
    container = getattr(request.app.state, "product_container", None)
    if container is None:
        raise RuntimeError("ProductContainer is not initialized")
    return container


def default_container() -> ProductContainer:
    settings = ProductSettings.from_env()
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    return ProductContainer.from_settings(settings, create_tables=True)
