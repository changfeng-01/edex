from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import Request

from goa_eval.product.analysis_service import AnalysisService
from goa_eval.product.artifact_store import ArtifactRef, LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.input_service import InputService
from goa_eval.product.comparison_service import ComparisonService
from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.job_runner import ProductJobRunner
from goa_eval.product.pia_experiment_adapter import PiaExperimentAdapter
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.product.settings import ProductSettings
from goa_eval.product.simulation_job_service import SimulationJobService
from goa_eval.product.simulator_registry import SimulatorRegistry, build_default_simulator_registry


@dataclass
class ProductContainer:
    settings: ProductSettings
    repository: SqlAlchemyProductRepository
    artifact_store: LocalArtifactStore
    project_service: ProjectService
    input_service: InputService
    analysis_service: AnalysisService
    experiment_service: ExperimentService
    simulation_job_service: SimulationJobService
    comparison_service: ComparisonService
    simulator_registry: SimulatorRegistry
    job_runner: ProductJobRunner

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
        project_service = ProjectService(repository, artifact_store)
        simulator_registry = build_default_simulator_registry()
        pia_adapter = PiaExperimentAdapter(repository, artifact_store)
        return cls(
            settings=settings,
            repository=repository,
            artifact_store=artifact_store,
            project_service=project_service,
            input_service=InputService(repository, artifact_store),
            analysis_service=AnalysisService(repository, artifact_store),
            experiment_service=ExperimentService(repository, pia_adapter=pia_adapter),
            simulation_job_service=SimulationJobService(
                repository,
                artifact_store,
                project_service,
                simulator_registry,
            ),
            comparison_service=ComparisonService(repository, artifact_store),
            simulator_registry=simulator_registry,
            job_runner=ProductJobRunner(repository, artifact_store, simulator_registry, settings),
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
