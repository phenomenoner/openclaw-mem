from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, cmd_graph_topology_extract
from openclaw_mem.graph.topology_extract import extract_topology_seed


class TestGraphTopologyExtract(unittest.TestCase):
    def test_extract_topology_seed_is_deterministic_for_nodes_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)

            (workspace / "repo-alpha").mkdir()
            (workspace / "repo-alpha" / ".git").mkdir()
            (workspace / "repo-beta").mkdir()
            (workspace / "repo-beta" / ".git").mkdir()

            state = root / "state"
            cron_dir = state / "cron"
            cron_dir.mkdir(parents=True)
            cron_jobs = {
                "version": 1,
                "jobs": [
                    {
                        "id": "job-alpha",
                        "name": "slow-cook repo-alpha",
                        "enabled": True,
                        "agentId": "cron-lite",
                        "sessionTarget": "isolated",
                        "wakeMode": "next-heartbeat",
                        "schedule": {"kind": "cron", "expr": "17 * * * *", "tz": "UTC"},
                        "delivery": {"mode": "announce", "channel": "telegram", "to": "telegram:1"},
                        "payload": {"kind": "agentTurn", "message": "Work in repo-alpha"},
                    }
                ],
            }
            cron_jobs_path = cron_dir / "jobs.json"
            cron_jobs_path.write_text(json.dumps(cron_jobs), encoding="utf-8")

            spec_dir = workspace / "openclaw-async-coding-playbook" / "cron" / "jobs"
            spec_dir.mkdir(parents=True)
            (spec_dir / "job-alpha.md").write_text(
                "- exec: python3 /root/.openclaw/workspace/repo-alpha/tools/run.py\n"
                "- ref: /root/.openclaw/workspace/repo-beta/docs/receipt.json\n",
                encoding="utf-8",
            )

            out_a = extract_topology_seed(
                workspace=workspace,
                cron_jobs_path=cron_jobs_path,
                spec_dir=spec_dir,
            )
            out_b = extract_topology_seed(
                workspace=workspace,
                cron_jobs_path=cron_jobs_path,
                spec_dir=spec_dir,
            )

            self.assertEqual(out_a["kind"], "openclaw-mem.graph.topology-seed.v0")
            self.assertEqual(out_a["nodes"], out_b["nodes"])
            self.assertEqual(out_a["edges"], out_b["edges"])
            self.assertEqual(out_a["counts"], out_b["counts"])
            self.assertEqual(out_a["counts"]["repos"], 2)
            self.assertEqual(out_a["counts"]["cron_jobs"], 1)
            self.assertEqual(out_a["counts"]["spec_files"], 1)

            edge_types = out_a["counts"]["edge_types"]
            self.assertGreaterEqual(edge_types.get("targets_repo", 0), 1)
            self.assertGreaterEqual(edge_types.get("reads", 0), 1)
            self.assertGreaterEqual(edge_types.get("runs", 0), 1)

            provenance_groups = out_a["counts"]["provenance_groups"]
            self.assertEqual(provenance_groups.get("cron_jobs"), 1)
            self.assertEqual(provenance_groups.get("cron_spec"), 3)

    def test_cmd_graph_topology_extract_writes_seed_and_emits_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "repo-alpha").mkdir()
            (workspace / "repo-alpha" / ".git").mkdir()

            cron_jobs_path = root / "jobs.json"
            cron_jobs_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "jobs": [
                            {
                                "id": "job-alpha",
                                "name": "alpha",
                                "enabled": True,
                                "schedule": {"kind": "cron", "expr": "0 * * * *", "tz": "UTC"},
                                "delivery": {"mode": "none", "channel": "telegram", "to": "telegram:1"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            spec_dir = workspace / "openclaw-async-coding-playbook" / "cron" / "jobs"
            spec_dir.mkdir(parents=True)
            (spec_dir / "job-alpha.md").write_text(
                "- /root/.openclaw/workspace/repo-alpha/docs/receipt.md\n",
                encoding="utf-8",
            )

            out_path = root / "seed.json"
            conn = _connect(str(root / "mem.sqlite"))
            try:
                args = type(
                    "Args",
                    (),
                    {
                        "workspace": str(workspace),
                        "cron_jobs": str(cron_jobs_path),
                        "spec_dir": str(spec_dir),
                        "out": str(out_path),
                        "json": True,
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_topology_extract(conn, args)

                receipt = json.loads(buf.getvalue())
                self.assertEqual(receipt["kind"], "openclaw-mem.graph.topology-extract.v0")
                self.assertTrue(receipt["result"]["ok"])
                self.assertEqual(receipt["result"]["cron_job_count"], 1)
                self.assertEqual(receipt["result"]["spec_count"], 1)
                self.assertEqual(receipt["result"]["provenance_groups"], {"cron_spec": 2})

                seed = json.loads(out_path.read_text(encoding="utf-8"))
                self.assertEqual(seed["kind"], "openclaw-mem.graph.topology-seed.v0")
                self.assertEqual(seed["counts"]["cron_jobs"], 1)
            finally:
                conn.close()

    def test_cmd_graph_topology_extract_defaults_spec_dir_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "repo-alpha").mkdir()
            (workspace / "repo-alpha" / ".git").mkdir()

            cron_jobs_path = root / "jobs.json"
            cron_jobs_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "jobs": [
                            {
                                "id": "job-alpha",
                                "name": "alpha",
                                "enabled": True,
                                "schedule": {"kind": "cron", "expr": "0 * * * *", "tz": "UTC"},
                                "delivery": {"mode": "none", "channel": "telegram", "to": "telegram:1"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            default_spec_dir = workspace / "openclaw-async-coding-playbook" / "cron" / "jobs"
            default_spec_dir.mkdir(parents=True)
            (default_spec_dir / "job-alpha.md").write_text(
                "- /root/.openclaw/workspace/repo-alpha/docs/receipt.md\n",
                encoding="utf-8",
            )

            out_path = root / "seed.json"
            conn = _connect(str(root / "mem.sqlite"))
            try:
                args = type(
                    "Args",
                    (),
                    {
                        "workspace": str(workspace),
                        "cron_jobs": str(cron_jobs_path),
                        "spec_dir": "",
                        "out": str(out_path),
                        "json": True,
                    },
                )()

                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_topology_extract(conn, args)

                receipt = json.loads(buf.getvalue())
                self.assertEqual(receipt["result"]["ok"], True)
                self.assertEqual(receipt["result"]["spec_count"], 1)
                self.assertEqual(receipt["result"]["provenance_groups"], {"cron_spec": 2})
                self.assertEqual(receipt["spec_dir"], str(default_spec_dir.resolve()))
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
