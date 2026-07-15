from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from goa_eval.product_api.dependencies import ProductContainer, default_container
from goa_eval.product_api.errors import (
    ProductApiError,
    product_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from goa_eval.product_api.routes import analyses, comparisons, experiments, inputs, profiles, projects, simulation_jobs, workspaces


def create_product_app(container: ProductContainer | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.product_container is None:
            app.state.product_container = default_container()
        yield

    product_app = FastAPI(title="CircuitPilot Product API", version="1.0", lifespan=lifespan)
    product_app.state.product_container = container
    product_app.add_exception_handler(ProductApiError, product_error_handler)
    product_app.add_exception_handler(RequestValidationError, validation_error_handler)
    product_app.add_exception_handler(Exception, unexpected_error_handler)
    product_app.include_router(workspaces.router)
    product_app.include_router(profiles.router)
    product_app.include_router(projects.router)
    product_app.include_router(inputs.router)
    product_app.include_router(analyses.router)
    product_app.include_router(experiments.router)
    product_app.include_router(simulation_jobs.router)
    product_app.include_router(comparisons.router)
    return product_app


app = create_product_app()
