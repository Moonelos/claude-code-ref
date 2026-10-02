"""The one exhaustive exception -> public error table for every route."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from math import ceil

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as FrameworkHTTPException

from my_service.api.dependencies import AuthenticationRequiredError
from my_service.domain.submissions import InvalidSelectionError
from my_service.ports.errors import DependencyRejectedError, DependencyUnavailableError

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicError:
    status: int
    code: str
    title: str


# Keyed by exception type; Starlette resolves handlers along the MRO, so every
# port error maps through its classification base.
PUBLIC_ERRORS: dict[type[Exception], PublicError] = {
    AuthenticationRequiredError: PublicError(
        status=status.HTTP_401_UNAUTHORIZED,
        code="authentication_required",
        title="Authentication required",
    ),
    InvalidSelectionError: PublicError(
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="invalid_selection",
        title="The selection violates submission policy",
    ),
    RequestValidationError: PublicError(
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="invalid_request",
        title="The request does not match the schema",
    ),
    DependencyUnavailableError: PublicError(
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="temporarily_unavailable",
        title="Try again later",
    ),
    # Integrity faults subclass the rejected base; they are our defect, not the client's.
    DependencyRejectedError: PublicError(
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        title="Internal error",
    ),
}
# Framework-raised 404 and 405 (an unknown path or method) share one handler.
FRAMEWORK_ERRORS: dict[int, PublicError] = {
    status.HTTP_404_NOT_FOUND: PublicError(
        status=status.HTTP_404_NOT_FOUND, code="not_found", title="Not found"
    ),
    status.HTTP_405_METHOD_NOT_ALLOWED: PublicError(
        status=status.HTTP_405_METHOD_NOT_ALLOWED,
        code="method_not_allowed",
        title="Method not allowed",
    ),
}
_FRAMEWORK_FALLBACK = PublicError(
    status=status.HTTP_400_BAD_REQUEST, code="bad_request", title="Bad request"
)


def problem(error: PublicError, *, retry_after: timedelta | None = None) -> JSONResponse:
    """The one response envelope; exception text never reaches the client."""
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(ceil(retry_after.total_seconds()))
    return JSONResponse(
        {"type": "about:blank", "title": error.title, "status": error.status, "code": error.code},
        status_code=error.status,
        media_type="application/problem+json",
        headers=headers,
    )


def _handler(error: PublicError) -> Callable[[Request, Exception], Awaitable[Response]]:
    async def handle(_request: Request, exc: Exception) -> Response:
        if error.status >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            log.error("request_failed", exc_info=exc)
        retry_after = exc.retry_after if isinstance(exc, DependencyUnavailableError) else None
        return problem(error, retry_after=retry_after)

    return handle


async def _framework_handler(_request: Request, exc: Exception) -> Response:
    code = exc.status_code if isinstance(exc, FrameworkHTTPException) else 0
    return problem(FRAMEWORK_ERRORS.get(code, _FRAMEWORK_FALLBACK))


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, error in PUBLIC_ERRORS.items():
        app.add_exception_handler(exc_type, _handler(error))
    app.add_exception_handler(FrameworkHTTPException, _framework_handler)
