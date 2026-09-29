#!/usr/bin/env python3
"""Static candidate checks for a layered Python service package or internal library.

Every finding cites the rule that owns it. Hits are candidates to confirm by
reading the code, not verdicts; a clean run never replaces the semantic audit.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import hashlib
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomllib

Severity = Literal["VIOLATION", "REVIEW"]
MethodKey = tuple[str, tuple[str, ...]]

ARCH = "python-service-architecture/references"
CONV = "python-code-conventions"
R_DIRECTION = f"{ARCH}/boundaries.md#The core rule"
R_CONFIG = f"{ARCH}/boundaries.md#config/"
R_TELEMETRY = f"{ARCH}/boundaries.md#observability/"
R_PORTS = f"{ARCH}/boundaries.md#When a port earns its cost"
R_APPLICATION_PORTS = f"{ARCH}/boundaries.md#Application ports"
R_FLAT = f"{ARCH}/boundaries.md#Flat-first growth across boundaries"
R_OWNERSHIP = f"{ARCH}/boundaries.md#Errors and constants follow ownership"
R_ADAPTERS = f"{ARCH}/boundaries.md#Adapters and their placement"
R_REPOSITORIES = f"{ARCH}/boundaries.md#Repositories apply decisions"
R_NONDETERMINISM = f"{ARCH}/boundaries.md#Nondeterminism"
R_CONSTRUCTOR_CONTRACTS = f"{ARCH}/boundaries.md#Constructor contracts"
R_BOOTSTRAP = f"{ARCH}/boundaries.md#bootstrap/"
R_WORKERS = f"{ARCH}/api-and-workers.md#Long-running worker"
R_BROKER = f"{ARCH}/api-and-workers.md#SQS, Kafka, or another broker"
R_SHARED = f"{ARCH}/shared-libraries.md"
R_CONTRACTS = "python-repository-setup/references/pre-commit.md#Architecture contracts"
R_CLASSIFICATION = f"{ARCH}/errors.md#Classification bases"
R_PUBLIC_ERRORS = f"{ARCH}/api-and-workers.md#Public error mapping"
R_IMPORTS = f"{CONV}#Imports and package markers"
R_ASSERT = f"{CONV}#No assert in production"
R_WRAPPERS = f"{CONV}#Constructors and wrappers"
R_ESCAPE = f"{CONV}#Type escape hatches"
R_ONE_OWNER = f"{CONV}#One owner per semantics"
R_MAGIC = f"{CONV}#Magic values and constants"
R_LIB_SHAPE = f"{ARCH}/shared-libraries.md#A library is not a smaller service"
R_LIB_KINDS = f"{ARCH}/shared-libraries.md#Library kinds and importers"
R_LIB_RULES = f"{ARCH}/shared-libraries.md#Library rules"
R_LIB_FLAT = f"{ARCH}/shared-libraries.md#Flat first"
R_LIB_API = f"{ARCH}/shared-libraries.md#Public API and compatibility"
R_LIB_ENFORCEMENT = f"{ARCH}/shared-libraries.md#Enforcement"

LIBRARY_KINDS = (
    "contract",
    "client",
    "persistence",
    "observability",
    "genai",
    "testing",
)
GENERIC_LIBRARY_NAMES = {"base", "common", "core", "helpers", "shared", "utils"}
SPECULATIVE_LIBRARY_PACKAGES = {
    "factories",
    "implementations",
    "interfaces",
    "plugins",
    "schemas",
    "types",
}
ENVIRONMENT_READS = {"os.environ", "os.getenv", "os.environb"}
LOGGING_CONFIG_CALLS = {"basicConfig", "dictConfig", "fileConfig"}
LANGCHAIN_ROOTS = ("langchain", "langgraph")
SESSION_MODULES = (
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm.session",
    "sqlmodel.ext.asyncio",
)
SESSION_NAMES = {
    "AsyncSession",
    "Session",
    "async_sessionmaker",
    "create_async_engine",
    "create_engine",
    "sessionmaker",
}

INTERNAL_FORBIDDEN: dict[str, set[str]] = {
    "domain": {
        "adapters",
        "api",
        "application",
        "bootstrap",
        "config",
        "db",
        "genai",
        "observability",
        "ports",
        "workers",
    },
    "ports": {
        "adapters",
        "api",
        "application",
        "bootstrap",
        "config",
        "db",
        "genai",
        "observability",
        "workers",
    },
    # application may import the service's own observability helpers (not OTel types).
    "application": {"adapters", "api", "bootstrap", "config", "db", "genai", "workers"},
    "db": {"adapters", "api", "application", "bootstrap", "genai", "workers"},
    "genai": {"adapters", "api", "bootstrap", "db", "workers"},
    "api": {"bootstrap", "db", "adapters", "genai", "workers"},
    # workers/ is the non-HTTP entry-point boundary: loops and consumers.
    "workers": {"adapters", "api", "bootstrap", "config", "db", "genai"},
    "core": {
        "domain",
        "ports",
        "application",
        "api",
        "adapters",
        "db",
        "genai",
        "bootstrap",
        "config",
        "observability",
        "workers",
    },
    # adapters may import the inbound contract a worker declares (workers/).
    "adapters": {"api", "bootstrap"},
    "observability": {"api", "application", "bootstrap", "workers"},
}
# The per-service contracts in python-repository-setup (pre-commit.md, "Architecture
# contracts"): (invariant, source boundaries, boundaries they must not import).
REQUIRED_CONTRACTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "application uses only admitted inner dependencies",
        ("application",),
        ("adapters", "api", "bootstrap", "config", "db", "genai", "workers"),
    ),
    (
        "domain and ports are pure",
        ("domain", "ports"),
        (
            "adapters",
            "api",
            "application",
            "bootstrap",
            "config",
            "db",
            "genai",
            "observability",
            "workers",
        ),
    ),
    (
        "entry points do not import concrete integrations",
        ("api", "workers"),
        ("adapters", "config", "db", "genai"),
    ),
    (
        "only entry points import bootstrap",
        ("adapters", "api", "db", "genai", "workers"),
        ("bootstrap",),
    ),
)
PURE_BOUNDARIES = {"application", "core", "domain", "ports"}
# Pure boundaries may import only the stdlib, these packages, and the service itself.
# Extend per repository with --allow-external.
PURE_ALLOWED_EXTERNAL = {
    "__future__",
    "annotated_types",
    "pydantic",
    "typing_extensions",
}
# Application actions may log a recorded fallback (errors.md, broad except
# shape 5); domain/ and ports/ never log.
APPLICATION_ALLOWED_EXTERNAL = {"structlog"}
GENERIC_COLLECTIONS = {
    Path("errors.py"),
    Path("constants.py"),
    Path("core/errors.py"),
    Path("core/constants.py"),
    Path("common/errors.py"),
    Path("common/constants.py"),
}
FRAMEWORK_PORT_NAMES = {
    "adelete_thread",
    "ainvoke",
    "astream",
    "checkpoint_ns",
    "configurable",
    "durability",
    "recursion_limit",
    "stream_mode",
}
TRANSPORT_COORDINATE_FIELDS = {
    "ack_token",
    "consumer_group",
    "delivery_attempt",
    "offset",
    "partition",
    "receipt_handle",
    "stream_seq",
    "trace_carrier",
    "traceparent",
}
NONDETERMINISTIC_CALLS = {
    "date.today",
    "datetime.now",
    "datetime.today",
    "datetime.utcnow",
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "time.time",
    "time.monotonic",
    "uuid.uuid4",
    "uuid4",
}
IO_CALL_ROOTS = {
    "boto3",
    "httpx",
    "open",
    "os",
    "requests",
    "socket",
    "subprocess",
    "urllib",
}
IO_METHODS = {"read_bytes", "read_text", "write_bytes", "write_text"}
TRANSPORT_EXCEPTION_FIELDS = {"public_message", "retryable", "status_code"}
SQL_HANDLE_HINTS = ("conn", "cursor", "session")
BOOTSTRAP_FUNCTION_LINES = 80
REPOSITORY_METHOD_LINES = 40
SHARED_LITERAL_MODULES = 3
# Standard names nobody owns; repeating them is not a missing owner.
STANDARD_TOKENS = {"utf-8", "utf-16", "us-ascii", "iso-8859-1"}
IDENTIFIER_LITERAL = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)+$")
LIFECYCLE_NAMES = {"aclose", "close", "dispose", "shutdown"}
STATE_METHODS = {"add", "append", "clear", "discard", "extend", "pop", "remove", "update"}
IMPLEMENTATION_OWNERS = {"adapters", "db", "genai"}
SKIPPED_DIRS = {
    ".git",
    ".mypy_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


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


# --- AST helpers -------------------------------------------------------------


def imports(tree: ast.AST) -> Iterator[tuple[str, list[str], int, int]]:
    """Yield (module, imported names, relative level, line) for every import."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, [], 0, node.lineno
        elif isinstance(node, ast.ImportFrom):
            yield (
                node.module or "",
                [alias.name for alias in node.names],
                node.level,
                node.lineno,
            )


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def class_fields(node: ast.ClassDef) -> set[str]:
    return {
        child.target.id
        for child in node.body
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
    }


