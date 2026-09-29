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

    def landscape_item(self, **overrides):
        fields = {
            "Status": "GA", "Relevance": "ADD-TO-NOTES", "In collection": "absent",
            "Why it matters": "changes the recommended baseline",
            "Suggested placement": "02_explain.md",
            "Sources": "https://example.org/release-notes (primary, 2026-09-29)",
        }
        fields.update(overrides)
        return "\n## New feature\n" + "".join(f"{key}: {value}\n" for key, value in fields.items())

    def test_missing_landscape_report_fails(self):
        (self.root / "landscape.audit.md").unlink()
        self.assertNotEqual(self.run_validator().returncode, 0)

    def test_complete_research_needs_items_or_explicit_no_changes(self):
        path = self.root / "landscape.audit.md"
        path.write_text(path.read_text().replace("Research: INCOMPLETE", "Research: COMPLETE"))
        self.assertNotEqual(self.run_validator().returncode, 0)
        path.write_text(path.read_text() + self.landscape_item())
        self.assertEqual(self.run_validator().returncode, 0, self.run_validator().stdout)

    def test_landscape_items_need_valid_status_and_sourced_urls(self):
        path = self.root / "landscape.audit.md"
        base = path.read_text()
        for overrides in ({"Status": "HOT"}, {"Relevance": "MAYBE"}, {"Sources": "memory"},
                          {"Status": "EMERGING"}):
            with self.subTest(overrides=overrides):
                path.write_text(base + self.landscape_item(**overrides))
                self.assertNotEqual(self.run_validator().returncode, 0)
        path.write_text(base + self.landscape_item(
            Status="EMERGING", Sources="https://a.example/talk; https://b.example/blog"))
        self.assertEqual(self.run_validator().returncode, 0)

    def test_per_note_blocks_require_visual_and_practice_verdicts(self):
        path = self.root / "root.audit.md"
        text = path.read_text()
        for field in ("VISUAL:", "PRACTICE:"):
            with self.subTest(field=field):
                path.write_text("\n".join(line for line in text.splitlines()
                                          if not line.startswith(field)) + "\n")
                self.assertNotEqual(self.run_validator().returncode, 0)

    def test_visual_fail_needs_a_finding_with_a_mermaid_sketch(self):
        path = self.root / "root.audit.md"
        text = path.read_text().replace("VISUAL: n/a; one actor and one transition; no required diagram shape.",
                                        "VISUAL: FAIL; three actors hand off a lease with no diagram.")
        path.write_text(text)
        self.assertNotEqual(self.run_validator().returncode, 0)
        path.write_text(text.replace("NO-ACTION: the fixture teaches its transition.",
                                     "FIX-HIGH: lease handoff lacks a diagram — add after line 5."))
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Mermaid sketch", result.stdout)
        path.write_text(path.read_text() + "    sequenceDiagram\n      A->>L: renew (t=20)\n")
        self.assertEqual(self.run_validator().returncode, 0, self.run_validator().stdout)

    def test_quick_mode_needs_only_note_landscape_and_metrics(self):
        for name in ("curriculum", "lesson_quality", "reader_paths", "coverage", "examples", "gaps"):
            (self.root / f"{name}.audit.md").unlink()
        command = [sys.executable, str(SKILL / "scripts/validate_audit_outputs.py"), str(self.root), "--quick"]
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        metrics = self.root / "metrics.audit.md"
        metrics.write_text("Mode: quick\n" + metrics.read_text())
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotEqual(self.run_validator().returncode, 0)


if __name__ == "__main__":
    unittest.main()
