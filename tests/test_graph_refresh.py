from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.graph.refresh import refresh_topology, refresh_topology_file


class TestGraphRefresh(unittest.TestCase):
    def test_refresh_topology_creates_schema_and_meta(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "artifact.receipt", "type": "artifact", "metadata": {"kind": "jsonl"}},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L12",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            out = refresh_topology(topology, db_path=db_path)

            self.assertTrue(out["ok"])
            self.assertEqual(out["node_count"], 2)
            self.assertEqual(out["edge_count"], 1)
            self.assertEqual(len(out["topology_digest"]), 64)

            conn = sqlite3.connect(str(db_path))
            try:
                node_count = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
                edge_count = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
                schema_version = conn.execute(
                    "SELECT value FROM graph_meta WHERE key='schema_version'"
                ).fetchone()[0]
                digest = conn.execute(
                    "SELECT value FROM graph_meta WHERE key='topology_digest'"
                ).fetchone()[0]
            finally:
                conn.close()

            self.assertEqual(node_count, 2)
            self.assertEqual(edge_count, 1)
            self.assertEqual(schema_version, "1")
            self.assertEqual(digest, out["topology_digest"])

    def test_refresh_topology_is_deterministic_for_reordered_input(self) -> None:
        topology_a = {
            "nodes": [
                {"id": "artifact.receipt", "type": "artifact", "tags": ["ops", "receipt"]},
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L12",
                    "metadata": {"slot": "dev", "lane": "A-deep"},
                }
            ],
        }
        topology_b = {
            "edges": [
                {
                    "dst": "artifact.receipt",
                    "src": "cron.job.alpha",
                    "type": "writes",
                    "metadata": {"lane": "A-deep", "slot": "dev"},
                    "provenance": "docs/topology.yaml#L12",
                }
            ],
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "artifact.receipt", "type": "artifact", "tags": ["receipt", "ops"]},
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            out_a = refresh_topology(topology_a, db_path=db_path)
            out_b = refresh_topology(topology_b, db_path=db_path)

            self.assertEqual(out_a["topology_digest"], out_b["topology_digest"])

    def test_refresh_topology_file_json(self) -> None:
        topology = {
            "nodes": [{"id": "n1", "type": "project"}, {"id": "n2", "type": "artifact"}],
            "edges": [{"src": "n1", "dst": "n2", "type": "feeds"}],
        }

        with tempfile.TemporaryDirectory() as td:
            topology_path = Path(td) / "topology.json"
            db_path = Path(td) / "graph.db"
            topology_path.write_text(json.dumps(topology), encoding="utf-8")

            out = refresh_topology_file(topology_path=topology_path, db_path=db_path)
            self.assertTrue(out["ok"])
            self.assertEqual(out["source_path"], str(topology_path))

    def test_refresh_rejects_unknown_edge_nodes(self) -> None:
        topology = {
            "nodes": [{"id": "n1", "type": "project"}],
            "edges": [{"src": "n1", "dst": "n404", "type": "feeds"}],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            with self.assertRaises(ValueError):
                refresh_topology(topology, db_path=db_path)


if __name__ == "__main__":
    unittest.main()
