from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_mem.graph.search_adapter import graph_search_candidates


def _node(
    node_id: str,
    *,
    source_path: str,
    receipt_id: str = "receipt:graph-1",
    freshness: str = "snapshot",
    name: str | None = None,
) -> dict:
    return {
        "id": node_id,
        "type": "symbol" if node_id.startswith("symbol.") else "file",
        "tags": ["code", "python"],
        "metadata": {
            "source_path": source_path,
            "span": {"line_start": 1, "line_end": 3},
            "commit": "abc123",
            "confidence": 0.9,
            "freshness": freshness,
            "receipt_id": receipt_id,
            "name": name or Path(source_path).stem,
            "qualname": name or Path(source_path).stem,
        },
    }


class TestGraphSearchAdapter(unittest.TestCase):
    def _write_graph(self, root: Path, payload: dict) -> Path:
        path = root / "graph.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_missing_graph_file_fails_open(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = graph_search_candidates(query="resolver", graph_path=Path(td) / "missing.json")

        self.assertEqual(out["candidates"], [])
        self.assertEqual(out["fallback_reason"], "graph_file_not_found")

    def test_malformed_graph_file_fails_open_without_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "graph.json"
            path.write_text("{not json", encoding="utf-8")
            out = graph_search_candidates(query="resolver", graph_path=path)

        self.assertEqual(out["candidates"], [])
        self.assertEqual(out["fallback_reason"], "graph_file_malformed")

    def test_stale_and_missing_provenance_nodes_are_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            graph_path = self._write_graph(
                root,
                {
                    "nodes": [
                        _node("symbol.pkg/resolver.py:Resolver", source_path="pkg/resolver.py", freshness="2020-01-01T00:00:00Z"),
                        _node("symbol.pkg/backend.py:Backend", source_path="pkg/backend.py", receipt_id=""),
                        _node("symbol.pkg/fresh.py:ResolverFresh", source_path="pkg/fresh.py", freshness="snapshot", name="ResolverFresh"),
                    ],
                    "edges": [],
                },
            )
            out = graph_search_candidates(
                query="resolver",
                graph_path=graph_path,
                stale_after_days=30,
                now=datetime(2026, 7, 7, tzinfo=timezone.utc),
            )

        self.assertEqual([c["source_path"] for c in out["candidates"]], ["pkg/fresh.py"])
        self.assertEqual(out["dropped"], {"missing_provenance": 1, "stale": 1})

    def test_rank_is_deterministic_and_graph_neighborhood_can_break_ties(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            graph_path = self._write_graph(
                root,
                {
                    "nodes": [
                        _node("symbol.pkg/b.py:Resolver", source_path="pkg/b.py", name="Resolver"),
                        _node("symbol.pkg/a.py:Resolver", source_path="pkg/a.py", name="Resolver"),
                    ],
                    "edges": [
                        {
                            "src": "symbol.pkg/b.py:Resolver",
                            "dst": "file.pkg/pack.py",
                            "type": "tests",
                            "provenance": "tests/test_pack.py",
                            "metadata": {"source_path": "tests/test_pack.py"},
                        }
                    ],
                },
            )

            first = graph_search_candidates(query="resolver pack", graph_path=graph_path)
            second = graph_search_candidates(query="resolver pack", graph_path=graph_path)

        self.assertEqual(first, second)
        self.assertEqual(first["candidates"][0]["source_path"], "pkg/b.py")
        self.assertGreater(first["candidates"][0]["score"], first["candidates"][1]["score"])

    def test_readiness_not_green_degrades_to_no_graph_hits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            graph_path = self._write_graph(root, {"nodes": [_node("symbol.pkg/resolver.py:Resolver", source_path="pkg/resolver.py")], "edges": []})
            readiness = root / "readiness.json"
            readiness.write_text(json.dumps({"status": "degraded"}), encoding="utf-8")

            out = graph_search_candidates(query="resolver", graph_path=graph_path, readiness_state_path=readiness)

        self.assertEqual(out["candidates"], [])
        self.assertEqual(out["fallback_reason"], "degraded")


if __name__ == "__main__":
    unittest.main()
