from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from openclaw_mem.cli import _connect, cmd_ingest, cmd_pack


class TestPackGraphAware(unittest.TestCase):
    FIXTURE_DIR = Path(__file__).parent / "data" / "graph_search_hybrid"

    def _ingest(self, conn) -> None:
        cmd_ingest(conn, SimpleNamespace(file=str(self.FIXTURE_DIR / "observations.jsonl"), json=True, importance_scorer=None))

    def _pack(self, conn, **kwargs) -> dict:
        args = {
            "db": None,
            "harness_home": None,
            "json": True,
            "query": "resolver",
            "query_en": None,
            "limit": 5,
            "budget_tokens": 600,
            "tail_text": None,
            "tail_file": None,
            "tail_max_items": 4,
            "tail_budget_tokens": 0,
            "use_gbrain": "off",
            "gbrain_bin": "",
            "gbrain_limit": 5,
            "gbrain_timeout_ms": 1000,
            "gbrain_expand": False,
            "use_graph": "off",
            "graph_scope": None,
            "graph_budget_tokens": 1200,
            "graph_take": 12,
            "graph_query_db": None,
            "graph_provenance_policy": "off",
            "graph_require_structured_provenance": True,
            "graph_provenance_hops": 1,
            "graph_provenance_max_nodes": 40,
            "graph_provenance_max_edges": 80,
            "pack_trust_policy": "off",
            "pack_lifecycle_shadow": "off",
            "pack_lifecycle_log_max_rows": 200,
            "pack_lifecycle_write": "off",
            "pack_artifacts": "off",
            "trace": False,
            "graph_probe": None,
            "graph_probe_limit": 5,
            "graph_probe_t_high": -5.0,
            "graph_probe_t_marginal": -2.0,
            "graph_probe_n_min": 3,
            "graph_latency_soft_ms": 150,
            "graph_latency_hard_ms": 300,
            "graph_aware": False,
            "graph_aware_path": "",
            "graph_aware_active_file": None,
            "graph_aware_recent_file": None,
            "graph_aware_stale_after_days": 30,
        }
        args.update(kwargs)
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_pack(conn, SimpleNamespace(**args))
        return json.loads(buf.getvalue())

    def test_flag_off_baseline_has_no_graph_aware_payload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            conn = _connect(str(Path(td) / "mem.sqlite"))
            try:
                self._ingest(conn)
                baseline = self._pack(conn)
            finally:
                conn.close()
        self.assertNotIn("graph_aware_pack", baseline)

    def test_graph_aware_trace_is_complete_budget_bound_and_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mem.sqlite"
            graph = root / "graph.json"
            graph.write_text((self.FIXTURE_DIR / "graph.json").read_text(encoding="utf-8"), encoding="utf-8")
            conn = _connect(str(db))
            try:
                self._ingest(conn)
                baseline = self._pack(conn)
                before = hashlib.sha256(db.read_bytes()).hexdigest()
                out = self._pack(
                    conn,
                    trace=True,
                    graph_aware=True,
                    graph_aware_path=str(graph),
                    graph_aware_active_file=["pkg/resolver.py"],
                    graph_aware_recent_file=["pkg/resolver.py"],
                )
                after = hashlib.sha256(db.read_bytes()).hexdigest()
            finally:
                conn.close()

        self.assertEqual(after, before)
        self.assertLessEqual(len(out["bundle_text"]), len(baseline["bundle_text"]))
        gp = out["graph_aware_pack"]
        self.assertFalse(gp["writes_performed"])
        self.assertIsNone(gp["fallback_reason"])
        self.assertGreaterEqual(len(gp["selected"]), 1)
        selected = gp["selected"][0]
        self.assertEqual(selected["source_path"], "pkg/resolver.py")
        self.assertEqual(selected["trace"]["node_id"], selected["node_id"])
        self.assertIn("graph_aware_pack", out["trace"]["extensions"])

    def test_missing_graph_fails_open_to_baseline_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = _connect(str(root / "mem.sqlite"))
            try:
                self._ingest(conn)
                baseline = self._pack(conn)
                out = self._pack(conn, graph_aware=True, graph_aware_path=str(root / "missing.json"))
            finally:
                conn.close()
        self.assertEqual(out["bundle_text"], baseline["bundle_text"])
        self.assertEqual(out["graph_aware_pack"]["fallback_reason"], "graph_file_not_found")

    def test_ab_harness_emits_predeclared_receipt(self) -> None:
        p = subprocess.run(
            [sys.executable, "scripts/graph_aware_pack_ab.py"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        receipt = json.loads(p.stdout)
        self.assertEqual(receipt["kind"], "openclaw-mem.pack.graph-aware.ab-receipt.v0")
        self.assertIn("win", receipt["criteria"])
        self.assertEqual(receipt["counts"], {"win": 1, "loss": 0, "noise": 0})


if __name__ == "__main__":
    unittest.main()
