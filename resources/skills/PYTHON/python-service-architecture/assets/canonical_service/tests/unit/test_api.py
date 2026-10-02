"""HTTP translation only: the runtime is fakes, so no database or lifespan runs."""

import inspect
import unittest
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

import my_service.api.dependencies
import my_service.domain.submissions
import my_service.ports.errors
import my_service.ports.submissions
from my_service.api.dependencies import ClientIdentity, get_runtime, get_write_identity
from my_service.api.exception_handlers import PUBLIC_ERRORS
from my_service.bootstrap.app import create_app
from my_service.domain.submissions import Selection, SubmissionPolicy
from my_service.ports.submissions import Receipt, SubmissionStoreUnavailableError

# Every module whose exceptions a request can raise.
REQUEST_ERROR_MODULES = (
    my_service.api.dependencies,
    my_service.domain.submissions,
    my_service.ports.errors,
    my_service.ports.submissions,
)


@dataclass
class FakeStore:
    failure: Exception | None = None
    client_id: str | None = None

    async def submit(self, *, client_id: str, selection: Selection, payload_hash: str) -> Receipt:
        if self.failure is not None:
            raise self.failure
        self.client_id = client_id
        return Receipt(request_id=uuid4(), replayed=False)


@dataclass(frozen=True)
class FakeRuntime:
    submission_store: FakeStore
    submission_policy: SubmissionPolicy


class ApiTests(unittest.TestCase):
    def client(self, store: FakeStore, *, identity: ClientIdentity | None) -> TestClient:
        app = create_app()
        runtime = FakeRuntime(
            submission_store=store,
            submission_policy=SubmissionPolicy(default_records=10, max_records=100),
        )
        app.dependency_overrides[get_runtime] = lambda: runtime
        if identity is not None:
            app.dependency_overrides[get_write_identity] = lambda: identity
        return TestClient(app)  # outside `with`: the lifespan does not run

    def test_every_request_error_is_mapped(self) -> None:
        for module in REQUEST_ERROR_MODULES:
            for name, value in inspect.getmembers(module, inspect.isclass):
                if issubclass(value, Exception) and value.__module__ == module.__name__:
                    with self.subTest(error=name):
                        self.assertTrue(any(cls in PUBLIC_ERRORS for cls in value.__mro__))

    def test_client_id_comes_from_the_verified_identity(self) -> None:
        store = FakeStore()
        client = self.client(store, identity=ClientIdentity(client_id="trusted"))
        response = client.post("/submissions", json={"record_type": "email"})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(store.client_id, "trusted")

    def test_body_cannot_carry_a_client_id(self) -> None:
        client = self.client(FakeStore(), identity=ClientIdentity(client_id="trusted"))
        response = client.post("/submissions", json={"record_type": "email", "client_id": "x"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "invalid_request")

    def test_missing_identity_is_401(self) -> None:
        client = self.client(FakeStore(), identity=None)
        response = client.post("/submissions", json={"record_type": "email"})
        self.assertEqual(response.status_code, 401)

    def test_invalid_selection_is_422(self) -> None:
        client = self.client(FakeStore(), identity=ClientIdentity(client_id="c"))
        response = client.post("/submissions", json={"record_type": "email", "max_records": 1000})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers["content-type"], "application/problem+json")
        self.assertEqual(response.json()["code"], "invalid_selection")

    def test_unavailable_store_is_503_with_retry_after(self) -> None:
        failure = SubmissionStoreUnavailableError(
            error_code="database_unavailable", retry_after=timedelta(seconds=30)
        )
        client = self.client(FakeStore(failure=failure), identity=ClientIdentity(client_id="c"))
        with self.assertLogs("my_service.api.exception_handlers", "ERROR"):
            response = client.post("/submissions", json={"record_type": "email"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["retry-after"], "30")
        self.assertNotIn("database_unavailable", response.text)

    def test_unknown_route_uses_the_envelope(self) -> None:
        client = self.client(FakeStore(), identity=None)
        response = client.get("/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")
