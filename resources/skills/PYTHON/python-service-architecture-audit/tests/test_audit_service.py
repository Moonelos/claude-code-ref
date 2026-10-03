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
_spec.loader.exec_module(audit_service)  # also puts scripts/ on sys.path

from service_audit import rules as rules_module  # noqa: E402
from service_audit.rules import REQUIRED_CONTRACTS  # noqa: E402


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
        self.assertFinding(
            "VIOLATION", "domain/logs.py", "external technology structlog"
        )

    def test_workers_do_not_import_concrete_integrations(self) -> None:
        self.pkg(
            "workers/orders.py",
            "from my_service.db.submissions import SqlSubmissionStore\n",
        )
        self.assertFinding("VIOLATION", "workers/orders.py", "workers imports db")

    def test_application_does_not_import_workers(self) -> None:
        self.pkg("application/bad.py", "from my_service.workers import runtime\n")
        self.assertFinding(
            "VIOLATION", "application/bad.py", "application imports workers"
        )

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
            "REVIEW",
            "bootstrap/supervisor.py",
            "binds application action submit_investigation",
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

    def test_entry_points_reject_config(self) -> None:
        for boundary in ("api", "workers"):
            with self.subTest(boundary=boundary):
                self.pkg(f"{boundary}/settings_reader.py", "from my_service import config\n")
                self.assertFinding(
                    "VIOLATION", f"{boundary}/settings_reader.py", f"{boundary} imports config"
                )

    def test_adapters_reach_other_integrations_only_through_ports(self) -> None:
        for boundary in ("db", "genai", "application"):
            with self.subTest(boundary=boundary):
                self.pkg("adapters/reach.py", f"from my_service import {boundary}\n")
                self.assertFinding(
                    "VIOLATION", "adapters/reach.py", f"adapters imports {boundary}"
                )

    def test_adapters_may_import_ports_domain_and_worker_inbox(self) -> None:
        self.pkg("adapters/fine.py", "from my_service import domain, ports, workers\n")
        self.assertClean()

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
    def test_bootstrap_function_building_many_collaborators(self) -> None:
        body = "".join(f"    x{i} = Store{i}(engine=build_engine{i}())\n" for i in range(5))
        self.pkg("bootstrap/big.py", f"def build() -> None:\n{body}")
        self.assertFinding(
            "REVIEW", "bootstrap/big.py", "bootstrap function build constructs 10 collaborators"
        )

    def test_long_bootstrap_function_with_few_collaborators_is_clean(self) -> None:
        # runtime() stays one flat function, however long, below ~10 collaborators.
        body = "".join(f"    x{i} = {i}\n" for i in range(120))
        body += "".join(f"    s{i} = Store{i}()\n" for i in range(9))
        body += "    return Runtime(a=s0, b=s1)\n"
        self.pkg("bootstrap/medium.py", f"def build() -> Runtime:\n{body}")
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


