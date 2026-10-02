"""The two bundled templates must not drift apart.

`assets/workspace-template/` and `assets/single-service-template/` share every
tooling decision; they differ only in paths, package names, and the few lines
listed here. Each test normalizes those differences and requires the rest to be
identical, so a rule changed in one template fails until it is changed in both.

Run: python3 -m unittest discover -s tests   (from the skill root)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parents[1]
WORKSPACE = SKILL / "assets/workspace-template"
SINGLE = SKILL / "assets/single-service-template"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(read(path))


def without(table: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in table.items() if key not in keys}


class IdenticalFilesTests(unittest.TestCase):
    def test_shared_files_are_byte_identical(self) -> None:
        for name in (".gitignore", ".dockerignore", ".python-version"):
            with self.subTest(file=name):
                self.assertEqual(read(WORKSPACE / name), read(SINGLE / name))


class PyprojectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = toml(WORKSPACE / "pyproject.toml")
        self.single = toml(SINGLE / "pyproject.toml")

    def test_uv_pin_and_dev_group(self) -> None:
        self.assertEqual(
            self.workspace["tool"]["uv"]["required-version"],
            self.single["tool"]["uv"]["required-version"],
        )
        self.assertEqual(
            self.workspace["dependency-groups"], self.single["dependency-groups"]
        )

    def test_ruff(self) -> None:
        workspace, single = self.workspace["tool"]["ruff"], self.single["tool"]["ruff"]
        self.assertEqual(without(workspace, "lint"), without(single, "lint"))
        self.assertEqual(
            without(workspace["lint"], "isort"), without(single["lint"], "isort")
        )

    def test_pytest(self) -> None:
        self.assertEqual(
            without(self.workspace["tool"]["pytest"]["ini_options"], "testpaths"),
            without(self.single["tool"]["pytest"]["ini_options"], "testpaths"),
        )

    def test_coverage(self) -> None:
        workspace, single = self.workspace["tool"]["coverage"], self.single["tool"]["coverage"]
        self.assertEqual(without(workspace["run"], "source"), without(single["run"], "source"))
        self.assertEqual(workspace["report"], single["report"])

    def test_mypy(self) -> None:
        # The single service sets mypy_path; the workspace sets MYPYPATH per member.
        self.assertEqual(
            self.workspace["tool"]["mypy"],
            without(self.single["tool"]["mypy"], "mypy_path"),
        )
        self.assertEqual(self.single["tool"]["mypy"]["mypy_path"], ["src", "tests"])

    def test_service_contracts(self) -> None:
        def service_contracts(document: dict[str, Any], package: str) -> list[str]:
            contracts = document["tool"]["importlinter"]["contracts"]
            rendered = [
                repr(contract).replace(package, "PKG")
                for contract in contracts
                if contract["name"].startswith(f"{package}:")
            ]
            self.assertTrue(rendered, f"no contracts for {package}")
            return rendered

        self.assertEqual(
            service_contracts(self.workspace, "sample_api"),
            service_contracts(self.single, "sample_service"),
        )


class PreCommitTests(unittest.TestCase):
    def test_hooks_match_except_mypy_entry(self) -> None:
        def normalized(path: Path) -> str:
            text = read(path)
            text = re.sub(r"name: mypy.*", "name: mypy", text)
            return re.sub(r"entry: .*mypy.*", "entry: MYPY", text)

        self.assertEqual(
            normalized(WORKSPACE / ".pre-commit-config.yaml"),
            normalized(SINGLE / ".pre-commit-config.yaml"),
        )


class CiTests(unittest.TestCase):
    def test_workflow_matches_except_workspace_sync(self) -> None:
        workspace = read(WORKSPACE / ".github/workflows/ci.yml")
        workspace = workspace.replace("uv sync --locked --all-packages", "uv sync --locked")
        workspace = workspace.replace("mypy per member", "mypy")
        self.assertEqual(workspace, read(SINGLE / ".github/workflows/ci.yml"))


class DockerfileTests(unittest.TestCase):
    @staticmethod
    def stage(text: str, start: str, end: str) -> str:
        return text[text.index(start) : text.index(end)]

    def test_base_and_runtime_stages_match(self) -> None:
        workspace = read(WORKSPACE / "services/api/Dockerfile")
        single = read(SINGLE / "Dockerfile")
        self.assertEqual(
            self.stage(workspace, "# syntax", "# Copy dependency metadata"),
            self.stage(single, "# syntax", "# Copy dependency metadata"),
        )
        self.assertEqual(
            self.stage(workspace, "FROM python-base AS runtime", "HEALTHCHECK"),
            self.stage(single, "FROM python-base AS runtime", "HEALTHCHECK"),
        )

    def test_single_service_has_no_workspace_flags(self) -> None:
        single = read(SINGLE / "Dockerfile")
        for flag in ("--package", "--no-install-workspace", "services/", "libs/"):
            with self.subTest(flag=flag):
                self.assertNotIn(flag, single)


class LocalStackTests(unittest.TestCase):
    def test_both_modes_ship_compose_and_root_env_example(self) -> None:
        for root in (WORKSPACE, SINGLE):
            for name in ("compose.yaml", ".env.example"):
                with self.subTest(file=root / name):
                    self.assertTrue((root / name).is_file())

    def test_every_deployable_env_example_starts_required_with_environment(self) -> None:
        services = sorted(path for path in (WORKSPACE / "services").iterdir() if path.is_dir())
        self.assertTrue(services)
        for path in (SINGLE / ".env.example", *(service / ".env.example" for service in services)):
            with self.subTest(file=path):
                text = read(path)
                self.assertIn("# REQUIRED", text)
                assignments = [
                    line for line in text.splitlines() if "=" in line and not line.startswith("#")
                ]
                self.assertTrue(assignments)
                self.assertTrue(assignments[0].startswith("ENVIRONMENT_NAME="))


class ToolchainTests(unittest.TestCase):
    def test_pins_are_consistent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SKILL / "scripts/update_toolchain.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