def self_assigned_fields(node: ast.ClassDef) -> set[str]:
    return {
        target.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Assign | ast.AnnAssign)
        for target in (
            child.targets if isinstance(child, ast.Assign) else [child.target]
        )
        if isinstance(target, ast.Attribute) and dotted_name(target.value) == "self"
    }


def functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def all_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    args = node.args
    extra = [arg for arg in (args.vararg, args.kwarg) if arg is not None]
    return [*args.posonlyargs, *args.args, *args.kwonlyargs, *extra]


def span(node: ast.stmt) -> int:
    return (node.end_lineno or node.lineno) - node.lineno + 1


def is_protocol(node: ast.ClassDef) -> bool:
    return any(dotted_name(base).split(".")[-1] == "Protocol" for base in node.bases)


def is_exception_class(node: ast.ClassDef) -> bool:
    return any(
        name.endswith(("Error", "Exception"))
        for name in (dotted_name(base).split(".")[-1] for base in node.bases)
    )


def public_methods(node: ast.ClassDef) -> set[tuple[str, tuple[str, ...]]]:
    """Public method names with their parameter names, for structural matching."""
    return {
        (child.name, tuple(arg.arg for arg in all_arguments(child)))
        for child in node.body
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
        and not child.name.startswith("_")
    }


