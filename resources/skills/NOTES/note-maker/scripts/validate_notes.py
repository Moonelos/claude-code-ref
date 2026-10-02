#!/usr/bin/env python3
"""Validate role-agnostic mechanical parts of the note-maker writing contract."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

EXCLUDED_DIRS = {"_meta", "_audit", "site", "node_modules", "vendor", "build", "dist"}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MERMAID_TYPES = (
    "flowchart", "graph", "sequenceDiagram", "stateDiagram", "stateDiagram-v2", "classDiagram",
    "erDiagram", "journey", "gantt", "pie", "quadrantChart", "requirementDiagram", "gitGraph",
    "mindmap", "timeline", "sankey-beta", "xychart-beta", "block-beta", "C4Context",
    "C4Container", "C4Component", "C4Dynamic", "C4Deployment", "architecture-beta", "packet-beta",
    "kanban", "radar-beta",
)
BRACKETS = {"(": ")", "[": "]", "{": "}"}


@dataclass
class Result:
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def collect_notes(paths: list[Path]) -> list[Path]:
    notes: set[Path] = set()
    for path in paths:
        if path.is_file():
            notes.add(path.resolve())
            continue
        if path.is_dir():
            notes.update(
                candidate.resolve()
                for candidate in path.rglob("*.md")
                if not any(part in EXCLUDED_DIRS or part.startswith(".")
                           for part in candidate.relative_to(path).parts[:-1])
            )
            continue
        raise FileNotFoundError(path)
    return sorted(notes)


def validate_links(path: Path, lines: list[str], result: Result) -> None:
    for line_number, line in enumerate(lines, start=1):
        for target in MARKDOWN_LINK.findall(line):
            clean_target = target.split("#", 1)[0].strip()
            if (
                not clean_target
                or "://" in clean_target
                or clean_target.startswith("mailto:")
            ):
                continue
            if not (path.parent / clean_target).exists():
                result.error(
                    f"line {line_number}: linked file does not exist: {clean_target}"
                )


def mermaid_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    start = 0
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if current is None and stripped.startswith("```") and stripped[3:].strip() == "mermaid":
            current, start = [], line_number
        elif current is not None and stripped.startswith("```"):
            blocks.append((start, current))
            current = None
        elif current is not None:
            current.append(line)
    return blocks


def unbalanced_brackets(line: str) -> bool:
    """Check flowchart node-shape nesting outside quoted labels."""
    stack: list[str] = []
    in_quote = False
    for index, char in enumerate(line):
        previous = line[index - 1] if index else ""
        if not in_quote and char == ">" and (previous.isalnum() or previous == "_"):
            stack.append("]")  # asymmetric node shape: id>label]
        elif char == '"':
            in_quote = not in_quote
        elif in_quote:
            continue
        elif char in BRACKETS:
            stack.append(BRACKETS[char])
        elif char in BRACKETS.values():
            if not stack or stack.pop() != char:
                return True
    return bool(stack) or in_quote


def validate_mermaid(lines: list[str], result: Result, render: bool) -> None:
    for start, body in mermaid_blocks(lines):
        content = [line.strip() for line in body
                   if line.strip() and not line.strip().startswith("%%")]
        if content and content[0] == "---" and "---" in content[1:]:
            # Skip YAML front matter such as a diagram title.
            content = content[content.index("---", 1) + 1:]
        if not content:
            result.error(f"line {start}: empty mermaid diagram")
            continue
        kind = content[0].split()[0]
        if kind not in MERMAID_TYPES:
            result.error(f"line {start}: unknown mermaid diagram type {kind!r}")
            continue
        if kind in {"flowchart", "graph"}:
            for offset, line in enumerate(body, start=1):
                if unbalanced_brackets(line.split("%%", 1)[0]):
                    result.error(f"line {start + offset}: unbalanced brackets or quotes in mermaid")
        if render:
            render_mermaid(start, body, result)


def render_mermaid(start: int, body: list[str], result: Result) -> None:
    mmdc = shutil.which("mmdc")
    if not mmdc:
        result.warn("mermaid render check skipped: mmdc (@mermaid-js/mermaid-cli) not installed")
        return
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "diagram.mmd"
        source.write_text("\n".join(body), encoding="utf-8")
        completed = subprocess.run(
            [mmdc, "-i", str(source), "-o", str(Path(tmp) / "diagram.svg")],
            capture_output=True, text=True,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            result.error(f"line {start}: mermaid failed to render: {detail[-1] if detail else 'unknown error'}")


def validate_note(path: Path, render: bool = False) -> Result:
    result = Result(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    total_lines = len(lines)

    fence_lines = [
        line_number
        for line_number, line in enumerate(lines, start=1)
        if line.strip().startswith("```")
    ]
    if len(fence_lines) % 2:
        result.error(f"unclosed fenced code block near line {fence_lines[-1]}")

    if total_lines > 500:
        result.warn(
            f"{total_lines} lines: inspect navigation and learning roles; length alone is not a defect"
        )

    validate_links(path, lines, result)
    validate_mermaid(lines, result, render)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Note files or directories")
    parser.add_argument(
        "--render-mermaid", action="store_true",
        help="also render each diagram with mmdc (@mermaid-js/mermaid-cli) when installed",
    )
    args = parser.parse_args()

    try:
        notes = collect_notes(args.paths)
    except FileNotFoundError as error:
        parser.error(f"path does not exist: {error}")

    if not notes:
        parser.error("no note files found")

    results = [validate_note(path, args.render_mermaid) for path in notes]
    for result in results:
        status = "STRUCTURE-FAIL" if result.errors else "STRUCTURE-PASS"
        print(f"{status} {result.path}")
        for message in result.errors:
            print(f"  ERROR: {message}")
        for message in result.warnings:
            print(f"  WARN:  {message}")

    failures = sum(bool(result.errors) for result in results)
    print(f"\nChecked {len(results)} note(s); {failures} structural failure(s).")
    print("DIAGRAM NEED NOT VERIFIED: syntax is checked; whether a required diagram exists is a review judgment.")
    print("PEDAGOGY NOT VERIFIED: run the curriculum teach-back and independent audit.")
    print("EXAMPLES NOT VERIFIED: inspect the collection's example verification manifest.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
