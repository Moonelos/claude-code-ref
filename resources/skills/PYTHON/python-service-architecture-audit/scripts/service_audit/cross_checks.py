"""Service checks that compare modules across the package or workspace."""

from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from service_audit.ast_helpers import (
    all_arguments,
    class_fields,
    docstring_nodes,
    dotted_name,
    imports,
    is_protocol,
    public_methods,
)
from service_audit.model import Finding, Module, python_files, review, violation
from service_audit.rules import (
    IDENTIFIER_LITERAL,
    IMPLEMENTATION_OWNERS,
    MethodKey,
    R_APPLICATION_PORTS,
    R_FLAT,
    R_MAGIC,
    R_ONE_OWNER,
    R_PORTS,
    R_SHARED,
    SHARED_LITERAL_MODULES,
    STANDARD_TOKENS,
)


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
            if (
                module.owner == "workers"
                and protocol.name == "Inbox"
                and {name for name, _params in methods} == {"receive", "settle"}
            ):
                continue  # the prescribed broker boundary in api-and-workers.md
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
