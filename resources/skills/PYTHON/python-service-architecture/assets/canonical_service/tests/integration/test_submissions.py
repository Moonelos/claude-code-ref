"""Executable fixture checks; SQLite does not prove PostgreSQL lock semantics."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.exc import TimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from my_service.db.submissions import _ERRORS, SqlSubmissionStore
from my_service.db.models import SubmissionRow
from my_service.db.transactions import transaction
from my_service.domain.submissions import Selection, payload_hash
from my_service.ports.submissions import (
    SubmissionStoreIntegrityError,
    SubmissionStoreUnavailableError,
)


class SubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / "submissions.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
        self.addAsyncCleanup(self.engine.dispose)

        # Explicit BEGIN makes SQLite savepoints participate in the outer
        # transaction even with sqlite3's legacy transaction mode.
        @event.listens_for(self.engine.sync_engine, "connect")
        def on_connect(connection, _record):
            connection.isolation_level = None

        @event.listens_for(self.engine.sync_engine, "begin")
        def on_begin(connection):
            connection.exec_driver_sql("BEGIN")

        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.store = SqlSubmissionStore(sessions=self.sessions)
        self.selection = Selection(record_type="email", max_records=10)

    async def test_concurrent_duplicates_return_one_receipt(self) -> None:
        receipts = await asyncio.gather(
            *(
                self.store.submit(
                    client_id="client",
                    selection=self.selection,
                    payload_hash=payload_hash(self.selection),
                )
                for _ in range(4)
            )
        )
        self.assertEqual(len({receipt.request_id for receipt in receipts}), 1)
        self.assertEqual(sum(not receipt.replayed for receipt in receipts), 1)
        async with self.sessions() as session:
            rows = (await session.scalars(select(SubmissionRow))).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].max_records, 10)

    async def test_idempotency_is_scoped_to_client(self) -> None:
        first = await self.store.submit(
            client_id="a", selection=self.selection, payload_hash="same"
        )
        second = await self.store.submit(
            client_id="b", selection=self.selection, payload_hash="same"
        )
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertFalse(second.replayed)

    async def test_unrelated_constraint_failure_is_preserved(self) -> None:
        request_id = uuid4()
        store = SqlSubmissionStore(sessions=self.sessions, id_factory=lambda: request_id)
        await store.submit(client_id="a", selection=self.selection, payload_hash="first")
        with self.assertRaises(SubmissionStoreIntegrityError):
            await store.submit(client_id="a", selection=self.selection, payload_hash="different")

    async def test_transaction_rolls_back_on_failure(self) -> None:
        with self.assertRaisesRegex(ValueError, "stop"):
            async with transaction(self.sessions, errors=_ERRORS) as session:
                session.add(
                    SubmissionRow(
                        request_id=uuid4(),
                        client_id="a",
                        record_type="email",
                        max_records=10,
                        payload_hash="rollback",
                    )
                )
                await session.flush()
                raise ValueError("stop")
        async with self.sessions() as session:
            self.assertEqual((await session.scalars(select(SubmissionRow))).all(), [])

    async def test_timeout_is_translated_with_cause(self) -> None:
        timeout = TimeoutError("pool timeout")
        sessions = Mock(side_effect=timeout)
        with self.assertRaises(SubmissionStoreUnavailableError) as caught:
            async with transaction(sessions, errors=_ERRORS):
                self.fail("must not enter")
        self.assertIs(caught.exception.__cause__, timeout)

    async def test_programming_failure_is_not_labelled_as_outage(self) -> None:
        error = ValueError("bad setup")
        with self.assertRaises(ValueError) as caught:
            async with transaction(Mock(side_effect=error), errors=_ERRORS):
                self.fail("must not enter")
        self.assertIs(caught.exception, error)

    async def test_refused_connection_is_translated(self) -> None:
        refused = ConnectionRefusedError("connection refused")
        session = Mock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.begin = Mock(return_value=session)
        session.connection = AsyncMock(side_effect=refused)
        with self.assertRaises(SubmissionStoreUnavailableError) as caught:
            async with transaction(Mock(return_value=session), errors=_ERRORS):
                self.fail("must not enter")
        self.assertIs(caught.exception.__cause__, refused)