def mentions_loose_type(annotation: ast.expr | None) -> bool:
    """True for annotations that contain Any, object, or Mapping[str, Any]."""
    if annotation is None:
        return False
    return any(
        dotted_name(node).split(".")[-1] in {"Any", "object"}
        for node in ast.walk(annotation)
        if isinstance(node, ast.Name | ast.Attribute)
    )


def is_optional_annotation(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:  # a quoted forward reference: "Model | None"
            annotation = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return False
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        sides = (annotation.left, annotation.right)
        return any(
            isinstance(side, ast.Constant) and side.value is None for side in sides
        )
    return isinstance(annotation, ast.Subscript) and dotted_name(
        annotation.value
    ).endswith("Optional")


def docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
            ):
                found.add(id(body[0].value))
    return found


# --- Per-module checks -------------------------------------------------------


def internal_targets(name: str, names: list[str], package: str) -> list[str]:
    """Top-level boundaries of `package` an import reaches; `from pkg import db` reaches db."""
    if name == package:
        return names
    if name.startswith(f"{package}."):
        return [name.removeprefix(f"{package}.").split(".", maxsplit=1)[0]]
    return []


def import_findings(
    module: Module, package: str, allowed: set[str]
) -> Iterator[Finding]:
    owner = module.owner
    for name, names, level, line in imports(module.tree):
        if level:
            yield violation(module, line, "relative import (forbidden)", R_IMPORTS)
            continue
        external_root = name.split(".", maxsplit=1)[0]
        if (
            owner in PURE_BOUNDARIES
            and external_root != package
            and external_root not in sys.stdlib_module_names
            and external_root not in allowed
            and not (owner == "application" and external_root in APPLICATION_ALLOWED_EXTERNAL)
        ):
            if external_root == "opentelemetry":
                message = f"{owner} imports opentelemetry; use the service's observability helpers"
                yield violation(module, line, message, R_TELEMETRY)
            else:
                message = f"{owner} imports external technology {external_root}"
                yield violation(module, line, message, R_DIRECTION)
        for target in internal_targets(name, names, package):
            if target in INTERNAL_FORBIDDEN.get(owner or "", set()):
                rule = R_CONFIG if target == "config" else R_DIRECTION
                yield violation(module, line, f"{owner} imports {target}", rule)
        if (
            module.path.name == "__init__.py"
            and owner == "observability"
            and module.display.count("/") == 1
            and external_root.startswith("langchain")
        ):
            message = "observability/__init__.py imports langchain; keep framework adapters apart"
            yield review(module, line, message, R_TELEMETRY)


def application_lifecycle_findings(module: Module) -> Iterator[Finding]:
    for node in functions(module.tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name not in {
            "run",
            "start",
        }:
            continue
        has_loop = any(isinstance(child, ast.While) for child in ast.walk(node))
        has_stop_event = any(
            dotted_name(arg.annotation) == "asyncio.Event"
            for arg in all_arguments(node)
            if arg.annotation is not None
        )
        if has_loop and has_stop_event:
            message = "application appears to own a long-running loop and stop-event lifecycle"
            yield review(module, node.lineno, message, R_WORKERS)


def transport_contract_findings(module: Module) -> Iterator[Finding]:
    if module.owner not in {"application", "domain", "ports"}:
        return
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ClassDef):
            leaked = sorted(class_fields(node) & TRANSPORT_COORDINATE_FIELDS)
            if leaked:
                message = f"{module.owner} contract exposes transport fields: {', '.join(leaked)}"
                yield review(module, node.lineno, message, R_BROKER)


def port_findings(module: Module) -> Iterator[Finding]:
    if module.owner != "ports":
        return
    for node in functions(module.tree):
        names = {node.name, *(arg.arg for arg in all_arguments(node))}
        leaked = sorted(names & FRAMEWORK_PORT_NAMES)
        if leaked:
            message = f"port exposes framework vocabulary: {', '.join(leaked)}"
            yield review(module, node.lineno, message, R_PORTS)
        annotations = [arg.annotation for arg in all_arguments(node)] + [node.returns]
        if any(mentions_loose_type(annotation) for annotation in annotations):
            yield review(
                module,
                node.lineno,
                f"port signature uses Any/object: {node.name}",
                R_PORTS,
            )
    for call in ast.walk(module.tree):
        if not isinstance(call, ast.Call):
            continue
        name = dotted_name(call.func)
        if name.split(".")[0] in IO_CALL_ROOTS or name.split(".")[-1] in IO_METHODS:
            yield review(
                module, call.lineno, f"ports module performs I/O: {name}()", R_PORTS
            )


