from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.governed_release import release_check, review_apply_plan
from openclaw_mem.mutation_framework import build_plan


class TestGovernedRelease(unittest.TestCase):
    def test_apply_review_allows_l1(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(mutations=[{"action": "write_file", "path": "x.txt", "content": "x", "risk_class": "L1"}])
            review = review_apply_plan(plan, allowed_root=Path(tmp) / "sandbox")
        self.assertTrue(review["ok"])
        self.assertEqual(review["decision"], "advisory_allow_local_apply")
        self.assertFalse(review["writes_performed"])

    def test_apply_review_blocks_l2_without_config_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(mutations=[{"action": "write_file", "path": "x.txt", "content": "x", "risk_class": "L2"}])
            review = review_apply_plan(plan, allowed_root=Path(tmp) / "sandbox")
        self.assertFalse(review["ok"])
        self.assertIn("l2_requires_config_gate", review["reasons"])

    def test_apply_review_allows_l2_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(mutations=[{"action": "write_file", "path": "x.txt", "content": "x", "risk_class": "L2"}])
            review = review_apply_plan(plan, allowed_root=Path(tmp) / "sandbox", l2_enabled=True)
        self.assertTrue(review["ok"])
        self.assertEqual(review["decision"], "advisory_allow_l2_local_apply")

    def test_apply_review_blocks_l3_l4_even_with_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(mutations=[{"action": "write_file", "path": "x.txt", "content": "x", "risk_class": "L4"}])
            review = review_apply_plan(plan, allowed_root=Path(tmp) / "sandbox", ck_approved=True, human_approved=True, l2_enabled=True)
        self.assertFalse(review["ok"])
        self.assertIn("l3_l4_not_auto_applyable", review["reasons"])

    def test_apply_review_reports_invalid_plan_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = {"schema_version": "wrong", "mutations": []}
            review = review_apply_plan(plan, allowed_root=Path(tmp) / "sandbox")
        self.assertFalse(review["ok"])
        self.assertIn("invalid_plan_schema", review["reasons"])

    def test_release_check_passes_consistent_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openclaw_mem").mkdir()
            (root / "docs").mkdir()
            (root / "pyproject.toml").write_text('version = "9.9.9"\n', encoding="utf-8")
            (root / "openclaw_mem" / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
            (root / "uv.lock").write_text('[[package]]\nname = "openclaw-context-pack"\nversion = "9.9.9"\n', encoding="utf-8")
            (root / "CHANGELOG.md").write_text('## [9.9.9] - 2026-05-12\n', encoding="utf-8")
            (root / "docs" / "2026-05-12_self-improvement-slice-7-receipt.md").write_text("receipt\n", encoding="utf-8")
            (root / "docs" / "self-improvement-slice-7.md").write_text("public safe\n", encoding="utf-8")
            check = release_check(repo_root=root, expected_version="9.9.9")
        self.assertTrue(check["ok"])
        self.assertTrue(check["checks"]["version_consistent"])
        self.assertTrue(check["checks"]["public_safety_clean"])

    def test_release_check_fails_version_and_public_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openclaw_mem").mkdir()
            (root / "docs").mkdir()
            (root / "pyproject.toml").write_text('version = "9.9.9"\n', encoding="utf-8")
            (root / "openclaw_mem" / "__init__.py").write_text('__version__ = "9.9.8"\n', encoding="utf-8")
            (root / "uv.lock").write_text('[[package]]\nname = "some-dependency"\nversion = "9.9.9"\n[[package]]\nname = "openclaw-context-pack"\nversion = "9.9.8"\n', encoding="utf-8")
            (root / "CHANGELOG.md").write_text('## [9.9.8] - 2026-05-12\n', encoding="utf-8")
            (root / "docs" / "self-improvement-slice-7.md").write_text("/home/ck secret\n", encoding="utf-8")
            check = release_check(repo_root=root, expected_version="9.9.9")
        self.assertFalse(check["ok"])
        self.assertIn("init_version_mismatch", check["errors"])
        self.assertIn("public_safety_markers_found", check["errors"])


if __name__ == "__main__":
    unittest.main()
