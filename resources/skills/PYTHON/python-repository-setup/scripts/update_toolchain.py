#!/usr/bin/env python3
"""Update and verify the bundled templates' duplicated toolchain pins."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = SKILL_ROOT / "toolchain.toml"

PYTHON_FILES = {
    "references/toolchain.md": 3,
    "assets/workspace-template/.python-version": 1,
    "assets/workspace-template/services/api/Dockerfile": 1,
    "assets/single-service-template/.python-version": 1,
    "assets/single-service-template/Dockerfile": 1,
}
UV_FILES = {
    "references/toolchain.md": 3,
    "assets/workspace-template/.pre-commit-config.yaml": 1,
    "assets/workspace-template/pyproject.toml": 1,
    "assets/workspace-template/services/api/Dockerfile": 1,
    "assets/workspace-template/.github/workflows/ci.yml": 2,
    "assets/single-service-template/.pre-commit-config.yaml": 1,
    "assets/single-service-template/pyproject.toml": 1,
    "assets/single-service-template/Dockerfile": 1,
    "assets/single-service-template/.github/workflows/ci.yml": 2,
}
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _read_manifest() -> dict[str, str]:
    return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))


def _validate_version(label: str, value: str) -> None:
    if not VERSION_RE.fullmatch(value):
        raise ValueError(f"{label} must be an X.Y.Z release, got {value!r}")


def _assert_consistent(python_version: str, uv_version: str) -> None:
    failures: list[str] = []
    for relative, expected_count in PYTHON_FILES.items():
        actual = (SKILL_ROOT / relative).read_text(encoding="utf-8").count(python_version)
        if actual != expected_count:
            failures.append(
                f"{relative}: expected Python {python_version} {expected_count} time(s), found {actual}"
            )
    for relative, expected_count in UV_FILES.items():
        actual = (SKILL_ROOT / relative).read_text(encoding="utf-8").count(uv_version)
        if actual != expected_count:
            failures.append(
                f"{relative}: expected uv {uv_version} {expected_count} time(s), found {actual}"
            )
    if failures:
        raise RuntimeError("Toolchain pins are inconsistent:\n" + "\n".join(failures))


def _updated_text(path: Path, old: str, new: str) -> str:
    current = path.read_text(encoding="utf-8")
    if old not in current:
        raise RuntimeError(f"Expected {old!r} in {path.relative_to(SKILL_ROOT)}")
    return current.replace(old, new)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", dest="python_version")
    parser.add_argument("--uv", dest="uv_version")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    current = _read_manifest()
    old_python = current["python"]
    old_uv = current["uv"]

    if args.check:
        if args.python_version or args.uv_version:
            parser.error("--check cannot be combined with --python or --uv")
        _assert_consistent(old_python, old_uv)
        return

    if not args.python_version or not args.uv_version:
        parser.error("--python and --uv are required when updating")
    _validate_version("Python", args.python_version)
    _validate_version("uv", args.uv_version)

    planned: dict[Path, str] = {}
    for relative in PYTHON_FILES:
        path = SKILL_ROOT / relative
        planned[path] = _updated_text(path, old_python, args.python_version)
    for relative in UV_FILES:
        path = SKILL_ROOT / relative
        base = planned.get(path, path.read_text(encoding="utf-8"))
        if old_uv not in base:
            raise RuntimeError(f"Expected {old_uv!r} in {relative}")
        planned[path] = base.replace(old_uv, args.uv_version)

    for path, content in planned.items():
        path.write_text(content, encoding="utf-8")
    MANIFEST.write_text(
        f'python = "{args.python_version}"\nuv = "{args.uv_version}"\n',
        encoding="utf-8",
    )
    _assert_consistent(args.python_version, args.uv_version)


if __name__ == "__main__":
    main()
