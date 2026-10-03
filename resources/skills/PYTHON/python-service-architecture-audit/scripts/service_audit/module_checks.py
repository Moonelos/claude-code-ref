"""Service checks that read one module at a time."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

from service_audit.ast_helpers import (
    all_arguments,
    class_fields,
    dotted_name,
    functions,
    imports,
    is_exception_class,
    is_optional_annotation,
    is_protocol,
    mentions_loose_type,
    self_assigned_fields,
    span,
)
from service_audit.model import Finding, Module, review, violation
from service_audit.rules import (
    APPLICATION_ALLOWED_EXTERNAL,
    BOOTSTRAP_COLLABORATORS,
    BOOTSTRAP_FACTORY_PREFIXES,
    FRAMEWORK_PORT_NAMES,
    GENERIC_COLLECTIONS,
    INTERNAL_FORBIDDEN,
    IO_CALL_ROOTS,
    IO_METHODS,
    LIFECYCLE_NAMES,
    MODEL_FACTORIES,
    MODEL_ID_KEYWORDS,
    MODEL_TUNING_KEYWORDS,
    NONDETERMINISTIC_CALLS,
    PURE_BOUNDARIES,
    REPOSITORY_METHOD_LINES,
    R_ADAPTERS,
    R_ASSERT,
    R_BOOTSTRAP,
    R_BROKER,
    R_CLASSIFICATION,
    R_CONFIG,
    R_CONSTRUCTOR_CONTRACTS,
    R_DIRECTION,
    R_GENAI_OWNERSHIP,
    R_ESCAPE,
    R_IMPORTS,
    R_NONDETERMINISM,
    R_OWNERSHIP,
    R_PORTS,
    R_PUBLIC_ERRORS,
    R_REPOSITORIES,
    R_TELEMETRY,
    R_WORKERS,
    R_WRAPPERS,
    SQL_HANDLE_HINTS,
    STATE_METHODS,
    TRANSPORT_COORDINATE_FIELDS,
    TRANSPORT_EXCEPTION_FIELDS,
)


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
    if module.owner in {"db", "alembic"}:  # migrations run SQL by definition
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


def own_calls(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.Call]:
    """Calls in a function's body, not in the functions it defines."""
    pending: list[ast.AST] = list(node.body)
    while pending:
        child = pending.pop()
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(child, ast.Call):
            yield child
        pending.extend(ast.iter_child_nodes(child))


def bundle_calls(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[int]:
    """The container a function yields or returns (`yield Runtime(...)`) is not a collaborator."""
    return {
        id(child.value)
        for child in ast.walk(node)
        if isinstance(child, ast.Yield | ast.Return) and isinstance(child.value, ast.Call)
    }


def constructed_collaborators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    bundles = bundle_calls(node)
    count = 0
    for call in own_calls(node):
        callee = dotted_name(call.func).split(".")[-1]
        if id(call) in bundles or not callee:
            continue
        if callee[:1].isupper() or callee.startswith(BOOTSTRAP_FACTORY_PREFIXES):
            count += 1
    return count


def size_findings(module: Module) -> Iterator[Finding]:
    if module.owner == "bootstrap":
        for node in functions(module.tree):
            built = constructed_collaborators(node)
            if built >= BOOTSTRAP_COLLABORATORS:
                message = (
                    f"bootstrap function {node.name} constructs {built} collaborators; "
                    "split at resource or capability seams into _build_<capability>() bundles"
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


def is_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and not isinstance(node.value, bool | type(None))


def genai_construction_findings(module: Module) -> Iterator[Finding]:
    """Literal model ids and tuning values, and SDK clients built by hand, in genai/."""
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        callee = dotted_name(node.func).split(".")[-1]
        for keyword in node.keywords:
            name = keyword.arg or ""
            tuned = name in MODEL_TUNING_KEYWORDS or name.endswith("effort")
            model_id = name in MODEL_ID_KEYWORDS and (
                callee in MODEL_FACTORIES or callee.startswith(("Chat", "Bedrock"))
            )
            if (tuned or model_id) and is_literal(keyword.value):
                message = (
                    f"{name}={ast.unparse(keyword.value)} is hardcoded; take it from the "
                    "task's settings slice (default in settings)"
                )
                yield review(module, node.lineno, message, R_GENAI_OWNERSHIP)
        if callee in MODEL_FACTORIES and node.args and is_literal(node.args[0]):
            message = f"{callee}() model id is hardcoded; take it from settings"
            yield review(module, node.lineno, message, R_GENAI_OWNERSHIP)
        if callee == "client" or any(
            dotted_name(arg).endswith(".client") for arg in node.args
        ):
            message = (
                "SDK client built by hand in genai/; pass timeouts, retries, and region to "
                "init_chat_model and let the integration build its clients"
            )
            yield review(module, node.lineno, message, R_GENAI_OWNERSHIP)


def audit_module(module: Module, package: str, allowed: set[str]) -> Iterator[Finding]:
    yield from import_findings(module, package, allowed)
    yield from bootstrap_binding_findings(module, package)
    if Path(module.display) in GENERIC_COLLECTIONS:
        yield violation(
            module, 1, "generic root/core error or constant collection", R_OWNERSHIP
        )
    if module.owner == "application":
        yield from application_lifecycle_findings(module)
    if module.owner == "genai":
        yield from genai_construction_findings(module)
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
