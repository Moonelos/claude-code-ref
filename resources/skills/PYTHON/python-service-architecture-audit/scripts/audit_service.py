#!/usr/bin/env python3
"""Static candidate checks for a layered Python service package or internal library.

Every finding cites the rule that owns it. Hits are candidates to confirm by
reading the code, not verdicts; a clean run never replaces the semantic audit.

The checks live in the sibling `service_audit/` package; this file is the CLI
and the service-mode driver.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

# Importable however the script is loaded (direct run, importlib, another cwd).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from service_audit.cross_checks import (  # noqa: E402
    cross_member_findings,
    db_layout_findings,
    duplicate_llm_findings,
    duplicate_private_function_findings,
    protocol_findings,
    shared_literal_findings,
    single_module_adapter_findings,
    tool_only_findings,
    unused_port_findings,
)
from service_audit.import_linter import contract_findings  # noqa: E402
from service_audit.library import audit_library  # noqa: E402
from service_audit.model import Finding, load_modules  # noqa: E402
from service_audit.module_checks import audit_module  # noqa: E402
from service_audit.rules import LIBRARY_KINDS, PURE_ALLOWED_EXTERNAL  # noqa: E402


def default_tests_root(root: Path) -> Path | None:
    """`<member>/tests` for a `<member>/src/<package>` import root."""
    candidate = root.parent.parent / "tests"
    return candidate if root.parent.name == "src" and candidate.is_dir() else None


def audit(
    root: Path,
    package: str,
    workspace: Path | None,
    tests_root: Path | None,
    allowed: set[str],
) -> list[Finding]:
    modules, findings = load_modules(root)
    tests = load_modules(tests_root)[0] if tests_root is not None else []
    checks: Iterable[Iterator[Finding]] = (
        *(audit_module(module, package, allowed) for module in modules),
        contract_findings(root, package, workspace),
        unused_port_findings(modules, package),
        tool_only_findings(modules, package),
        protocol_findings(modules, tests),
        single_module_adapter_findings(root),
        db_layout_findings(root, modules, package),
        duplicate_llm_findings(modules),
        duplicate_private_function_findings(modules),
        shared_literal_findings(modules),
    )
    for check in checks:
        findings.extend(check)
    if workspace is not None:
        findings.extend(cross_member_findings(modules, root, workspace))
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package_root", type=Path, help="Import package directory, e.g. src/my_service"
    )
    parser.add_argument(
        "--package", help="Import package name; defaults to the directory name"
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Workspace root for cross-member duplicate checks",
    )
    parser.add_argument(
        "--tests",
        type=Path,
        help="Test directory searched for Protocol doubles; defaults to <member>/tests",
    )
    parser.add_argument(
        "--allow-external",
        action="append",
        default=[],
        metavar="PACKAGE",
        help=(
            "Extra third-party package domain/, ports/, and application/ (or a contract "
            "library) may import; repeatable"
        ),
    )
    parser.add_argument(
        "--library",
        choices=LIBRARY_KINDS,
        metavar="KIND",
        help=f"Audit an internal library of this kind instead of a service: {', '.join(LIBRARY_KINDS)}",
    )
    parser.add_argument(
        "--service-package",
        action="append",
        default=[],
        metavar="PACKAGE",
        help="Service import package a library must not import (besides services/*/src/*); repeatable",
    )
    args = parser.parse_args()
    root: Path = args.package_root.resolve()
    if not root.is_dir():
        parser.error(f"package root is not a directory: {root}")
    workspace: Path | None = args.workspace.resolve() if args.workspace else None
    tests_root: Path | None = (
        args.tests.resolve() if args.tests else default_tests_root(root)
    )
    allowed = PURE_ALLOWED_EXTERNAL | set(args.allow_external)
    package = args.package or root.name
    if args.library:
        findings = audit_library(
            root,
            package,
            args.library,
            workspace,
            tests_root,
            allowed,
            set(args.service_package),
        )
    else:
        findings = audit(root, package, workspace, tests_root, allowed)
    for finding in findings:
        print(finding.render())
    violations = sum(item.severity == "VIOLATION" for item in findings)
    reviews = len(findings) - violations
    if not findings:
        print("static checks passed; semantic audit pending")
        return 0
    print(
        f"static checks: {violations} violation candidate(s), {reviews} review notice(s)"
    )
    print("confirm each hit by reading the code; semantic audit pending")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
