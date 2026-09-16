"""Exercise learning-contract invariants, compatibility, and mirrored teaching policy."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

MAKER = Path(__file__).resolve().parents[1]
REVIEWER = MAKER.parent / "note-reviewer"


class ContractRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "collection"
        shutil.copytree(MAKER / "tests/fixtures/good_collection", self.root)
        self.contract_path = self.root / "_meta/learning_contract.json"
        self.data = json.loads(self.contract_path.read_text())

    def run_contract(self):
        self.contract_path.write_text(json.dumps(self.data))
        return subprocess.run(
            [sys.executable, str(MAKER / "scripts/validate_learning_contract.py"), str(self.root)],
            capture_output=True, text=True,
        )

    def make_v2(self):
        self.data.update(
            schema_version=2,
            assumed_knowledge=["basic programming"],
            scope="Trace one transition; deployment is excluded",
            research="_meta/curriculum_research.md",
            prerequisite_bridges=[{"concept": "stored state", "owner": "01_first_result.md"}],
            transfer_checks=[{
                "path_name": "First-time path",
                "after_note": "02_mental_model.md",
                "prompt": "Predict the result after changing the input without changing stored state.",
                "expected_reasoning": "Apply the earlier transition rule to the unchanged stored state.",
                "evidence_notes": ["01_first_result.md", "02_mental_model.md"],
            }],
        )
        (self.root / "_meta/curriculum_research.md").write_text(
            "# Research\nResearch: INCOMPLETE\nExternal source verification unavailable in this fixture.\n"
        )

    def test_legacy_contract_still_supported(self):
        result = self.run_contract()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("LEGACY CONTRACT", result.stdout)

    def test_v2_tracks_unverified_research_without_claiming_semantic_success(self):
        self.make_v2()
        result = self.run_contract()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("RESEARCH AND TRANSFER NOT VERIFIED", result.stdout)

    def test_missing_audience_research_and_checkpoint_are_rejected(self):
        for field in ("assumed_knowledge", "scope", "research", "prerequisite_bridges", "transfer_checks"):
            with self.subTest(field=field):
                self.make_v2()
                self.data.pop(field)
                self.assertNotEqual(self.run_contract().returncode, 0)

    def test_transfer_cannot_borrow_later_teaching(self):
        self.make_v2()
        self.data["transfer_checks"][0]["after_note"] = "01_first_result.md"
        result = self.run_contract()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("later or off-path", result.stdout)

    def test_delayed_payoff_is_allowed_with_prerequisite_rationale(self):
        self.make_v2()
        third = "03_composition.md"
        (self.root / third).write_text("# Composing the learned mechanisms\n")
        self.data["notes"].append({
            "path": third, "role": "implementation", "prerequisites": ["02_mental_model.md"],
            "entry_capability": "Can explain the individual transition",
            "exit_capability": "Can explain composition",
        })
        path = self.data["paths"][0]
        path["entries"].append(third)
        path["understanding_payoff_by"] = 3
        self.assertNotEqual(self.run_contract().returncode, 0)
        path["milestone_rationale"] = "The composition needs the two previously taught mechanisms."
        result = self.run_contract()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_broken_prerequisite_order_remains_a_failure(self):
        self.make_v2()
        self.data["paths"][0]["entries"].reverse()
        result = self.run_contract()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("appears before prerequisite", result.stdout)

    def test_pure_reference_can_explain_transfer_exemption(self):
        self.make_v2()
        self.data["paths"][0]["kind"] = "reference"
        self.data["transfer_checks"] = []
        self.assertNotEqual(self.run_contract().returncode, 0)
        self.data["transfer_exemption"] = "This path is a lookup index, not a teaching sequence."
        self.assertEqual(self.run_contract().returncode, 0)

    def test_long_prose_without_house_style_markers_is_not_structurally_invalid(self):
        note = self.root / "03_long.md"
        note.write_text("# A coherent long lesson\n\n" + "Explanatory prose.\n" * 510)
        result = subprocess.run(
            [sys.executable, str(MAKER / "scripts/validate_notes.py"), str(note)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PEDAGOGY NOT VERIFIED", result.stdout)

    def test_broken_link_remains_a_structural_failure(self):
        note = self.root / "03_broken.md"
        note.write_text("# Lesson\n[Needed prerequisite](absent.md)\n")
        result = subprocess.run(
            [sys.executable, str(MAKER / "scripts/validate_notes.py"), str(note)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_directory_scan_checks_existing_unnumbered_notes_and_skips_metadata(self):
        (self.root / "lesson.md").write_text("# Lesson\n[Missing bridge](missing.md)\n")
        (self.root / "_meta/internal.md").write_text("[Contributor placeholder](absent.md)\n")
        command = [sys.executable, str(MAKER / "scripts/validate_notes.py"), str(self.root)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lesson.md", result.stdout)
        self.assertNotIn("internal.md", result.stdout)
        (self.root / "lesson.md").write_text("# Lesson\n[Earlier note](01_first_result.md)\n")
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_shared_references_remain_synchronized(self):
        for name in ("how-we-write-notes.md", "example-selection.md", "curriculum-research.md", "delegation.md"):
            with self.subTest(name=name):
                self.assertEqual((MAKER / "references" / name).read_bytes(),
                                 (REVIEWER / "references" / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