def domain_io_findings(module: Module) -> Iterator[Finding]:
    """Obvious stdlib I/O, including import aliases; not a purity proof."""
    if module.owner != "domain":
        return
    aliases: dict[str, str] = {}
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = (
                    item.name if item.asname else item.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        head, dot, tail = name.partition(".")
        resolved = aliases.get(head, head) + (dot + tail if dot else "")
        filesystem = (
            isinstance(node.func, ast.Attribute) and node.func.attr in IO_METHODS
        )
        effect = resolved in {"open", "builtins.open", "io.open", "os.open"} or (
            resolved.startswith(
                ("subprocess.", "socket.", "urllib.request.", "os.remove", "os.unlink")
            )
        )
        if filesystem or effect:
            label = name or (
                node.func.attr if isinstance(node.func, ast.Attribute) else "I/O"
            )
            yield review(
                module,
                node.lineno,
                f"domain appears to perform I/O: {label}()",
                R_DIRECTION,
            )


def smell_findings(module: Module) -> Iterator[Finding]:
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Assert):
            yield review(module, node.lineno, "assert in production code", R_ASSERT)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and dotted_name(child.func) == "getattr"
                    and child.args
                    and dotted_name(child.args[0]) == node.name
                ):
                    message = f"getattr({node.name}, ...) on a caught exception; declare it on a base"
                    yield review(module, child.lineno, message, R_CLASSIFICATION)
        elif isinstance(node, ast.ClassDef) and is_exception_class(node):
            carried = sorted(
                (class_fields(node) | self_assigned_fields(node))
                & TRANSPORT_EXCEPTION_FIELDS
            )
            if carried:
                message = f"exception carries transport mapping: {', '.join(carried)}"
                yield review(module, node.lineno, message, R_PUBLIC_ERRORS)

    if module.owner in {"application", "genai"}:
        for node in functions(module.tree):
            if node.name != "__init__":
                continue
            args = node.args
            positional = [*args.posonlyargs, *args.args]
            pairs = list(
                zip(
                    positional[len(positional) - len(args.defaults) :],
                    args.defaults,
                    strict=True,
                )
            )
            pairs += [
                (arg, default)
                for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)
                if default is not None
            ]
            for arg, default in pairs:
                if (
                    isinstance(default, ast.Constant)
                    and default.value is None
                    and is_optional_annotation(arg.annotation)
                ):
                    message = (
                        f"optional constructor collaborator {arg.arg}: X | None = None"
                    )
                    yield review(module, node.lineno, message, R_CONSTRUCTOR_CONTRACTS)

    if module.owner == "genai":
        for node in functions(module.tree):
            annotations = [arg.annotation for arg in all_arguments(node)] + [
                node.returns
            ]
            if any(
                annotation is not None
                and dotted_name(annotation).split(".")[-1] == "Any"
                for annotation in annotations
            ):
                yield review(
                    module,
                    node.lineno,
                    f"genai signature uses Any: {node.name}",
                    R_ESCAPE,
                )


def nondeterminism_findings(module: Module) -> Iterator[Finding]:
    if module.owner not in {"application", "db", "domain"}:
        return
    defaults: set[int] = set()
    for node in functions(module.tree):
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                defaults.update(id(child) for child in ast.walk(default))
    for call in ast.walk(module.tree):
        if not isinstance(call, ast.Call) or id(call) in defaults:
            continue
        name = dotted_name(call.func)
        if name in NONDETERMINISTIC_CALLS or name.startswith("random."):
            message = f"{module.owner} reads nondeterminism directly: {name}(); inject a callable"
            yield review(module, call.lineno, message, R_NONDETERMINISM)


def sql_findings(module: Module) -> Iterator[Finding]:
    if module.owner == "db":
        return
    sql_text_names = {
        alias
        for name, names, _level, _line in imports(module.tree)
        if name.split(".")[0] in {"sqlalchemy", "sqlmodel"}
        for alias in names
        if alias == "text"
    }
    for name, _names, _level, line in imports(module.tree):
        if name.split(".")[0] == "psycopg":
            yield review(module, line, "psycopg imported outside db/", R_ADAPTERS)
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        func = dotted_name(node.func)
        if func in sql_text_names:
            yield review(module, node.lineno, "raw SQL text() outside db/", R_ADAPTERS)
        elif isinstance(node.func, ast.Attribute) and node.func.attr in {
            "exec",
            "execute",
        }:
            receiver = dotted_name(node.func.value).split(".")[-1].lower()
            first = node.args[0] if node.args else None
            raw_sql = isinstance(first, ast.Constant) and isinstance(first.value, str)
            if raw_sql or any(hint in receiver for hint in SQL_HANDLE_HINTS):
                yield review(
                    module,
                    node.lineno,
                    f"SQL execution outside db/: {func}()",
                    R_ADAPTERS,
                )


