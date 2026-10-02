"""Greeting endpoint backed by the shared library."""

from fastapi import APIRouter

from sample_shared import greeting

router = APIRouter()


@router.get("/")
def root() -> dict[str, str]:
    return {"message": greeting()}
