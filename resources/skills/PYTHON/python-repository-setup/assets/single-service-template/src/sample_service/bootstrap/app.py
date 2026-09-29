from fastapi import FastAPI

from sample_service.api.routes import router


def create_app() -> FastAPI:
    """ASGI factory: `uvicorn --factory sample_service.bootstrap.app:create_app`."""
    app = FastAPI(title="Sample Service")
    app.include_router(router)
    return app
