"""Liveness endpoint."""

from fastapi import APIRouter, status

router = APIRouter()


@router.get("/health/live", status_code=status.HTTP_200_OK)
def live() -> dict[str, str]:
    """Liveness: the process is serving requests. Calls no application action."""
    return {"status": "ok"}
