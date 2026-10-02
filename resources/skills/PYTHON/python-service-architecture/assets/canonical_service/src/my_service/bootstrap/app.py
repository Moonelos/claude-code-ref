from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from my_service.api.routers.submissions import router
from my_service.bootstrap.runtime import runtime
from my_service.config.settings import Settings


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with runtime(Settings()) as built:
            app.state.runtime = built
            yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app
