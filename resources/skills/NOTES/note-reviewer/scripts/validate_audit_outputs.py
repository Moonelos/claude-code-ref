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


def has_repair_content(block: str, field: str, fields: tuple[str, ...]) -> bool:
    """Require content, including multiline prose, without mistaking the next field for it."""
    match = re.search(r"(?m)^" + re.escape(field) + r"[ \t]*(.*)$", block)
    if not match:
        return False
    if match.group(1).strip():
        return True
    for line in block[match.end():].splitlines():
        if not line.strip():
            continue
        return not (line.startswith(fields) or line.startswith(("#", "FIX-", "NO-ACTION:", "RELATED:")))
    return False


CORE_REPORTS = {
    "curriculum.audit.md", "lesson_quality.audit.md", "reader_paths.audit.md",
    "coverage.audit.md", "examples.audit.md", "metrics.audit.md", "gaps.audit.md",
    "landscape.audit.md",
}
METRICS_ALWAYS = [
    "Current-landscape items absent or stale",
    "Landscape by relevance",
    "Notes with required diagrams present",
    "Notes with retention practice",
]
LANDSCAPE_ITEM_FIELDS = ["Status:", "Relevance:", "In collection:", "Why it matters:",
                         "Suggested placement:", "Sources:"]


def validate_landscape(path: Path, errors: list[str]) -> None:
    require(path, ["Research:", "Baseline:", "Searched:"], errors)
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    research = re.search(r"(?m)^Research: (COMPLETE|INCOMPLETE)$", text)
    if not research:
        errors.append("landscape.audit.md: explicit COMPLETE or INCOMPLETE research status required")
    items = [block for block in re.split(r"(?m)(?=^## )", text) if block.startswith("## ")]
    if not items and "NO-LANDSCAPE-CHANGES:" not in text and not (research and research.group(1) == "INCOMPLETE"):
        errors.append("landscape.audit.md: needs item blocks or NO-LANDSCAPE-CHANGES after complete research")
    for index, item in enumerate(items, start=1):
        label = f"landscape.audit.md item {index}"
        for field in LANDSCAPE_ITEM_FIELDS:
            if not re.search(r"(?m)^" + re.escape(field) + r" *\S", item):
                errors.append(f"{label}: missing {field!r}")
        status = re.search(r"(?m)^Status: (\S+)", item)
        if status and status.group(1) not in {"GA", "PREVIEW", "DEPRECATED", "EMERGING"}:
            errors.append(f"{label}: invalid status {status.group(1)}")
        relevance = re.search(r"(?m)^Relevance: (\S+)", item)
        if relevance and relevance.group(1) not in {"CHANGES-BASELINE", "ADD-TO-NOTES", "MENTION"}:
            errors.append(f"{label}: invalid relevance {relevance.group(1)}")
        sources = re.search(r"(?m)^Sources: (.*)$", item)
        if sources and "http" not in sources.group(1):
            errors.append(f"{label}: sources need URLs")
        if status and status.group(1) == "EMERGING" and sources and sources.group(1).count("http") < 2:
            errors.append(f"{label}: EMERGING items need two independent sources")


