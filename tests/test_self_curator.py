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

    def test_apply_plan_checkpoint_verify_and_rollback_restores_exact_hash(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            skill = ws / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: demo\n---\n\nBody\n", encoding="utf-8")
            before_sha = self_curator.sha256_file(skill)
            mutations = [
                {
                    "mutation_id": "m1",
                    "target_ref": "skills/demo/SKILL.md",
                    "action": "set_frontmatter_field",
                    "field": "description",
                    "value": "Demo skill refreshed by checkpointed curator.",
                    "preconditions": {"sha256": before_sha},
                }
            ]
            plan = self_curator.build_apply_plan(mutations=mutations, plan_id="plan-demo")
            receipt = self_curator.apply_plan(
                plan=plan,
                workspace_root=ws,
                checkpoint_root=Path(td) / "checkpoints",
                receipt_root=Path(td) / "receipts",
                run_id="apply-demo",
            )

            self.assertEqual(receipt["kind"], self_curator.APPLY_RECEIPT_KIND)
            self.assertEqual(receipt["writes_performed"], 1)
            self.assertIn("description: Demo skill refreshed", skill.read_text(encoding="utf-8"))
            self.assertTrue(Path(receipt["diff_path"]).exists())
            verify = self_curator.verify_apply_receipt(receipt=receipt)
            self.assertTrue(verify["ok"])
            rollback = self_curator.rollback_apply_receipt(receipt=receipt)
            self.assertTrue(rollback["ok"])
            self.assertEqual(self_curator.sha256_file(skill), before_sha)

    def test_apply_plan_precondition_mismatch_fails_closed_with_zero_writes(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            skill = ws / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: demo\n---\n\nBody\n", encoding="utf-8")
            before = skill.read_text(encoding="utf-8")
            plan = self_curator.build_apply_plan(
                mutations=[
                    {
                        "mutation_id": "m1",
                        "target_ref": "skills/demo/SKILL.md",
                        "action": "replace_text",
                        "preconditions": {"sha256": "0" * 64},
                        "patch": {"old_text": "Body", "new_text": "Changed"},
                    }
                ],
                plan_id="bad-precondition",
            )
            receipt = self_curator.apply_plan(
                plan=plan,
                workspace_root=ws,
                checkpoint_root=Path(td) / "checkpoints",
                receipt_root=Path(td) / "receipts",
                run_id="apply-fail",
            )

            self.assertEqual(receipt["mode"], "failed_closed")
            self.assertEqual(receipt["writes_performed"], 0)
            self.assertEqual(skill.read_text(encoding="utf-8"), before)

    def test_archive_file_apply_and_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            source = ws / "skills" / "old" / "SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text("---\nname: old\ndescription: old\n---\n\nBody\n", encoding="utf-8")
            before_sha = self_curator.sha256_file(source)
            dest_ref = "skills/.archive/old/SKILL.md"
            plan = self_curator.build_apply_plan(
                mutations=[
                    {
                        "mutation_id": "archive-old",
                        "target_ref": "skills/old/SKILL.md",
                        "dest_ref": dest_ref,
                        "action": "archive_file",
                        "preconditions": {"sha256": before_sha},
                    }
                ],
                plan_id="archive-plan",
            )
            receipt = self_curator.apply_plan(
                plan=plan,
                workspace_root=ws,
                checkpoint_root=Path(td) / "checkpoints",
                receipt_root=Path(td) / "receipts",
                run_id="archive-run",
            )
            archived = ws / dest_ref
            self.assertFalse(source.exists())
            self.assertTrue(archived.exists())
            self.assertEqual(receipt["writes_performed"], 1)
            verify = self_curator.verify_apply_receipt(receipt=receipt)
            self.assertTrue(verify["ok"])
            archived.write_text("tampered", encoding="utf-8")
            verify_tampered = self_curator.verify_apply_receipt(receipt=receipt)
            self.assertFalse(verify_tampered["ok"])
            rollback = self_curator.rollback_apply_receipt(receipt=receipt)
            self.assertTrue(rollback["ok"])
            self.assertTrue(source.exists())
            self.assertFalse(archived.exists())
            self.assertEqual(self_curator.sha256_file(source), before_sha)

    def test_verify_detects_tampered_file_after_apply(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            skill = ws / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: demo\n---\n\nBody\n", encoding="utf-8")
            before_sha = self_curator.sha256_file(skill)
            plan = self_curator.build_apply_plan(
                mutations=[{"mutation_id": "m1", "target_ref": "skills/demo/SKILL.md", "action": "replace_text", "preconditions": {"sha256": before_sha}, "patch": {"old_text": "Body", "new_text": "Changed"}}],
                plan_id="tamper-plan",
            )
            receipt = self_curator.apply_plan(plan=plan, workspace_root=ws, checkpoint_root=Path(td) / "checkpoints", receipt_root=Path(td) / "receipts", run_id="tamper-run")
            skill.write_text(skill.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
            verify = self_curator.verify_apply_receipt(receipt=receipt)
            self.assertFalse(verify["ok"])

    def test_exception_inside_first_mutation_restores_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            skill = ws / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: demo\n---\n\nBody\n", encoding="utf-8")
            before = skill.read_text(encoding="utf-8")
            before_sha = self_curator.sha256_file(skill)
            plan = self_curator.build_apply_plan(
                mutations=[{"mutation_id": "m1", "target_ref": "skills/demo/SKILL.md", "action": "replace_text", "preconditions": {"sha256": before_sha}, "patch": {"old_text": "Body", "new_text": "Changed"}}],
                plan_id="first-exception-plan",
            )
            original = self_curator._apply_one_mutation
            def write_then_boom(mutation, *, workspace_root):
                target = Path(workspace_root) / mutation["target_ref"]
                target.write_text(target.read_text(encoding="utf-8").replace("Body", "Changed"), encoding="utf-8")
                raise RuntimeError("boom after write")
            self_curator._apply_one_mutation = write_then_boom
            try:
                receipt = self_curator.apply_plan(plan=plan, workspace_root=ws, checkpoint_root=Path(td) / "checkpoints", receipt_root=Path(td) / "receipts", run_id="first-exception-run")
            finally:
                self_curator._apply_one_mutation = original
            self.assertEqual(receipt["mode"], "failed_closed")
            self.assertEqual(receipt["writes_performed"], 0)
            self.assertEqual(skill.read_text(encoding="utf-8"), before)

    def test_exception_after_prior_write_restores_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            skill = ws / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: demo\n---\n\nBody\n", encoding="utf-8")
            before = skill.read_text(encoding="utf-8")
            before_sha = self_curator.sha256_file(skill)
            plan = self_curator.build_apply_plan(
                mutations=[
                    {"mutation_id": "m1", "target_ref": "skills/demo/SKILL.md", "action": "replace_text", "preconditions": {"sha256": before_sha}, "patch": {"old_text": "Body", "new_text": "Changed"}},
                    {"mutation_id": "m2", "target_ref": "skills/demo/SKILL.md", "action": "replace_text", "patch": {"old_text": "Changed", "new_text": "Boom"}},
                ],
                plan_id="exception-plan",
            )
            original = self_curator._apply_one_mutation
            def boom_once(mutation, *, workspace_root):
                if mutation.get("mutation_id") == "m2":
                    raise RuntimeError("boom")
                return original(mutation, workspace_root=workspace_root)
            self_curator._apply_one_mutation = boom_once
            try:
                receipt = self_curator.apply_plan(plan=plan, workspace_root=ws, checkpoint_root=Path(td) / "checkpoints", receipt_root=Path(td) / "receipts", run_id="exception-run")
            finally:
                self_curator._apply_one_mutation = original
            self.assertEqual(receipt["mode"], "failed_closed")
            self.assertEqual(receipt["writes_performed"], 0)
            self.assertEqual(skill.read_text(encoding="utf-8"), before)
            self.assertIsNotNone(receipt.get("exception"))

    def test_write_file_rollback_removes_expected_absent_file(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            ws.mkdir()
            plan = self_curator.build_apply_plan(
                mutations=[{"mutation_id": "new", "target_ref": "skills/new/SKILL.md", "action": "write_file", "preconditions": {"exists": False}, "content": "---\nname: new\ndescription: new\n---\n\nBody\n"}],
                plan_id="write-plan",
            )
            receipt = self_curator.apply_plan(plan=plan, workspace_root=ws, checkpoint_root=Path(td) / "checkpoints", receipt_root=Path(td) / "receipts", run_id="write-run")
            target = ws / "skills" / "new" / "SKILL.md"
            self.assertTrue(target.exists())
            rollback = self_curator.rollback_apply_receipt(receipt=receipt)
            self.assertTrue(rollback["ok"])
            self.assertFalse(target.exists())

    def test_apply_rejects_directory_targets(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            (ws / "skills" / "dir").mkdir(parents=True)
            plan = self_curator.build_apply_plan(
                mutations=[{"mutation_id": "bad", "target_ref": "skills/dir", "action": "write_file", "content": "x"}],
                plan_id="dir-target",
            )
            with self.assertRaises(ValueError):
                self_curator.validate_apply_plan(plan, workspace_root=ws)

    def test_archive_failure_after_prior_write_restores_source_and_dest(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            a = ws / "skills" / "a" / "SKILL.md"
            old = ws / "skills" / "old" / "SKILL.md"
            dest = ws / "skills" / ".archive" / "old" / "SKILL.md"
            a.parent.mkdir(parents=True)
            old.parent.mkdir(parents=True)
            dest.parent.mkdir(parents=True)
            a.write_text("A body", encoding="utf-8")
            old.write_text("old", encoding="utf-8")
            dest.write_text("already", encoding="utf-8")
            a_before = a.read_text(encoding="utf-8")
            old_before = old.read_text(encoding="utf-8")
            dest_before = dest.read_text(encoding="utf-8")
            plan = self_curator.build_apply_plan(
                mutations=[
                    {"mutation_id": "m1", "target_ref": "skills/a/SKILL.md", "action": "replace_text", "preconditions": {"sha256": self_curator.sha256_file(a)}, "patch": {"old_text": "A body", "new_text": "changed"}},
                    {"mutation_id": "m2", "target_ref": "skills/old/SKILL.md", "dest_ref": "skills/.archive/old/SKILL.md", "action": "archive_file", "preconditions": {"sha256": self_curator.sha256_file(old)}},
                ],
                plan_id="archive-fail-plan",
            )
            receipt = self_curator.apply_plan(plan=plan, workspace_root=ws, checkpoint_root=Path(td) / "checkpoints", receipt_root=Path(td) / "receipts", run_id="archive-fail")
            self.assertEqual(receipt["mode"], "failed_closed")
            self.assertEqual(receipt["writes_performed"], 0)
            self.assertEqual(a.read_text(encoding="utf-8"), a_before)
            self.assertEqual(old.read_text(encoding="utf-8"), old_before)
            self.assertEqual(dest.read_text(encoding="utf-8"), dest_before)

    def test_apply_plan_rejects_unsafe_targets(self):
        plan = self_curator.build_apply_plan(
            mutations=[{"mutation_id": "bad", "target_ref": "../escape", "action": "write_file", "content": "x"}],
            plan_id="unsafe-target",
        )
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                self_curator.validate_apply_plan(plan, workspace_root=Path(td))


if __name__ == "__main__":
    unittest.main()
