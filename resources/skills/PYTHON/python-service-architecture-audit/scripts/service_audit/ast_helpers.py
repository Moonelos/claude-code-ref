"""Small AST queries shared by the checks."""

from __future__ import annotations

import ast
from collections.abc import Iterator


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