def size_findings(module: Module) -> Iterator[Finding]:
    if module.owner == "bootstrap":
        for node in functions(module.tree):
            if span(node) > BOOTSTRAP_FUNCTION_LINES:
                message = f"bootstrap function {node.name} spans {span(node)} lines; split by capability"
                yield review(module, node.lineno, message, R_BOOTSTRAP)
    if module.owner == "db":
        for cls in ast.walk(module.tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for method in cls.body:
                if (
                    isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef)
                    and span(method) > REPOSITORY_METHOD_LINES
                ):
                    message = (
                        f"repository method {cls.name}.{method.name} spans {span(method)} lines;"
                        " check it applies decisions rather than making them"
                    )
                    yield review(module, method.lineno, message, R_REPOSITORIES)


def module_shape_findings(module: Module) -> Iterator[Finding]:
    body = module.tree.body
    if module.path.name == "__init__.py":
        for node in body:
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                yield review(
                    module, node.lineno, f"__init__.py defines {node.name}", R_IMPORTS
                )
        return
    statements = [
        node
        for node in body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    only_reexports = bool(statements) and all(
        isinstance(node, ast.Import | ast.ImportFrom)
        or (
            isinstance(node, ast.Assign)
            and any(dotted_name(target) == "__all__" for target in node.targets)
        )
        for node in statements
    )
    if only_reexports and any(isinstance(node, ast.Assign) for node in statements):
        yield review(module, 1, "module only re-exports imports via __all__", R_IMPORTS)


def forwarded_name(node: ast.expr, params: set[str]) -> str | None:
    """The parameter or `self.<attr>` a call argument forwards unchanged, else None."""
    if isinstance(node, ast.Starred):
        node = node.value
    if isinstance(node, ast.Name) and node.id in params:
        return node.id
    if isinstance(node, ast.Attribute) and dotted_name(node.value) == "self":
        return f"self.{node.attr}"
    return None


def pass_through_findings(module: Module) -> Iterator[Finding]:
    protocol_methods = {
        id(child)
        for node in ast.walk(module.tree)
        if isinstance(node, ast.ClassDef) and is_protocol(node)
        for child in node.body
    }
    for node in functions(module.tree):
        if (
            id(node) in protocol_methods
            or node.name.startswith("__")
            or node.name in LIFECYCLE_NAMES
            or any(
                dotted_name(decorator) not in {"staticmethod", "classmethod"}
                for decorator in node.decorator_list
            )
        ):
            continue
        body = [
            stmt
            for stmt in node.body
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        ]
        if len(body) != 1 or not isinstance(body[0], ast.Return | ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Await):
            value = value.value
        if not isinstance(value, ast.Call):
            continue
        callee = dotted_name(value.func)
        if not callee or callee.split(".")[-1][:1].isupper():
            continue  # constructors and computed callees are not plain forwarding
        if callee.startswith("self._") and callee.split(".")[-1] in STATE_METHODS:
            continue  # a method guarding private state is encapsulation, not forwarding
        params = {arg.arg for arg in all_arguments(node)} - {"self", "cls"}
        if not params:
            continue
        forwarded = [forwarded_name(arg, params) for arg in value.args]
        forwarded += [
            forwarded_name(keyword.value, params) for keyword in value.keywords
        ]
        receiver = callee.split(".")[
            0
        ]  # `store.save(x)` forwards `store` as the receiver
        if None in forwarded or not params <= {*forwarded, receiver}:
            continue
        if (
            module.owner == "application"
            and isinstance(node, ast.AsyncFunctionDef)
            and not node.name.startswith("_")
        ):
            continue  # public one-call actions are allowed; semantic audit confirms the boundary
        message = f"{node.name}() only forwards its parameters to {callee}(); call it directly"
        yield review(module, node.lineno, message, R_WRAPPERS)


def forwarding_lambda_target(node: ast.expr) -> str | None:
    """`lambda s: Repo(s).name(...)` -> "name"; anything else -> None."""
    if not isinstance(node, ast.Lambda):
        return None
    body = node.body.value if isinstance(node.body, ast.Await) else node.body
    if isinstance(body, ast.Call) and isinstance(body.func, ast.Attribute):
        return body.func.attr
    return None


def transaction_coordinator_findings(module: Module) -> Iterator[Finding]:
    """db/ methods whose body only runs a same-named repository call inside a transaction."""
    if module.owner != "db":
        return
    for node in functions(module.tree):
        body = [
            stmt
            for stmt in node.body
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        ]
        in_transaction = False
        # Peel a translating try/except and `with transaction(...) as session:` around the call.
        while len(body) == 1 and isinstance(
            body[0], ast.Try | ast.With | ast.AsyncWith
        ):
            in_transaction |= not isinstance(body[0], ast.Try)
            body = body[0].body
        if len(body) != 1 or not isinstance(body[0], ast.Return | ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Await):
            value = value.value
        if not isinstance(value, ast.Call):
            continue
        targets = {forwarding_lambda_target(arg) for arg in value.args} | {
            forwarding_lambda_target(keyword.value) for keyword in value.keywords
        }
        if in_transaction and isinstance(value.func, ast.Attribute):
            targets.add(value.func.attr)  # `Repo(session).submit(...)` inside the block
        if node.name in targets:
            message = (
                f"{node.name}() only opens a transaction around a same-named call; "
                "let the port implementation open it and run its queries"
            )
            yield review(module, node.lineno, message, R_WRAPPERS)


def bootstrap_binding_findings(module: Module, package: str) -> Iterator[Finding]:
    """`partial(action, ...)` or a lambda over an action in bootstrap/ hides an entry point."""
    if module.owner != "bootstrap":
        return
    actions = {
        alias
        for name, names, level, _line in imports(module.tree)
        if not level and name.startswith(f"{package}.application")
        for alias in names
    }
    for node in ast.walk(module.tree):
        target = ""
        if (
            isinstance(node, ast.Call)
            and dotted_name(node.func) in {"partial", "functools.partial"}
            and node.args
        ):
            target = dotted_name(node.args[0])
        elif isinstance(node, ast.Lambda):
            body = node.body.value if isinstance(node.body, ast.Await) else node.body
            if isinstance(body, ast.Call):
                target = dotted_name(body.func)
        if target in actions:
            message = (
                f"bootstrap binds application action {target}; an entry point in "
                "api/ or workers/ calls it directly with runtime collaborators"
            )
            yield review(module, node.lineno, message, R_WORKERS)


def audit_module(module: Module, package: str, allowed: set[str]) -> Iterator[Finding]:
    yield from import_findings(module, package, allowed)
    yield from bootstrap_binding_findings(module, package)
    if Path(module.display) in GENERIC_COLLECTIONS:
        yield violation(
            module, 1, "generic root/core error or constant collection", R_OWNERSHIP
        )
    if module.owner == "application":
        yield from application_lifecycle_findings(module)
    yield from transport_contract_findings(module)
    yield from port_findings(module)
    yield from domain_io_findings(module)
    yield from smell_findings(module)
    yield from nondeterminism_findings(module)
    yield from sql_findings(module)
    yield from size_findings(module)
    yield from module_shape_findings(module)
    yield from pass_through_findings(module)
    yield from transaction_coordinator_findings(module)


# --- Cross-module checks -----------------------------------------------------


def unused_port_findings(modules: list[Module], package: str) -> Iterator[Finding]:
    ports_prefix = f"{package}.ports"
    port_modules = [
        module
        for module in modules
        if module.owner == "ports" and module.path.name != "__init__.py"
    ]
    by_name = {
        f"{package}."
        + module.display.removesuffix(".py")
        .replace("/", ".")
        .removesuffix(".__init__"): module
        for module in modules
        if module.owner == "ports"
    }
    used: set[str] = set()

    def mark(name: str, names: list[str]) -> None:
        if name not in by_name or name in used:
            return
        used.add(name)
        for symbol in names:
            mark(f"{name}.{symbol}", [])
        # Follow re-exports/dependencies, with `used` breaking import cycles.
        for imported, symbols, level, _line in imports(by_name[name].tree):
            if not level:
                mark(imported, symbols)
                for symbol in symbols:
                    mark(f"{imported}.{symbol}", [])

    for module in modules:
        if module.owner != "application":
            continue
        for name, names, level, _line in imports(module.tree):
            if level or not (
                name == ports_prefix or name.startswith(f"{ports_prefix}.")
            ):
                continue
            mark(name, names)
            for symbol in names:
                mark(f"{name}.{symbol}", [])
    for module in port_modules:
        name = f"{package}." + module.display.removesuffix(".py").replace("/", ".")
        if name not in used:
            message = "port module is not imported by application/; it may belong beside its consumer"
            yield review(module, 1, message, R_PORTS)


def returns_context_manager(protocol: ast.ClassDef) -> bool:
    """`__call__` returning an (async) context manager: a unit-of-work factory."""
    for child in protocol.body:
        if (
            isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            and child.name == "__call__"
            and child.returns is not None
        ):
            return "ContextManager" in ast.unparse(child.returns)
    return False


def method_names(node: ast.ClassDef) -> set[MethodKey]:
    """Public method names; a callable (`__call__`) also carries its parameter names,
    because a bare `__call__` would match every callable class."""
    names: set[MethodKey] = {(name, ()) for name, _params in public_methods(node)}
    for child in node.body:
        if (
            isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            and child.name == "__call__"
        ):
            names.add((child.name, tuple(arg.arg for arg in all_arguments(child))))
    return names


def implements(
    cls: ast.ClassDef, protocol: ast.ClassDef, methods: set[MethodKey]
) -> bool:
    """Structural match; annotated fields satisfy `@property` members (a frozen dataclass
    `Runtime` satisfies an `ApiRuntime` Protocol)."""
    members = method_names(cls) | {(field, ()) for field in class_fields(cls)}
    return methods <= members or any(
        dotted_name(base).split(".")[-1] == protocol.name for base in cls.bases
    )


def protocol_findings(modules: list[Module], tests: list[Module]) -> Iterator[Finding]:
    """Callable stand-ins for domain functions, ports without an implementation, and
    non-port Protocols with one implementation and no test double."""
    classes = [
        (module, node)
        for module in modules
        for node in ast.walk(module.tree)
        if isinstance(node, ast.ClassDef) and not is_protocol(node)
    ]
    test_classes = [
        node
        for module in tests
        for node in ast.walk(module.tree)
        if isinstance(node, ast.ClassDef) and not is_protocol(node)
    ]
    for module in modules:
        for protocol in ast.walk(module.tree):
            if not isinstance(protocol, ast.ClassDef) or not is_protocol(protocol):
                continue
            methods = method_names(protocol)
            if not methods:
                continue
            is_port = module.owner == "ports"
            if {name for name, _params in methods} == {"__call__"}:
                if returns_context_manager(protocol):
                    continue  # a unit-of-work factory (persistence.md), not a function stand-in
                message = (
                    f"Protocol {protocol.name} only declares __call__; if a domain function "
                    "satisfies it, import that function directly"
                )
                finding = violation if is_port else review
                yield finding(module, protocol.lineno, message, R_APPLICATION_PORTS)
                continue
            implementations = [
                (owner, cls)
                for owner, cls in classes
                if implements(cls, protocol, methods)
            ]
            if is_port:
                if not any(
                    owner.owner in IMPLEMENTATION_OWNERS for owner, _ in implementations
                ):
                    message = f"port {protocol.name} has no implementation in db/, adapters/, or genai/"
                    yield review(module, protocol.lineno, message, R_APPLICATION_PORTS)
                continue
            if len(implementations) > 1:
                continue
            if implementations and implementations[0][0].owner == "bootstrap":
                continue  # a narrow runtime Protocol that keeps api/ etc. off bootstrap
            pattern = re.compile(rf"\b{re.escape(protocol.name)}\b")
            faked = any(methods <= method_names(cls) for cls in test_classes) or any(
                pattern.search(test.source) for test in tests
            )
            if faked:
                continue
            if implementations:
                owner, cls = implementations[0]
                message = (
                    f"Protocol {protocol.name} has one implementation ({cls.name} in "
                    f"{owner.display}) and no test double; type callers with {cls.name} "
                    "unless a decorator or library boundary needs the Protocol"
                )
            else:
                message = (
                    f"Protocol {protocol.name} has no class implementation here and no test "
                    "double; keep it only if another package implements it"
                )
            yield review(module, protocol.lineno, message, R_PORTS)


def single_module_adapter_findings(root: Path) -> Iterator[Finding]:
    adapters = root / "adapters"
    if not adapters.is_dir():
        return
    for directory in sorted(path for path in adapters.iterdir() if path.is_dir()):
        members = [
            path for path in directory.glob("*.py") if path.name != "__init__.py"
        ]
        if len(members) == 1 and not any(
            child.is_dir()
            for child in directory.iterdir()
            if child.name != "__pycache__"
        ):
            display = str(members[0].relative_to(root))
            message = f"one-module adapter subpackage {directory.name}/; keep it flat"
            yield Finding(display, 1, message, R_FLAT, "REVIEW")


def normalized_body(module: Module) -> str:
    return ast.dump(module.tree, annotate_fields=False, include_attributes=False)


def duplicate_llm_findings(modules: list[Module]) -> Iterator[Finding]:
    groups: dict[str, list[Module]] = defaultdict(list)
    for module in modules:
        if module.owner == "genai" and module.path.name == "llm.py":
            groups[normalized_body(module)].append(module)
    for group in groups.values():
        if len(group) > 1:
            others = ", ".join(item.display for item in group[1:])
            yield review(
                group[0], 1, f"identical genai llm.py bodies: {others}", R_ONE_OWNER
            )


def duplicate_private_function_findings(modules: list[Module]) -> Iterator[Finding]:
    """Same-named private helpers with identical bodies; a shared name alone is not a copy."""
    owners: dict[tuple[str, str], list[tuple[Module, int]]] = defaultdict(list)
    for module in modules:
        for node in module.tree.body:
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name.startswith("_")
                and not node.name.startswith("__")
            ):
                body = ast.dump(
                    ast.Module(body=node.body, type_ignores=[]),
                    annotate_fields=False,
                    include_attributes=False,
                )
                owners[(node.name, body)].append((module, node.lineno))
    for (name, _body), sites in sorted(owners.items()):
        if len(sites) > 1:
            first, line = sites[0]
            others = ", ".join(site.display for site, _ in sites[1:])
            yield review(
                first,
                line,
                f"private helper {name} is copied verbatim in {others}",
                R_ONE_OWNER,
            )


