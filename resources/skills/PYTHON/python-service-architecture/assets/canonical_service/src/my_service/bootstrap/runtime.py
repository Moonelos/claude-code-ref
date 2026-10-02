from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_service.config.secrets import Secrets
from my_service.config.settings import Settings
from my_service.db.submissions import SqlSubmissionStore
from my_service.domain.submissions import SubmissionPolicy
from my_service.ports.submissions import SubmissionStore


@dataclass(frozen=True, slots=True, kw_only=True)
class Runtime:
    """Implementations and policies, built once; entry points pass them to actions."""

    submission_store: SubmissionStore
    submission_policy: SubmissionPolicy


@asynccontextmanager
async def runtime(settings: Settings, secrets: Secrets) -> AsyncIterator[Runtime]:
    async with AsyncExitStack() as stack:
        engine = create_async_engine(secrets.database_dsn.get_secret_value())
        # Kept only for disposal: the engine lives in the exit stack, not on Runtime.
        stack.push_async_callback(engine.dispose)
        yield Runtime(
            submission_store=SqlSubmissionStore(sessions=async_sessionmaker(engine)),
            submission_policy=SubmissionPolicy(
                default_records=settings.default_records, max_records=settings.max_records
            ),
        )
