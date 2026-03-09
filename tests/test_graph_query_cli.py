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
