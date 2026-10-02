"""Library mode: checks for an internal shared library."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import tomllib

from service_audit.ast_helpers import dotted_name, imports
from service_audit.cross_checks import (
    cross_member_findings,
    duplicate_private_function_findings,
)
from service_audit.import_linter import contract_findings, missing_independence_findings
from service_audit.model import (
    Finding,
    Module,
    load_modules,
    python_files,
    review,
    violation,
)
from service_audit.module_checks import module_shape_findings, pass_through_findings
from service_audit.rules import (
    ENVIRONMENT_READS,
    GENERIC_LIBRARY_NAMES,
    LANGCHAIN_ROOTS,
    LOGGING_CONFIG_CALLS,
    R_ASSERT,
    R_IMPORTS,
    R_LIB_API,
    R_LIB_CONFIG,
    R_LIB_ENFORCEMENT,
    R_LIB_EXCEPTION,
    R_LIB_FLAT,
    R_LIB_KINDS,
    R_LIB_RULES,
    R_LIB_SHAPE,
    SESSION_MODULES,
    SESSION_NAMES,
    SPECULATIVE_LIBRARY_PACKAGES,
)


def library_import_findings(
    module: Module,
    package: str,
    kind: str,
    allowed: set[str],
    services: set[str],
    *,
    database_runtime: bool = False,
) -> Iterator[Finding]:
    for name, names, level, line in imports(module.tree):
        if level:
            yield violation(module, line, "relative import (forbidden)", R_IMPORTS)
            continue
        root = name.split(".", maxsplit=1)[0]
        if root in services:
            message = f"library imports service package {root}"
            yield violation(module, line, message, R_LIB_RULES)
        if root == "pydantic_settings" and kind != "configuration":
            message = "library imports pydantic_settings; take explicit options instead"
            yield violation(module, line, message, R_LIB_RULES)
        if name == "os" and {"environ", "getenv", "environb"} & set(names):
            yield violation(module, line, "library reads the environment", R_LIB_RULES)
        if kind != "observability" and (
            name == "opentelemetry.sdk" or name.startswith("opentelemetry.sdk.")
        ):
            message = "only an observability library imports the OpenTelemetry SDK"
            yield violation(module, line, message, R_LIB_KINDS)
        if kind != "genai" and root.startswith(LANGCHAIN_ROOTS):
            message = f"only a genai library imports {root}"
            yield violation(module, line, message, R_LIB_KINDS)
        if (
            kind == "contract"
            and root != package
            and root not in sys.stdlib_module_names
            and root not in allowed
        ):
            message = f"contract library imports {root}; contracts use only the stdlib and pydantic"
            yield violation(module, line, message, R_LIB_KINDS)
        if (
            kind == "persistence"
            and not database_runtime
            and (name.startswith(SESSION_MODULES) or SESSION_NAMES.intersection(names))
        ):
            message = "persistence library imports session or engine machinery; it owns metadata only"
            yield violation(module, line, message, R_LIB_KINDS)


def library_body_findings(module: Module) -> Iterator[Finding]:
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Attribute) and dotted_name(node) in ENVIRONMENT_READS:
            yield violation(
                module, node.lineno, "library reads the environment", R_LIB_RULES
            )
        elif isinstance(node, ast.Assert):
            yield review(module, node.lineno, "assert in production code", R_ASSERT)
        elif isinstance(node, ast.Call):
            func = dotted_name(node.func)
            if func.split(".")[-1] in LOGGING_CONFIG_CALLS:
                message = f"library configures logging: {func}()"
                yield violation(module, node.lineno, message, R_LIB_RULES)
            elif (
                isinstance(node.func, ast.Attribute) and node.func.attr == "addHandler"
            ) and not (
                node.args
                and isinstance(node.args[0], ast.Call)
                and dotted_name(node.args[0].func).endswith("NullHandler")
            ):
                message = "library adds a logging handler; only NullHandler is allowed"
                yield violation(module, node.lineno, message, R_LIB_RULES)


def library_package_findings(root: Path, package: str) -> Iterator[Finding]:
    if package in GENERIC_LIBRARY_NAMES:
        message = f"library named only {package!r}; name it after its capability"
        yield Finding("(package)", 0, message, R_LIB_KINDS, "VIOLATION")
    if not (root / "py.typed").is_file():
        yield Finding(
            "(package)", 0, "library ships no py.typed marker", R_LIB_RULES, "REVIEW"
        )
    for shell in ("main.py", "bootstrap"):
        if (root / shell).exists():
            message = f"library has a service shell ({shell}); a process belongs under services/"
            yield Finding(shell, 0, message, R_LIB_SHAPE, "VIOLATION")
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        members = [
            path for path in directory.glob("*.py") if path.name != "__init__.py"
        ]
        if directory.name in SPECULATIVE_LIBRARY_PACKAGES and len(members) <= 1:
            message = (
                f"speculative {directory.name}/ package with {len(members)} module(s)"
            )
            yield Finding(f"{directory.name}/", 0, message, R_LIB_FLAT, "REVIEW")


def service_packages(workspace: Path | None) -> set[str]:
    """Import packages of deployables laid out as services/<name>/src/<package>/."""
    if workspace is None:
        return set()
    return {init.parent.name for init in workspace.glob("services/*/src/*/__init__.py")}


def private_import_findings(
    package: str, root: Path, workspace: Path, tests_root: Path | None
) -> Iterator[Finding]:
    """Consumers that import `_`-prefixed modules or names of the library."""
    member = root.parent.parent if root.parent.name == "src" else root
    for path in python_files(workspace):
        if path.is_relative_to(member) or (
            tests_root and path.is_relative_to(tests_root)
        ):
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for name, names, level, line in imports(tree):
            if level or not (name == package or name.startswith(f"{package}.")):
                continue
            private = [part for part in name.split(".")[1:] if part.startswith("_")]
            private += [
                item for item in names if item.startswith("_") and item[:2] != "__"
            ]
            if private:
                display = str(path.relative_to(workspace))
                message = f"imports private {package} name(s): {', '.join(private)}"
                yield Finding(display, line, message, R_LIB_API, "REVIEW")


def configuration_schema_findings(module: Module) -> Iterator[Finding]:
    """Resolve direct BaseSettings bases, including import aliases."""
    bases = {"pydantic_settings.BaseSettings"}
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ImportFrom) and node.module == "pydantic_settings":
            bases.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "BaseSettings"
            )
        elif isinstance(node, ast.Import):
            bases.update(
                f"{alias.asname or alias.name}.BaseSettings"
                for alias in node.names
                if alias.name == "pydantic_settings"
            )
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ClassDef) and any(
            dotted_name(base) in bases for base in node.bases
        ):
            yield violation(
                module,
                node.lineno,
                "configuration library defines a service settings schema",
                R_LIB_CONFIG,
            )


def database_runtime_exception(
    root: Path, package: str, kind: str, services: set[str], workspace: Path | None
) -> tuple[bool, list[Finding]]:
    """A member-local, named exception; invalid declarations never relax checks."""
    member = root.parent.parent if root.parent.name == "src" else root
    path = member / "pyproject.toml"
    if not path.is_file():
        return False, []
    try:
        config = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return False, [
            Finding(
                "(repository)",
                0,
                "cannot parse member pyproject.toml; no exception applied",
                R_LIB_EXCEPTION,
                "VIOLATION",
            )
        ]
    declaration = (
        config.get("tool", {}).get("service-audit", {}).get("library-exception")
    )
    if declaration is None:
        return False, []
    valid = isinstance(declaration, dict)
    if valid:
        consumers = declaration.get("consumers")
        reason = declaration.get("reason")
        valid = (
            kind == "persistence"
            and declaration.get("package") == package
            and declaration.get("profile") == "database-runtime"
            and isinstance(reason, str)
            and bool(reason.strip())
            and isinstance(consumers, list)
            and all(isinstance(item, str) and bool(item.strip()) for item in consumers)
            and len(set(consumers)) >= 2
            and (workspace is None or set(consumers) <= services)
        )
    if not valid:
        return False, [
            Finding(
                "(repository)",
                0,
                "invalid database-runtime exception: require matching persistence package, "
                "profile, reason and two current service consumers; no exception applied",
                R_LIB_EXCEPTION,
                "VIOLATION",
            )
        ]
    return True, [
        Finding(
            "(repository)",
            0,
            "database-runtime exception applied; review admission, technical versus business "
            "SQL, service-owned configuration, and borrowed/owned resource cleanup",
            R_LIB_EXCEPTION,
            "REVIEW",
        )
    ]


def consumer_placement_findings(
    package: str, workspace: Path, allowed_layers: set[str]
) -> Iterator[Finding]:
    """Check actual production imports, including boundary package markers."""
    for init in sorted(workspace.glob("services/*/src/*/__init__.py")):
        root = init.parent
        for path in python_files(root):
            try:
                tree = ast.parse(path.read_text(), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            relative = path.relative_to(root)
            layer = relative.parts[0].removesuffix(".py")
            for name, _names, level, line in imports(tree):
                if (
                    not level
                    and (name == package or name.startswith(f"{package}."))
                    and layer not in allowed_layers
                ):
                    yield Finding(
                        str(path.relative_to(workspace)),
                        line,
                        f"{package} imported outside allowed layers: {', '.join(sorted(allowed_layers))}",
                        R_LIB_KINDS,
                        "VIOLATION",
                    )


def audit_library(
    root: Path,
    package: str,
    kind: str,
    workspace: Path | None,
    tests_root: Path | None,
    allowed: set[str],
    extra_services: set[str],
) -> list[Finding]:
    modules, findings = load_modules(root)
    services = (service_packages(workspace) | extra_services) - {package}
    database_runtime, exception_findings = database_runtime_exception(
        root, package, kind, services, workspace
    )
    findings.extend(exception_findings)
    if not services:
        message = (
            "no service packages known; pass --workspace (services/*/src/*) or --service-package "
            "to verify the independence contract"
        )
        findings.append(
            Finding("(repository)", 0, message, R_LIB_ENFORCEMENT, "REVIEW")
        )
    checks: Iterable[Iterator[Finding]] = (
        *(
            library_import_findings(
                module,
                package,
                kind,
                allowed,
                services,
                database_runtime=database_runtime,
            )
            for module in modules
        ),
        *(library_body_findings(module) for module in modules),
        *(
            configuration_schema_findings(module)
            for module in modules
            if kind == "configuration"
        ),
        *(module_shape_findings(module) for module in modules),
        *(pass_through_findings(module) for module in modules),
        library_package_findings(root, package),
        contract_findings(
            root,
            package,
            workspace,
            lambda config: missing_independence_findings(
                config, package, services, kind
            ),
        ),
        duplicate_private_function_findings(modules),
    )
    for check in checks:
        findings.extend(check)
    if workspace is not None:
        if kind == "configuration" or database_runtime:
            layers = (
                {"config", "bootstrap"}
                if kind == "configuration"
                else {"db", "bootstrap"}
            )
            findings.extend(consumer_placement_findings(package, workspace, layers))
        findings.extend(private_import_findings(package, root, workspace, tests_root))
        findings.extend(cross_member_findings(modules, root, workspace))
    return sorted(set(findings))
