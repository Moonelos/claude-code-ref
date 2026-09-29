"""Regression tests for scripts/audit_service.py.

The canonical examples live in `python-service-architecture/assets/` (the
service follows the canonical feature in its `references/templates.md`) and must
stay clean. Each
test applies one defect to a temporary copy and asserts the finding it causes, so
a check that silently stops matching fails here.

Run: python3 -m unittest discover -s tests   (from the skill root)
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts/audit_service.py"
SKILLS = SKILL.parent  # every skill is a sibling (skills/CLAUDE.md)
EXAMPLES = SKILLS / "python-service-architecture/assets"
FIXTURE = EXAMPLES / "canonical_service"
LIBRARY_FIXTURE = EXAMPLES / "canonical_library"

_spec = importlib.util.spec_from_file_location("audit_service", SCRIPT)
assert _spec is not None and _spec.loader is not None
audit_service = importlib.util.module_from_spec(_spec)
sys.modules["audit_service"] = audit_service  # dataclasses resolve their module by name
_spec.loader.exec_module(audit_service)


class AuditCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.member = Path(tmp.name) / "service"
        shutil.copytree(FIXTURE, self.member)
        self.package = self.member / "src/my_service"

    def write(self, relative: str, source: str) -> None:
        """Write a module relative to the member root (`src/my_service/...`, `tests/...`)."""
        path = self.member / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip())

    def pkg(self, relative: str, source: str) -> None:
        self.write(f"src/my_service/{relative}", source)

    def findings(self, *, allowed: set[str] | None = None) -> list[str]:
        found = audit_service.audit(
            self.package,
            "my_service",
            self.member,
            self.member / "tests",
            audit_service.PURE_ALLOWED_EXTERNAL | (allowed or set()),
        )
        return [finding.render() for finding in found]

    def assertFinding(self, severity: str, path: str, fragment: str) -> None:
        rendered = self.findings()
        prefix = f"{severity} {path}:"
        matches = [
            line for line in rendered if line.startswith(prefix) and fragment in line
        ]
        self.assertTrue(
            matches, f"no {prefix} ... {fragment!r} in:\n" + "\n".join(rendered)
        )

    def assertClean(self, **kwargs: set[str]) -> None:
        rendered = self.findings(**kwargs)
        self.assertEqual(rendered, [], "\n".join(rendered))


class CanonicalServiceTests(AuditCase):
    def test_canonical_service_is_clean(self) -> None:
        self.assertClean()

    def test_cli_reports_clean_run_as_static_only(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.package),
                "--workspace",
                str(self.member),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("static checks passed; semantic audit pending", result.stdout)

    def test_cli_exits_non_zero_on_violation(self) -> None:
        self.pkg("domain/leak.py", "import httpx\n")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.package),
                "--workspace",
                str(self.member),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("semantic audit pending", result.stdout)


class ImportDirectionTests(AuditCase):
    def test_relative_import(self) -> None:
        self.pkg("domain/other.py", "from .submissions import Selection\n")
        self.assertFinding("VIOLATION", "domain/other.py", "relative import")

    def test_pure_layer_rejects_unlisted_third_party(self) -> None:
        for owner in ("domain", "ports", "application"):
            with self.subTest(owner=owner):
                self.pkg(f"{owner}/leak.py", "import httpx\n")
                self.assertFinding(
                    "VIOLATION", f"{owner}/leak.py", "external technology httpx"
                )

    def test_pure_layer_accepts_stdlib_pydantic_and_own_package(self) -> None:
        self.pkg(
            "domain/fine.py",
            """
            import datetime
            from typing_extensions import Self
            from pydantic import BaseModel
            from my_service.domain.submissions import Selection
            """,
        )
        self.assertClean()

    def test_application_may_log_but_domain_may_not(self) -> None:
        self.pkg("application/logs.py", "import structlog\n")
        self.assertClean()
        self.pkg("domain/logs.py", "import structlog\n")
        self.assertFinding("VIOLATION", "domain/logs.py", "external technology structlog")

    def test_workers_do_not_import_concrete_integrations(self) -> None:
        self.pkg(
            "workers/orders.py",
            "from my_service.db.submissions import SqlSubmissionStore\n",
        )
        self.assertFinding("VIOLATION", "workers/orders.py", "workers imports db")

    def test_application_does_not_import_workers(self) -> None:
        self.pkg("application/bad.py", "from my_service.workers import runtime\n")
        self.assertFinding("VIOLATION", "application/bad.py", "application imports workers")

    def test_bootstrap_binding_an_action_is_reviewed(self) -> None:
        self.pkg(
            "bootstrap/supervisor.py",
            """
            from functools import partial

            from my_service.application.submit import submit_investigation

            handler = partial(submit_investigation, store=None)
            """,
        )
        self.assertFinding(
            "REVIEW", "bootstrap/supervisor.py", "binds application action submit_investigation"
        )

    def test_method_guarding_private_state_is_not_forwarding(self) -> None:
        self.pkg(
            "bootstrap/health.py",
            """
            class ProcessHealth:
                def __init__(self) -> None:
                    self._failed: set[str] = set()

                def mark_failed(self, name: str) -> None:
                    self._failed.add(name)
            """,
        )
        self.assertClean()

    def test_allow_external_admits_a_package(self) -> None:
        self.pkg("domain/contract.py", "from workflow_contracts import Envelope\n")
        self.assertClean(allowed={"workflow_contracts"})

    def test_application_imports_opentelemetry(self) -> None:
        self.pkg("application/traced.py", "from opentelemetry import trace\n")
        self.assertFinding(
            "VIOLATION", "application/traced.py", "imports opentelemetry"
        )

    def test_application_imports_outer_package(self) -> None:
        self.pkg(
            "application/bad.py",
            "from my_service.db.submissions import SqlSubmissionStore\n",
        )
        self.assertFinding("VIOLATION", "application/bad.py", "application imports db")

    def test_application_imports_outer_package_from_root(self) -> None:
        self.pkg("application/bad.py", "from my_service import db\n")
        self.assertFinding("VIOLATION", "application/bad.py", "application imports db")

    def test_application_imports_inner_package_from_root(self) -> None:
        self.pkg("application/fine.py", "from my_service import domain, ports\n")
        self.assertClean()

    def test_outer_package_imports_bootstrap(self) -> None:
        self.pkg("api/bad.py", "from my_service.bootstrap.runtime import Runtime\n")
        self.assertFinding("VIOLATION", "api/bad.py", "api imports bootstrap")

    def test_generic_error_collection(self) -> None:
        self.pkg("errors.py", "class AppError(Exception):\n    pass\n")
        self.assertFinding("VIOLATION", "errors.py", "generic root/core")

    def test_api_rejects_concrete_integrations(self) -> None:
        for boundary in ("db", "adapters", "genai"):
            with self.subTest(boundary=boundary):
                self.pkg("api/direct.py", f"from my_service import {boundary}\n")
                self.assertFinding(
                    "VIOLATION", "api/direct.py", f"api imports {boundary}"
                )

    def test_application_siblings_core_and_observability_allowed(self) -> None:
        self.pkg(
            "application/allowed.py",
            "from my_service import application, core, observability\n",
        )
        self.assertClean()

    def test_core_cannot_import_outer_layers(self) -> None:
        self.pkg("core/leak.py", "from my_service import db\n")
        self.assertFinding("VIOLATION", "core/leak.py", "core imports db")


class DomainPurityTests(AuditCase):
    def test_domain_file_io_and_import_aliases(self) -> None:
        for source in (
            'from pathlib import Path\nDATA = Path("policy.txt").read_text()\n',
            'from io import open as read_file\nDATA = read_file("policy.txt")\n',
            'from subprocess import run as execute\nexecute(["whoami"])\n',
        ):
            with self.subTest(source=source):
                self.pkg("domain/io.py", source)
                self.assertFinding("REVIEW", "domain/io.py", "appears to perform I/O")

    def test_pure_path_manipulation_is_allowed(self) -> None:
        self.pkg(
            "domain/path.py",
            'from pathlib import PurePath\nNAME = PurePath("a/b").name\n',
        )
        self.assertClean()


class ContractShapeTests(AuditCase):
    def test_application_owns_loop_lifecycle(self) -> None:
        self.pkg(
            "application/loop.py",
            """
            import asyncio

            async def run(stop: asyncio.Event) -> None:
                while not stop.is_set():
                    await asyncio.sleep(1)
            """,
        )
        self.assertFinding("REVIEW", "application/loop.py", "long-running loop")

    def test_transport_fields_in_port_contract(self) -> None:
        self.pkg(
            "ports/messages.py",
            """
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Delivery:
                body: bytes
                receipt_handle: str
            """,
        )
        self.assertFinding(
            "REVIEW", "ports/messages.py", "transport fields: receipt_handle"
        )

    def test_port_framework_vocabulary_and_any(self) -> None:
        self.pkg(
            "ports/agent.py",
            """
            from typing import Any, Protocol

            class Agent(Protocol):
                async def ainvoke(self, payload: Any) -> Any: ...
            """,
        )
        self.assertFinding("REVIEW", "ports/agent.py", "framework vocabulary: ainvoke")
        self.assertFinding("REVIEW", "ports/agent.py", "uses Any/object")

    def test_port_performs_io(self) -> None:
        self.pkg("ports/io.py", "TEMPLATE = open('t.txt').read()\n")
        self.assertFinding("REVIEW", "ports/io.py", "performs I/O: open()")


class SmellTests(AuditCase):
    def test_assert_in_production(self) -> None:
        self.pkg(
            "domain/checks.py",
            "def f(x: int) -> int:\n    assert x > 0\n    return x\n",
        )
        self.assertFinding("REVIEW", "domain/checks.py", "assert in production")

    def test_getattr_on_caught_exception(self) -> None:
        self.pkg(
            "api/handlers.py",
            """
            def code(fn) -> str:
                try:
                    fn()
                except Exception as exc:
                    return getattr(exc, "error_code", "unknown")
                return "ok"
            """,
        )
        self.assertFinding("REVIEW", "api/handlers.py", "getattr(exc, ...)")

    def test_exception_carries_transport_mapping(self) -> None:
        self.pkg(
            "domain/failures.py",
            """
            class NotFoundError(Exception):
                def __init__(self) -> None:
                    self.status_code = 404
            """,
        )
        self.assertFinding(
            "REVIEW", "domain/failures.py", "transport mapping: status_code"
        )

    def test_optional_constructor_collaborator(self) -> None:
        self.pkg(
            "genai/classifier.py",
            """
            class Classifier:
                def __init__(self, *, model: "Model | None" = None) -> None:
                    self._model = model
            """,
        )
        self.assertFinding(
            "REVIEW", "genai/classifier.py", "optional constructor collaborator"
        )

    def test_genai_signature_any(self) -> None:
        self.pkg(
            "genai/parse.py",
            """
            from typing import Any

            def parse(raw: Any) -> str:
                return str(raw)
            """,
        )
        self.assertFinding("REVIEW", "genai/parse.py", "genai signature uses Any")

    def test_nondeterminism_in_inner_layers(self) -> None:
        source = textwrap.dedent(
            """
            from datetime import datetime

            def stamp() -> object:
                return datetime.now()
            """
        )
        for owner in ("domain", "application", "db"):
            with self.subTest(owner=owner):
                self.pkg(f"{owner}/clock_use.py", source)
                self.assertFinding("REVIEW", f"{owner}/clock_use.py", "datetime.now()")

    def test_injected_clock_default_is_allowed(self) -> None:
        self.pkg(
            "application/stamped.py",
            """
            from collections.abc import Callable
            from datetime import UTC, datetime

            def stamp(*, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> datetime:
                value = clock()
                return value
            """,
        )
        self.assertClean()

    def test_sql_outside_db(self) -> None:
        self.pkg(
            "adapters/report.py",
            """
            import psycopg
            from sqlalchemy import text

            async def count(session) -> int:
                return await session.execute(text("select 1"))
            """,
        )
        self.assertFinding(
            "REVIEW", "adapters/report.py", "psycopg imported outside db/"
        )
        self.assertFinding("REVIEW", "adapters/report.py", "raw SQL text() outside db/")
        self.assertFinding("REVIEW", "adapters/report.py", "SQL execution outside db/")


class SizeAndShapeTests(AuditCase):
    def test_long_bootstrap_function(self) -> None:
        body = "".join(f"    x{i} = {i}\n" for i in range(85))
        self.pkg("bootstrap/big.py", f"def build() -> None:\n{body}")
        self.assertFinding(
            "REVIEW", "bootstrap/big.py", "bootstrap function build spans"
        )

    def test_bootstrap_function_under_threshold(self) -> None:
        body = "".join(f"    x{i} = {i}\n" for i in range(70))
        self.pkg("bootstrap/medium.py", f"def build() -> None:\n{body}")
        self.assertClean()

    def test_long_repository_method(self) -> None:
        body = "".join(f"        x{i} = {i}\n" for i in range(45))
        self.pkg("db/big.py", f"class Repo:\n    def apply(self) -> None:\n{body}")
        self.assertFinding("REVIEW", "db/big.py", "repository method Repo.apply spans")

    def test_init_defines_code(self) -> None:
        self.pkg("domain/__init__.py", "def helper() -> None:\n    pass\n")
        self.assertFinding("REVIEW", "domain/__init__.py", "__init__.py defines helper")

    def test_reexport_only_module(self) -> None:
        self.pkg(
            "domain/api.py",
            'from my_service.domain.submissions import Selection\n\n__all__ = ["Selection"]\n',
        )
        self.assertFinding("REVIEW", "domain/api.py", "only re-exports")

    def test_one_module_adapter_subpackage(self) -> None:
        self.pkg("adapters/aws/__init__.py", "")
        self.pkg("adapters/aws/s3_store.py", "class S3Store:\n    pass\n")
        self.assertFinding(
            "REVIEW", "adapters/aws/s3_store.py", "one-module adapter subpackage"
        )


class ForwardingTests(AuditCase):
    def test_function_that_only_forwards(self) -> None:
        self.pkg(
            "application/helpers.py",
            """
            from my_service.domain import submissions

            async def _decide(request, policy):
                return submissions.normalize(request, policy)
            """,
        )
        self.assertFinding(
            "REVIEW", "application/helpers.py", "_decide() only forwards"
        )

    def test_one_call_write_and_calculation_actions_are_allowed(self) -> None:
        self.pkg(
            "application/simple.py",
            """
            from my_service.domain.submissions import normalize

            async def delete_submission(*, store, submission_id):
                return await store.delete(submission_id=submission_id)

            async def calculate_selection(*, request, policy):
                return normalize(request, policy)
            """,
        )
        self.assertClean()

    def test_bootstrap_forwarder_still_reports(self) -> None:
        self.pkg(
            "bootstrap/handler.py",
            "async def handle(*, action, item):\n    return await action(item)\n",
        )
        self.assertFinding("REVIEW", "bootstrap/handler.py", "only forwards")

    def test_read_action_with_one_port_call_is_a_catalog_entry(self) -> None:
        self.pkg(
            "application/get.py",
            """
            from my_service.ports.submissions import SubmissionStore

            async def get_receipt(*, store: SubmissionStore, client_id: str):
                return await store.find(client_id=client_id)
            """,
        )
        self.assertClean()

    def test_transaction_coordinator_with_block(self) -> None:
        self.pkg(
            "db/coordinator.py",
            """
            from my_service.db.transactions import transaction

            class Coordinator:
                def __init__(self, sessions) -> None:
                    self._sessions = sessions

                async def submit(self, *, selection):
                    async with transaction(self._sessions) as session:
                        return await Repo(session).submit(selection=selection)
            """,
        )
        self.assertFinding(
            "REVIEW", "db/coordinator.py", "submit() only opens a transaction"
        )

    def test_transaction_coordinator_lambda(self) -> None:
        self.pkg(
            "db/coordinator.py",
            """
            class Coordinator:
                async def expire(self, *, now):
                    return await self._run(lambda s: Repo(s).expire(now=now))
            """,
        )
        self.assertFinding(
            "REVIEW", "db/coordinator.py", "expire() only opens a transaction"
        )


class ProtocolTests(AuditCase):
    def test_unused_port_module(self) -> None:
        self.pkg(
            "ports/unused.py",
            """
            from typing import Protocol

            class Unused(Protocol):
                async def fetch(self) -> str: ...
            """,
        )
        self.pkg(
            "adapters/unused_impl.py",
            """
            class Impl:
                async def fetch(self) -> str:
                    return ""
            """,
        )
        self.assertFinding("REVIEW", "ports/unused.py", "not imported by application/")

    def test_port_used_through_package_reexport(self) -> None:
        self.pkg(
            "ports/mail.py",
            """
            from typing import Protocol

            class Mailer(Protocol):
                async def send(self, *, to: str) -> None: ...
            """,
        )
        self.pkg("ports/__init__.py", "from my_service.ports.mail import Mailer\n")
        self.pkg(
            "application/notify.py",
            """
            from my_service.ports import Mailer

            async def notify(*, mailer: Mailer, to: str) -> None:
                await mailer.send(to=to)
                return None
            """,
        )
        self.pkg(
            "adapters/smtp_mailer.py",
            """
            class SmtpMailer:
                async def send(self, *, to: str) -> None:
                    return None
            """,
        )
        self.assertClean()

    def test_nested_ports_track_full_module_names(self) -> None:
        for area in ("used", "unused"):
            self.pkg(f"ports/{area}/store.py", "VALUE = 1\n")
        self.pkg(
            "application/read.py", "from my_service.ports.used.store import VALUE\n"
        )
        findings = self.findings()
        self.assertFalse(
            any("ports/used/store.py" in hit for hit in findings), findings
        )
        self.assertFinding("REVIEW", "ports/unused/store.py", "not imported")

    def test_nested_port_reexport_is_followed(self) -> None:
        self.pkg("ports/nested/store.py", "VALUE = 1\n")
        self.pkg(
            "ports/nested/__init__.py",
            "from my_service.ports.nested.store import VALUE\n",
        )
        self.pkg("application/read.py", "from my_service.ports.nested import VALUE\n")
        self.assertClean()

    def test_port_without_implementation(self) -> None:
        self.pkg(
            "ports/mail.py",
            """
            from typing import Protocol

            class Mailer(Protocol):
                async def send(self, *, to: str) -> None: ...
            """,
        )
        self.pkg(
            "application/notify.py",
            """
            from my_service.ports.mail import Mailer

            async def notify(*, mailer: Mailer) -> None:
                await mailer.send(to="x")
                return None
            """,
        )
        self.assertFinding(
            "REVIEW", "ports/mail.py", "port Mailer has no implementation"
        )

    def test_callable_protocol_in_ports_is_violation(self) -> None:
        self.pkg(
            "ports/policy.py",
            """
            from typing import Protocol

            class ExpiryPolicy(Protocol):
                def __call__(self, *, age: int) -> bool: ...
            """,
        )
        self.assertFinding("VIOLATION", "ports/policy.py", "only declares __call__")

    def test_unit_of_work_factory_is_not_a_callable_stand_in(self) -> None:
        self.pkg(
            "ports/reviews.py",
            """
            from contextlib import AbstractAsyncContextManager
            from typing import Protocol


            class ReviewWork(Protocol):
                async def commit(self) -> None: ...


            class ReviewWorkFactory(Protocol):
                def __call__(self) -> AbstractAsyncContextManager[ReviewWork]: ...
            """,
        )
        rendered = self.findings()
        self.assertFalse(any("only declares __call__" in line for line in rendered), rendered)

    def test_callable_protocol_outside_ports_is_review(self) -> None:
        self.pkg(
            "adapters/hooks.py",
            """
            from typing import Protocol

            class OnDone(Protocol):
                def __call__(self, *, ok: bool) -> None: ...
            """,
        )
        self.assertFinding("REVIEW", "adapters/hooks.py", "only declares __call__")

    def test_non_port_protocol_with_one_implementation(self) -> None:
        self.pkg(
            "adapters/fetch.py",
            """
            from typing import Protocol

            class Fetcher(Protocol):
                async def fetch_page(self, *, url: str) -> bytes: ...

            class HttpFetcher:
                async def fetch_page(self, *, url: str) -> bytes:
                    return b""
            """,
        )
        self.assertFinding(
            "REVIEW", "adapters/fetch.py", "Protocol Fetcher has one implementation"
        )

    def test_non_port_protocol_with_test_double_is_fine(self) -> None:
        self.pkg(
            "adapters/fetch.py",
            """
            from typing import Protocol

            class Fetcher(Protocol):
                async def fetch_page(self, *, url: str) -> bytes: ...

            class HttpFetcher:
                async def fetch_page(self, *, url: str) -> bytes:
                    return b""
            """,
        )
        self.write(
            "tests/fakes.py",
            """
            class FakeFetcher:
                async def fetch_page(self, *, url: str) -> bytes:
                    return b"x"
            """,
        )
        self.assertClean()

    def test_runtime_protocol_satisfied_by_dataclass_fields(self) -> None:
        # The fixture's ApiRuntime (properties) is satisfied by bootstrap's Runtime (fields);
        # removing the fields must surface the Protocol again.
        runtime = self.package / "bootstrap/runtime.py"
        runtime.write_text(
            runtime.read_text().replace(
                "    submission_store: SubmissionStore\n    submission_policy: SubmissionPolicy\n",
                "    engine_url: str\n",
            )
        )
        self.assertFinding(
            "REVIEW", "api/dependencies.py", "Protocol ApiRuntime has no class"
        )


class DuplicationTests(AuditCase):
    def test_identical_llm_modules(self) -> None:
        source = "def build():\n    return object()\n"
        self.pkg("genai/a/llm.py", source)
        self.pkg("genai/b/llm.py", source)
        self.assertFinding("REVIEW", "genai/a/llm.py", "identical genai llm.py bodies")

    def test_duplicate_private_helper(self) -> None:
        self.pkg(
            "adapters/one.py", "def _clean(x: str) -> str:\n    return x.strip()\n"
        )
        self.pkg(
            "adapters/two.py", "def _clean(x: str) -> str:\n    return x.strip()\n"
        )
        self.assertFinding(
            "REVIEW", "adapters/one.py", "private helper _clean is copied verbatim"
        )

    def test_same_named_private_helpers_with_different_bodies(self) -> None:
        self.pkg(
            "adapters/one.py", "def _clean(x: str) -> str:\n    return x.strip() or \"-\"\n"
        )
        self.pkg(
            "adapters/two.py", "def _clean(x: str) -> str:\n    return x.lower() or \"-\"\n"
        )
        self.assertClean()

    def test_migration_and_standard_literals_are_not_owners(self) -> None:
        for name in ("a", "b", "c"):
            self.pkg(f"adapters/{name}.py", "ENCODING = 'utf-8'\n")
            self.pkg(
                f"db/alembic/versions/rev_{name}.py", "STATUS = 'shipment_pending'\n"
            )
        self.assertClean()

    def test_shared_identifier_literal(self) -> None:
        for name in ("a", "b", "c"):
            self.pkg(
                f"adapters/{name}.py",
                f'def {name}() -> str:\n    return "email.received"\n',
            )
        self.assertFinding(
            "REVIEW", "adapters/a.py", "'email.received' appears in 3 modules"
        )

    def test_byte_identical_module_in_other_member(self) -> None:
        source = (self.package / "domain/submissions.py").read_text()
        self.write("../other_service/src/other/submissions.py", source)
        found = audit_service.audit(
            self.package,
            "my_service",
            self.member.parent,
            self.member / "tests",
            audit_service.PURE_ALLOWED_EXTERNAL,
        )
        messages = [f.render() for f in found if f.path == "domain/submissions.py"]
        self.assertTrue(any("byte-identical copy" in m for m in messages), messages)


class ArchitectureContractTests(AuditCase):
    def test_missing_contracts(self) -> None:
        (self.member / "pyproject.toml").write_text('[project]\nname = "my-service"\n')
        self.assertFinding("VIOLATION", "(repository)", "no import-linter contracts")

    def test_contracts_for_another_package(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().replace('["my_service"]', '["billing"]')
        )
        self.assertFinding("VIOLATION", "(repository)", "does not list my_service")

    def test_contracts_without_precommit_hook(self) -> None:
        (self.member / ".pre-commit-config.yaml").unlink()
        self.assertFinding("REVIEW", "(repository)", "no lint-imports pre-commit hook")

    def test_roots_without_contracts(self) -> None:
        pyproject = self.member / "pyproject.toml"
        roots_only = pyproject.read_text().partition("[[tool.importlinter.contracts]]")[
            0
        ]
        pyproject.write_text(roots_only)
        for edge in (
            "application → db",
            "api → db",
            "domain → config",
            "api → bootstrap",
        ):
            with self.subTest(edge=edge):
                self.assertFinding("VIOLATION", "(repository)", edge)
        self.assertEqual(
            sum(line.startswith("VIOLATION (repository)") for line in self.findings()), 1
        )

    def test_contract_missing_only_an_absent_boundary_is_review(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().replace('    "my_service.workers",\n', "", 1)
        )
        self.assertFinding("REVIEW", "(repository)", "application → workers")

    def test_contract_missing_one_forbidden_module(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().replace('    "my_service.db",\n', "", 1)
        )
        self.assertFinding("VIOLATION", "(repository)", "unforbidden: application → db")

    def test_missing_api_contract_is_reported(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().rsplit("[[tool.importlinter.contracts]]", 1)[0]
        )
        self.assertFinding("VIOLATION", "(repository)", "api → db")

    def test_contract_name_alone_is_not_enforcement(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().replace(
                'forbidden_modules = ["my_service.bootstrap"]',
                'forbidden_modules = ["my_service.config"]',
            )
        )
        self.assertFinding("VIOLATION", "(repository)", "api → bootstrap")

    def test_layers_contract_is_recognized(self) -> None:
        pyproject = self.member / "pyproject.toml"
        roots_only = pyproject.read_text().partition("[[tool.importlinter.contracts]]")[
            0
        ]
        pyproject.write_text(
            roots_only
            + textwrap.dedent(
                """
                [[tool.importlinter.contracts]]
                name = "hexagon"
                type = "layers"
                containers = ["my_service"]
                layers = [
                    "bootstrap",
                    "api | workers | adapters | db | genai | config",
                    "application",
                    "observability",
                    "ports",
                    "domain",
                ]
                """
            )
        )
        self.assertClean()

    def test_ini_config_is_recognized(self) -> None:
        (self.member / "pyproject.toml").write_text('[project]\nname = "my-service"\n')
        contracts = "".join(
            f"\n[importlinter:contract:{index}]\ntype = forbidden\n"
            f"source_modules =\n{''.join(f'    my_service.{s}.**' + chr(10) for s in sources)}"
            f"forbidden_modules =\n{''.join(f'    my_service.{t}' + chr(10) for t in targets)}"
            for index, (_, sources, targets) in enumerate(
                audit_service.REQUIRED_CONTRACTS
            )
        )
        (self.member / ".importlinter").write_text(
            "[importlinter]\nroot_packages =\n    my_service\n    billing\n" + contracts
        )
        self.assertClean()

    def test_ini_config_without_contracts(self) -> None:
        (self.member / "pyproject.toml").write_text('[project]\nname = "my-service"\n')
        (self.member / ".importlinter").write_text(
            "[importlinter]\nroot_package = my_service\n"
        )
        self.assertFinding("VIOLATION", "(repository)", "domain → db")


class LibraryCase(unittest.TestCase):
    """A temporary workspace: `services/my-service` (the canonical service) and
    `libs/edm-client` (the canonical client library)."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)
        shutil.copytree(FIXTURE, self.workspace / "services/my-service")
        self.member = self.workspace / "libs/edm-client"
        shutil.copytree(LIBRARY_FIXTURE, self.member)
        self.package = self.member / "src/edm_client"

    def lib(self, relative: str, source: str) -> None:
        path = self.package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip())

    def findings(self, kind: str = "client", *, workspace: bool = True) -> list[str]:
        found = audit_service.audit_library(
            self.package,
            "edm_client",
            kind,
            self.workspace if workspace else None,
            None,
            audit_service.PURE_ALLOWED_EXTERNAL,
            set(),
        )
        return [finding.render() for finding in found]

    def assertFinding(
        self, severity: str, path: str, fragment: str, kind: str = "client"
    ) -> None:
        rendered = self.findings(kind)
        prefix = f"{severity} {path}:"
        matches = [
            line for line in rendered if line.startswith(prefix) and fragment in line
        ]
        self.assertTrue(
            matches, f"no {prefix} ... {fragment!r} in:\n" + "\n".join(rendered)
        )

    def assertClean(self, kind: str = "client") -> None:
        rendered = self.findings(kind)
        self.assertEqual(rendered, [], "\n".join(rendered))


