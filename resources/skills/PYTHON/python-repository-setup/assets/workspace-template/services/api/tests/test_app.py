"""Routes and the application factory of the sample API."""

from sample_api.api.routers.greetings import root
from sample_api.api.routers.health import health
from sample_api.bootstrap.app import create_app


def test_health() -> None:
    assert health() == {"status": "ok"}


def test_root_uses_shared_library() -> None:
    assert root() == {"message": "hello from the workspace"}


def test_app_serves_routes() -> None:
    # The public schema, not app.routes: included routers are not flattened there.
    assert {"/", "/health"} <= create_app().openapi()["paths"].keys()
