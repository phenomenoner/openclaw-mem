from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, cmd_graph_topology_diff
from openclaw_mem.graph.topology_diff import compare_topology_files


class TestGraphTopologyDiff(unittest.TestCase):
    def test_compare_topology_files_reports_missing_and_stale_entities(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seed_path = root / "seed.json"
            curated_path = root / "curated.json"

            seed_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "repo.alpha", "type": "repo", "tags": ["derived"]},
                            {"id": "cron.job.a", "type": "cron_job", "tags": ["enabled"]},
                            {"id": "script.path.run", "type": "script", "tags": ["derived"]},
                        ],
                        "edges": [
                            {"src": "cron.job.a", "dst": "repo.alpha", "type": "targets_repo", "provenance": "jobs.json#job=a"},
                            {"src": "cron.job.a", "dst": "script.path.run", "type": "runs", "provenance": "spec.md#L1"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            curated_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "repo.alpha", "type": "repo", "tags": ["curated"]},
                            {"id": "cron.job.a", "type": "cron_job", "tags": ["enabled"]},
                            {"id": "artifact.legacy", "type": "artifact", "tags": ["manual"]},
                        ],
                        "edges": [
                            {"src": "cron.job.a", "dst": "repo.alpha", "type": "targets_repo", "provenance": "manual"},
                            {"src": "cron.job.a", "dst": "artifact.legacy", "type": "reads", "provenance": "manual"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            out = compare_topology_files(seed_path=seed_path, curated_path=curated_path, limit=10)
            diff = out["diff"]
            counts = diff["counts"]

            self.assertTrue(out["ok"])
            self.assertEqual(counts["missing_nodes"], 1)
            self.assertEqual(counts["stale_nodes"], 1)
            self.assertEqual(counts["node_contract_mismatches"], 1)
            self.assertEqual(counts["missing_edges"], 1)
            self.assertEqual(counts["stale_edges"], 1)
            self.assertEqual(counts["edge_contract_mismatches"], 1)
            self.assertEqual(diff["edge_contract_mismatches"][0]["src"], "cron.job.a")
            self.assertEqual(diff["edge_contract_mismatches"][0]["dst"], "repo.alpha")
            self.assertEqual(
                [entry["provenance"] for entry in diff["edge_contract_mismatches"][0]["seed_variants"]],
                ["jobs.json#job=a"],
            )
            self.assertEqual(
                [entry["provenance"] for entry in diff["edge_contract_mismatches"][0]["curated_variants"]],
                ["manual"],
            )
            self.assertEqual(diff["missing_nodes"][0]["id"], "script.path.run")
            self.assertEqual(diff["stale_nodes"][0]["id"], "artifact.legacy")
            self.assertEqual(diff["node_contract_mismatches"][0]["id"], "repo.alpha")

    def test_compare_topology_files_keeps_all_edge_contract_variants(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seed_path = root / "seed.json"
            curated_path = root / "curated.json"

            seed_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "cron.job.a", "type": "cron_job", "tags": ["enabled"]},
                            {"id": "repo.alpha", "type": "repo", "tags": ["derived"]},
                        ],
                        "edges": [
                            {"src": "cron.job.a", "dst": "repo.alpha", "type": "targets_repo", "provenance": "jobs.json#job=a"},
                            {"src": "cron.job.a", "dst": "repo.alpha", "type": "targets_repo", "provenance": "spec-alpha.md#L1"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            curated_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "cron.job.a", "type": "cron_job", "tags": ["enabled"]},
                            {"id": "repo.alpha", "type": "repo", "tags": ["derived"]},
                        ],
                        "edges": [
                            {"src": "cron.job.a", "dst": "repo.alpha", "type": "targets_repo", "provenance": "spec-alpha.md#L1"},
                            {"src": "cron.job.a", "dst": "repo.alpha", "type": "targets_repo", "provenance": "manual-map.yaml#L4"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            out = compare_topology_files(seed_path=seed_path, curated_path=curated_path, limit=10)
            diff = out["diff"]

            self.assertEqual(diff["counts"]["missing_edges"], 0)
            self.assertEqual(diff["counts"]["stale_edges"], 0)
            self.assertEqual(diff["counts"]["edge_contract_mismatches"], 1)

            mismatch = diff["edge_contract_mismatches"][0]
            self.assertEqual(mismatch["src"], "cron.job.a")
            self.assertEqual(mismatch["dst"], "repo.alpha")
            self.assertEqual(mismatch["type"], "targets_repo")
            self.assertEqual(
                [entry["provenance"] for entry in mismatch["seed_variants"]],
                ["jobs.json#job=a", "spec-alpha.md#L1"],
            )
            self.assertEqual(
                [entry["provenance"] for entry in mismatch["curated_variants"]],
                ["manual-map.yaml#L4", "spec-alpha.md#L1"],
            )

    def test_cmd_graph_topology_diff_emits_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seed_path = root / "seed.json"
            curated_path = root / "curated.json"
            seed_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "repo.alpha", "type": "repo", "tags": ["derived"]},
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )
            curated_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "repo.alpha", "type": "repo", "tags": ["derived"]},
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            conn = _connect(str(root / "mem.sqlite"))
            try:
                args = type(
                    "Args",
                    (),
                    {
                        "seed": str(seed_path),
                        "curated": str(curated_path),
                        "limit": 25,
                        "json": True,
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_topology_diff(conn, args)

                receipt = json.loads(buf.getvalue())
                self.assertEqual(receipt["kind"], "openclaw-mem.graph.topology-diff.v0")
                self.assertTrue(receipt["result"]["ok"])
                self.assertEqual(receipt["result"]["diff"]["counts"]["missing_nodes"], 0)
                self.assertEqual(receipt["result"]["diff"]["counts"]["stale_edges"], 0)
                self.assertEqual(receipt["result"]["diff"]["counts"]["edge_contract_mismatches"], 0)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
