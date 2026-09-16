"""Check that incomplete research and missing transfer evidence cannot disappear from reports."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "_audit"
        shutil.copytree(SKILL / "tests/audit_outputs_good", self.root)

    def run_validator(self):
        return subprocess.run(
            [sys.executable, str(SKILL / "scripts/validate_audit_outputs.py"), str(self.root)],
            capture_output=True, text=True,
        )

    def test_explicitly_incomplete_research_is_a_valid_report(self):
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("JUDGMENT NOT VERIFIED", result.stdout)

    def test_missing_curriculum_report_fails(self):
        (self.root / "curriculum.audit.md").unlink()
        self.assertNotEqual(self.run_validator().returncode, 0)

    def test_missing_transfer_evidence_fails(self):
        path = self.root / "reader_paths.audit.md"
        path.write_text(path.read_text().replace("Evidence:", "Omitted:"))
        self.assertNotEqual(self.run_validator().returncode, 0)

    def test_every_transfer_checkpoint_requires_reasoning(self):
        path = self.root / "reader_paths.audit.md"
        path.write_text(path.read_text() + "\n## Later checkpoint\nTRANSFER: PASS\n"
                        "Checkpoint: final\nScenario: changed input\nEvidence: final note\n")
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checkpoint missing Reasoning:", result.stdout)

    def test_invalid_research_status_fails(self):
        path = self.root / "curriculum.audit.md"
        path.write_text(path.read_text().replace("Research: INCOMPLETE", "Research: TRUST-MEMORY"))
        self.assertNotEqual(self.run_validator().returncode, 0)

    def test_invalid_transfer_status_fails(self):
        path = self.root / "reader_paths.audit.md"
        path.write_text(path.read_text().replace("TRANSFER: PASS", "TRANSFER: PROBABLY"))
        self.assertNotEqual(self.run_validator().returncode, 0)


if __name__ == "__main__":
    unittest.main()
