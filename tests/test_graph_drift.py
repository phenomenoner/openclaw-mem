from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.graph.drift import query_drift
from openclaw_mem.graph.refresh import refresh_topology


class TestGraphDrift(unittest.TestCase):
    def test_query_drift_detects_missing_runtime_only_and_non_ok(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "cron.job.beta", "type": "cron_job"},
                {"id": "artifact.daily-mission", "type": "artifact"},
            ],
            "edges": [],
        }

        runtime = {
            "nodes": [
                {"id": "cron.job.alpha", "status": "ok"},
                {"id": "cron.job.beta", "status": "stale"},
                {"id": "cron.job.beta", "status": "error"},
                {"id": "cron.job.gamma", "status": "ok"},
            ]
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            runtime_path = Path(td) / "runtime.json"
            refresh_topology(topology, db_path=db_path)
            runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

            out = query_drift(db_path=db_path, live_json_path=runtime_path)

            self.assertTrue(out["ok"])
            self.assertEqual(out["query"], "drift")
            self.assertEqual(out["topology_node_count"], 3)
            self.assertEqual(out["runtime_node_count"], 3)

            self.assertEqual(out["missing_in_runtime"]["count"], 1)
            self.assertEqual(out["missing_in_runtime"]["node_ids"], ["artifact.daily-mission"])

            self.assertEqual(out["runtime_only"]["count"], 1)
            self.assertEqual(out["runtime_only"]["node_ids"], ["cron.job.gamma"])

            self.assertEqual(out["non_ok_nodes"]["count"], 1)
            self.assertEqual(out["non_ok_nodes"]["items"][0]["node_id"], "cron.job.beta")
            self.assertEqual(out["non_ok_nodes"]["items"][0]["status"], "error")

            self.assertEqual(out["duplicate_runtime_ids"]["count"], 1)
            self.assertEqual(out["duplicate_runtime_ids"]["node_ids"], ["cron.job.beta"])
            self.assertEqual(out["status_counts"], {"error": 1, "ok": 2})

    def test_query_drift_supports_status_map_and_limit(self) -> None:
        topology = {
            "nodes": [
                {"id": "n1", "type": "node"},
                {"id": "n2", "type": "node"},
                {"id": "n3", "type": "node"},
            ],
            "edges": [],
        }

        runtime = {
            "status_by_node": {
                "n1": "ok",
            }
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            runtime_path = Path(td) / "runtime.json"
            refresh_topology(topology, db_path=db_path)
            runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

            out = query_drift(db_path=db_path, live_json_path=runtime_path, limit=1)
            self.assertEqual(out["missing_in_runtime"]["count"], 2)
            self.assertEqual(len(out["missing_in_runtime"]["node_ids"]), 1)
            self.assertTrue(out["missing_in_runtime"]["truncated"])


if __name__ == "__main__":
    unittest.main()
