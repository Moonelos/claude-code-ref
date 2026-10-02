"""Liveness router and its registration in the app."""

from sample_service.api.routers.health import live
from sample_service.bootstrap.app import create_app


def test_live_reports_ok() -> None:
    assert live() == {"status": "ok"}


def test_app_serves_liveness() -> None:
    # The public schema, not app.routes: included routers are not flattened there.
    assert "/health/live" in create_app().openapi()["paths"]
