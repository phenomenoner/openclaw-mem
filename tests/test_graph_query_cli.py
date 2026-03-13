import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, cmd_graph_query
from openclaw_mem.graph.refresh import refresh_topology


class TestGraphQueryCli(unittest.TestCase):
    def test_cmd_graph_query_upstream_json_payload(self) -> None:
        topology = {
            "nodes": [
                {"id": "project.finlife", "type": "project"},
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "cron.job.beta", "type": "cron_job", "tags": ["background", "human_facing"]},
                {"id": "artifact.daily-mission", "type": "artifact", "tags": ["deliverable"]},
            ],
            "edges": [
                {"src": "project.finlife", "dst": "cron.job.alpha", "type": "depends_on", "provenance": "docs/topology.yaml#L10"},
                {"src": "cron.job.alpha", "dst": "artifact.daily-mission", "type": "writes", "provenance": "docs/topology.yaml#L20"},
                {"src": "cron.job.beta", "dst": "artifact.daily-mission", "type": "alerts_to", "provenance": "docs/topology.yaml#L21"},
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path)

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "upstream",
                    "db": str(db_path),
                    "node_id": "artifact.daily-mission",
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["kind"], "openclaw-mem.graph.query.v0")
            self.assertEqual(out["query_cmd"], "upstream")
            self.assertEqual(out["result"]["count"], 2)
            self.assertEqual(out["result"]["edges"][0]["src"], "cron.job.alpha")
            self.assertEqual(out["result"]["edges"][1]["src"], "cron.job.beta")
            conn.close()

    def test_cmd_graph_query_subgraph_json_payload(self) -> None:
        topology = {
            "nodes": [
                {"id": "project.finlife", "type": "project"},
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "cron.job.beta", "type": "cron_job", "tags": ["background", "human_facing"]},
                {"id": "artifact.daily-mission", "type": "artifact", "tags": ["deliverable"]},
            ],
            "edges": [
                {"src": "project.finlife", "dst": "cron.job.alpha", "type": "depends_on", "provenance": "docs/topology.yaml#L10"},
                {"src": "cron.job.alpha", "dst": "artifact.daily-mission", "type": "writes", "provenance": "docs/topology.yaml#L20"},
                {"src": "cron.job.beta", "dst": "artifact.daily-mission", "type": "alerts_to", "provenance": "docs/topology.yaml#L21"},
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path, source_path="docs/topology.yaml")

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "subgraph",
                    "db": str(db_path),
                    "node_id": "artifact.daily-mission",
                    "hops": 2,
                    "direction": "upstream",
                    "max_nodes": 40,
                    "max_edges": 80,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["kind"], "openclaw-mem.graph.query.v0")
            self.assertEqual(out["query_cmd"], "subgraph")
            self.assertEqual(out["result"]["center_node_id"], "artifact.daily-mission")
            self.assertEqual(out["result"]["edge_count"], 3)
            self.assertIn("Edges (with provenance)", out["result"]["bundle_text"])
            self.assertIn("docs/topology.yaml#L20", out["result"]["bundle_text"])
            conn.close()


    def test_cmd_graph_query_subgraph_max_nodes_cap_is_consistent(self) -> None:
        topology = {
            "nodes": [
                {"id": "artifact.center", "type": "artifact"},
                {"id": "artifact.alpha", "type": "artifact"},
                {"id": "artifact.beta", "type": "artifact"},
            ],
            "edges": [
                {"src": "artifact.center", "dst": "artifact.alpha", "type": "writes", "provenance": "docs/topology.yaml#L10"},
                {"src": "artifact.center", "dst": "artifact.beta", "type": "alerts_to", "provenance": "docs/topology.yaml#L20"},
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path, source_path="docs/topology.yaml")

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "subgraph",
                    "db": str(db_path),
                    "node_id": "artifact.center",
                    "hops": 1,
                    "direction": "both",
                    "max_nodes": 2,
                    "max_edges": 10,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "subgraph")
            self.assertEqual(out["result"]["stopped_reason"], "max_nodes")
            self.assertEqual(out["result"]["node_count"], 2)
            self.assertEqual(out["result"]["edge_count"], 1)
            node_ids = {node["id"] for node in out["result"]["nodes"]}
            edge = out["result"]["edges"][0]
            self.assertIn(edge["src"], node_ids)
            self.assertIn(edge["dst"], node_ids)
            conn.close()

    def test_cmd_graph_query_filter_json_payload(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job", "tags": ["background"]},
                {"id": "cron.job.beta", "type": "cron_job", "tags": ["background", "human_facing"]},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path)

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "filter",
                    "db": str(db_path),
                    "tag": "background",
                    "not_tag": "human_facing",
                    "node_type": "cron_job",
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "filter")
            self.assertEqual(out["result"]["count"], 1)
            self.assertEqual(out["result"]["nodes"][0]["id"], "cron.job.alpha")
            conn.close()

    def test_cmd_graph_query_receipts_json_payload(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L42",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path, source_path="docs/topology.yaml")

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "receipts",
                    "db": str(db_path),
                    "limit": 5,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "receipts")
            self.assertEqual(out["result"]["count"], 1)
            self.assertEqual(out["result"]["receipts"][0]["source_path"], "docs/topology.yaml")
            conn.close()

    def test_cmd_graph_query_receipts_supports_source_filter(self) -> None:
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
                    "provenance": "docs/topology-a.yaml#L42",
                }
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
                    "provenance": "docs/topology-b.yaml#L48",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology_a, db_path=db_path, source_path="docs/topology-a.yaml")
            refresh_topology(topology_b, db_path=db_path, source_path="docs/topology-b.yaml")

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "receipts",
                    "db": str(db_path),
                    "limit": 10,
                    "source_path": "docs/topology-a.yaml",
                    "topology_digest": None,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "receipts")
            self.assertEqual(out["result"]["count"], 1)
            self.assertEqual(out["result"]["total_count"], 1)
            self.assertEqual(out["result"]["receipts"][0]["source_path"], "docs/topology-a.yaml")
            conn.close()

    def test_cmd_graph_query_provenance_json_payload(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "cron.job.beta", "type": "cron_job"},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L42",
                },
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L42",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path)

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "provenance",
                    "db": str(db_path),
                    "node_id": "artifact.receipt",
                    "edge_type": "writes",
                    "min_edge_count": 2,
                    "limit": 10,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "provenance")
            self.assertEqual(out["result"]["total_distinct"], 1)
            self.assertEqual(out["result"]["count"], 1)
            self.assertEqual(out["result"]["filters"]["min_edge_count"], 2)
            self.assertEqual(out["result"]["items"][0]["edge_count"], 2)
            self.assertEqual(
                out["result"]["items"][0]["edge_types"],
                [{"edge_type": "writes", "edge_count": 2}],
            )
            conn.close()

    def test_cmd_graph_query_provenance_plaintext_includes_edge_types(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "cron.job.beta", "type": "cron_job"},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L42",
                },
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.receipt",
                    "type": "alerts_to",
                    "provenance": "docs/topology.yaml#L42",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path)

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "provenance",
                    "db": str(db_path),
                    "node_id": None,
                    "edge_type": None,
                    "min_edge_count": 1,
                    "limit": 10,
                    "json": False,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            text = buf.getvalue()
            self.assertIn("count=1 total_distinct=1", text)
            self.assertIn("docs/topology.yaml#L42 edges=2", text)
            self.assertIn("edge_types=alerts_to:1,writes:1", text)
            conn.close()


    def test_cmd_graph_query_provenance_supports_group_by_source_json(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "cron.job.beta", "type": "cron_job"},
                {"id": "artifact.receipt", "type": "artifact"},
            ],
            "edges": [
                {
                    "src": "cron.job.alpha",
                    "dst": "artifact.receipt",
                    "type": "writes",
                    "provenance": "docs/topology.yaml#L42",
                },
                {
                    "src": "cron.job.beta",
                    "dst": "artifact.receipt",
                    "type": "alerts_to",
                    "provenance": "docs/topology.yaml#L48",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path)

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "provenance",
                    "db": str(db_path),
                    "node_id": None,
                    "edge_type": None,
                    "group_by_source": True,
                    "min_edge_count": 1,
                    "limit": 10,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "provenance")
            self.assertEqual(out["result"]["filters"]["group_by_source"], True)
            self.assertEqual(out["result"]["total_distinct"], 1)
            self.assertEqual(out["result"]["items"][0]["provenance"], "docs/topology.yaml")
            self.assertEqual(out["result"]["items"][0]["source_path"], "docs/topology.yaml")
            self.assertEqual(
                out["result"]["items"][0]["edge_types"],
                [
                    {"edge_type": "alerts_to", "edge_count": 1},
                    {"edge_type": "writes", "edge_count": 1},
                ],
            )
            conn.close()

    def test_cmd_graph_query_lineage_supports_max_depth(self) -> None:
        topology = {
            "nodes": [
                {"id": "project.finlife", "type": "project"},
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "artifact.daily-mission", "type": "artifact"},
                {"id": "artifact.report", "type": "artifact"},
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
                    "src": "artifact.daily-mission",
                    "dst": "artifact.report",
                    "type": "feeds",
                    "provenance": "docs/topology.yaml#L30",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path)

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "lineage",
                    "db": str(db_path),
                    "node_id": "artifact.daily-mission",
                    "max_depth": 2,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "lineage")
            self.assertEqual(out["result"]["max_depth"], 2)
            upstream_depths = {(edge["src"], edge["depth"]) for edge in out["result"]["upstream"]}
            downstream_depths = {(edge["dst"], edge["depth"]) for edge in out["result"]["downstream"]}
            self.assertIn(("cron.job.alpha", 1), upstream_depths)
            self.assertIn(("project.finlife", 2), upstream_depths)
            self.assertIn(("artifact.report", 1), downstream_depths)
            conn.close()

    def test_cmd_graph_query_drift_json_payload(self) -> None:
        topology = {
            "nodes": [
                {"id": "cron.job.alpha", "type": "cron_job"},
                {"id": "cron.job.beta", "type": "cron_job"},
            ],
            "edges": [],
        }
        runtime = {
            "nodes": [
                {"id": "cron.job.alpha", "status": "ok"},
                {"id": "cron.job.beta", "status": "stale"},
                {"id": "cron.job.gamma", "status": "ok"},
            ]
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mem.sqlite"
            runtime_path = Path(td) / "runtime.json"
            runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

            conn = _connect(str(db_path))
            refresh_topology(topology, db_path=db_path)

            args = type(
                "Args",
                (),
                {
                    "graph_query_cmd": "drift",
                    "db": str(db_path),
                    "live_json": str(runtime_path),
                    "limit": 20,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_graph_query(conn, args)

            out = json.loads(buf.getvalue())
            self.assertEqual(out["query_cmd"], "drift")
            self.assertEqual(out["result"]["missing_in_runtime"]["count"], 0)
            self.assertEqual(out["result"]["runtime_only"]["count"], 1)
            self.assertEqual(out["result"]["non_ok_nodes"]["count"], 1)
            conn.close()


if __name__ == "__main__":
    unittest.main()
