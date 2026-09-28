#!/usr/bin/env python3
"""Static candidate checks for a layered Python service package.

Every finding cites the rule that owns it. Hits are candidates to confirm by
reading the code, not verdicts; a clean run never replaces the semantic audit.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["VIOLATION", "REVIEW"]

ARCH = "python-service-architecture/references"
CONV = "python-code-conventions"
R_DIRECTION = f"{ARCH}/boundaries.md#The core rule"
R_CONFIG = f"{ARCH}/boundaries.md#config/"
R_TELEMETRY = f"{ARCH}/boundaries.md#observability/"
R_PORTS = f"{ARCH}/boundaries.md#When a port earns its cost"
R_FLAT = f"{ARCH}/boundaries.md#Flat-first growth across boundaries"
R_OWNERSHIP = f"{ARCH}/boundaries.md#Errors and constants follow ownership"
R_ADAPTERS = f"{ARCH}/boundaries.md#Adapters"
R_REPOSITORIES = f"{ARCH}/boundaries.md#Repositories apply decisions"
R_NONDETERMINISM = f"{ARCH}/boundaries.md#Nondeterminism"
R_CONSTRUCTOR_CONTRACTS = f"{ARCH}/boundaries.md#Constructor contracts"
R_BOOTSTRAP = f"{ARCH}/boundaries.md#bootstrap/"
R_WORKERS = f"{ARCH}/api-and-workers.md#Long-running worker"
R_BROKER = f"{ARCH}/api-and-workers.md#SQS, Kafka, or another broker"
R_SHARED = f"{ARCH}/shared-libraries.md"
R_CLASSIFICATION = f"{ARCH}/errors.md#Classification bases"
R_PUBLIC_ERRORS = f"{ARCH}/errors.md#Public error mapping"
R_IMPORTS = f"{CONV}#Imports and package markers"
R_ASSERT = f"{CONV}#No assert in production"
R_ESCAPE = f"{CONV}#Type escape hatches"
R_ONE_OWNER = f"{CONV}#One owner per semantics"
R_MAGIC = f"{CONV}#Magic values and constants"

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
    },
    # application may import the service's own observability helpers (not OTel types).
    "application": {"adapters", "api", "bootstrap", "config", "db", "genai"},
    "db": {"adapters", "api", "application", "bootstrap", "genai"},
    "genai": {"adapters", "api", "bootstrap", "db"},
    "api": {"bootstrap"},
    "adapters": {"api", "bootstrap"},
    "observability": {"api", "application", "bootstrap"},
}
PURE_BOUNDARIES = {"application", "core", "domain", "ports"}
FORBIDDEN_EXTERNAL = {
    "boto3",
    "botocore",
    "fastapi",
    "langchain",
    "langchain_aws",
    "langchain_core",
    "langgraph",
    "opentelemetry",
    "pgvector",
    "psycopg",
    "sqlalchemy",
    "sqlmodel",
    "starlette",
}
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
IO_CALL_ROOTS = {"boto3", "httpx", "open", "os", "requests", "socket", "subprocess", "urllib"}
IO_METHODS = {"read_bytes", "read_text", "write_bytes", "write_text"}
TRANSPORT_EXCEPTION_FIELDS = {"public_message", "retryable", "status_code"}
SQL_HANDLE_HINTS = ("conn", "cursor", "session")
BOOTSTRAP_FUNCTION_LINES = 60
REPOSITORY_METHOD_LINES = 40
SHARED_LITERAL_MODULES = 3
IDENTIFIER_LITERAL = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)+$")
SKIPPED_DIRS = {".git", ".mypy_cache", ".venv", "__pycache__", "build", "dist", "node_modules"}


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
            yield node.module or "", [alias.name for alias in node.names], node.level, node.lineno


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
        for target in (child.targets if isinstance(child, ast.Assign) else [child.target])
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
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        sides = (annotation.left, annotation.right)
        return any(isinstance(side, ast.Constant) and side.value is None for side in sides)
    return isinstance(annotation, ast.Subscript) and dotted_name(annotation.value).endswith(
        "Optional"
    )


def docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


# --- Per-module checks -------------------------------------------------------


def import_findings(module: Module, package: str) -> Iterator[Finding]:
    owner = module.owner
    prefix = f"{package}."
    for name, _names, level, line in imports(module.tree):
        if level:
            yield violation(module, line, "relative import (forbidden)", R_IMPORTS)
            continue
        external_root = name.split(".", maxsplit=1)[0]
        if owner in PURE_BOUNDARIES and external_root in FORBIDDEN_EXTERNAL:
            if external_root == "opentelemetry":
                message = f"{owner} imports opentelemetry; use the service's observability helpers"
                yield violation(module, line, message, R_TELEMETRY)
            else:
                message = f"{owner} imports external technology {external_root}"
                yield violation(module, line, message, R_DIRECTION)
        if owner in INTERNAL_FORBIDDEN and name.startswith(prefix):
            target = name.removeprefix(prefix).split(".", maxsplit=1)[0]
            if target in INTERNAL_FORBIDDEN[owner]:
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
        if not isinstance(node, ast.AsyncFunctionDef) or node.name not in {"run", "start"}:
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
                module, node.lineno, f"port signature uses Any/object: {node.name}", R_PORTS
            )
    for call in ast.walk(module.tree):
        if not isinstance(call, ast.Call):
            continue
        name = dotted_name(call.func)
        if name.split(".")[0] in IO_CALL_ROOTS or name.split(".")[-1] in IO_METHODS:
            yield review(module, call.lineno, f"ports module performs I/O: {name}()", R_PORTS)


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
                    message = (
                        f"getattr({node.name}, ...) on a caught exception; declare it on a base"
                    )
                    yield review(module, child.lineno, message, R_CLASSIFICATION)
        elif isinstance(node, ast.ClassDef) and is_exception_class(node):
            carried = sorted(
                (class_fields(node) | self_assigned_fields(node)) & TRANSPORT_EXCEPTION_FIELDS
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
                zip(positional[len(positional) - len(args.defaults) :], args.defaults, strict=True)
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
                    message = f"optional constructor collaborator {arg.arg}: X | None = None"
                    yield review(module, node.lineno, message, R_CONSTRUCTOR_CONTRACTS)

    if module.owner == "genai":
        for node in functions(module.tree):
            annotations = [arg.annotation for arg in all_arguments(node)] + [node.returns]
            if any(
                annotation is not None and dotted_name(annotation).split(".")[-1] == "Any"
                for annotation in annotations
            ):
                yield review(
                    module, node.lineno, f"genai signature uses Any: {node.name}", R_ESCAPE
                )


def nondeterminism_findings(module: Module) -> Iterator[Finding]:
    if module.owner not in {"application", "domain"}:
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
        elif isinstance(node.func, ast.Attribute) and node.func.attr in {"exec", "execute"}:
            receiver = dotted_name(node.func.value).split(".")[-1].lower()
            first = node.args[0] if node.args else None
            raw_sql = isinstance(first, ast.Constant) and isinstance(first.value, str)
            if raw_sql or any(hint in receiver for hint in SQL_HANDLE_HINTS):
                yield review(
                    module, node.lineno, f"SQL execution outside db/: {func}()", R_ADAPTERS
                )


def size_findings(module: Module) -> Iterator[Finding]:
    if module.owner == "bootstrap":
        for node in functions(module.tree):
            if span(node) > BOOTSTRAP_FUNCTION_LINES:
                message = (
                    f"bootstrap function {node.name} spans {span(node)} lines; split by capability"
                )
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
                yield review(module, node.lineno, f"__init__.py defines {node.name}", R_IMPORTS)
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


def audit_module(module: Module, package: str) -> Iterator[Finding]:
    yield from import_findings(module, package)
    if Path(module.display) in GENERIC_COLLECTIONS:
        yield violation(module, 1, "generic root/core error or constant collection", R_OWNERSHIP)
    if module.owner == "application":
        yield from application_lifecycle_findings(module)
    yield from transport_contract_findings(module)
    yield from port_findings(module)
    yield from smell_findings(module)
    yield from nondeterminism_findings(module)
    yield from sql_findings(module)
    yield from size_findings(module)
    yield from module_shape_findings(module)


# --- Cross-module checks -----------------------------------------------------


def unused_port_findings(modules: list[Module], package: str) -> Iterator[Finding]:
    ports_prefix = f"{package}.ports"
    used: set[str] = set()
    package_level_import = False
    for module in modules:
        if module.owner != "application":
            continue
        for name, names, _level, _line in imports(module.tree):
            if name == ports_prefix:
                used.update(names)
                package_level_import = True
            elif name.startswith(f"{ports_prefix}."):
                used.add(name.removeprefix(f"{ports_prefix}.").split(".")[0])
    for module in modules:
        if module.owner != "ports" or module.path.name == "__init__.py":
            continue
        stem = module.path.stem
        if stem not in used and not package_level_import:
            message = (
                "port module is not imported by application/; it may belong beside its consumer"
            )
            yield review(module, 1, message, R_PORTS)


def single_application_implementation_findings(modules: list[Module]) -> Iterator[Finding]:
    protocols: list[tuple[Module, ast.ClassDef, set[tuple[str, tuple[str, ...]]]]] = []
    classes: list[tuple[Module, ast.ClassDef]] = []
    for module in modules:
        for node in ast.walk(module.tree):
            if isinstance(node, ast.ClassDef):
                if is_protocol(node):
                    protocols.append((module, node, public_methods(node)))
                else:
                    classes.append((module, node))
    for module, protocol, methods in protocols:
        if not methods:
            continue
        implementations = [
            (owner, cls)
            for owner, cls in classes
            if methods <= public_methods(cls)
            or any(dotted_name(base).split(".")[-1] == protocol.name for base in cls.bases)
        ]
        if len(implementations) == 1 and implementations[0][0].owner == "application":
            impl_module, impl = implementations[0]
            message = (
                f"Protocol {protocol.name} has one implementation, "
                f"{impl.name} in {impl_module.display}"
            )
            yield review(module, protocol.lineno, message, R_PORTS)


def single_module_adapter_findings(root: Path) -> Iterator[Finding]:
    adapters = root / "adapters"
    if not adapters.is_dir():
        return
    for directory in sorted(path for path in adapters.iterdir() if path.is_dir()):
        members = [path for path in directory.glob("*.py") if path.name != "__init__.py"]
        if len(members) == 1 and not any(
            child.is_dir() for child in directory.iterdir() if child.name != "__pycache__"
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
            yield review(group[0], 1, f"identical genai llm.py bodies: {others}", R_ONE_OWNER)


def duplicate_private_function_findings(modules: list[Module]) -> Iterator[Finding]:
    owners: dict[str, list[tuple[Module, int]]] = defaultdict(list)
    for module in modules:
        for node in module.tree.body:
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name.startswith("_")
                and not node.name.startswith("__")
            ):
                owners[node.name].append((module, node.lineno))
    for name, sites in sorted(owners.items()):
        if len(sites) > 1:
            first, line = sites[0]
            others = ", ".join(site.display for site, _ in sites[1:])
            yield review(
                first, line, f"private helper {name} also defined in {others}", R_ONE_OWNER
            )


def shared_literal_findings(modules: list[Module]) -> Iterator[Finding]:
    sites: dict[str, list[tuple[Module, int]]] = defaultdict(list)
    for module in modules:
        skipped = docstring_nodes(module.tree)
        seen: set[str] = set()
        for node in ast.walk(module.tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skipped
                and IDENTIFIER_LITERAL.match(node.value)
                and node.value not in seen
            ):
                seen.add(node.value)
                sites[node.value].append((module, node.lineno))
    for literal, found in sorted(sites.items()):
        if len(found) >= SHARED_LITERAL_MODULES:
            first, line = found[0]
            message = (
                f"string literal {literal!r} appears in {len(found)} modules; give it one owner"
            )
            yield review(first, line, message, R_MAGIC)


def python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if not SKIPPED_DIRS.intersection(path.parts) and "site-packages" not in path.parts:
            yield path


def cross_member_findings(modules: list[Module], root: Path, workspace: Path) -> Iterator[Finding]:
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
        message = (
            f"byte-identical copy in {listed}; >=3 deployables or diverged copies is a finding"
        )
        yield review(local[digest], 1, message, R_SHARED)


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
                Finding(display, exc.lineno or 0, f"cannot parse module: {exc.msg}", "syntax")
            )
            continue
        modules.append(Module(path, display, boundary_for(path, root), source, tree))
    return modules, failures


def audit(root: Path, package: str, workspace: Path | None) -> list[Finding]:
    modules, findings = load_modules(root)
    checks: Iterable[Iterator[Finding]] = (
        *(audit_module(module, package) for module in modules),
        unused_port_findings(modules, package),
        single_application_implementation_findings(modules),
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
    parser.add_argument("--package", help="Import package name; defaults to the directory name")
    parser.add_argument(
        "--workspace", type=Path, help="Workspace root for cross-member duplicate checks"
    )
    args = parser.parse_args()
    root: Path = args.package_root.resolve()
    if not root.is_dir():
        parser.error(f"package root is not a directory: {root}")
    workspace: Path | None = args.workspace.resolve() if args.workspace else None
    findings = audit(root, args.package or root.name, workspace)
    for finding in findings:
        print(finding.render())
    violations = sum(item.severity == "VIOLATION" for item in findings)
    reviews = len(findings) - violations
    if not findings:
        print("static checks passed; semantic audit pending")
        return 0
    print(f"static checks: {violations} violation candidate(s), {reviews} review notice(s)")
    print("confirm each hit by reading the code; semantic audit pending")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
