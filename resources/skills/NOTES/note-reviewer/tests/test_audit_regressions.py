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

    def test_missing_lesson_report_fails(self):
        (self.root / "lesson_quality.audit.md").unlink()
        self.assertNotEqual(self.run_validator().returncode, 0)

    def test_structural_repair_needs_a_concrete_plan(self):
        path = self.root / "lesson_quality.audit.md"
        path.write_text(path.read_text().replace("Structure: KEEP", "Structure: REWRITE"))
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("structural repair missing Rewrite sample:", result.stdout)
        with path.open("a") as report:
            report.write("\nProposed sequence: follow the same state through the changed input.\n"
                         "Content mapping: retain the trace; develop its causal explanation.\n"
                         "Example development: change the input while holding the previous state fixed.\n"
                         "Rewrite sample: the unchanged stored state still selects the same branch, "
                         "so a new label alone cannot change this result.\n"
                         "Acceptance task: predict which changed state would select the other branch.\n")
        self.assertEqual(self.run_validator().returncode, 0)

    def test_next_field_does_not_count_as_a_rewrite_sample(self):
        self.test_structural_repair_needs_a_concrete_plan()
        path = self.root / "lesson_quality.audit.md"
        text = path.read_text()
        start = text.index("Rewrite sample:")
        end = text.index("Acceptance task:", start)
        path.write_text(text[:start] + "Rewrite sample:\n\n" + text[end:])
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("structural repair missing Rewrite sample:", result.stdout)

    def test_failed_lesson_cannot_be_marked_clean(self):
        path = self.root / "lesson_quality.audit.md"
        path.write_text(path.read_text().replace("LESSON: PASS", "LESSON: FAIL"))
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot claim NO-ACTION", result.stdout)

    def test_extractable_facts_do_not_override_failed_lesson(self):
        path = self.root / "root.audit.md"
        path.write_text(path.read_text().replace("LESSON: PASS", "LESSON: FAIL"))
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explanation cannot pass a failed lesson", result.stdout)
        path.write_text(path.read_text().replace("EXPLANATION: PASS", "EXPLANATION: FAIL")
                        .replace("NO-ACTION:", "RELATED:"))
        self.assertEqual(self.run_validator().returncode, 0)

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
