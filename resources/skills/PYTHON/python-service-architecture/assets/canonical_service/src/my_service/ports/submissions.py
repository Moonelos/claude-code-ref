from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from my_service.ports.errors import DependencyRejectedError, DependencyUnavailableError
from my_service.domain.submissions import Selection


class SubmissionStoreUnavailableError(DependencyUnavailableError):
    """The store could not complete the transaction; retry later."""


class SubmissionStoreIntegrityError(DependencyRejectedError):
    """A constraint other than the duplicate-submission key was violated."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Receipt:
    request_id: UUID
    replayed: bool


class SubmissionStore(Protocol):
    async def submit(
        self, *, client_id: str, selection: Selection, payload_hash: str
    ) -> Receipt: ...