class DbLayoutTests(AuditCase):
    def test_capability_without_contract(self) -> None:
        self.pkg("db/orders.py", "class SqlOrderStore:\n    pass\n")
        self.assertFinding("REVIEW", "db/orders.py", "matches no port module or Protocol")

    def test_shared_root_and_suffixed_implementation_are_clean(self) -> None:
        self.pkg("db/engine.py", "def build_engine() -> None: ...\n")
        self.pkg("db/submissions_legacy.py", "class LegacySubmissionStore:\n    pass\n")
        self.assertClean()

    def test_promoted_capability_is_clean(self) -> None:
        source = (self.package / "db/submissions.py").read_text()
        (self.package / "db/submissions.py").unlink()
        self.pkg("db/submissions/__init__.py", "")
        self.pkg("db/submissions/store.py", source)
        self.pkg("db/submissions/rows.py", "ROW_LIMIT = 1\n")
        self.assertClean()

    def test_subpackage_without_store(self) -> None:
        self.pkg("db/submissions/__init__.py", "")
        self.pkg("db/submissions/reads.py", "VALUE = 1\n")
        self.pkg("db/submissions/writes.py", "VALUE = 2\n")
        self.assertFinding("REVIEW", "db/submissions/", "has no store.py")

    def test_one_module_subpackage(self) -> None:
        self.pkg("db/submissions_archive/__init__.py", "")
        self.pkg("db/submissions_archive/store.py", "class SqlArchive:\n    pass\n")
        self.assertFinding(
            "REVIEW", "db/submissions_archive/store.py", "one-module db/ subpackage"
        )

    def test_capability_named_after_protocol_is_clean(self) -> None:
        self.pkg(
            "ports/submissions.py",
            (self.package / "ports/submissions.py").read_text()
            + "\n\nclass WorkQueue(Protocol):\n    async def claim(self) -> None: ...\n",
        )
        self.pkg(
            "db/queue.py", "class PgWorkQueue:\n    async def claim(self) -> None: ...\n"
        )
        rendered = self.findings()
        self.assertFalse(
            any("db/queue.py" in line for line in rendered), "\n".join(rendered)
        )

    def test_shared_helper_used_by_two_capabilities_is_clean(self) -> None:
        self.pkg("ports/orders.py", "VALUE = 1\n")
        self.pkg("db/fencing.py", "def fence() -> None: ...\n")
        self.pkg("db/orders.py", "from my_service.db.fencing import fence\n")
        self.pkg(
            "db/submissions.py",
            "from my_service.db.fencing import fence\n"
            + (self.package / "db/submissions.py").read_text(),
        )
        rendered = self.findings()
        self.assertFalse(
            any("db/fencing.py" in line or "imports capability" in line for line in rendered),
            "\n".join(rendered),
        )

    def test_shared_helper_used_by_one_capability(self) -> None:
        self.pkg("db/owners.py", "def owner() -> None: ...\n")
        self.pkg(
            "db/submissions.py",
            "from my_service.db.owners import owner\n"
            + (self.package / "db/submissions.py").read_text(),
        )
        self.assertFinding("REVIEW", "db/owners.py", "used only by submissions")

    def test_import_between_capabilities(self) -> None:
        self.pkg("ports/orders.py", "VALUE = 1\n")
        self.pkg("db/orders.py", "from my_service.db.submissions import SqlSubmissionStore\n")
        self.assertFinding(
            "REVIEW", "db/orders.py", "capability orders imports capability submissions"
        )

    def test_import_of_shared_root_module_is_not_a_capability_import(self) -> None:
        self.pkg("ports/orders.py", "VALUE = 1\n")
        self.pkg("db/orders.py", "from my_service.db import transactions\n")
        rendered = self.findings()
        self.assertFalse(
            any("imports capability" in line for line in rendered), "\n".join(rendered)
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
        self.assertFalse(
            any("only declares __call__" in line for line in rendered), rendered
        )

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

    def test_prescribed_worker_inbox_is_not_a_single_implementation_notice(
        self,
    ) -> None:
        self.pkg(
            "workers/inbox.py",
            """
            from typing import Protocol

            class Inbox(Protocol):
                async def receive(self) -> list[str]: ...
                async def settle(self, message: str) -> None: ...
            """,
        )
        self.pkg(
            "adapters/sqs_inbox.py",
            """
            class SqsInbox:
                async def receive(self) -> list[str]:
                    return []

                async def settle(self, message: str) -> None:
                    return None
            """,
        )
        rendered = self.findings()
        self.assertFalse(
            any("Protocol Inbox has one implementation" in line for line in rendered),
            rendered,
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
        self.pkg("genai/a/llms.py", source)
        self.pkg("genai/b/llms.py", source)
        self.assertFinding("REVIEW", "genai/a/llms.py", "identical genai llms.py bodies")

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
            "adapters/one.py",
            'def _clean(x: str) -> str:\n    return x.strip() or "-"\n',
        )
        self.pkg(
            "adapters/two.py",
            'def _clean(x: str) -> str:\n    return x.lower() or "-"\n',
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

    def test_identical_classification_bases_are_expected(self) -> None:
        source = (self.package / "ports/errors.py").read_text()
        self.write("../other_service/src/other/ports/errors.py", source)
        found = audit_service.audit(
            self.package,
            "my_service",
            self.member.parent,
            self.member / "tests",
            audit_service.PURE_ALLOWED_EXTERNAL,
        )
        messages = [f.render() for f in found if "byte-identical copy" in f.render()]
        self.assertEqual(messages, [])


class ArchitectureContractTests(AuditCase):
    def test_missing_contracts(self) -> None:
        (self.member / "pyproject.toml").write_text('[project]\nname = "my-service"\n')
        self.assertFinding("VIOLATION", "(repository)", "no import-linter contracts")

    def test_migration_runner_needs_no_service_contracts(self) -> None:
        (self.member / "pyproject.toml").write_text('[project]\nname = "my-service"\n')
        (self.member / "alembic.ini").write_text("[alembic]\n")
        shutil.rmtree(self.package)
        self.pkg("__init__.py", "")
        self.pkg("main.py", "def main() -> None: ...\n")
        self.pkg("db/__init__.py", "")
        self.assertNotIn("no import-linter contracts", "\n".join(self.findings()))

    def test_alembic_inside_package_may_run_sql(self) -> None:
        self.pkg(
            "alembic/env.py",
            """
            from sqlalchemy import text


            def run(connection: object) -> None:
                connection.execute(text("SET lock_timeout = '5s'"))
            """,
        )
        self.assertNotIn("alembic/env.py", "\n".join(self.findings()))

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
            sum(line.startswith("VIOLATION (repository)") for line in self.findings()),
            1,
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
            for index, (_, sources, targets) in enumerate(REQUIRED_CONTRACTS)
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
    `libs/docstore-client` (the canonical client library)."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)
        shutil.copytree(FIXTURE, self.workspace / "services/my-service")
        self.member = self.workspace / "libs/docstore-client"
        shutil.copytree(LIBRARY_FIXTURE, self.member)
        self.package = self.member / "src/docstore_client"

    def lib(self, relative: str, source: str) -> None:
        path = self.package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip())

    def findings(self, kind: str = "client", *, workspace: bool = True) -> list[str]:
        found = audit_service.audit_library(
            self.package,
            "docstore_client",
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

    def test_documented_example_links_fixture(self) -> None:
        """shared-libraries.md documents this fixture by linking each module, not copying it."""
        doc = (
            SKILLS / "python-service-architecture/references/shared-libraries.md"
        ).read_text()
        linked = re.findall(
            r"\]\(\.\./assets/canonical_library/src/docstore_client/([^)\s]+)\)", doc
        )
        self.assertEqual(
            sorted(set(linked)), ["__init__.py", "client.py", "errors.py", "models.py"]
        )
        for name in linked:
            with self.subTest(module=name):
                self.assertTrue((self.package / name).is_file())
        self.assertNotIn("# libs/docstore-client/src/docstore_client/", doc)


class LibraryRuleTests(LibraryCase):
    def test_imports_service_package(self) -> None:
        self.lib("hooks.py", "from my_service.domain.submissions import Selection\n")
        self.assertFinding(
            "VIOLATION", "hooks.py", "imports service package my_service"
        )

    def test_reads_environment(self) -> None:
        for source in (
            "import os\nURL = os.environ['DOCSTORE_URL']\n",
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
            logging.getLogger("docstore_client").addHandler(logging.StreamHandler())
            """,
        )
        self.assertFinding("VIOLATION", "log.py", "adds a logging handler")

    def test_null_handler_is_allowed(self) -> None:
        self.lib(
            "log.py",
            """
            import logging
            logging.getLogger("docstore_client").addHandler(logging.NullHandler())
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


class ConfigurationLibraryTests(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        for name in ("client.py", "models.py", "errors.py"):
            (self.package / name).unlink()
        self.lib("__init__.py", "")
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace(', "pydantic_settings"', ""))
        self.lib(
            "sources.py",
            """
            from pathlib import Path
            from pydantic_settings import BaseSettings, YamlConfigSettingsSource

            def yaml_source(settings_cls: type[BaseSettings], path: Path) -> YamlConfigSettingsSource:
                return YamlConfigSettingsSource(settings_cls, yaml_file=path)
        """,
        )

    def test_source_construction_and_service_import_are_allowed(self) -> None:
        consumer = (
            self.workspace / "services/my-service/src/my_service/config/loading.py"
        )
        consumer.write_text("from docstore_client import yaml_source\n")
        self.assertClean("configuration")

    def test_cli_configuration_kind(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.package),
                "--library",
                "configuration",
                "--workspace",
                str(self.workspace),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("static checks passed", result.stdout)

    def test_configuration_still_forbids_environment_and_service_imports(self) -> None:
        self.lib(
            "bad.py",
            "import os\nfrom my_service.config.settings import Settings\nVALUE = os.getenv('SECRET')\n",
        )
        self.assertFinding(
            "VIOLATION", "bad.py", "reads the environment", "configuration"
        )
        self.assertFinding(
            "VIOLATION", "bad.py", "imports service package", "configuration"
        )

    def test_settings_schema_is_forbidden_including_aliases(self) -> None:
        for source in (
            "from pydantic_settings import BaseSettings\nclass Settings(BaseSettings): pass\n",
            "from pydantic_settings import BaseSettings as BS\nclass Settings(BS): pass\n",
            "import pydantic_settings as ps\nclass Settings(ps.BaseSettings): pass\n",
        ):
            with self.subTest(source=source):
                self.lib("settings.py", source)
                self.assertFinding(
                    "VIOLATION",
                    "settings.py",
                    "defines a service settings schema",
                    "configuration",
                )

    def test_wrong_importer_including_boundary_init_is_forbidden(self) -> None:
        for layer in ("db", "application"):
            consumer = (
                self.workspace
                / f"services/my-service/src/my_service/{layer}/__init__.py"
            )
            consumer.write_text("from docstore_client import yaml_source\n")
            self.assertFinding(
                "VIOLATION",
                str(consumer.relative_to(self.workspace)),
                "outside allowed layers",
                "configuration",
            )

    def test_service_independence_contract_is_still_required(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().replace('"my_service"', '"other_service"')
        )
        self.assertFinding(
            "VIOLATION", "(repository)", "docstore_client → my_service", "configuration"
        )


class DatabaseRuntimeExceptionTests(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        other = self.workspace / "services/other/src/other_service"
        other.mkdir(parents=True)
        (other / "__init__.py").write_text("")
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text().replace(
                '"my_service",', '"my_service", "other_service",'
            )
        )
        self.lib(
            "engine.py", "from sqlalchemy.ext.asyncio import create_async_engine\n"
        )

    def declare(
        self,
        *,
        package: str = "docstore_client",
        consumers: str = '["my_service", "other_service"]',
    ) -> None:
        pyproject = self.member / "pyproject.toml"
        with pyproject.open("a") as stream:
            stream.write(
                f'\n[tool.service-audit.library-exception]\npackage = "{package}"\n'
                f'profile = "database-runtime"\nreason = "Shared transaction lifecycle"\nconsumers = {consumers}\n'
            )

    def test_exception_relaxes_engine_import_and_keeps_review(self) -> None:
        self.declare()
        found = self.findings("persistence")
        self.assertFalse(any(line.startswith("VIOLATION") for line in found), found)
        self.assertTrue(
            any(
                "exception applied" in line and "borrowed/owned" in line
                for line in found
            ),
            found,
        )

    def test_without_exception_persistence_remains_metadata_only(self) -> None:
        self.assertFinding("VIOLATION", "engine.py", "session or engine", "persistence")

    def test_invalid_declaration_does_not_relax_engine_imports(self) -> None:
        for consumers in (
            '["my_service"]',
            '["my_service", "my_service"]',
            '["my_service", "missing_service"]',
            "[1, 2]",
        ):
            with self.subTest(consumers=consumers):
                pyproject = self.member / "pyproject.toml"
                original = pyproject.read_text()
                self.declare(consumers=consumers)
                self.assertFinding(
                    "VIOLATION",
                    "(repository)",
                    "invalid database-runtime",
                    "persistence",
                )
                self.assertFinding(
                    "VIOLATION", "engine.py", "session or engine", "persistence"
                )
                pyproject.write_text(original)

    def test_exception_cannot_apply_to_another_package_or_kind(self) -> None:
        self.declare(package="another_package")
        self.assertFinding("VIOLATION", "engine.py", "session or engine", "persistence")
        self.assertFinding(
            "VIOLATION", "(repository)", "invalid database-runtime", "configuration"
        )

    def test_exception_preserves_settings_and_service_bans(self) -> None:
        self.declare()
        self.lib(
            "bad.py",
            "from pydantic_settings import BaseSettings\nfrom my_service.config import Settings\n",
        )
        self.assertFinding("VIOLATION", "bad.py", "pydantic_settings", "persistence")
        self.assertFinding(
            "VIOLATION", "bad.py", "imports service package", "persistence"
        )

    def test_exception_allows_db_and_bootstrap_but_not_application(self) -> None:
        self.declare()
        for layer in ("db", "bootstrap"):
            consumer = (
                self.workspace
                / f"services/my-service/src/my_service/{layer}/runtime.py"
            )
            consumer.write_text("from docstore_client import Database\n")
        self.assertFalse(
            any(line.startswith("VIOLATION") for line in self.findings("persistence"))
        )
        consumer = (
            self.workspace
            / "services/my-service/src/my_service/application/__init__.py"
        )
        consumer.write_text("from docstore_client import Database\n")
        self.assertFinding(
            "VIOLATION",
            str(consumer.relative_to(self.workspace)),
            "outside allowed layers",
            "persistence",
        )


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
        consumer = self.workspace / "services/my-service/src/my_service/db/docstore.py"
        consumer.write_text("from docstore_client.client import _retry_after\n")
        self.assertFinding(
            "REVIEW", "services/my-service/src/my_service/db/docstore.py", "_retry_after"
        )

    def test_consumer_imports_public_root(self) -> None:
        consumer = self.workspace / "services/my-service/src/my_service/db/docstore.py"
        consumer.write_text("from docstore_client import DocstoreClient\n")
        self.assertClean()


class LibraryContractTests(LibraryCase):
    def test_contract_missing_service(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace('"my_service", ', ""))
        self.assertFinding("VIOLATION", "(repository)", "docstore_client → my_service")

    def test_contract_missing_pydantic_settings(self) -> None:
        pyproject = self.member / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace(', "pydantic_settings"', ""))
        self.assertFinding(
            "VIOLATION", "(repository)", "docstore_client → pydantic_settings"
        )

    def test_no_contracts(self) -> None:
        (self.member / "pyproject.toml").write_text('[project]\nname = "docstore-client"\n')
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
            for name, value in vars(rules_module).items()
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


class ToolOnlyTests(AuditCase):
    def write_search(self) -> None:
        self.pkg(
            "ports/retrieval.py",
            """
            from typing import Protocol

            class EvidenceIndex(Protocol):
                async def search(self, *, query: str) -> tuple[str, ...]: ...
            """,
        )
        self.pkg(
            "application/search_documents.py",
            """
            from my_service.ports.retrieval import EvidenceIndex

            async def search_documents(*, index: EvidenceIndex, query: str) -> tuple[str, ...]:
                return await index.search(query=query)
            """,
        )
        self.pkg(
            "db/retrieval.py",
            """
            class PgvectorIndex:
                async def search(self, *, query: str) -> tuple[str, ...]:
                    return ()
            """,
        )
        self.pkg(
            "genai/tools.py",
            """
            from my_service.application.search_documents import search_documents
            from my_service.ports.retrieval import EvidenceIndex

            async def rag_search(*, index: EvidenceIndex, query: str) -> str:
                hits = await search_documents(index=index, query=query)
                return ",".join(hits)
            """,
        )

    def test_action_imported_only_by_genai(self) -> None:
        self.write_search()
        self.assertFinding(
            "REVIEW", "application/search_documents.py", "imported only by genai/"
        )
        self.assertFinding(
            "REVIEW", "ports/retrieval.py", "used only by tool-only actions"
        )

    def test_action_with_route_is_not_tool_only(self) -> None:
        self.write_search()
        self.pkg(
            "api/search.py",
            """
            from my_service.application.search_documents import search_documents

            async def search(*, index, query: str) -> tuple[str, ...]:
                return await search_documents(index=index, query=query)
            """,
        )
        rendered = self.findings()
        self.assertFalse(
            [line for line in rendered if "tool" in line and "only" in line],
            "\n".join(rendered),
        )


class GenaiConstructionTests(AuditCase):
    def test_literal_tuning_and_model_id(self) -> None:
        self.pkg(
            "genai/factory.py",
            """
            from langchain.chat_models import init_chat_model

            def build(*, region: str):
                return init_chat_model(
                    "anthropic.claude", region_name=region, reasoning_effort="low", max_tokens=512
                )
            """,
        )
        self.assertFinding("REVIEW", "genai/factory.py", "reasoning_effort='low' is hardcoded")
        self.assertFinding("REVIEW", "genai/factory.py", "max_tokens=512 is hardcoded")
        self.assertFinding("REVIEW", "genai/factory.py", "init_chat_model() model id is hardcoded")

    def test_hand_built_sdk_client(self) -> None:
        self.pkg(
            "genai/clients.py",
            """
            import asyncio

            async def open_client(*, session):
                return await asyncio.to_thread(session.client, "bedrock-runtime")
            """,
        )
        self.assertFinding("REVIEW", "genai/clients.py", "SDK client built by hand")

    def test_settings_driven_factory_is_clean(self) -> None:
        self.pkg(
            "genai/factory.py",
            """
            from langchain.chat_models import init_chat_model

            def build(*, settings):
                return init_chat_model(
                    settings.model_id,
                    model_provider="bedrock_converse",
                    reasoning_effort=settings.reasoning_effort,
                    max_tokens=settings.max_output_tokens,
                    disable_streaming=True,
                )
            """,
        )
        rendered = self.findings()
        self.assertFalse(
            [line for line in rendered if "genai/factory.py" in line], "\n".join(rendered)
        )


if __name__ == "__main__":
    unittest.main()