def shared_literal_findings(modules: list[Module]) -> Iterator[Finding]:
    sites: dict[str, list[tuple[Module, int]]] = defaultdict(list)
    for module in modules:
        if "alembic" in module.path.parts and "versions" in module.path.parts:
            continue  # migrations freeze their literals on purpose
        skipped = docstring_nodes(module.tree)
        seen: set[str] = set()
        for node in ast.walk(module.tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skipped
                and IDENTIFIER_LITERAL.match(node.value)
                and node.value not in STANDARD_TOKENS
                and node.value not in seen
            ):
                seen.add(node.value)
                sites[node.value].append((module, node.lineno))
    for literal, found in sorted(sites.items()):
        if len(found) >= SHARED_LITERAL_MODULES:
            first, line = found[0]
            message = f"string literal {literal!r} appears in {len(found)} modules; give it one owner"
            yield review(first, line, message, R_MAGIC)


def python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if (
            not SKIPPED_DIRS.intersection(path.parts)
            and "site-packages" not in path.parts
        ):
            yield path


def cross_member_findings(
    modules: list[Module], root: Path, workspace: Path
) -> Iterator[Finding]:
    """Report modules of the audited package that are byte-identical elsewhere in the workspace."""
    local = {
        hashlib.sha256(module.source.encode()).hexdigest(): module
        for module in modules
        if module.path.name != "__init__.py" and module.source.count("\n") >= 5
    }
    copies: dict[str, list[Path]] = defaultdict(list)
    for path in python_files(workspace):
        if path.is_relative_to(root) or "tests" in path.parts:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in local:
            copies[digest].append(path)
    for digest, paths in copies.items():
        listed = ", ".join(str(path.relative_to(workspace)) for path in paths)
        message = f"byte-identical copy in {listed}; >=3 deployables or diverged copies is a finding"
        yield review(local[digest], 1, message, R_SHARED)


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
        message = f"import-linter contracts for {package} leave unforbidden: {unforbidden}"
        yield Finding("(repository)", 0, message, R_CONTRACTS, "VIOLATION")
    else:
        message = (
            f"import-linter contracts for {package} omit boundaries that do not exist "
            f"yet ({unforbidden}); list them so the rule holds when one is created"
        )
        yield Finding("(repository)", 0, message, R_CONTRACTS, "REVIEW")


