# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13.15
ARG UV_VERSION=0.12.7

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM python:${PYTHON_VERSION}-slim-trixie AS python-base


FROM python-base AS builder

ARG PYTHON_VERSION

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1 \
    UV_PYTHON_DOWNLOADS=0

# Copy dependency metadata first to preserve the expensive dependency layer.
COPY .python-version pyproject.toml uv.lock ./

# Docker cannot populate a pre-FROM ARG from .python-version. Keep the literal
# pins aligned and make drift fail immediately.
RUN test "$(tr -d '\r\n' < .python-version)" = "${PYTHON_VERSION}"

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --locked \
        --no-dev \
        --no-install-project

COPY src src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --locked \
        --no-dev \
        --no-editable


FROM python-base AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

ENV HOME=/home/appuser \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" appuser \
    && useradd \
        --uid "${APP_UID}" \
        --gid "${APP_GID}" \
        --create-home \
        --home-dir /home/appuser \
        --shell /usr/sbin/nologin \
        --no-log-init \
        appuser

COPY --from=builder /app/.venv /app/.venv

USER ${APP_UID}:${APP_GID}

EXPOSE 8080
STOPSIGNAL SIGTERM

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3).close()"]

ENTRYPOINT ["/usr/bin/tini", "--"]
# This launcher command owns the bind host and port (python-settings-config:
# never a YAML key); a platform that assigns the port overrides CMD. The app
# is built by its factory so the lifespan enters the runtime.
CMD ["/app/.venv/bin/uvicorn", "--factory", "sample_service.bootstrap.app:create_app", "--host", "0.0.0.0", "--port", "8080"]
