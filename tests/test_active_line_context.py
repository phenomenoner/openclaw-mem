from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.active_line_context import build_active_line_context, load_receipt


class TestActiveLineContext(unittest.TestCase):
    def test_builds_context_pack_fragment_from_goal_receipt(self):
        receipt = {
            "goal": {
                "goal_id": "demo-goal",
                "objective": "Ship the synthetic proof",
                "status": "active",
                "updated_at": "2026-05-10T00:00:00Z",
                "next_gate": "run verifier",
                "stop_loss": "two failed attempts",
            }
        }
        context = build_active_line_context(receipt, source_ref="synthetic://goal")
        self.assertEqual(context["schema_version"], "openclaw-mem.active-line-context.v0")
        self.assertFalse(context["writes_performed"])
        self.assertEqual(context["active_line"]["goal_id"], "demo-goal")
        self.assertEqual(context["active_line"]["status"], "active")
        fragment = context["context_pack_fragment"]
        self.assertIn("active-line:demo-goal", fragment["bundle_text"])
        self.assertEqual(fragment["items"][0]["type"], "active_line")
        self.assertEqual(fragment["items"][0]["importance"], "must_remember")

    def test_load_receipt_requires_json_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            path.write_text(json.dumps({"goal_id": "demo", "status": "complete"}), encoding="utf-8")
            self.assertEqual(load_receipt(path)["goal_id"], "demo")
            bad = Path(tmp) / "bad.json"
            bad.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_receipt(bad)

    def test_completed_goal_is_nice_to_have(self):
        context = build_active_line_context({"goal_id": "done", "status": "complete", "objective": "Finished"})
        self.assertEqual(context["context_pack_fragment"]["items"][0]["importance"], "nice_to_have")


if __name__ == "__main__":
    unittest.main()
