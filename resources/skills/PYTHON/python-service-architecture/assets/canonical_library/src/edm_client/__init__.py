"""Async client for the EDM document API."""

from edm_client.client import EdmClient, EdmOptions
from edm_client.errors import (
    EdmError,
    EdmProtocolError,
    EdmRejectedError,
    EdmUnavailableError,
)
from edm_client.models import Document

__all__ = [
    "Document",
    "EdmClient",
    "EdmError",
    "EdmOptions",
    "EdmProtocolError",
    "EdmRejectedError",
    "EdmUnavailableError",
]
