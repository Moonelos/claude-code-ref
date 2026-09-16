#!/usr/bin/env python3
"""Validate structural invariants in a note collection's learning contract.

This intentionally does not claim to validate pedagogy or example correctness.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LEVELS = {"mentioned", "defined", "explained", "demonstrated", "operationalized"}
ROLES = {"foundation", "tutorial", "implementation", "deep dive", "decision guide", "reference"}
PATH_KINDS = {"first-time", "production", "decision", "reference"}


def objects(value: object, label: str, errors: list[str]) -> list[dict]:
    if not isinstance(value, list):
        errors.append(f"{label}: must be a list")
        return []
    result: list[dict] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            errors.append(f"{label}[{index}]: must be an object")
        else:
            result.append(entry)
    return result


def validate_v2(data: dict, root: Path, note_map: dict, paths: list[dict], errors: list[str]) -> None:
    """Validate declared audience/research/transfer structure, never semantic quality."""
    assumed = data.get("assumed_knowledge")
    if not isinstance(assumed, list) or not all(isinstance(x, str) and x.strip() for x in assumed):
        errors.append("assumed_knowledge: list of explicit skills required (may be empty)")
    if not isinstance(data.get("scope"), str) or not data["scope"].strip():
        errors.append("scope: non-empty learning scope required")
    research = data.get("research")
    if not isinstance(research, str) or not research.strip():
        errors.append("research: curriculum research file path required")
    else:
        research_path = (root / research).resolve()
        if not research_path.is_relative_to(root) or not research_path.is_file():
            errors.append("research: must resolve to a file within the collection")
        elif not any(line in {"Research: COMPLETE", "Research: INCOMPLETE"}
                     for line in research_path.read_text(encoding="utf-8").splitlines()):
            errors.append("research: ledger must explicitly record COMPLETE or INCOMPLETE")
    for bridge in objects(data.get("prerequisite_bridges"), "prerequisite_bridges", errors):
        if not isinstance(bridge.get("concept"), str) or not bridge["concept"].strip():
            errors.append("prerequisite bridge: non-empty concept required")
        if not isinstance(bridge.get("owner"), str) or bridge["owner"] not in note_map:
            errors.append("prerequisite bridge: owner must be a declared note")

    path_map = {p["name"]: p for p in paths if isinstance(p.get("name"), str)}
    if len(path_map) != len(paths):
        errors.append("paths: unique non-empty names required")
    checked_paths: set[str] = set()
    checks = objects(data.get("transfer_checks"), "transfer_checks", errors)
    for check in checks:
        path_name = check.get("path_name")
        if not isinstance(path_name, str) or path_name not in path_map:
            errors.append("transfer check: path_name must identify a declared path")
            continue
        checked_paths.add(path_name)
        entries = path_map[path_name].get("entries", [])
        if not isinstance(entries, list):
            continue  # The main validator reports invalid path entries.
        after = check.get("after_note")
        if not isinstance(after, str) or after not in entries:
            errors.append(f"transfer check {path_name}: after_note must be in that path")
            continue
        for key in ("prompt", "expected_reasoning"):
            if not isinstance(check.get(key), str) or not check[key].strip():
                errors.append(f"transfer check {path_name}: non-empty {key} required")
        evidence = check.get("evidence_notes")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(x, str) for x in evidence):
            errors.append(f"transfer check {path_name}: non-empty evidence_notes required")
            continue
        available = entries[:entries.index(after) + 1]
        if any(note not in available for note in evidence):
            errors.append(f"transfer check {path_name}: evidence borrows from later or off-path notes")
    for path in paths:
        name = path.get("name")
        if path.get("kind") != "reference" and isinstance(name, str) and name not in checked_paths:
            errors.append(f"path {name}: teaching path needs a transfer checkpoint")
        delayed = any(type(path.get(key)) is int and path[key] > 2
                      for key in ("execution_payoff_by", "understanding_payoff_by"))
        if delayed and not (isinstance(path.get("milestone_rationale"), str)
                            and path["milestone_rationale"].strip()):
            errors.append(f"path {name}: later payoff needs milestone_rationale, not an automatic failure")
    if not checks and paths and all(p.get("kind") == "reference" for p in paths):
        if not isinstance(data.get("transfer_exemption"), str) or not data["transfer_exemption"].strip():
            errors.append("transfer_exemption: explain why pure reference paths need no checkpoint")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", type=Path)
    args = parser.parse_args()
    root = args.collection.resolve()
    contract_path = root / "_meta" / "learning_contract.json"

    if not contract_path.is_file():
        print(f"CONTRACT FAIL: missing {contract_path}")
        return 1

    try:
        data = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"CONTRACT FAIL: {error}")
        return 1

    errors: list[str] = []
    if not isinstance(data, dict):
        print("CONTRACT FAIL: root must be an object")
        return 1
    if not isinstance(data.get("audience"), str) or not data["audience"].strip():
        errors.append("audience: non-empty string required")
    notes = objects(data.get("notes"), "notes", errors)
    paths = objects(data.get("paths"), "paths", errors)
    mechanisms = objects(data.get("mechanisms"), "mechanisms", errors)
    note_map: dict[str, dict] = {}
    for index, entry in enumerate(notes):
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            errors.append(f"notes[{index}]: non-empty path required")
            continue
        if path in note_map:
            errors.append(f"{path}: duplicate note declaration")
        note_map[path] = entry

    for path, entry in note_map.items():
        if entry.get("role") not in ROLES:
            errors.append(f"{path}: unknown role {entry.get('role')!r}")
        for key in ("entry_capability", "exit_capability"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                errors.append(f"{path}: non-empty {key} required")
        if not (root / path).is_file():
            errors.append(f"{path}: note file does not exist")
        prerequisites = entry.get("prerequisites")
        if not isinstance(prerequisites, list) or not all(isinstance(item, str) for item in prerequisites):
            errors.append(f"{path}: prerequisites must be a list of note paths")
            prerequisites = []
            entry["prerequisites"] = prerequisites
        for prerequisite in prerequisites:
            if prerequisite not in note_map:
                errors.append(f"{path}: prerequisite is not declared: {prerequisite}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(path: str) -> None:
        if path in visiting:
            errors.append(f"{path}: prerequisite cycle detected")
            return
        if path in visited or path not in note_map:
            return
        visiting.add(path)
        for prerequisite in note_map[path].get("prerequisites", []):
            visit(prerequisite)
        visiting.remove(path)
        visited.add(path)

    for path in note_map:
        visit(path)

    owners: dict[str, str] = {}
    for mechanism in mechanisms:
        name = mechanism.get("name")
        owner = mechanism.get("owner")
        level = mechanism.get("required_level")
        if not name or not owner:
            errors.append("mechanism entry requires name and owner")
            continue
        if name in owners:
            errors.append(f"{name}: duplicate canonical owner ({owners[name]}, {owner})")
        owners[name] = owner
        if owner not in note_map:
            errors.append(f"{name}: owner is not a declared note: {owner}")
        if level not in LEVELS:
            errors.append(f"{name}: unknown coverage level {level!r}")
        for key in ("reader_must_explain",):
            value = mechanism.get(key)
            if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
                errors.append(f"{name}: non-empty {key} list required")
        if not isinstance(mechanism.get("carrier"), str) or not mechanism["carrier"].strip():
            errors.append(f"{name}: non-empty carrier required")

    for path in paths:
        name = path.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("path: non-empty name required")
            name = "<unnamed>"
        if path.get("kind") not in PATH_KINDS:
            errors.append(f"path {name}: unknown kind {path.get('kind')!r}")
        if not isinstance(path.get("stop_point"), str) or not path["stop_point"].strip():
            errors.append(f"path {name}: non-empty stop_point required")
        entries = path.get("entries", [])
        if not isinstance(entries, list) or not entries or not all(isinstance(item, str) for item in entries):
            errors.append(f"path {name}: no entries")
            continue
        positions = {entry: index for index, entry in enumerate(entries)}
        for entry in entries:
            if entry not in note_map:
                errors.append(f"path {name}: undeclared entry {entry}")
                continue
            for prerequisite in note_map[entry].get("prerequisites", []):
                if prerequisite not in positions or positions[prerequisite] >= positions[entry]:
                    errors.append(f"path {name}: {entry} appears before prerequisite {prerequisite}")
        for key in ("execution_payoff_by", "understanding_payoff_by"):
            value = path.get(key)
            if not isinstance(value, int) or value < 1 or value > len(entries):
                errors.append(f"path {name}: invalid {key}={value!r}")

    first_time_entries = {
        entry
        for path in paths
        if path.get("kind") == "first-time"
        for entry in path.get("entries", [])
    }
    for mechanism in mechanisms:
        owner = mechanism.get("owner")
        if owner in first_time_entries and note_map.get(owner, {}).get("role") == "deep dive":
            errors.append(f"{mechanism.get('name')}: first-time owner cannot be a deep dive: {owner}")

    version = data.get("schema_version", 1)
    if type(version) is not int or version not in {1, 2}:
        errors.append(f"unsupported schema_version: {version!r}")
    elif version == 2:
        validate_v2(data, root, note_map, paths, errors)

    if errors:
        print("CONTRACT FAIL")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1

    print("CONTRACT STRUCTURE PASS")
    if version == 1:
        print("LEGACY CONTRACT: audience assumptions, curriculum research, and transfer metadata not validated")
    print("RESEARCH AND TRANSFER NOT VERIFIED: inspect sources and solve the declared checkpoints")
    print("PEDAGOGY NOT VERIFIED: run the evidence-backed teach-back and independent audit")
    print("EXAMPLES NOT VERIFIED: run validate_example_verification.py and independent reproduction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
