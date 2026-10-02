from collections.abc import Callable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col

from my_service.db.models import SubmissionRow
from my_service.db.transactions import PortErrors, transaction
from my_service.domain.submissions import Selection
from my_service.ports.submissions import (
    Receipt,
    SubmissionStoreIntegrityError,
    SubmissionStoreUnavailableError,
)

_ERRORS = PortErrors(
    unavailable=SubmissionStoreUnavailableError, integrity=SubmissionStoreIntegrityError
)


class SqlSubmissionStore:
    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._sessions = sessions
        self._id_factory = id_factory

    async def submit(self, *, client_id: str, selection: Selection, payload_hash: str) -> Receipt:
        # Requires READ COMMITTED on PostgreSQL: the read after a conflicting
        # insert sees the winner. The savepoint preserves the outer transaction.
        async with transaction(self._sessions, errors=_ERRORS) as session:
            request_id = self._id_factory()
            try:
                async with session.begin_nested():
                    session.add(
                        SubmissionRow(
                            request_id=request_id,
                            client_id=client_id,
                            record_type=selection.record_type,
                            max_records=selection.max_records,
                            payload_hash=payload_hash,
                        )
                    )
                    await session.flush()
            except IntegrityError:
                existing = await session.scalar(
                    select(col(SubmissionRow.request_id)).where(
                        col(SubmissionRow.client_id) == client_id,
                        col(SubmissionRow.payload_hash) == payload_hash,
                    )
                )
                if existing is None:
                    raise  # an unrelated constraint failure is not a duplicate
                return Receipt(request_id=existing, replayed=True)
            return Receipt(request_id=request_id, replayed=False)
