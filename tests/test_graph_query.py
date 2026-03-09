from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.graph.query import (
    query_downstream,
    query_filter_nodes,
    query_lineage,
    query_provenance,
    query_refresh_receipts,
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

    def test_query_provenance_groups_and_filters_edges(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "cron.job.beta", "type": "cron_job"},
                {"id": "artifact.daily-mission", "type": "artifact"},
                {"id": "artifact.alert", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.daily-mission",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L10",
                },
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.daily-mission",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L10",
                },
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.alert",
                    "type": "alerts_to",
                    "provenance": "docs/topology.yaml#L14",
                },
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.alert",
                    "type": "alerts_to",
                    "provenance": "",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology(topology, db_path=db_path)

            out = query_provenance(db_path=db_path, limit=10)
            self.assertTrue(out["ok"])
            self.assertEqual(out["query"], "provenance")
            self.assertEqual(out["total_distinct"], 2)
            self.assertEqual(out["count"], 2)
            self.assertEqual(out["items"][0]["provenance"], "docs/topology.yaml#L10")
            self.assertEqual(out["items"][0]["edge_count"], 2)
            self.assertEqual(
                out["items"][0]["edge_types"],
                [{"edge_type": "writes", "edge_count": 2}],
            )

            filtered = query_provenance(
                db_path=db_path,
                node_id="artifact.daily-mission",
                edge_type="writes",
                limit=10,
            )
            self.assertEqual(filtered["total_distinct"], 1)
            self.assertEqual(filtered["count"], 1)
            self.assertEqual(filtered["items"][0]["edge_count"], 2)
            self.assertEqual(
                filtered["items"][0]["edge_types"],
                [{"edge_type": "writes", "edge_count": 2}],
            )

    def test_query_provenance_ignores_whitespace_and_supports_min_edge_count(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "cron.job.beta", "type": "cron_job"},
                {"id": "cron.job.gamma", "type": "cron_job"},
                {"id": "artifact.daily-mission", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.daily-mission",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L10",
                },
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.daily-mission",
                    "type": "alerts_to",
                    "provenance": "docs/topology.yaml#L20",
                },
                {
                    "src": "cron.job.gamma",
                    "dst": "artifact.daily-mission",
                    "type": "feeds",
                    "provenance": "docs/topology.yaml#L20",
                },
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.daily-mission",
                    "type": "blocks",
                    "provenance": "   ",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology(topology, db_path=db_path)

            out = query_provenance(db_path=db_path, min_edge_count=2, limit=10)
            self.assertTrue(out["ok"])
            self.assertEqual(out["total_distinct"], 1)
            self.assertEqual(out["count"], 1)
            self.assertEqual(out["filters"]["min_edge_count"], 2)
            self.assertEqual(out["items"][0]["provenance"], "docs/topology.yaml#L20")
            self.assertEqual(out["items"][0]["edge_count"], 2)
            self.assertEqual(
                out["items"][0]["edge_types"],
                [
                    {"edge_type": "alerts_to", "edge_count": 1},
                    {"edge_type": "feeds", "edge_count": 1},
                ],
            )

            broad = query_provenance(db_path=db_path, min_edge_count=1, limit=10)
            self.assertEqual(broad["total_distinct"], 2)
            self.assertEqual(broad["count"], 2)
            self.assertEqual(
                [item["provenance"] for item in broad["items"]],
                ["docs/topology.yaml#L20", "docs/topology.yaml#L10"],
            )

    def test_query_provenance_rejects_invalid_min_edge_count(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology({"nodes": [], "edges": []}, db_path=db_path)

            with self.assertRaises(ValueError) as ctx:
                query_provenance(db_path=db_path, min_edge_count=0)
            self.assertIn("min_edge_count must be > 0", str(ctx.exception))

    def test_query_refresh_receipts_returns_recent_runs(self) -> None:
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
                    "provenance": "docs/topology.yaml#L31",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology(topology, db_path=db_path, source_path="docs/topology-a.yaml")
            refresh_topology(topology, db_path=db_path, source_path="docs/topology-b.yaml")

            out = query_refresh_receipts(db_path=db_path, limit=1)
            self.assertTrue(out["ok"])
            self.assertEqual(out["query"], "receipts")
            self.assertEqual(out["count"], 1)
            self.assertEqual(out["total_count"], 2)
            self.assertEqual(len(out["receipts"]), 1)
            self.assertEqual(out["receipts"][0]["source_path"], "docs/topology-b.yaml")
            self.assertEqual(out["receipts"][0]["node_count"], 2)
            self.assertEqual(out["receipts"][0]["edge_count"], 1)

    def test_query_refresh_receipts_supports_source_and_digest_filters(self) -> None:
        topology_a = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology-a.yaml#L10",
                },
            ],
        }
        topology_b = {
            "nodes": [
                {"id": "cron.job.beta", "type": "cron_job"},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.receipt",
                    "type": "alerts_to",
                    "provenance": "docs/topology-b.yaml#L20",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            out_a = refresh_topology(topology_a, db_path=db_path, source_path="docs/topology-a.yaml")
            out_b = refresh_topology(topology_b, db_path=db_path, source_path="docs/topology-b.yaml")
            refresh_topology(topology_a, db_path=db_path, source_path="docs/topology-a-v2.yaml")

            filtered_source = query_refresh_receipts(
                db_path=db_path,
                source_path="docs/topology-a.yaml",
                limit=10,
            )
            self.assertTrue(filtered_source["ok"])
            self.assertEqual(filtered_source["count"], 1)
            self.assertEqual(filtered_source["total_count"], 1)
            self.assertEqual(filtered_source["filters"]["source_path"], "docs/topology-a.yaml")
            self.assertEqual(filtered_source["receipts"][0]["topology_digest"], out_a["topology_digest"])

            filtered_digest = query_refresh_receipts(
                db_path=db_path,
                topology_digest=out_b["topology_digest"],
                limit=10,
            )
            self.assertEqual(filtered_digest["count"], 1)
            self.assertEqual(filtered_digest["total_count"], 1)
            self.assertEqual(filtered_digest["filters"]["topology_digest"], out_b["topology_digest"])
            self.assertEqual(filtered_digest["receipts"][0]["source_path"], "docs/topology-b.yaml")

    def test_queries_require_existing_graph_db(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "missing.db"

            with self.assertRaises(ValueError) as ctx:
                query_upstream(db_path=db_path, node_id="artifact.daily-mission")
            self.assertIn("graph db not found", str(ctx.exception))

    def test_queries_reject_db_without_graph_schema(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            sqlite3.connect(str(db_path)).close()

            with self.assertRaises(ValueError) as ctx:
                query_refresh_receipts(db_path=db_path, limit=1)
            self.assertIn("graph schema missing required tables", str(ctx.exception))

    def test_queries_reject_db_with_missing_schema_version_meta(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology({"nodes": [], "edges": []}, db_path=db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                with conn:
                    conn.execute("DELETE FROM graph_meta WHERE key = ?", ("schema_version",))
            finally:
                conn.close()

            with self.assertRaises(ValueError) as ctx:
                query_refresh_receipts(db_path=db_path, limit=1)
            self.assertIn("graph schema missing required meta key: schema_version", str(ctx.exception))

    def test_queries_reject_db_with_mismatched_schema_version_meta(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology({"nodes": [], "edges": []}, db_path=db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO graph_meta(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        ("schema_version", "999"),
                    )
            finally:
                conn.close()

            with self.assertRaises(ValueError) as ctx:
                query_refresh_receipts(db_path=db_path, limit=1)
            self.assertIn("graph schema version mismatch", str(ctx.exception))

    def test_query_provenance_rejects_limit_above_cap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology({"nodes": [], "edges": []}, db_path=db_path)

            with self.assertRaises(ValueError) as ctx:
                query_provenance(db_path=db_path, limit=201)
            self.assertIn("limit must be <= 200", str(ctx.exception))

    def test_query_refresh_receipts_rejects_limit_above_cap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "graph.db"
            refresh_topology({"nodes": [], "edges": []}, db_path=db_path)

            with self.assertRaises(ValueError) as ctx:
                query_refresh_receipts(db_path=db_path, limit=201)
            self.assertIn("limit must be <= 200", str(ctx.exception))

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
