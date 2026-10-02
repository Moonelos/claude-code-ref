from dataclasses import dataclass, field
from datetime import timedelta

import httpx
from pydantic import ValidationError

from edm_client.errors import EdmProtocolError, EdmRejectedError, EdmUnavailableError
from edm_client.models import Document


@dataclass(frozen=True, slots=True, kw_only=True)
class EdmOptions:
    base_url: str
    api_token: str = field(repr=False)


class EdmClient:
    """Async EDM client. One call is one attempt; the caller owns `http` and retries."""

    def __init__(self, *, http: httpx.AsyncClient, options: EdmOptions) -> None:
        self._http = http
        self._options = options

    async def find_document(self, document_id: str) -> Document | None:
        response = await self._get(f"/documents/{document_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        try:
            return Document.model_validate_json(response.content)
        except ValidationError as exc:
            raise EdmProtocolError(f"document {document_id}: unexpected body") from exc

    async def _get(self, path: str) -> httpx.Response:
        try:
            response = await self._http.get(
                f"{self._options.base_url}{path}",
                headers={"Authorization": f"Bearer {self._options.api_token}"},
            )
        except httpx.TransportError as exc:
            raise EdmUnavailableError(f"GET {path}: {type(exc).__name__}") from exc
        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS or response.is_server_error:
            raise EdmUnavailableError(
                f"GET {path}: HTTP {status}", retry_after=_retry_after(response)
            )
        if response.is_client_error and status != httpx.codes.NOT_FOUND:
            raise EdmRejectedError(f"GET {path}: HTTP {status}")
        return response


def _retry_after(response: httpx.Response) -> timedelta | None:
    value = response.headers.get("Retry-After", "")
    return timedelta(seconds=int(value)) if value.isdigit() else None
