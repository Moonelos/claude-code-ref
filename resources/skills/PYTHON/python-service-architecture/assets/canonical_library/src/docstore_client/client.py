from dataclasses import dataclass, field
from datetime import timedelta

import httpx
from pydantic import ValidationError

from docstore_client.errors import DocstoreProtocolError, DocstoreRejectedError, DocstoreUnavailableError
from docstore_client.models import Document

# Statuses that refuse this request's data: repeating it fails the same way. Any
# other 4xx (401/403 credentials or permissions, 405 a wrong method, 408) would
# fail every request, so it is an outage an operator fixes, not a rejection.
_REJECTED = frozenset(
    {httpx.codes.BAD_REQUEST, httpx.codes.CONFLICT, httpx.codes.UNPROCESSABLE_ENTITY}
)
_MAX_RETRY_AFTER_SECONDS = 3600


@dataclass(frozen=True, slots=True, kw_only=True)
class DocstoreOptions:
    base_url: str
    api_token: str = field(repr=False)


class DocstoreClient:
    """Async document-store client. One call is one attempt; the caller owns `http` and retries."""

    def __init__(self, *, http: httpx.AsyncClient, options: DocstoreOptions) -> None:
        self._http = http
        self._options = options

    async def find_document(self, document_id: str) -> Document | None:
        response = await self._get(f"/documents/{document_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None  # on this route, 404 means no such document
        try:
            return Document.model_validate_json(response.content)
        except ValidationError as exc:
            raise DocstoreProtocolError(f"document {document_id}: unexpected body") from exc

    async def _get(self, path: str) -> httpx.Response:
        """Return 2xx and 404 responses; each method decides what its 404 means."""
        try:
            response = await self._http.get(
                f"{self._options.base_url}{path}",
                headers={"Authorization": f"Bearer {self._options.api_token}"},
            )
        except httpx.TransportError as exc:
            raise DocstoreUnavailableError(f"GET {path}: {type(exc).__name__}") from exc
        status = response.status_code
        if status == httpx.codes.NOT_FOUND:
            return response
        if status in _REJECTED:
            raise DocstoreRejectedError(f"GET {path}: HTTP {status}")
        if response.is_error:
            raise DocstoreUnavailableError(
                f"GET {path}: HTTP {status}", retry_after=_retry_after(response)
            )
        return response


def _retry_after(response: httpx.Response) -> timedelta | None:
    """The delay-seconds form, capped; an HTTP-date, Unicode digits, or junk give None."""
    value = response.headers.get("Retry-After", "").strip()
    if not (value.isascii() and value.isdigit()):
        return None
    # Check the length first: int() refuses very long strings and timedelta overflows.
    if len(value) > len(str(_MAX_RETRY_AFTER_SECONDS)):
        return timedelta(seconds=_MAX_RETRY_AFTER_SECONDS)
    return timedelta(seconds=min(int(value), _MAX_RETRY_AFTER_SECONDS))
