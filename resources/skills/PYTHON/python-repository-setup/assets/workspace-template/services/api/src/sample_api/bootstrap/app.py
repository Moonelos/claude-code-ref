"""ASGI application factory for the sample API."""

from fastapi import FastAPI

from sample_api.api.routers import greetings, health


def create_app() -> FastAPI:
    """ASGI factory: `uvicorn --factory sample_api.bootstrap.app:create_app`."""
    app = FastAPI(title="Sample API")
    app.include_router(health.router)
    app.include_router(greetings.router)
    return app
