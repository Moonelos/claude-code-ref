"""Findings, parsed modules, and loading a package from disk."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from service_audit.rules import SKIPPED_DIRS, Severity


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    message: str
    rule: str
    severity: Severity = "VIOLATION"

    def render(self) -> str:
        return f"{self.severity} {self.path}:{self.line}: {self.message} [{self.rule}]"


@dataclass(frozen=True)
class Module:
    path: Path
    display: str
    owner: str | None
    source: str
    tree: ast.Module


def review(module: Module, line: int, message: str, rule: str) -> Finding:
    return Finding(module.display, line, message, rule, "REVIEW")


def violation(module: Module, line: int, message: str, rule: str) -> Finding:
    return Finding(module.display, line, message, rule, "VIOLATION")


def python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if (
            not SKIPPED_DIRS.intersection(path.parts)
            and "site-packages" not in path.parts
        ):
            yield path


def boundary_for(path: Path, root: Path) -> str | None:
    relative = path.relative_to(root)
    return relative.parts[0] if len(relative.parts) > 1 else None


def load_modules(root: Path) -> tuple[list[Module], list[Finding]]:
    modules: list[Module] = []
    failures: list[Finding] = []
    for path in python_files(root):
        display = str(path.relative_to(root))
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            failures.append(
                Finding(
                    display,
                    exc.lineno or 0,
                    f"cannot parse module: {exc.msg}",
                    "syntax",
                )
            )
            continue
        modules.append(Module(path, display, boundary_for(path, root), source, tree))
    return modules, failures
