"""ASGI application factory for the sample service."""

from fastapi import FastAPI

from sample_service.api.routers import health


def create_app() -> FastAPI:
    """ASGI factory: `uvicorn --factory sample_service.bootstrap.app:create_app`."""
    app = FastAPI(title="Sample Service")
    app.include_router(health.router)
    return app