class CanonicalLibraryTests(LibraryCase):
    def test_canonical_library_is_clean(self) -> None:
        self.assertClean()

    def test_cli_library_mode(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.package),
                "--library",
                "client",
                "--workspace",
                str(self.workspace),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("static checks passed; semantic audit pending", result.stdout)

    def test_without_known_services_asks_for_workspace(self) -> None:
        rendered = self.findings(workspace=False)
        self.assertTrue(
            any("no service packages known" in line for line in rendered), rendered
        )

    def test_documented_example_matches_fixture(self) -> None:
        """The client library in shared-libraries.md is this fixture, so the two cannot drift."""
        doc = (
            SKILLS / "python-service-architecture/references/shared-libraries.md"
        ).read_text()
        blocks = re.findall(
            r"```python\n# libs/edm-client/src/edm_client/(\S+)\n(.*?)```",
            doc,
            re.DOTALL,
        )
        self.assertEqual(
            sorted(name for name, _ in blocks),
            ["__init__.py", "client.py", "errors.py", "models.py"],
        )
        for name, body in blocks:
            with self.subTest(module=name):
                self.assertEqual(body, (self.package / name).read_text())


class LibraryRuleTests(LibraryCase):
    def test_imports_service_package(self) -> None:
        self.lib("hooks.py", "from my_service.domain.submissions import Selection\n")
        self.assertFinding(
            "VIOLATION", "hooks.py", "imports service package my_service"
        )

    def test_reads_environment(self) -> None:
        for source in (
            "import os\nURL = os.environ['EDM_URL']\n",
            "from os import getenv\n",
        ):
            with self.subTest(source=source):
                self.lib("settings.py", source)
                self.assertFinding("VIOLATION", "settings.py", "reads the environment")

    def test_imports_pydantic_settings(self) -> None:
        self.lib("settings.py", "from pydantic_settings import BaseSettings\n")
        self.assertFinding("VIOLATION", "settings.py", "pydantic_settings")

    def test_configures_logging(self) -> None:
        self.lib("log.py", "import logging\nlogging.basicConfig(level=logging.INFO)\n")
        self.assertFinding("VIOLATION", "log.py", "configures logging")

    def test_adds_handler(self) -> None:
        self.lib(
            "log.py",
            """
            import logging
            logging.getLogger("edm_client").addHandler(logging.StreamHandler())
            """,
        )
        self.assertFinding("VIOLATION", "log.py", "adds a logging handler")

    def test_null_handler_is_allowed(self) -> None:
        self.lib(
            "log.py",
            """
            import logging
            logging.getLogger("edm_client").addHandler(logging.NullHandler())
            """,
        )
        self.assertClean()

    def test_otel_sdk_outside_observability(self) -> None:
        self.lib("tracing.py", "from opentelemetry.sdk.trace import TracerProvider\n")
        self.assertFinding("VIOLATION", "tracing.py", "OpenTelemetry SDK")
        self.assertClean(kind="observability")

    def test_langchain_outside_genai(self) -> None:
        self.lib("llm.py", "from langchain_core.language_models import BaseChatModel\n")
        self.assertFinding("VIOLATION", "llm.py", "only a genai library")
        self.assertClean(kind="genai")

    def test_contract_library_is_pure(self) -> None:
        self.assertFinding(
            "VIOLATION", "client.py", "contract library imports httpx", "contract"
        )

    def test_persistence_library_owns_metadata_only(self) -> None:
        self.lib(
            "engine.py", "from sqlalchemy.ext.asyncio import create_async_engine\n"
        )
        self.assertFinding("VIOLATION", "engine.py", "session or engine", "persistence")

    def test_relative_import(self) -> None:
        self.lib("extra.py", "from .models import Document\n")
        self.assertFinding("VIOLATION", "extra.py", "relative import")


