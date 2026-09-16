#!/usr/bin/env python3
"""Validate that a note-reviewer run emitted every required audit surface."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def require(path: Path, needles: list[str], errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing {path.name}")
        return
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            errors.append(f"{path.name}: missing required marker {needle!r}")


def blocks(text: str) -> list[str]:
    return [block for block in re.split(r"(?m)(?=^# )", text) if block.startswith("# ")]


def require_per_block(path: Path, markers: list[str], errors: list[str]) -> None:
    if not path.is_file():
        return
    found = blocks(path.read_text(encoding="utf-8"))
    if not found:
        errors.append(f"{path.name}: no report blocks")
    for index, block in enumerate(found, start=1):
        for marker in markers:
            if marker not in block:
                errors.append(f"{path.name} block {index}: missing {marker!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_directory", type=Path)
    args = parser.parse_args()
    root = args.audit_directory.resolve()
    errors: list[str] = []

    curriculum = root / "curriculum.audit.md"
    require(curriculum, ["Research:", "Audience:", "Scope:", "Sources:", "Limitations:"], errors)
    if curriculum.is_file():
        text = curriculum.read_text(encoding="utf-8")
        if not re.search(r"(?m)^Research: (COMPLETE|INCOMPLETE)$", text):
            errors.append("curriculum.audit.md: explicit COMPLETE or INCOMPLETE research status required")
        if not re.search(r"(?m)^\| Item / capability \|", text):
            errors.append("curriculum.audit.md: curriculum inventory table required")

    reader_path = root / "reader_paths.audit.md"
    coverage_path = root / "coverage.audit.md"
    examples_path = root / "examples.audit.md"
    require(reader_path, ["EXECUTION PAYOFF:", "UNDERSTANDING PAYOFF:"], errors)
    require_per_block(reader_path, ["EXECUTION PAYOFF:", "UNDERSTANDING PAYOFF:", "TRANSFER:", "Checkpoint:", "Scenario:", "Reasoning:", "Evidence:", "Summary:"], errors)
    if reader_path.is_file():
        for index, block in enumerate(blocks(reader_path.read_text(encoding="utf-8")), start=1):
            statuses = re.findall(r"(?m)^TRANSFER: (.*)$", block)
            if not statuses:
                errors.append(f"reader_paths.audit.md block {index}: absent transfer status")
            if any(status not in {"PASS", "FAIL", "NOT-CHECKED", "n/a"} for status in statuses):
                errors.append(f"reader_paths.audit.md block {index}: invalid transfer status")
            # Fields may precede or follow the verdict. Require evidence for each checkpoint
            # without imposing a rhetorical field order on the report author.
            for marker in ("Checkpoint:", "Scenario:", "Reasoning:", "Evidence:"):
                if len(re.findall(r"(?m)^" + re.escape(marker), block)) < len(statuses):
                    errors.append(f"reader_paths.audit.md block {index}: checkpoint missing {marker}")

    require(coverage_path, ["Required:", "Achieved:", "TEACH-BACK:", "ROLE:", "SIGNAL:", "SOURCE:"], errors)
    require_per_block(coverage_path, ["Required:", "Achieved:", "TEACH-BACK:", "ROLE:", "SIGNAL:", "SOURCE:"], errors)
    if examples_path.is_file() and examples_path.read_text(encoding="utf-8").startswith("NO-EXECUTABLE-CLAIMS:"):
        pass
    else:
        require(examples_path, ["Claim:", "Status:", "Observed:"], errors)
        require_per_block(examples_path, ["Claim:", "Status:", "Command:", "Environment:", "Observed:"], errors)
        if examples_path.is_file():
            valid = {"VERIFIED", "BROKEN", "PARTIAL", "NOT-RUN", "EXCERPT"}
            for status in re.findall(r"(?m)^Status: ([A-Z-]+)$", examples_path.read_text(encoding="utf-8")):
                if status not in valid:
                    errors.append(f"examples.audit.md: invalid status {status}")
    require(
        root / "metrics.audit.md",
        [
            "Paths with an execution payoff within two entries",
            "Paths with an understanding payoff within two entries",
            "Core mechanisms at required coverage level",
            "Executable claims reproduced",
            "Current-landscape items absent or stale",
            "Research:",
            "Essential curriculum items accounted for",
            "Transfer checkpoints passed",
        ],
        errors,
    )
    gaps_path = root / "gaps.audit.md"
    require(gaps_path, ["# "], errors)
    if gaps_path.is_file() and re.search(r"(?m)^FIX-(?:CRITICAL|HIGH|MED|LOW):", gaps_path.read_text(encoding="utf-8")):
        errors.append("gaps.audit.md: FIX severities are forbidden")

    folder_reports = [
        path
        for path in root.glob("*.audit.md")
        if path.name
        not in {
            "curriculum.audit.md",
            "reader_paths.audit.md",
            "coverage.audit.md",
            "examples.audit.md",
            "metrics.audit.md",
            "gaps.audit.md",
        }
    ]
    if not folder_reports:
        errors.append("no per-folder audit reports found")
    for path in folder_reports:
        require(path, ["ORDERING:", "EXPLANATION:", "teach-back"], errors)
        require_per_block(path, ["ORDERING:", "EXPLANATION:", "Summary:"], errors)

    if errors:
        print("AUDIT OUTPUT FAIL")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1

    print("AUDIT OUTPUT STRUCTURE PASS")
    print("AUDIT JUDGMENT NOT VERIFIED: run an independent behavioral calibration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