def validate_folder_reports(root: Path, errors: list[str]) -> None:
    folder_reports = [path for path in root.glob("*.audit.md") if path.name not in CORE_REPORTS]
    if not folder_reports:
        errors.append("no per-folder audit reports found")
    for path in folder_reports:
        require(path, ["ORDERING:", "EXPLANATION:", "teach-back"], errors)
        require_per_block(path, ["ORDERING:", "EXPLANATION:", "LESSON:", "VISUAL:", "PRACTICE:", "Summary:"], errors)
        for index, block in enumerate(blocks(path.read_text(encoding="utf-8")), start=1):
            lesson = re.search(r"(?m)^LESSON: (PASS|FAIL|NOT-CHECKED|n/a)(?:;|$)", block)
            if not lesson:
                errors.append(f"{path.name} block {index}: invalid or missing lesson verdict")
            elif lesson.group(1) == "FAIL" and re.search(r"(?m)^EXPLANATION: PASS\b", block):
                errors.append(f"{path.name} block {index}: explanation cannot pass a failed lesson")
            for field in ("VISUAL", "PRACTICE"):
                verdict = re.search(r"(?m)^" + field + r": (PASS|FAIL|n/a)(?:;|$)", block)
                if not verdict:
                    errors.append(f"{path.name} block {index}: invalid or missing {field} verdict")
                elif verdict.group(1) == "FAIL" and not re.search(r"(?m)^FIX-(?:HIGH|MED):", block):
                    errors.append(f"{path.name} block {index}: {field} FAIL needs a FIX-HIGH or FIX-MED finding")
            if (re.search(r"(?m)^VISUAL: FAIL", block)
                    and not re.search(r"(?m)^\s*(?:```mermaid|(?:sequenceDiagram|flowchart|graph|stateDiagram(?:-v2)?)\b)", block)):
                errors.append(f"{path.name} block {index}: VISUAL FAIL needs a Mermaid sketch in the finding")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_directory", type=Path)
    parser.add_argument("--quick", action="store_true",
                        help="quick review: per-note, landscape, and metrics reports only")
    args = parser.parse_args()
    root = args.audit_directory.resolve()
    errors: list[str] = []

    validate_landscape(root / "landscape.audit.md", errors)
    validate_folder_reports(root, errors)
    if args.quick:
        require(root / "metrics.audit.md", ["Mode: quick", "Research:", *METRICS_ALWAYS], errors)
        return report(errors)

    curriculum = root / "curriculum.audit.md"
    require(curriculum, ["Research:", "Audience:", "Scope:", "Sources:", "Limitations:"], errors)
    if curriculum.is_file():
        text = curriculum.read_text(encoding="utf-8")
        if not re.search(r"(?m)^Research: (COMPLETE|INCOMPLETE)$", text):
            errors.append("curriculum.audit.md: explicit COMPLETE or INCOMPLETE research status required")
        if not re.search(r"(?m)^\| Item / capability \|", text):
            errors.append("curriculum.audit.md: curriculum inventory table required")

    lessons = root / "lesson_quality.audit.md"
    lesson_fields = ["Files:", "LESSON:", "Reader:", "Evidence:", "Reasoning burden:",
                     "Visual support:", "Structure:", "Summary:"]
    require(lessons, lesson_fields, errors)
    require_per_block(lessons, lesson_fields, errors)
    if lessons.is_file():
        for index, block in enumerate(blocks(lessons.read_text(encoding="utf-8")), start=1):
            match = re.search(r"(?m)^LESSON: (PASS|FAIL|NOT-CHECKED|n/a)$", block)
            label = f"lesson_quality.audit.md block {index}"
            if not match:
                errors.append(f"{label}: invalid or missing lesson verdict")
            elif match.group(1) in {"FAIL", "NOT-CHECKED"} and re.search(r"(?m)^NO-ACTION:", block):
                errors.append(f"{label}: failed/unchecked lesson cannot claim NO-ACTION")
            if re.search(r"(?m)^Structure:.*\b(?:REORDER|MERGE|SPLIT|REWRITE)\b", block):
                repair_fields = ("Proposed sequence:", "Content mapping:", "Example development:",
                                 "Rewrite sample:", "Acceptance task:")
                for field in repair_fields:
                    if not has_repair_content(block, field, repair_fields + tuple(lesson_fields)):
                        errors.append(f"{label}: structural repair missing {field}")

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
            "Lesson quality passed",
            *METRICS_ALWAYS,
        ],
        errors,
    )
    gaps_path = root / "gaps.audit.md"
    require(gaps_path, ["# "], errors)
    if gaps_path.is_file() and re.search(r"(?m)^FIX-(?:CRITICAL|HIGH|MED|LOW):", gaps_path.read_text(encoding="utf-8")):
        errors.append("gaps.audit.md: FIX severities are forbidden")

    return report(errors)


def report(errors: list[str]) -> int:
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
