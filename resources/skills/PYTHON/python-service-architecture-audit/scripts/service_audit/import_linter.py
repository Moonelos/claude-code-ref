"""Reading import-linter configs and checking the contracts they declare."""

from __future__ import annotations

import configparser
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import tomllib

from service_audit.model import Finding
from service_audit.rules import APPLICATION_BOUNDARIES, R_CONTRACTS, REQUIRED_CONTRACTS


@dataclass(frozen=True)
class ImportLinterConfig:
    roots: set[str]
    # One dict per contract, keys as in the config: type, source_modules, layers, ...
    contracts: list[dict[str, object]]


def ini_list(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def importlinter_config(directory: Path) -> ImportLinterConfig | None:
    """The import-linter config in `directory`, or None if it has none."""
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        try:
            config = (
                tomllib.loads(pyproject.read_text()).get("tool", {}).get("importlinter")
            )
        except tomllib.TOMLDecodeError:
            config = None
        if config is not None:
            roots = {
                *config.get("root_packages", []),
                config.get("root_package", ""),
            } - {""}
            return ImportLinterConfig(roots, list(config.get("contracts", [])))
    for name in (".importlinter", "setup.cfg"):
        parser = configparser.ConfigParser()
        if (
            (directory / name).is_file()
            and parser.read(directory / name)
            and parser.has_section("importlinter")
        ):
            section = parser["importlinter"]
            listed = (
                f"{section.get('root_packages', '')} {section.get('root_package', '')}"
            )
            contracts: list[dict[str, object]] = [
                {
                    key: ini_list(value) if "\n" in value else value.strip()
                    for key, value in body.items()
                }
                for title, body in parser.items()
                if title.startswith("importlinter:contract:")
            ]
            return ImportLinterConfig(set(listed.split()), contracts)
    return None


def as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value] if isinstance(value, list) else []


def module_pattern(pattern: str) -> re.Pattern[str]:
    """import-linter wildcards: `*` is one segment, `**` is one or more."""
    segments = {"*": r"[^.]+", "**": r"[^.]+(?:\.[^.]+)*"}
    parts = (segments.get(part, re.escape(part)) for part in pattern.split("."))
    return re.compile(r"\.".join(parts) + r"\Z")


def covers_package(patterns: list[str], module: str) -> bool:
    """True if one pattern names `module` or all of its descendants (contracts act on packages)."""
    return any(
        module_pattern(pattern).match(candidate)
        for pattern in patterns
        for candidate in (module, f"{module}._")
    )


def forbidden_edges(
    contract: dict[str, object],
) -> Iterator[tuple[list[str], list[str]]]:
    """(importers, imported) pairs a contract forbids, from its modules, not its name."""
    kind = contract.get("type")
    if kind == "forbidden":
        yield (
            as_list(contract.get("source_modules")),
            as_list(contract.get("forbidden_modules")),
        )
    elif kind == "layers":
        containers = as_list(contract.get("containers")) or [""]
        for container in containers:
            prefix = f"{container}." if container else ""
            levels: list[tuple[list[str], bool]] = []
            for entry in as_list(contract.get("layers")):
                independent = "|" in entry
                names = re.split(r"[|:]", entry)
                levels.append(
                    ([prefix + name.strip(" ()") for name in names], independent)
                )
            for index, (higher, independent) in enumerate(levels):
                for lower, _ in levels[index + 1 :]:
                    yield lower, higher
                if independent:
                    for sibling in higher:
                        yield [sibling], [other for other in higher if other != sibling]


def missing_contract_findings(
    config: ImportLinterConfig, package: str, root: Path | None = None
) -> Iterator[Finding]:
    """One finding for every unforbidden edge; the contracts name every canonical
    boundary, including ones the service does not have yet."""
    edges = [
        edge for contract in config.contracts for edge in forbidden_edges(contract)
    ]
    missing: list[tuple[str, str]] = [
        (source, target)
        for _invariant, sources, targets in REQUIRED_CONTRACTS
        for source in sources
        for target in targets
        if not any(
            covers_package(importers, f"{package}.{source}")
            and covers_package(imported, f"{package}.{target}")
            for importers, imported in edges
        )
    ]
    if not missing:
        return

    def exists(boundary: str) -> bool:
        return (
            root is None
            or (root / boundary).is_dir()
            or (root / f"{boundary}.py").is_file()
        )

    unforbidden = ", ".join(f"{source} → {target}" for source, target in missing)
    if any(exists(source) and exists(target) for source, target in missing):
        message = (
            f"import-linter contracts for {package} leave unforbidden: {unforbidden}"
        )
        yield Finding("(repository)", 0, message, R_CONTRACTS, "VIOLATION")
    else:
        message = (
            f"import-linter contracts for {package} omit boundaries that do not exist "
            f"yet ({unforbidden}); list them so the rule holds when one is created"
        )
        yield Finding("(repository)", 0, message, R_CONTRACTS, "REVIEW")


def missing_independence_findings(
    config: ImportLinterConfig, package: str, services: set[str], kind: str = "client"
) -> Iterator[Finding]:
    """Forbid deployables, plus settings dependencies outside configuration libraries."""
    edges = [
        edge for contract in config.contracts for edge in forbidden_edges(contract)
    ]
    missing = [
        target
        for target in (
            *sorted(services),
            *(() if kind == "configuration" else ("pydantic_settings",)),
        )
        if not any(
            covers_package(importers, package) and covers_package(imported, target)
            for importers, imported in edges
        )
    ]
    if missing:
        message = (
            f"no import-linter independence contract for library {package}: "
            f"unforbidden {', '.join(f'{package} → {target}' for target in missing)}"
        )
        yield Finding("(repository)", 0, message, R_CONTRACTS, "VIOLATION")


def is_migration_runner(root: Path) -> bool:
    """A member owning Alembic with no application boundary (repo-layout.md, "Monorepo")."""
    member = root.parent.parent if root.parent.name == "src" else root.parent
    return (member / "alembic.ini").is_file() and not any(
        (root / boundary).exists() or (root / f"{boundary}.py").exists()
        for boundary in APPLICATION_BOUNDARIES
    )


def contract_findings(
    root: Path,
    package: str,
    workspace: Path | None,
    missing: Callable[[ImportLinterConfig], Iterator[Finding]] | None = None,
) -> Iterator[Finding]:
    """The import-linter contracts from python-repository-setup, found upward from the package.

    `missing` checks the contracts themselves; the default checks the service invariants."""
    if missing is None and is_migration_runner(root):
        return  # no application code, so none of the service contracts apply
    for directory in root.parents:
        config = importlinter_config(directory)
        if config is not None:
            if package not in config.roots:
                message = (
                    f"import-linter config in {directory.name}/ does not list {package}"
                )
                yield Finding("(repository)", 0, message, R_CONTRACTS, "VIOLATION")
            elif missing is not None:
                yield from missing(config)
            else:
                yield from missing_contract_findings(config, package, root)
            precommit = directory / ".pre-commit-config.yaml"
            if not precommit.is_file() or "lint-imports" not in precommit.read_text():
                message = (
                    "import-linter config found but no lint-imports pre-commit hook"
                )
                yield Finding("(repository)", 0, message, R_CONTRACTS, "REVIEW")
            return
        if directory == workspace or (directory / ".git").exists():
            break
    message = (
        f"no import-linter contracts for {package}; architecture rules are not enforced"
    )
    yield Finding("(repository)", 0, message, R_CONTRACTS, "VIOLATION")
