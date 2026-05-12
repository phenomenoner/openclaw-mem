from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.skill_capture import MAX_TEXT_CHARS, build_proposal, write_proposal


class TestSkillCapture(unittest.TestCase):
    def test_builds_l1_staged_proposal_without_live_write(self):
        proposal = build_proposal(
            text="When a command changes package version, refresh uv.lock before PR checks.",
            source_ref="test://turn",
            target_skill="ck-software-engineering-ops",
            rationale="prevents CI lockfile failure",
            run_id="demo-run",
        )
        self.assertTrue(proposal["ok"])
        self.assertEqual(proposal["mode"], "stage")
        self.assertEqual(proposal["risk_class"], "L1")
        self.assertFalse(proposal["writes_performed"])
        self.assertEqual(proposal["target_skill"], "ck-software-engineering-ops")

    def test_rejects_path_like_target_skill(self):
        proposal = build_proposal(text="x", target_skill="../SKILL.md")
        self.assertFalse(proposal["ok"])
        self.assertIn("target_skill", " ".join(proposal["errors"]))

    def test_rejects_oversized_text(self):
        proposal = build_proposal(text="x" * (MAX_TEXT_CHARS + 1))
        self.assertFalse(proposal["ok"])
        self.assertIn("exceeds", " ".join(proposal["errors"]))

    def test_write_proposal_marks_only_staged_artifact_write(self):
        proposal = build_proposal(text="Capture this learning", rationale="demo")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_proposal(proposal, out_dir=tmp)
            stored = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertTrue(stored["writes_performed"])
            self.assertEqual(stored["write_scope"], "staged_proposal_artifact")
            self.assertTrue(Path(path).name.startswith("skill-capture-"))


if __name__ == "__main__":
    unittest.main()
