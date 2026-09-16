#!/usr/bin/env python3
"""Validate role-agnostic mechanical parts of the note-maker writing contract."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXCLUDED_DIRS = {"_meta", "_audit", "site", "node_modules", "vendor", "build", "dist"}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


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


def validate_note(path: Path) -> Result:
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
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Note files or directories")
    args = parser.parse_args()

    try:
        notes = collect_notes(args.paths)
    except FileNotFoundError as error:
        parser.error(f"path does not exist: {error}")

    if not notes:
        parser.error("no note files found")

    results = [validate_note(path) for path in notes]
    for result in results:
        status = "STRUCTURE-FAIL" if result.errors else "STRUCTURE-PASS"
        print(f"{status} {result.path}")
        for message in result.errors:
            print(f"  ERROR: {message}")
        for message in result.warnings:
            print(f"  WARN:  {message}")

    failures = sum(bool(result.errors) for result in results)
    print(f"\nChecked {len(results)} note(s); {failures} structural failure(s).")
    print("PEDAGOGY NOT VERIFIED: run the curriculum teach-back and independent audit.")
    print("EXAMPLES NOT VERIFIED: inspect the collection's example verification manifest.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
