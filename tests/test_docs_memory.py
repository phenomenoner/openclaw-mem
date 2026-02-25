from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser, cmd_docs_ingest, cmd_docs_search
from openclaw_mem.docs_memory import chunk_markdown, fuse_rankings_rrf


class TestDocsMemory(unittest.TestCase):
    def test_chunking_stability(self):
        text = """
# Title

## Alpha
first paragraph

second paragraph

## Alpha
third paragraph
""".strip()

        c1 = chunk_markdown(text, default_title="test", max_chars=80)
        c2 = chunk_markdown(text, default_title="test", max_chars=80)

        ids1 = [c.chunk_id for c in c1]
        ids2 = [c.chunk_id for c in c2]
        paths1 = [c.heading_path for c in c1]
        paths2 = [c.heading_path for c in c2]

        self.assertEqual(ids1, ids2)
        self.assertEqual(paths1, paths2)
        self.assertIn("title-alpha:001", ids1)
        self.assertIn("title-alpha~2:001", ids1)

    def test_rrf_fusion_is_deterministic(self):
        # Equal final RRF score for IDs 1 and 2; deterministic tie-break should be id asc.
        fts_ids = [2, 1]
        vec_ids = [1, 2]

        r1 = fuse_rankings_rrf(fts_ids=fts_ids, vec_ids=vec_ids, k=60, limit=5)
        r2 = fuse_rankings_rrf(fts_ids=fts_ids, vec_ids=vec_ids, k=60, limit=5)

        self.assertEqual(r1, r2)
        self.assertEqual([x[0] for x in r1[:2]], [1, 2])

    def test_docs_parser_accepts_subcommands_and_json_flag(self):
        a = build_parser().parse_args(["docs", "ingest", "--path", "/tmp", "--json"])
        self.assertEqual(a.cmd, "docs")
        self.assertEqual(a.docs_cmd, "ingest")
        self.assertTrue(a.json)

        a = build_parser().parse_args(["docs", "search", "hybrid", "--trace", "--json"])
        self.assertEqual(a.cmd, "docs")
        self.assertEqual(a.docs_cmd, "search")
        self.assertEqual(a.query, "hybrid")
        self.assertTrue(a.trace)
        self.assertTrue(a.json)

    def test_docs_fts_query_returns_expected_doc(self):
        conn = _connect(":memory:")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "alpha.md").write_text(
                "# Alpha\n\n## Overview\nThis guide explains hybrid retrieval orchestration.",
                encoding="utf-8",
            )
            (root / "beta.md").write_text(
                "# Beta\n\n## Notes\nThis file discusses gardening tips.",
                encoding="utf-8",
            )

            ingest_args = type(
                "Args",
                (),
                {
                    "path": [str(root)],
                    "max_chars": 1200,
                    "embed": False,
                    "batch": 8,
                    "model": "text-embedding-3-small",
                    "base_url": "https://api.openai.com/v1",
                    "json": True,
                },
            )()

            with redirect_stdout(io.StringIO()):
                cmd_docs_ingest(conn, ingest_args)

            search_args = type(
                "Args",
                (),
                {
                    "query": "orchestration",
                    "limit": 5,
                    "fts_k": 10,
                    "vec_k": 10,
                    "k": 60,
                    "trace": True,
                    "model": "text-embedding-3-small",
                    "base_url": "https://api.openai.com/v1",
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_docs_search(conn, search_args)

            out = json.loads(buf.getvalue())
            self.assertGreaterEqual(len(out["results"]), 1)
            self.assertEqual(out["results"][0]["path"], "alpha.md")
            self.assertIn("recordRef", out["results"][0])
            self.assertIn("trace", out)
            self.assertIn("fts_top_k", out["trace"])

        conn.close()


if __name__ == "__main__":
    unittest.main()
