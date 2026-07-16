from __future__ import annotations

import io
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from openclaw_mem.cli import _connect, cmd_ingest, cmd_search


class TestSearchHybridCli(unittest.TestCase):
    FIXTURE_DIR = Path(__file__).parent / "data" / "graph_search_hybrid"

    def _ingest_fixture(self, conn, root: Path) -> None:
        jsonl = self.FIXTURE_DIR / "observations.jsonl"
        cmd_ingest(
            conn,
            SimpleNamespace(file=str(jsonl), json=True, importance_scorer=None),
        )

    def _run_search(self, conn, **kwargs):
        args = {
            "query": "resolver",
            "limit": 10,
            "json": True,
            "graph": False,
            "graph_path": "",
            "graph_readiness_state": "",
            "graph_stale_after_days": 30,
        }
        args.update(kwargs)
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_search(conn, SimpleNamespace(**args))
        return json.loads(buf.getvalue())

    def _write_graph(self, root: Path) -> Path:
        path = root / "graph.json"
        path.write_text((self.FIXTURE_DIR / "graph.json").read_text(encoding="utf-8"), encoding="utf-8")
        return path

    def test_flag_off_preserves_legacy_list_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = _connect(str(root / "mem.sqlite"))
            try:
                self._ingest_fixture(conn, root)
                out = self._run_search(conn)
            finally:
                conn.close()

        self.assertIsInstance(out, list)
        self.assertNotIsInstance(out, dict)
        self.assertNotIn("lane", out[0])
        self.assertNotIn("rank", out[0])
        self.assertEqual(out[0]["summary"], "resolver lexical baseline")
        self.assertTrue(
            {"query_lang", "lane_hits", "fallback_triggered", "cross_lang_recovered"}.issubset(out[0])
        )

    def test_graph_missing_fails_open_to_lexical_hybrid_contract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = _connect(str(root / "mem.sqlite"))
            try:
                self._ingest_fixture(conn, root)
                out = self._run_search(conn, graph=True, graph_path=str(root / "missing.json"))
            finally:
                conn.close()

        self.assertEqual(out["kind"], "openclaw-mem.search.hybrid.v0")
        self.assertEqual(out["graph"]["fallback_reason"], "graph_file_not_found")
        self.assertEqual(out["graph"]["count"], 0)
        self.assertEqual([r["lane"] for r in out["results"]], ["lexical"])
        self.assertTrue(
            {"query_lang", "lane_hits", "fallback_triggered", "cross_lang_recovered"}.issubset(out)
        )

    def test_graph_hit_carries_provenance_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = _connect(str(root / "mem.sqlite"))
            try:
                self._ingest_fixture(conn, root)
                graph_path = self._write_graph(root)
                out = self._run_search(conn, graph=True, graph_path=str(graph_path))
            finally:
                conn.close()

        graph_hits = [r for r in out["results"] if r["lane"] == "graph"]
        self.assertEqual(len(graph_hits), 1)
        hit = graph_hits[0]
        self.assertEqual(hit["rank"], 1)
        self.assertGreater(hit["hybrid_score"], 0)
        self.assertEqual(hit["rank_components"]["graph"], hit["hybrid_score"])
        self.assertEqual(hit["source_path"], "pkg/resolver.py")
        self.assertEqual(hit["span"], {"line_start": 3, "line_end": 5})
        self.assertEqual(hit["commit"], "abc123")
        self.assertEqual(hit["confidence"], 1.0)
        self.assertEqual(hit["freshness"], "snapshot")
        self.assertEqual(hit["receipt_id"], "receipt:resolver")

    def test_cli_subprocess_extract_then_hybrid_search_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "mem.sqlite"
            fixture_repo = root / "repo"
            (fixture_repo / "pkg").mkdir(parents=True)
            (fixture_repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (fixture_repo / "pkg" / "resolver.py").write_text(
                "class Resolver:\n"
                "    def resolve(self):\n"
                "        return 'ok'\n",
                encoding="utf-8",
            )
            graph_path = root / "extracted-graph.json"
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["NODE_NO_WARNINGS"] = "1"

            ingest = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openclaw_mem",
                    "--db",
                    str(db_path),
                    "--json",
                    "ingest",
                    "--file",
                    str(self.FIXTURE_DIR / "observations.jsonl"),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(ingest.returncode, 0, ingest.stderr)
            extract = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openclaw_mem",
                    "--db",
                    str(db_path),
                    "--json",
                    "graph",
                    "extract",
                    "--repo",
                    str(fixture_repo),
                    "--out",
                    str(graph_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(extract.returncode, 0, extract.stderr)
            self.assertTrue(graph_path.is_file())
            db_hash_before = hashlib.sha256(db_path.read_bytes()).hexdigest()

            search = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openclaw_mem",
                    "--db",
                    str(db_path),
                    "--json",
                    "search",
                    "resolver",
                    "--graph",
                    "--graph-path",
                    str(graph_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            db_hash_after = hashlib.sha256(db_path.read_bytes()).hexdigest()

        self.assertEqual(search.returncode, 0, search.stderr)
        self.assertEqual(db_hash_after, db_hash_before)
        out = json.loads(search.stdout)
        self.assertEqual(out["kind"], "openclaw-mem.search.hybrid.v0")
        self.assertIsNone(out["graph"]["fallback_reason"])
        self.assertGreaterEqual(out["graph"]["count"], 1)
        graph_paths = {item["source_path"] for item in out["results"] if item.get("lane") == "graph"}
        self.assertIn("pkg/resolver.py", graph_paths)


if __name__ == "__main__":
    unittest.main()
