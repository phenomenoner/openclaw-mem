from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, cmd_graph_code_extract, cmd_graph_code_impact, cmd_graph_query
from openclaw_mem.graph.code_extract import extract_code_graph


class TestGraphCodeExtract(unittest.TestCase):
    def _write_fixture_repo(self, root: Path) -> None:
        (root / ".git").mkdir()
        (root / "pkg").mkdir()
        (root / "tests").mkdir()
        (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (root / "pkg" / "resolver.py").write_text(
            "from pkg.backend import load_backend\n\n"
            "class Resolver:\n"
            "    def resolve(self, config):\n"
            "        return load_backend(config)\n\n"
            "def build_pack(graph):\n"
            "    return {'nodes': graph.get('nodes', [])}\n",
            encoding="utf-8",
        )
        (root / "pkg" / "backend.py").write_text(
            "def load_backend(config):\n"
            "    return config.get('backend', 'sqlite')\n",
            encoding="utf-8",
        )
        (root / "tests" / "test_resolver.py").write_text(
            "from pkg.resolver import Resolver, build_pack\n\n"
            "def test_resolver_loads_backend():\n"
            "    assert Resolver().resolve({'backend': 'qdrant'}) == 'qdrant'\n\n"
            "def test_build_pack_keeps_nodes():\n"
            "    assert build_pack({'nodes': [1]}) == {'nodes': [1]}\n",
            encoding="utf-8",
        )

    def test_extract_code_graph_is_deterministic_with_provenance_and_test_links(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            self._write_fixture_repo(repo)

            first = extract_code_graph(repo=repo)
            second = extract_code_graph(repo=repo)

            self.assertEqual(first["kind"], "openclaw-mem.graph.code-extract.v0")
            self.assertEqual(first["nodes"], second["nodes"])
            self.assertEqual(first["edges"], second["edges"])
            self.assertEqual(first["counts"], second["counts"])

            node_ids = {node["id"] for node in first["nodes"]}
            self.assertIn("repo.repo", node_ids)
            self.assertIn("file.pkg/resolver.py", node_ids)
            self.assertIn("symbol.pkg/resolver.py:Resolver", node_ids)
            self.assertIn("symbol.pkg/resolver.py:build_pack", node_ids)

            edge_keys = {(edge["src"], edge["dst"], edge["type"]) for edge in first["edges"]}
            self.assertIn(("file.pkg/resolver.py", "symbol.pkg/resolver.py:Resolver", "defines"), edge_keys)
            self.assertIn(("file.pkg/resolver.py", "file.pkg/backend.py", "imports"), edge_keys)
            self.assertIn(("file.tests/test_resolver.py", "file.pkg/resolver.py", "tests"), edge_keys)

            symbol = next(node for node in first["nodes"] if node["id"] == "symbol.pkg/resolver.py:build_pack")
            meta = symbol["metadata"]
            self.assertEqual(meta["source_path"], "pkg/resolver.py")
            self.assertEqual(meta["span"], {"line_start": 7, "line_end": 8})
            self.assertEqual(meta["extractor"], "openclaw-mem.code-graph")
            self.assertEqual(meta["extractor_version"], "0.1.0")
            self.assertEqual(meta["confidence"], 1.0)
            self.assertEqual(meta["freshness"], "snapshot")
            self.assertEqual(meta["policySource"], "openclaw-mem-engine")
            self.assertFalse(meta["canonicalWritesAllowed"])

    def test_graph_extract_query_symbol_and_impact_cli_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            repo.mkdir()
            self._write_fixture_repo(repo)
            graph_path = root / "graph.jsonl"

            conn = _connect(str(root / "mem.sqlite"))
            try:
                extract_args = type(
                    "Args",
                    (),
                    {
                        "repo": str(repo),
                        "out": str(graph_path),
                        "json": True,
                    },
                )()
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_code_extract(conn, extract_args)

                extract_out = json.loads(buf.getvalue())
                self.assertEqual(extract_out["kind"], "openclaw-mem.graph.code-extract.v0")
                self.assertTrue(extract_out["result"]["ok"])
                self.assertTrue(graph_path.is_file())

                query_args = type(
                    "Args",
                    (),
                    {
                        "graph_query_cmd": "symbol",
                        "db": "",
                        "topology": "",
                        "graph": str(graph_path),
                        "symbol": "Resolver",
                        "json": True,
                    },
                )()
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_query(conn, query_args)

                query_out = json.loads(buf.getvalue())
                self.assertEqual(query_out["query_cmd"], "symbol")
                self.assertEqual(query_out["result"]["count"], 1)
                self.assertEqual(query_out["result"]["nodes"][0]["id"], "symbol.pkg/resolver.py:Resolver")

                impact_args = type(
                    "Args",
                    (),
                    {
                        "graph": str(graph_path),
                        "path": "pkg/resolver.py",
                        "json": True,
                    },
                )()
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cmd_graph_code_impact(conn, impact_args)

                impact_out = json.loads(buf.getvalue())
                self.assertEqual(impact_out["kind"], "openclaw-mem.graph.impact.v0")
                self.assertEqual(impact_out["result"]["path"], "pkg/resolver.py")
                edge_types = {edge["type"] for edge in impact_out["result"]["edges"]}
                self.assertIn("imports", edge_types)
                self.assertIn("tests", edge_types)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