class LibraryShapeTests(LibraryCase):
    def test_generic_name(self) -> None:
        package = self.member / "src/common"
        self.package.rename(package)
        found = audit_service.audit_library(
            package, "common", "client", self.workspace, None, set(), set()
        )
        self.assertTrue(any("named only 'common'" in item.render() for item in found))

    def test_missing_py_typed(self) -> None:
        (self.package / "py.typed").unlink()
        self.assertFinding("REVIEW", "(package)", "py.typed")

    def test_service_shell(self) -> None:
        self.lib("main.py", "def main() -> None: ...\n")
        self.assertFinding("VIOLATION", "main.py", "service shell")

    def test_speculative_package(self) -> None:
        self.lib("interfaces/__init__.py", "")
        self.lib("interfaces/client.py", "class ClientLike: ...\n")
        self.assertFinding("REVIEW", "interfaces/", "speculative interfaces/")

    def test_init_defines_code(self) -> None:
        self.lib("__init__.py", "def helper() -> None: ...\n")
        self.assertFinding("REVIEW", "__init__.py", "__init__.py defines helper")


class LibraryConsumerTests(LibraryCase):
    def test_consumer_imports_private_name(self) -> None:
        consumer = self.workspace / "services/my-service/src/my_service/db/edm.py"
        consumer.write_text("from edm_client.client import _retry_after\n")
        self.assertFinding(
            "REVIEW", "services/my-service/src/my_service/db/edm.py", "_retry_after"
        )

    def test_consumer_imports_public_root(self) -> None:
        consumer = self.workspace / "services/my-service/src/my_service/db/edm.py"
        consumer.write_text("from edm_client import EdmClient\n")
        self.assertClean()


