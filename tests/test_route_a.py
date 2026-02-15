import tempfile
import unittest
from pathlib import Path

from openclaw_mem.cli import _connect, _build_index, _extract_obs_ids, _rank_obs_ids_from_snippet, _cjk_terms, _search_cjk_fallback, _tokenize_query


class TestRouteAIndex(unittest.TestCase):
    def test_extract_obs_ids(self):
        snippet = "- obs#12 2026-02-06 [tool] exec :: did a thing\n- obs#7 ..."
        self.assertEqual(_extract_obs_ids(snippet), [7, 12])

    def test_rank_obs_ids_from_snippet_prefers_exact(self):
        snippet = "- obs#1 tool :: alpha\n- obs#5 tool :: harvest test\n"
        ranked = _rank_obs_ids_from_snippet(snippet, query="obs#5")
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][0], 5)

    def test_tokenize_query_keeps_obs_id_and_filters_short_tokens(self):
        tokens = _tokenize_query("Need obs#5 status + api timeout aa a b")
        self.assertIn("obs#5", tokens)
        self.assertIn("status", tokens)
        self.assertNotIn("aa", tokens)
        self.assertNotIn("a", tokens)

    def test_cjk_terms_extracts_full_run_and_bigrams(self):
        terms = _cjk_terms("測試測試", max_terms=16)
        self.assertGreaterEqual(len(terms), 3)
        self.assertIn("測試測試", terms)
        self.assertIn("測試", terms)
        self.assertIn("試測", terms)
        # Stable de-duplication should remove duplicated bigrams.
        self.assertEqual(len(terms), len(set(terms)))

    def test_search_cjk_fallback_matches_local_terms(self):
        conn = _connect(":memory:")
        conn.execute(
            "INSERT INTO observations (ts, kind, summary, tool_name, detail_json) VALUES (?,?,?,?,?)",
            ("2026-02-06T00:00:00Z", "tool", "台北開會", "calendar", "{}"),
        )
        conn.execute(
            "INSERT INTO observations (ts, kind, summary, tool_name, detail_json) VALUES (?,?,?,?,?)",
            ("2026-02-06T00:01:00Z", "tool", "高雄旅行", "calendar", "{}"),
        )
        conn.commit()

        rows = _search_cjk_fallback(conn, "台北", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertIn("台北", rows[0]["summary"])

        conn.close()

    def test_build_index_writes_file(self):
        conn = _connect(":memory:")
        # Insert minimal observations
        conn.execute(
            "INSERT INTO observations (ts, kind, summary, tool_name, detail_json) VALUES (?,?,?,?,?)",
            ("2026-02-06T00:00:00Z", "tool", "first", "exec", "{}"),
        )
        conn.execute(
            "INSERT INTO observations_fts (rowid, summary, tool_name, detail_json) VALUES (?,?,?,?)",
            (1, "first", "exec", "{}"),
        )
        conn.execute(
            "INSERT INTO observations (ts, kind, summary, tool_name, detail_json) VALUES (?,?,?,?,?)",
            ("2026-02-06T00:01:00Z", "tool", "second", "cron.list", "{}"),
        )
        conn.execute(
            "INSERT INTO observations_fts (rowid, summary, tool_name, detail_json) VALUES (?,?,?,?)",
            (2, "second", "cron.list", "{}"),
        )
        conn.commit()

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.md"
            n = _build_index(conn, out, limit=100)
            self.assertEqual(n, 2)
            content = out.read_text(encoding="utf-8")
            self.assertIn("obs#1", content)
            self.assertIn("obs#2", content)
            self.assertIn("cron.list", content)

        conn.close()


if __name__ == "__main__":
    unittest.main()
