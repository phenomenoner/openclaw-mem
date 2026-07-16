from __future__ import annotations

import tempfile
import unittest
import json
import sqlite3
import subprocess
import sys
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

    def test_builds_verify_posture_with_cli_symbolic_canvas_and_readonly_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            state = Path(tmp) / "state"
            (root / "openclaw_mem").mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            (root / "openclaw_mem" / "context_pack_v1.py").write_text("", encoding="utf-8")
            (root / "openclaw_mem" / "steward_review.py").write_text("", encoding="utf-8")
            (state / "memory").mkdir(parents=True)
            db = state / "memory" / "openclaw-mem.sqlite"
            conn = sqlite3.connect(db)
            try:
                conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY)")
                conn.execute("CREATE TABLE docs_chunks (id INTEGER PRIMARY KEY)")
                conn.execute("CREATE TABLE docs_embeddings (id INTEGER PRIMARY KEY)")
                conn.execute("CREATE TABLE episodic_events (id INTEGER PRIMARY KEY)")
                conn.executemany("INSERT INTO observations DEFAULT VALUES", [(), ()])
                conn.execute("INSERT INTO docs_chunks DEFAULT VALUES")
                conn.commit()
            finally:
                conn.close()
            (state / "openclaw.json").write_text(
                json.dumps(
                    {
                        "plugins": {
                            "slots": {"memory": "openclaw-mem-engine"},
                            "entries": {
                                "openclaw-mem-engine": {
                                    "config": {
                                        "autoCapture": {"enabled": True},
                                        "autoRecall": {
                                            "enabled": False,
                                            "routeAuto": {"enabled": True},
                                        },
                                        "docsColdLane": {"enabled": True},
                                        "workingSet": {"enabled": True},
                                        "symbolicCanvas": {
                                            "autoBuild": {
                                                "enabled": True,
                                                "command": "openclaw-mem",
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = build_status(workspace_root=root, state_root=state)

        self.assertEqual(status["durable_truth_owner"]["surface_id"], "store.sqlite")
        self.assertEqual(status["memory_slot"], "openclaw-mem-engine")
        self.assertIn("openclaw-mem", status["cli_availability"])
        self.assertIn("uv", status["cli_availability"])
        self.assertIn("gbrain", status["cli_availability"])
        self.assertTrue(status["symbolic_canvas"]["enabled"])
        self.assertEqual(status["symbolic_canvas"]["configured_command"], "openclaw-mem")
        self.assertIn(status["symbolic_canvas"]["readiness"], {"ready", "missing_command"})
        self.assertFalse(status["coverage"]["qdrant_edge"]["probed"])
        self.assertEqual(status["coverage"]["sqlite"]["tables"]["observations"]["count"], 2)
        self.assertEqual(status["coverage"]["sqlite"]["tables"]["docs_chunks"]["count"], 1)
        self.assertFalse(status["writes_performed"])
        self.assertFalse(status["topology_changed"])

    def test_mem_system_verify_cli_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            state = Path(tmp) / "state"
            (root / "openclaw_mem").mkdir(parents=True)
            (state / "memory").mkdir(parents=True)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openclaw_mem",
                    "mem-system",
                    "verify",
                    "--workspace-root",
                    str(root),
                    "--state-root",
                    str(state),
                    "--json",
                ],
                check=True,
                text=True, encoding="utf-8", errors="replace",
                capture_output=True,
            )
            payload = json.loads(proc.stdout)

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["writes_performed"])
        self.assertFalse(payload["topology_changed"])

    def test_build_status_infers_state_root_from_active_harness_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            harness_home = Path(tmp) / ".agent-harness"
            db = harness_home / "memory" / "openclaw-mem.sqlite"
            root.mkdir(parents=True)
            db.parent.mkdir(parents=True)
            conn = sqlite3.connect(db)
            try:
                conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO observations DEFAULT VALUES")
                conn.commit()
            finally:
                conn.close()

            status = build_status(workspace_root=root, db_path=db)

        self.assertEqual(Path(status["state_root"]), harness_home.resolve())
        self.assertEqual(Path(status["db_path"]), db.resolve())
        self.assertEqual(status["coverage"]["sqlite"]["tables"]["observations"]["count"], 1)

    def test_mem_system_status_accepts_harness_home_and_db_cli_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            harness_home = Path(tmp) / ".agent-harness"
            db = harness_home / "memory" / "openclaw-mem.sqlite"
            root.mkdir(parents=True)
            db.parent.mkdir(parents=True)
            sqlite3.connect(db).close()

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openclaw_mem",
                    "mem-system",
                    "status",
                    "--workspace-root",
                    str(root),
                    "--harness-home",
                    str(harness_home),
                    "--db",
                    str(db),
                    "--json",
                ],
                check=True,
                text=True, encoding="utf-8", errors="replace",
                capture_output=True,
            )
            payload = json.loads(proc.stdout)

        self.assertEqual(Path(payload["state_root"]), harness_home.resolve())
        self.assertEqual(Path(payload["db_path"]), db.resolve())


if __name__ == "__main__":
    unittest.main()
