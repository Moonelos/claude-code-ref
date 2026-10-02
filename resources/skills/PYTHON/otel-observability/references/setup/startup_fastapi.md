# FastAPI Startup and Shutdown

Read this file only for FastAPI. Read `startup_prefork.md` as well when
Gunicorn or another pre-fork server owns the worker processes.

The ASGI app factory in `bootstrap/app.py` owns this sequence; process
ownership (who loads settings, enters the runtime, starts workers) is in
`../../../python-service-architecture/references/api-and-workers.md`
(FastAPI / HTTP API). Nothing runs at import time; launch with
`uvicorn --factory <package>.bootstrap.app:create_app`.

```python
# bootstrap/app.py
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from observability.logging import add_otel_trace_context, configure_logging
from observability.tracing import configure_observability, shutdown_observability


def create_app() -> FastAPI:
    # 1. Providers exist before any instrumented work happens. The same owner
    # shuts down traces and metrics. The config values come from the service
    # settings, loaded here by the composition root, never at import time.
    settings = load_settings()
    configure_observability(telemetry_config(settings))
    configure_logging(logging_config(settings), correlation=[add_otel_trace_context])

    # 2. Process-wide hooks, before any client is constructed.
    HTTPXClientInstrumentor().instrument()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 3. Constructed after HTTPX instrumentation is active.
        app.state.pricing_client = httpx.AsyncClient(
            base_url="http://pricing-service:8080", timeout=5.0
        )
        try:
            yield
        finally:
            # 4. Close clients while telemetry is still running.
            await app.state.pricing_client.aclose()
            # 5. Flush last.
            shutdown_observability()

    app = FastAPI(lifespan=lifespan)
    # 6. Instrument in the factory, before the server builds the middleware stack.
    FastAPIInstrumentor.instrument_app(app)
    return app
```

Never call `FastAPIInstrumentor.instrument_app(app)` inside the lifespan.
Lifespan runs after the server has built the middleware stack; the call fails
or silently does nothing.
