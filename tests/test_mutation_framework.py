from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openclaw_mem.mutation_framework import apply_plan, build_plan, rollback_apply_receipt, stage_plan, validate_plan


class TestMutationFramework(unittest.TestCase):
    def test_plan_validate_stage_apply_and_rollback_write_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            plan = build_plan(mutations=[{"action": "write_file", "path": "demo.txt", "content": "hello", "risk_class": "L1"}])
            validation = validate_plan(plan, allowed_root=root, allow_apply=True)
            self.assertTrue(validation["ok"])
            staged = stage_plan(plan, stage_root=Path(tmp) / "staged", allowed_root=root)
            self.assertTrue(staged["ok"])
            self.assertTrue(staged["writes_performed"])
            applied = apply_plan(plan, allowed_root=root, receipt_root=Path(tmp) / "runs")
            self.assertTrue(applied["ok"])
            self.assertTrue(applied["writes_performed"])
            self.assertEqual((root / "demo.txt").read_text(encoding="utf-8"), "hello")
            rollback = rollback_apply_receipt(applied)
            self.assertTrue(rollback["ok"])
            self.assertTrue(rollback["writes_performed"])
            self.assertFalse((root / "demo.txt").exists())

    def test_replace_text_roundtrip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            root.mkdir()
            (root / "demo.txt").write_text("before", encoding="utf-8")
            plan = build_plan(mutations=[{"action": "replace_text", "path": "demo.txt", "old": "before", "new": "after", "risk_class": "L1"}])
            applied = apply_plan(plan, allowed_root=root, receipt_root=Path(tmp) / "runs")
            self.assertTrue(applied["ok"])
            self.assertEqual((root / "demo.txt").read_text(encoding="utf-8"), "after")
            rollback_apply_receipt(applied)
            self.assertEqual((root / "demo.txt").read_text(encoding="utf-8"), "before")

    def test_blocks_protected_and_l3_l4(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            plan = build_plan(mutations=[{"action": "write_file", "path": "demo.txt", "content": "x", "risk_class": "L3", "protected": True}])
            validation = validate_plan(plan, allowed_root=root, allow_apply=True)
            self.assertFalse(validation["ok"])
            joined = " ".join(validation["errors"])
            self.assertIn("protected", joined)
            self.assertIn("manual approval", joined)

    def test_blocks_path_escape(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            plan = build_plan(mutations=[{"action": "write_file", "path": "../escape.txt", "content": "x", "risk_class": "L1"}])
            validation = validate_plan(plan, allowed_root=root, allow_apply=True)
            self.assertFalse(validation["ok"])
            self.assertIn("path", " ".join(validation["errors"]))

    def test_blocks_absolute_path(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            plan = build_plan(mutations=[{"action": "write_file", "path": "/tmp/escape.txt", "content": "x", "risk_class": "L1"}])
            validation = validate_plan(plan, allowed_root=root, allow_apply=True)
            self.assertFalse(validation["ok"])
            self.assertIn("absolute_paths_forbidden", " ".join(validation["errors"]))

    def test_rollback_missing_backup_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            receipt = {
                "schema_version": "openclaw-mem.mutation.apply.v0",
                "run_id": "apply-demo",
                "allowed_root": str(root),
                "mutations_applied": [
                    {"path": "demo.txt", "snapshot": {"path": "demo.txt", "existed": True, "backup_path": str(Path(tmp) / "missing")}}
                ],
            }
            rollback = rollback_apply_receipt(receipt)
            self.assertFalse(rollback["ok"])
            self.assertIn("missing_backup:demo.txt", rollback["errors"])

    def test_failed_apply_rolls_back_partial_changes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            root.mkdir()
            (root / "first.txt").write_text("old", encoding="utf-8")
            (root / "second.txt").write_text("unchanged", encoding="utf-8")
            plan = build_plan(
                mutations=[
                    {"action": "replace_text", "path": "first.txt", "old": "old", "new": "new", "risk_class": "L1"},
                    {"action": "replace_text", "path": "second.txt", "old": "missing", "new": "bad", "risk_class": "L1"},
                ]
            )
            applied = apply_plan(plan, allowed_root=root, receipt_root=Path(tmp) / "runs")
            self.assertFalse(applied["ok"])
            self.assertEqual((root / "first.txt").read_text(encoding="utf-8"), "old")
            self.assertEqual((root / "second.txt").read_text(encoding="utf-8"), "unchanged")


if __name__ == "__main__":
    unittest.main()
