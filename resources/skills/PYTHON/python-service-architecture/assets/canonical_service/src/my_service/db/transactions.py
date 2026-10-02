from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_service.ports.errors import DependencyRejectedError, DependencyUnavailableError

# SQLAlchemy wraps driver socket and timeout failures in these. Unknown
# failures propagate unlabelled instead of being reported as outages.
_UNAVAILABLE = (OperationalError, InterfaceError, PoolTimeoutError)


@dataclass(frozen=True, slots=True, kw_only=True)
class PortErrors:
    """The calling port's own error types; each store passes its module constant."""

    unavailable: type[DependencyUnavailableError]
    integrity: type[DependencyRejectedError]


@asynccontextmanager
async def transaction(
    sessions: async_sessionmaker[AsyncSession], *, errors: PortErrors
) -> AsyncIterator[AsyncSession]:
    try:
        async with sessions() as session, session.begin():
            try:
                await session.connection()
            except OSError as exc:
                # asyncpg raises a bare OSError while connecting; only checkout
                # is guarded, never the body.
                raise errors.unavailable(error_code="database_unreachable") from exc
            yield session
    except IntegrityError as exc:
        raise errors.integrity(error_code="integrity_violation") from exc
    except _UNAVAILABLE as exc:
        raise errors.unavailable(error_code="database_unavailable") from exc
