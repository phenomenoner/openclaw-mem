from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openclaw_mem.mem_system_status import build_status, render_status


class TestMemSystemStatus(unittest.TestCase):
    def test_builds_read_only_plane_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            state = Path(tmp) / "state"
            (root / "openclaw_mem").mkdir(parents=True)
            (root / "openclaw_mem" / "context_pack_v1.py").write_text("", encoding="utf-8")
            (root / "openclaw_mem" / "goal_primitive.py").write_text("", encoding="utf-8")
            (root / "openclaw_mem" / "self_curator.py").write_text("", encoding="utf-8")
            (root / "openclaw_mem" / "skill_capture.py").write_text("", encoding="utf-8")
            (root / "openclaw_mem" / "steward_review.py").write_text("", encoding="utf-8")
            (state / "memory" / "lancedb").mkdir(parents=True)
            (state / "memory" / "openclaw-mem.sqlite").write_text("", encoding="utf-8")
            status = build_status(workspace_root=root, state_root=state)
        self.assertTrue(status["ok"])
        self.assertFalse(status["writes_performed"])
        self.assertFalse(status["topology_changed"])
        self.assertIn("Store", status["planes"])
        self.assertGreaterEqual(status["counts_by_state"].get("stable", 0), 3)
        self.assertIn("writes_performed=false", render_status(status))


if __name__ == "__main__":
    unittest.main()
