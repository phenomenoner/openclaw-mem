from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.graph.query import (
    query_downstream,
    query_filter_nodes,
    query_lineage,
    query_upstream,
    query_writers,
)
from openclaw_mem.graph.refresh import refresh_topology


class TestGraphQuery(unittest.TestCase):
    def test_upstream_downstream_and_writers_queries(self) -> None:
        topology = {
            "nodes": [
                {"id": "project.finlife", "type": "project"},
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "cron.job.beta", "type": "cron_job", "tags": ["background", "human_facing"]},
                {"id": "artifact.daily-mission", "type": "artifact", "tags": ["deliverable"]},
            ],
            "edges": [
                {
                    "src": "project.finlife",
                    "dst": "cron.job.alpha",
                    "type": "depends_on",
                    "provenance": "docs/topology.yaml#L10",
                },
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.daily-mission",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L20",
                },
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.daily-mission",
                    "type": "alerts_to",
                    "provenance": "docs/topology.yaml#L21",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology(topology, db_path=db_path)

            upstream = query_upstream(db_path=db_path, node_id="artifact.daily-mission")
            self.assertTrue(upstream["ok"])
            self.assertEqual(upstream["count"], 2)
            self.assertEqual(upstream["edges"][0]["src"], "cron.job.alpha")
            self.assertEqual(upstream["edges"][1]["src"], "cron.job.beta")
            self.assertEqual(upstream["edges"][0]["provenance"], "docs/topology.yaml#L20")

            downstream = query_downstream(db_path=db_path, node_id="project.finlife")
            self.assertTrue(downstream["ok"])
            self.assertEqual(downstream["count"], 1)
            self.assertEqual(downstream["edges"][0]["dst"], "cron.job.alpha")

            writers = query_writers(db_path=db_path, artifact_id="artifact.daily-mission")
            self.assertTrue(writers["ok"])
            self.assertEqual(writers["count"], 1)
            self.assertEqual(writers["edges"][0]["src"], "cron.job.alpha")
            self.assertEqual(writers["edges"][0]["type"], "writes")

    def test_filter_nodes_and_lineage(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "cron.job.beta", "type": "cron_job", "tags": ["background", "human_facing"]},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L31",
                    "metadata": {"lane": "A-deep"},
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology(topology, db_path=db_path)

            filtered = query_filter_nodes(db_path=db_path, tag="background", not_tag="human_facing")
            self.assertTrue(filtered["ok"])
            self.assertEqual(filtered["count"], 1)
            self.assertEqual(filtered["nodes"][0]["id"], "cron.job.alpha")

            lineage = query_lineage(db_path=db_path, node_id="artifact.receipt")
            self.assertTrue(lineage["ok"])
            self.assertEqual(lineage["upstream_count"], 1)
            self.assertEqual(lineage["downstream_count"], 0)
            self.assertEqual(lineage["upstream"][0]["provenance"], "docs/topology.yaml#L31")
            self.assertEqual(lineage["upstream"][0]["metadata"], {"lane": "A-deep"})

    def test_queries_tolerate_malformed_persisted_json(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L40",
                    "metadata": {"lane": "A-deep"},
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology(topology, db_path=db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                with conn:
                    conn.execute(
                        "UPDATE graph_nodes SET tags_json = ?, metadata_json = ? WHERE node_id = ?",
                        ('{"bad":"shape"}', '["not-an-object"]', "cron.job.alpha"),
                    )
                    conn.execute(
                        "UPDATE graph_edges SET metadata_json = ? WHERE src_id = ? AND dst_id = ? AND edge_type = ?",
                        ('["not-an-object"]', "cron.job.alpha", "artifact.receipt", "writes"),
                    )
            finally:
                conn.close()

            filtered = query_filter_nodes(db_path=db_path, node_type="cron_job")
            self.assertTrue(filtered["ok"])
            self.assertEqual(filtered["count"], 1)
            self.assertEqual(filtered["nodes"][0]["tags"], [])
            self.assertEqual(filtered["nodes"][0]["metadata"], {})

            lineage = query_lineage(db_path=db_path, node_id="artifact.receipt")
            self.assertTrue(lineage["ok"])
            self.assertEqual(lineage["upstream_count"], 1)
            self.assertEqual(lineage["upstream"][0]["metadata"], {})


if __name__ == "__main__":
    unittest.main()