def missing_independence_findings(
    config: ImportLinterConfig, package: str, services: set[str]
) -> Iterator[Finding]:
    """A library's contract must forbid every service package and pydantic_settings."""
    edges = [
        edge for contract in config.contracts for edge in forbidden_edges(contract)
    ]
    missing = [
        target
        for target in (*sorted(services), "pydantic_settings")
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


def contract_findings(
    root: Path,
    package: str,
    workspace: Path | None,
    missing: Callable[[ImportLinterConfig], Iterator[Finding]] | None = None,
) -> Iterator[Finding]:
    """The import-linter contracts from python-repository-setup, found upward from the package.

    `missing` checks the contracts themselves; the default checks the service invariants."""
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


# --- Library mode ------------------------------------------------------------


def library_import_findings(
    module: Module, package: str, kind: str, allowed: set[str], services: set[str]
) -> Iterator[Finding]:
    for name, names, level, line in imports(module.tree):
        if level:
            yield violation(module, line, "relative import (forbidden)", R_IMPORTS)
            continue
        root = name.split(".", maxsplit=1)[0]
        if root in services:
            message = f"library imports service package {root}"
            yield violation(module, line, message, R_LIB_RULES)
        if root == "pydantic_settings":
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
        if kind == "persistence" and (
            name.startswith(SESSION_MODULES) or SESSION_NAMES.intersection(names)
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
            library_import_findings(module, package, kind, allowed, services)
            for module in modules
        ),
        *(library_body_findings(module) for module in modules),
        *(module_shape_findings(module) for module in modules),
        *(pass_through_findings(module) for module in modules),
        library_package_findings(root, package),
        contract_findings(
            root,
            package,
            workspace,
            lambda config: missing_independence_findings(config, package, services),
        ),
        duplicate_private_function_findings(modules),
    )
    for check in checks:
        findings.extend(check)
    if workspace is not None:
        findings.extend(private_import_findings(package, root, workspace, tests_root))
        findings.extend(cross_member_findings(modules, root, workspace))
    return sorted(set(findings))


# --- Driver ------------------------------------------------------------------


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
        protocol_findings(modules, tests),
        single_module_adapter_findings(root),
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
