#!/usr/bin/env python3
"""Keep scripts/resources_manifest.txt in sync with resources/ and catch losses.

- Any file listed in the manifest that no longer exists under resources/ is
  reported as missing and fails the commit.
- Any file under resources/ that is not yet in the manifest is added
  automatically; the commit is then failed once so the updated manifest gets
  staged and committed alongside the new file.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_DIR = REPO_ROOT / "resources"
MANIFEST_PATH = REPO_ROOT / "scripts" / "resources_manifest.txt"
IGNORED_NAMES = {".DS_Store"}
IGNORED_DIRS = {"__pycache__"}


def collect_current_files() -> set[str]:
    files = set()
    for path in RESOURCES_DIR.rglob("*"):
        if not path.is_file() or path.name in IGNORED_NAMES:
            continue
        if IGNORED_DIRS.intersection(path.relative_to(RESOURCES_DIR).parts):
            continue
        files.add(str(path.relative_to(RESOURCES_DIR)))
    return files


def load_manifest() -> set[str]:
    if not MANIFEST_PATH.exists():
        return set()
    return {
        line.strip()
        for line in MANIFEST_PATH.read_text().splitlines()
        if line.strip()
    }


def write_manifest(paths: set[str]) -> None:
    MANIFEST_PATH.write_text("\n".join(sorted(paths)) + "\n")


def main() -> int:
    if not RESOURCES_DIR.is_dir():
        print(f"ERROR: {RESOURCES_DIR} does not exist.")
        return 1

    current = collect_current_files()
    known = load_manifest()

    missing = sorted(known - current)
    new = sorted(current - known)

    if missing:
        print("ERROR: these resources are listed in the manifest but are missing from resources/:")
        for path in missing:
            print(f"  - {path}")
        print(f"\nRestore them, or if removed on purpose, delete them from {MANIFEST_PATH.relative_to(REPO_ROOT)}.")
        return 1

    if new:
        write_manifest(current)
        print(f"Added new resource(s) to {MANIFEST_PATH.relative_to(REPO_ROOT)}:")
        for path in new:
            print(f"  + {path}")
        print("\nStage the updated manifest and commit again.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
