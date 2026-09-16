#!/usr/bin/env python3
"""Validate the structure and completeness of an example-verification manifest.

The independent reviewer must still reproduce the claims; this script does not trust evidence as
proof of behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CLAIMS = {"runnable", "copyable", "integration", "test", "end-to-end"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", type=Path)
    args = parser.parse_args()
    root = args.collection.resolve()
    manifest_path = root / "_meta" / "example_verification.json"

    if not manifest_path.is_file():
        print(f"EXAMPLE EVIDENCE FAIL: missing {manifest_path}")
        return 1
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"EXAMPLE EVIDENCE FAIL: {error}")
        return 1

    examples = data.get("examples")
    if not isinstance(examples, list):
        print("EXAMPLE EVIDENCE FAIL: 'examples' must be a list")
        return 1

    errors: list[str] = []
    seen: set[str] = set()
    required = {"id", "note", "claim", "command", "environment", "exit_code", "observed_output", "verified"}
    for index, example in enumerate(examples):
        label = example.get("id", f"entry {index}") if isinstance(example, dict) else f"entry {index}"
        if not isinstance(example, dict):
            errors.append(f"{label}: must be an object")
            continue
        missing = sorted(required - example.keys())
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
        if label in seen:
            errors.append(f"{label}: duplicate id")
        seen.add(label)
        note = example.get("note")
        if note and not (root / note).is_file():
            errors.append(f"{label}: note does not exist: {note}")
        if example.get("claim") not in CLAIMS:
            errors.append(f"{label}: claim must be one of {', '.join(sorted(CLAIMS))}")
        if example.get("verified") is not True:
            errors.append(f"{label}: runnable claim is not verified")
        if example.get("exit_code") != 0:
            errors.append(f"{label}: verified exit_code must be 0")
        if not example.get("observed_output"):
            errors.append(f"{label}: observed_output is empty")

    if errors:
        print("EXAMPLE EVIDENCE FAIL")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1

    print(f"EXAMPLE EVIDENCE STRUCTURE PASS: {len(examples)} claim(s)")
    print("BEHAVIOR NOT INDEPENDENTLY VERIFIED: the reviewer must reproduce every claim.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