class LibraryContractTests(LibraryCase):
    def test_contract_missing_service(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace('"my_service", ', ""))
        self.assertFinding("VIOLATION", "(repository)", "edm_client → my_service")

    def test_contract_missing_pydantic_settings(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace(', "pydantic_settings"', ""))
        self.assertFinding(
            "VIOLATION", "(repository)", "edm_client → pydantic_settings"
        )

    def test_no_contracts(self) -> None:
        (self.member / "pyproject.toml").write_text('[project]\nname = "edm-client"\n')
        self.assertFinding("VIOLATION", "(repository)", "no import-linter contracts")


class RobustnessTests(AuditCase):
    def test_unparseable_module_is_reported(self) -> None:
        self.pkg("domain/broken.py", "def (:\n")
        rendered = self.findings()
        self.assertTrue(
            any("cannot parse module" in line for line in rendered), rendered
        )


class RuleCitationTests(unittest.TestCase):
    """Every rule the script cites must name a heading that exists, so docs and script
    cannot drift apart silently."""

    def test_every_cited_section_exists(self) -> None:
        rules = {
            value
            for name, value in vars(audit_service).items()
            if name.startswith("R_") and isinstance(value, str)
        }
        self.assertTrue(rules)
        for rule in sorted(rules):
            with self.subTest(rule=rule):
                target, _, section = rule.partition("#")
                path = SKILLS / target
                if path.is_dir():
                    path /= "SKILL.md"
                self.assertTrue(path.is_file(), f"{rule}: {path} does not exist")
                if section:
                    headings = {
                        match.group(1).replace("`", "").strip()
                        for match in re.finditer(
                            r"^#+\s+(.+)$", path.read_text(), re.MULTILINE
                        )
                    }
                    self.assertIn(
                        section, headings, f"{rule}: no such heading in {path.name}"
                    )


if __name__ == "__main__":
    unittest.main()
