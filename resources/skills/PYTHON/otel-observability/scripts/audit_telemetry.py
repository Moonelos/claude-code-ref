#!/usr/bin/env python3
"""Report telemetry error-contract violations (references/conventions/errors.md); exit 1 on findings."""

import argparse
import ast
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical", "log"})
OTEL_API = frozenset({"set_attribute", "set_attributes", "set_status", "add", "record", "inject", "extract", "end"})
ERROR_TYPE_OK = re.compile(r"^(_OTHER|_ABANDONED|[A-Za-z][A-Za-z0-9_.]*|\d{3})$")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    code: str
    message: str


def _name(node: ast.expr | None) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


def _catches(handler: ast.ExceptHandler, *names: str) -> bool:
    return handler.type is None or _name(handler.type) in names


def _reraises_or_logs(handler: ast.ExceptHandler) -> bool:
    nodes = [n for stmt in handler.body for n in ast.walk(stmt)]
    return any(isinstance(n, ast.Raise) or (isinstance(n, ast.Call) and _name(n.func) in LOG_METHODS) for n in nodes)


def _bad_error_type(value: ast.expr) -> bool:
    text = value.value if isinstance(value, ast.Constant) else None
    message = isinstance(value, ast.Call) and _name(value.func) in {"str", "repr", "format"}
    return isinstance(value, ast.JoinedStr) or message or (isinstance(text, str) and not ERROR_TYPE_OK.match(text))


def _check_try(node: ast.Try, path: str) -> Iterator[Finding]:
    for index, handler in enumerate(node.handlers):
        if _catches(handler, "Exception", "BaseException") and not _reraises_or_logs(handler):
            yield Finding(path, handler.lineno, "broad-except", "broad except neither re-raises nor logs")
        later = any(_catches(h, "BaseException") for h in node.handlers[index + 1 :])  # would catch cancellation
        only_raise = len(handler.body) == 1 and isinstance(handler.body[0], ast.Raise) and handler.body[0].exc is None
        if _name(handler.type) == "CancelledError" and only_raise and not later:
            yield Finding(path, handler.lineno, "redundant-cancel", "`except CancelledError: raise` changes nothing")
    calls = [s.value for s in node.body if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)]
    if node.handlers and len(calls) == len(node.body) and all(_name(c.func) in OTEL_API for c in calls):
        yield Finding(path, node.lineno, "guarded-otel-api", "try/except around OpenTelemetry API calls")


def _check_pair(key: ast.expr | None, value: ast.expr, line: int, path: str) -> Iterator[Finding]:
    if isinstance(key, ast.JoinedStr):
        yield Finding(path, line, "fstring-key", "attribute key built from runtime values")
    if isinstance(key, ast.Constant) and key.value == "error.type" and _bad_error_type(value):
        yield Finding(path, line, "error-type", "error.type is not a class name, code, or sentinel")


def _check_call(node: ast.Call, path: str) -> Iterator[Finding]:
    func = _name(node.func)
    if func in {"record_exception", "add_event"}:
        yield Finding(path, node.lineno, "span-event", f"`{func}()` creates a span event")
    if func == "set_attribute" and len(node.args) >= 2:
        yield from _check_pair(node.args[0], node.args[1], node.lineno, path)
    mappings = [a for a in [*node.args, *(k.value for k in node.keywords)] if isinstance(a, ast.Dict)]
    for mapping in mappings:
        for key, value in zip(mapping.keys, mapping.values, strict=True):
            yield from _check_pair(key, value, node.lineno, path)


def audit_source(source: str, path: str, processor: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(ast.parse(source, filename=path)):
        if isinstance(node, ast.Try):
            findings.extend(_check_try(node, path))
        elif isinstance(node, ast.Call):
            findings.extend(_check_call(node, path))
        elif isinstance(node, ast.Constant) and str(node.value).startswith("exception.") and not processor:
            findings.append(Finding(path, node.lineno, "exception-field", "only the processor builds exception.*"))
    return sorted(findings, key=lambda f: (f.path, f.line, f.code))


BAD = """
try: work()
except Exception: pass
try: span.set_attribute("x", 1)
except Exception as err: log.warning("telemetry_failed", exc_info=err)
try: await_it()
except asyncio.CancelledError: raise
except Exception: raise
span.record_exception(exc); span.add_event("checkpoint")
span.set_attribute(f"app.{name}.count", 1); span.set_attribute("error.type", str(exc))
log.error("failed", **{"exception.message": str(exc), "error.type": "_NONE"})
"""
GOOD = """
try: await_it()
except TimeoutError as err:
    log.error("work_failed", exc_info=err, **{"error.type": "TimeoutError"}); raise
except asyncio.CancelledError:
    span.set_attribute("app.outcome", "cancelled"); raise
except BaseException:
    span.set_attribute("error.type", "_OTHER"); raise
"""
EXPECTED = {"broad-except": 1, "guarded-otel-api": 1, "redundant-cancel": 1, "span-event": 2,
            "fstring-key": 1, "error-type": 2, "exception-field": 1}  # fmt: skip


def self_test() -> int:
    counts = dict(Counter(finding.code for finding in audit_source(BAD, "bad.py")))
    if counts != EXPECTED:
        raise AssertionError(f"bad snippet: expected {EXPECTED}, got {counts}")
    if good := audit_source(GOOD, "good.py"):
        raise AssertionError(f"good snippet produced findings: {good}")
    if audit_source('x = "exception.stacktrace"', "logging.py", processor=True):
        raise AssertionError("the processor module may build exception.* fields")
    print("self-test passed")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="files or directories to audit")
    parser.add_argument("--processor", action="append", default=[], metavar="SUFFIX",
                        help="path suffix of the logging processor module (may build exception.*)")  # fmt: skip
    parser.add_argument("--self-test", action="store_true", help="run the embedded checks and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.paths:
        parser.error("give at least one path, or --self-test")
    files = [f for p in map(Path, args.paths) for f in (sorted(p.rglob("*.py")) if p.is_dir() else [p])]
    findings: list[Finding] = []
    for file in files:
        processor = any(str(file).endswith(suffix) for suffix in args.processor)
        findings.extend(audit_source(file.read_text(encoding="utf-8"), str(file), processor))
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.code}: {finding.message}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
