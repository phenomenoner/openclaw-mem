import json
import tempfile
import unittest
from pathlib import Path

from openclaw_mem import self_curator


class SelfCuratorTests(unittest.TestCase):
    def test_skill_review_packet_is_review_only_and_detects_refresh_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skills"
            skill = root / "stub-skill"
            skill.mkdir(parents=True)
            source = skill / "SKILL.md"
            source.write_text(
                "---\nname: stub-skill\ndescription: tiny\n---\n\nTODO\n",
                encoding="utf-8",
            )
            before = source.read_text(encoding="utf-8")

            packet = self_curator.build_skill_review(skill_roots=[root], run_id="test-run")

            self.assertEqual(packet["kind"], self_curator.PACKET_KIND)
            self.assertEqual(packet["mode"], "review_only")
            self.assertEqual(packet["scope"], "skill")
            self.assertEqual(packet["writes_performed"], 0)
            self.assertEqual(packet["summary"]["writes_performed"], 0)
            self.assertEqual(packet["summary"]["skills_scanned"], 1)
            self.assertEqual(packet["summary"]["candidate_count"], 1)
            self.assertEqual(packet["candidates"][0]["lifecycle_action"], "refresh")
            self.assertTrue(packet["candidates"][0]["checkpoint_required"])
            self.assertEqual(source.read_text(encoding="utf-8"), before)

    def test_rejects_path_traversal_run_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skills"
            skill = root / "stub-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\n\nTODO\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                self_curator.build_skill_review(skill_roots=[root], run_id="../../escape")

            packet = self_curator.build_skill_review(skill_roots=[root], run_id="safe-run")
            packet["run_id"] = "../escape"
            with self.assertRaises(ValueError):
                self_curator.write_review_artifacts(packet, Path(td) / "out")
            self.assertFalse((Path(td) / "escape").exists())

    def test_write_review_artifacts_only_writes_run_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skills"
            skill = root / "substantial"
            skill.mkdir(parents=True)
            source = skill / "SKILL.md"
            source.write_text(
                "---\nname: substantial\ndescription: A real skill with enough body to review safely.\n---\n\n"
                + "Use this skill for deterministic lifecycle scanner tests. " * 12,
                encoding="utf-8",
            )
            before = source.read_text(encoding="utf-8")
            packet = self_curator.build_skill_review(skill_roots=[root], run_id="artifact-run")
            artifacts = self_curator.write_review_artifacts(packet, Path(td) / "out")

            review = Path(artifacts["review_json"])
            report = Path(artifacts["report_md"])
            self.assertTrue(review.exists())
            self.assertTrue(report.exists())
            loaded = json.loads(review.read_text(encoding="utf-8"))
            self.assertEqual(loaded["writes_performed"], 0)
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("Self Curator skill lifecycle review", report_text)
            self.assertIn("source_packet: `review.json`", report_text)
            self.assertEqual(source.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
