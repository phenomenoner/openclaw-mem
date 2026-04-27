from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openclaw_mem.cli import (
    _connect,
    _docs_repo_relpath,
    _docs_vec_candidates_exist,
    _docs_vec_rows,
    build_parser,
    cmd_docs_ingest,
    cmd_docs_search,
)
from openclaw_mem.docs_memory import chunk_content_hash, chunk_markdown, fuse_rankings_rrf
from openclaw_mem.vector import l2_norm, pack_f32


class TestDocsMemory(unittest.TestCase):
    def _insert_doc_chunk(self, conn, *, repo: str, rel_path: str, text: str, title: str, chunk_id: str = "chunk:001") -> int:
        now = "2026-03-22T00:00:00+00:00"
        doc_id = f"{repo}:{rel_path}"
        content_hash = chunk_content_hash(heading_path=title, title=title, text=text)
        cur = conn.execute(
            """
            INSERT INTO docs_chunks (
                doc_id, chunk_id, repo, path, doc_kind, heading_path, title,
                text, source_kind, source_ref, ts_hint, content_hash, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                chunk_id,
                repo,
                rel_path,
                "spec",
                title,
                title,
                text,
                "operator",
                f"{repo}/{rel_path}",
                None,
                content_hash,
                now,
            ),
        )
        return int(cur.lastrowid)

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

        a = build_parser().parse_args(["docs", "search", "hybrid", "--scope-repos", "repo-a", "repo-b", "--json"])
        self.assertEqual(a.scope_repos, ["repo-a", "repo-b"])
        self.assertTrue(a.json)

    def test_docs_repo_relpath_uses_parent_walk_for_normal_nested_repo(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo-a"
            nested = repo / "docs" / "guides"
            nested.mkdir(parents=True)
            (repo / ".git").mkdir()
            doc = nested / "alpha.md"
            doc.write_text("# Alpha\n", encoding="utf-8")

            with patch("openclaw_mem.cli.subprocess.run", side_effect=AssertionError("git subprocess should not run")):
                repo_name, rel_path = _docs_repo_relpath(doc, {})

            self.assertEqual(repo_name, "repo-a")
            self.assertEqual(rel_path, "docs/guides/alpha.md")

    def test_docs_repo_relpath_falls_back_for_git_file_worktree_marker(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo-a"
            nested = repo / "docs" / "guides"
            nested.mkdir(parents=True)
            (repo / ".git").write_text("gitdir: ../actual.git\n", encoding="utf-8")
            doc = nested / "alpha.md"
            doc.write_text("# Alpha\n", encoding="utf-8")

            completed = subprocess.CompletedProcess(
                ["git", "-C", str(doc.parent), "rev-parse", "--show-toplevel"],
                0,
                stdout=f"{repo}\n",
                stderr="",
            )
            with patch("openclaw_mem.cli.subprocess.run", return_value=completed) as run:
                repo_name, rel_path = _docs_repo_relpath(doc, {})

            run.assert_called_once()
            self.assertEqual(repo_name, "repo-a")
            self.assertEqual(rel_path, "docs/guides/alpha.md")

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
                    "scope_repos": None,
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
            self.assertFalse(out["pushdown_applied"])
            self.assertEqual(out["pushdown_repos"], [])

        conn.close()

    def test_docs_search_scope_repos_filters_fts_results(self):
        conn = _connect(":memory:")
        self._insert_doc_chunk(conn, repo="repo-a", rel_path="alpha.md", title="Alpha", text="target phrase for scoped docs test")
        self._insert_doc_chunk(conn, repo="repo-b", rel_path="beta.md", title="Beta", text="target phrase for scoped docs test")
        conn.commit()

        scoped_args = type(
            "Args",
            (),
            {
                "query": "target",
                "limit": 5,
                "fts_k": 10,
                "vec_k": 10,
                "k": 60,
                "scope_repos": ["repo-a"],
                "trace": True,
                "model": "text-embedding-3-small",
                "base_url": "https://api.openai.com/v1",
                "json": True,
            },
        )()

        with patch("openclaw_mem.cli._get_api_key", return_value=None):
            scoped_buf = io.StringIO()
            with redirect_stdout(scoped_buf):
                cmd_docs_search(conn, scoped_args)

            unscoped_args = type(
                "Args",
                (),
                {
                    "query": "target",
                    "limit": 5,
                    "fts_k": 10,
                    "vec_k": 10,
                    "k": 60,
                    "scope_repos": None,
                    "trace": True,
                    "model": "text-embedding-3-small",
                    "base_url": "https://api.openai.com/v1",
                    "json": True,
                },
            )()
            unscoped_buf = io.StringIO()
            with redirect_stdout(unscoped_buf):
                cmd_docs_search(conn, unscoped_args)

        scoped = json.loads(scoped_buf.getvalue())
        self.assertEqual([item["repo"] for item in scoped["results"]], ["repo-a"])
        self.assertTrue(scoped["pushdown_applied"])
        self.assertEqual(scoped["pushdown_repos"], ["repo-a"])
        self.assertEqual(scoped["trace"]["pushdown_repos"], ["repo-a"])

        unscoped = json.loads(unscoped_buf.getvalue())
        self.assertEqual({item["repo"] for item in unscoped["results"]}, {"repo-a", "repo-b"})
        self.assertFalse(unscoped["pushdown_applied"])

        conn.close()

    def test_docs_search_no_embeddings_skips_embedding_client_and_keeps_fts_ordering(self):
        conn = _connect(":memory:")
        self._insert_doc_chunk(conn, repo="repo-a", rel_path="alpha.md", title="Alpha", text="target phrase first")
        self._insert_doc_chunk(conn, repo="repo-a", rel_path="beta.md", title="Beta", text="target phrase second")
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "query": "target",
                "limit": 5,
                "fts_k": 10,
                "vec_k": 10,
                "k": 60,
                "scope_repos": None,
                "trace": True,
                "model": "text-embedding-3-small",
                "base_url": "https://example.com/v1",
                "json": True,
            },
        )()

        class _UnexpectedEmbedClient:
            def __init__(self, *args, **kwargs):
                raise AssertionError("embedding client should not be instantiated when no docs embeddings exist")

        with patch("openclaw_mem.cli._get_api_key", return_value=None):
            fts_only_buf = io.StringIO()
            with redirect_stdout(fts_only_buf):
                cmd_docs_search(conn, args)

        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch(
            "openclaw_mem.cli.OpenAIEmbeddingsClient", _UnexpectedEmbedClient
        ):
            no_vec_buf = io.StringIO()
            with redirect_stdout(no_vec_buf):
                cmd_docs_search(conn, args)

        fts_only = json.loads(fts_only_buf.getvalue())
        no_vec = json.loads(no_vec_buf.getvalue())
        self.assertEqual([item["id"] for item in no_vec["results"]], [item["id"] for item in fts_only["results"]])
        self.assertEqual(no_vec["trace"]["vec_top_k"], [])
        self.assertNotIn("vector_status", no_vec)

        conn.close()

    def test_docs_vector_candidate_precheck_matches_vec_row_scope_visibility(self):
        conn = _connect(":memory:")
        rid_a = self._insert_doc_chunk(conn, repo="repo-a", rel_path="alpha.md", title="Alpha", text="lexical miss one")
        conn.execute(
            "INSERT INTO docs_embeddings (chunk_rowid, model, dim, vector, norm, text_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rid_a, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "hash-a", "2026-03-22T00:00:00+00:00"),
        )
        conn.commit()

        query_vec = [1.0, 0.0]
        cases = [
            (None, True),
            (["repo-a"], True),
            (["repo-b"], False),
        ]
        for scope_repos, expected in cases:
            with self.subTest(scope_repos=scope_repos):
                self.assertEqual(_docs_vec_candidates_exist(conn, model="test-model", scope_repos=scope_repos), expected)
                self.assertEqual(
                    bool(_docs_vec_rows(conn, query_vec=query_vec, model="test-model", top_k=5, scope_repos=scope_repos)),
                    expected,
                )

        self.assertFalse(_docs_vec_candidates_exist(conn, model="other-model", scope_repos=None))
        self.assertFalse(_docs_vec_rows(conn, query_vec=query_vec, model="other-model", top_k=5, scope_repos=None))

        conn.close()

    def test_docs_vec_rows_filters_to_query_dimension_and_skips_legacy_zero_or_null_dim_rows(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE docs_chunks (
                id INTEGER PRIMARY KEY, doc_id TEXT, chunk_id TEXT, repo TEXT, path TEXT,
                doc_kind TEXT, heading_path TEXT, title TEXT, text TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE docs_embeddings (
                chunk_rowid INTEGER, model TEXT, dim INTEGER, vector BLOB, norm REAL, text_hash TEXT, created_at TEXT
            )
            """
        )
        rows = [
            (1, "good-2d", 2, [1.0, 0.0], 1.0),
            (2, "wrong-3d", 3, [1.0, 0.0, 0.0], 1.0),
            (3, "legacy-zero-dim-empty", 0, [], 0.0),
            (4, "legacy-null-dim-empty", None, [], 0.0),
        ]
        for rid, title, dim, vec, norm in rows:
            conn.execute(
                "INSERT INTO docs_chunks (id, doc_id, chunk_id, repo, path, doc_kind, heading_path, title, text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, f"doc-{rid}", f"chunk-{rid}", "repo-a", f"doc-{rid}.md", "spec", title, title, title),
            )
            conn.execute(
                "INSERT INTO docs_embeddings (chunk_rowid, model, dim, vector, norm, text_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rid, "test-model", dim, pack_f32(vec), norm, f"hash-{rid}", "2026-03-22T00:00:00+00:00"),
            )
        conn.commit()

        model_count = conn.execute("SELECT COUNT(*) FROM docs_embeddings WHERE model = ?", ("test-model",)).fetchone()[0]
        dim_count = conn.execute("SELECT COUNT(*) FROM docs_embeddings WHERE model = ? AND dim = ?", ("test-model", 2)).fetchone()[0]
        out = _docs_vec_rows(conn, query_vec=[1.0, 0.0], model="test-model", top_k=10)

        self.assertEqual(model_count, 4)
        self.assertEqual(dim_count, 1)
        self.assertEqual([r["id"] for r in out], [1])
        conn.close()

    def test_docs_search_scope_repos_filters_vector_candidates(self):
        conn = _connect(":memory:")
        rid_a = self._insert_doc_chunk(conn, repo="repo-a", rel_path="alpha.md", title="Alpha", text="lexical miss one")
        rid_b = self._insert_doc_chunk(conn, repo="repo-b", rel_path="beta.md", title="Beta", text="lexical miss two")
        conn.execute(
            "INSERT INTO docs_embeddings (chunk_rowid, model, dim, vector, norm, text_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rid_a, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "hash-a", "2026-03-22T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO docs_embeddings (chunk_rowid, model, dim, vector, norm, text_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rid_b, "test-model", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "hash-b", "2026-03-22T00:00:00+00:00"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[0.0, 1.0] for _ in texts]

        args = type(
            "Args",
            (),
            {
                "query": "semantic only",
                "limit": 5,
                "fts_k": 5,
                "vec_k": 5,
                "k": 60,
                "scope_repos": ["repo-b"],
                "trace": True,
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "json": True,
            },
        )()

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                cmd_docs_search(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual([item["repo"] for item in out["results"]], ["repo-b"])
        self.assertIn("vector", out["results"][0]["match"])
        self.assertEqual(out["pushdown_repos"], ["repo-b"])
        self.assertTrue(out["pushdown_applied"])

        conn.close()


if __name__ == "__main__":
    unittest.main()
