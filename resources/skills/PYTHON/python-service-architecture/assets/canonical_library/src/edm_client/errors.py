from datetime import timedelta


class EdmError(Exception):
    """Base for every failure this library raises."""


class EdmUnavailableError(EdmError):
    """Timeout, connection failure, 429, or 5xx: the same call may succeed later."""

    def __init__(self, message: str, *, retry_after: timedelta | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EdmRejectedError(EdmError):
    """A 4xx other than 404 and 429: repeating the call fails the same way."""


class EdmProtocolError(EdmError):
    """The response did not match the documented contract."""
