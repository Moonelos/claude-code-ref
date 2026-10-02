from datetime import timedelta


class DocstoreError(Exception):
    """Base for every failure this library raises."""


class DocstoreUnavailableError(DocstoreError):
    """Not about this request: a timeout, connection failure, 429, 5xx, or a 4xx every
    request would hit (401/403 credentials or permissions, 405 a wrong method).

    The same call may succeed once the dependency or its configuration recovers.
    """

    def __init__(self, message: str, *, retry_after: timedelta | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class DocstoreRejectedError(DocstoreError):
    """400, 409, or 422: the API refused this request's data; repeating it fails the same way."""


class DocstoreProtocolError(DocstoreError):
    """The response did not match the documented contract."""
