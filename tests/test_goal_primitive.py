from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.active_line_context import build_active_line_context
from openclaw_mem.goal_primitive import build_goal_status, load_goal_receipt, render_goal_status


class TestGoalPrimitive(unittest.TestCase):
    def test_builds_read_only_goal_status(self):
        status = build_goal_status(
            {
                "goal": {
                    "goal_id": "self-improvement-pilot",
                    "objective": "Ship read-only goal status",
                    "status": "active",
                    "phase": "phase-1",
                    "next_gate": "run tests",
                    "continuation_owner": "Lyria",
                    "completion_verifier": "pytest",
                }
            },
            source_ref="fixture://goal",
        )
        self.assertTrue(status["ok"])
        self.assertFalse(status["writes_performed"])
        self.assertEqual(status["goal"]["goal_id"], "self-improvement-pilot")
        self.assertTrue(status["goal"]["active"])
        self.assertTrue(status["goal"]["has_verifier"])
        self.assertIn("writes_performed=false", render_goal_status(status))

    def test_active_goal_without_continuation_warns(self):
        status = build_goal_status({"goal_id": "g", "objective": "Do it", "status": "active", "next_gate": "next"})
        self.assertTrue(status["ok"])
        self.assertIn("continuation owner", " ".join(status["warnings"]))

    def test_missing_objective_fails(self):
        status = build_goal_status({"goal_id": "g", "status": "active"})
        self.assertFalse(status["ok"])
        self.assertIn("objective", " ".join(status["errors"]))

    def test_invalid_status_fails(self):
        status = build_goal_status({"goal_id": "g", "objective": "Do it", "status": "running-hot"})
        self.assertFalse(status["ok"])
        self.assertIn("status", " ".join(status["errors"]))

    def test_load_goal_receipt_requires_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "goal.json"
            good.write_text(json.dumps({"goal_id": "g", "objective": "x", "status": "complete"}), encoding="utf-8")
            self.assertEqual(load_goal_receipt(good)["goal_id"], "g")
            bad = Path(tmp) / "bad.json"
            bad.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_goal_receipt(bad)

    def test_goal_receipt_can_feed_context_pack_fragment(self):
        receipt = {
            "goal": {
                "goal_id": "survival-pack",
                "objective": "Survive compaction",
                "status": "active",
                "next_gate": "pack current gate",
                "continuation_owner": "operator",
                "completion_verifier": "context fragment readback",
            }
        }
        fragment = build_active_line_context(receipt, source_ref="test://goal")
        self.assertFalse(fragment["writes_performed"])
        self.assertEqual(fragment["active_line"]["goal_id"], "survival-pack")
        self.assertTrue(fragment["active_line"]["has_verifier"])
        self.assertIn("active-line:survival-pack", fragment["context_pack_fragment"]["bundle_text"])


if __name__ == "__main__":
    unittest.main()
