import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from openclaw_mem.vector import l2_norm, pack_f32

from openclaw_mem.cli import _connect, _episodes_vector_rankings, build_parser


class TestEpisodesCli(unittest.TestCase):
    def _run(self, conn, argv, *, expect_exit=None):
        args = build_parser().parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            if expect_exit is None:
                args.func(conn, args)
            else:
                with self.assertRaises(SystemExit) as cm:
                    args.func(conn, args)
                self.assertEqual(cm.exception.code, expect_exit)

        text = buf.getvalue().strip()
        return json.loads(text) if text else None

    def test_episodic_schema_and_indexes_exist(self):
        conn = _connect(":memory:")
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        self.assertIn("episodic_events", tables)
        self.assertIn("episodic_event_embeddings", tables)

        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'episodic_events'"
            ).fetchall()
        }
        self.assertIn("uq_episodic_event_id", idx)
        self.assertIn("idx_episodic_scope_ts", idx)
        self.assertIn("idx_episodic_session_ts", idx)
        self.assertIn("idx_episodic_scope_type_ts", idx)
        conn.close()

    def test_episodes_query_summary_only_default_and_include_payload_optin(self):
        conn = _connect(":memory:")

        self._run(
            conn,
            [
                "episodes",
                "append",
                "--scope",
                "proj-a",
                "--session-id",
                "s1",
                "--agent-id",
                "lyria",
                "--type",
                "conversation.user",
                "--summary",
                "hello",
                "--payload-json",
                '{"note":"payload"}',
                "--refs-json",
                '{"recordRef":"obs:1"}',
                "--json",
            ],
        )

        out_default = self._run(
            conn,
            ["episodes", "query", "--scope", "proj-a", "--session-id", "s1", "--json"],
        )
        self.assertEqual(out_default["count"], 1)
        self.assertNotIn("payload", out_default["items"][0])
        self.assertEqual(out_default["items"][0]["summary"], "hello")

        out_payload = self._run(
            conn,
            [
                "episodes",
                "query",
                "--scope",
                "proj-a",
                "--session-id",
                "s1",
                "--include-payload",
                "--json",
            ],
        )
        self.assertEqual(out_payload["count"], 1)
        self.assertEqual(out_payload["items"][0]["payload"], {"note": "payload"})
        conn.close()

    def test_episodes_scope_isolation_and_no_unscoped_fallback(self):
        conn = _connect(":memory:")

        for scope in ("proj-alpha", "proj-beta"):
            self._run(
                conn,
                [
                    "episodes",
                    "append",
                    "--scope",
                    scope,
                    "--session-id",
                    "s-same",
                    "--agent-id",
                    "worker",
                    "--type",
                    "ops.alert",
                    "--summary",
                    f"event-{scope}",
                    "--json",
                ],
            )

        out_alpha = self._run(
            conn,
            ["episodes", "query", "--scope", "proj-alpha", "--session-id", "s-same", "--json"],
        )
        self.assertEqual(out_alpha["count"], 1)
        self.assertEqual(out_alpha["items"][0]["scope"], "proj-alpha")

        out_err = self._run(conn, ["episodes", "query", "--json"], expect_exit=2)
        self.assertFalse(out_err["ok"])
        self.assertIn("scope is required", out_err["error"])
        conn.close()

    def test_episodes_append_rejects_payload_bounds(self):
        conn = _connect(":memory:")
        oversized = "x" * 9000
        out = self._run(
            conn,
            [
                "episodes",
                "append",
                "--scope",
                "proj-a",
                "--session-id",
                "s1",
                "--agent-id",
                "lyria",
                "--type",
                "conversation.assistant",
                "--summary",
                "oversized payload",
                "--payload-json",
                json.dumps({"blob": oversized}, ensure_ascii=False),
                "--json",
            ],
            expect_exit=2,
        )
        self.assertFalse(out["ok"])
        self.assertIn("payload exceeds cap", out["error"])
        conn.close()

    def test_episodes_redact_by_session_sets_flag_and_payload(self):
        conn = _connect(":memory:")

        for summary in ("a", "b"):
            self._run(
                conn,
                [
                    "episodes",
                    "append",
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s2",
                    "--agent-id",
                    "lyria",
                    "--type",
                    "tool.result",
                    "--summary",
                    summary,
                    "--payload-json",
                    '{"raw":"value"}',
                    "--refs-json",
                    '{"recordRef":"obs:1"}',
                    "--json",
                ],
            )

        redact_out = self._run(
            conn,
            [
                "episodes",
                "redact",
                "--session-id",
                "s2",
                "--scope",
                "proj-a",
                "--replacement",
                "placeholder",
                "--json",
            ],
        )
        self.assertEqual(redact_out["redacted_count"], 2)

        query_out = self._run(
            conn,
            [
                "episodes",
                "query",
                "--scope",
                "proj-a",
                "--session-id",
                "s2",
                "--include-payload",
                "--json",
            ],
        )
        self.assertEqual(query_out["count"], 2)
        for item in query_out["items"]:
            self.assertTrue(item["redacted"])
            self.assertEqual(item["payload"], "[REDACTED]")
            self.assertEqual(item["refs"], "[REDACTED]")
        conn.close()

    def test_episodes_query_deterministic_ordering(self):
        conn = _connect(":memory:")

        self._run(
            conn,
            [
                "episodes",
                "append",
                "--event-id",
                "ev-1",
                "--ts-ms",
                "2000",
                "--scope",
                "proj-a",
                "--session-id",
                "s3",
                "--agent-id",
                "a",
                "--type",
                "conversation.user",
                "--summary",
                "second-time-first-insert",
                "--json",
            ],
        )
        self._run(
            conn,
            [
                "episodes",
                "append",
                "--event-id",
                "ev-2",
                "--ts-ms",
                "1000",
                "--scope",
                "proj-a",
                "--session-id",
                "s3",
                "--agent-id",
                "a",
                "--type",
                "conversation.user",
                "--summary",
                "first-time",
                "--json",
            ],
        )
        self._run(
            conn,
            [
                "episodes",
                "append",
                "--event-id",
                "ev-3",
                "--ts-ms",
                "2000",
                "--scope",
                "proj-a",
                "--session-id",
                "s3",
                "--agent-id",
                "a",
                "--type",
                "conversation.assistant",
                "--summary",
                "second-time-second-insert",
                "--json",
            ],
        )

        out = self._run(
            conn,
            ["episodes", "query", "--scope", "proj-a", "--session-id", "s3", "--json"],
        )
        ordered_event_ids = [item["event_id"] for item in out["items"]]
        self.assertEqual(ordered_event_ids, ["ev-2", "ev-1", "ev-3"])
        conn.close()

    def test_episodes_gc_emits_aggregate_receipt(self):
        conn = _connect(":memory:")
        now_ts_ms = 1_800_000_000_000

        # old tool.result (should be deleted by default 30d retention)
        self._run(
            conn,
            [
                "episodes",
                "append",
                "--event-id",
                "old-tool",
                "--ts-ms",
                str(now_ts_ms - (40 * 24 * 60 * 60 * 1000)),
                "--scope",
                "proj-gc",
                "--session-id",
                "s-gc",
                "--agent-id",
                "w",
                "--type",
                "tool.result",
                "--summary",
                "old tool result",
                "--json",
            ],
        )
        # old ops.decision (forever by default)
        self._run(
            conn,
            [
                "episodes",
                "append",
                "--event-id",
                "old-decision",
                "--ts-ms",
                str(now_ts_ms - (400 * 24 * 60 * 60 * 1000)),
                "--scope",
                "proj-gc",
                "--session-id",
                "s-gc",
                "--agent-id",
                "w",
                "--type",
                "ops.decision",
                "--summary",
                "keep decision",
                "--json",
            ],
        )

        gc_out = self._run(
            conn,
            [
                "episodes",
                "gc",
                "--scope",
                "proj-gc",
                "--now-ts-ms",
                str(now_ts_ms),
                "--json",
            ],
        )
        self.assertEqual(gc_out["deleted_by_type"]["tool.result"], 1)
        self.assertEqual(gc_out["deleted_by_type"]["ops.decision"], 0)

        post = self._run(
            conn,
            ["episodes", "query", "--scope", "proj-gc", "--session-id", "s-gc", "--json"],
        )
        self.assertEqual([x["event_id"] for x in post["items"]], ["old-decision"])
        conn.close()

    def test_episodes_gc_conversation_type_default_retention(self):
        conn = _connect(":memory:")
        now_ts_ms = 1_800_000_000_000

        self._run(
            conn,
            [
                "episodes",
                "append",
                "--event-id",
                "old-user",
                "--ts-ms",
                str(now_ts_ms - (70 * 24 * 60 * 60 * 1000)),
                "--scope",
                "proj-ret",
                "--session-id",
                "s-ret",
                "--agent-id",
                "w",
                "--type",
                "conversation.user",
                "--summary",
                "old user",
                "--json",
            ],
        )
        self._run(
            conn,
            [
                "episodes",
                "append",
                "--event-id",
                "old-assistant",
                "--ts-ms",
                str(now_ts_ms - (70 * 24 * 60 * 60 * 1000)),
                "--scope",
                "proj-ret",
                "--session-id",
                "s-ret",
                "--agent-id",
                "w",
                "--type",
                "conversation.assistant",
                "--summary",
                "old assistant",
                "--json",
            ],
        )

        gc_out = self._run(
            conn,
            [
                "episodes",
                "gc",
                "--scope",
                "proj-ret",
                "--now-ts-ms",
                str(now_ts_ms),
                "--json",
            ],
        )
        self.assertEqual(gc_out["deleted_by_type"]["conversation.user"], 1)
        self.assertEqual(gc_out["deleted_by_type"]["conversation.assistant"], 0)

        post = self._run(
            conn,
            ["episodes", "query", "--scope", "proj-ret", "--session-id", "s-ret", "--json"],
        )
        self.assertEqual([x["event_id"] for x in post["items"]], ["old-assistant"])
        conn.close()

    def test_episodes_embed_and_hybrid_search_vector_lane(self):
        conn = _connect(":memory:")

        self._run(
            conn,
            [
                "episodes",
                "append",
                "--scope",
                "proj-sem",
                "--session-id",
                "sess-hermes",
                "--agent-id",
                "lyria",
                "--type",
                "conversation.user",
                "--summary",
                "Hermes retrieval lane review",
                "--payload-json",
                json.dumps({"note": "compare recall posture"}, ensure_ascii=False),
                "--json",
            ],
        )
        self._run(
            conn,
            [
                "episodes",
                "append",
                "--scope",
                "proj-sem",
                "--session-id",
                "sess-weather",
                "--agent-id",
                "lyria",
                "--type",
                "conversation.user",
                "--summary",
                "Weather notes only",
                "--payload-json",
                json.dumps({"note": "sunny"}, ensure_ascii=False),
                "--json",
            ],
        )

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                out = []
                for text in texts:
                    t = str(text).lower()
                    if any(tok in t for tok in ["hermes", "semantic", "recall"]):
                        out.append([1.0, 0.0])
                    else:
                        out.append([0.0, 1.0])
                return out

        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            embed_out = self._run(
                conn,
                ["episodes", "embed", "--scope", "proj-sem", "--limit", "20", "--json"],
            )
            self.assertEqual(embed_out["embedded"], 2)

            out = self._run(
                conn,
                [
                    "episodes",
                    "search",
                    "semantic evidence",
                    "--scope",
                    "proj-sem",
                    "--mode",
                    "hybrid",
                    "--trace",
                    "--json",
                ],
            )

        self.assertGreaterEqual(out["result"]["count"], 1)
        self.assertEqual(out["result"]["mode"], "hybrid")
        self.assertEqual(out["vector_status"], "ok")
        session = out["result"]["sessions"][0]
        self.assertEqual(session["session_id"], "sess-hermes")
        self.assertIn("vector", session["matched_items"][0]["match"]["lanes"])
        self.assertIn("trace", out)
        self.assertGreaterEqual(len(out["trace"]["vec_top_k"]), 1)
        conn.close()

    def test_episodes_vector_rankings_filters_to_query_dimension_and_skips_legacy_zero_dim_rows(self):
        conn = _connect(":memory:")
        for idx, (summary, dim, vec, norm) in enumerate(
            [
                ("good semantic event", 2, [1.0, 0.0], 1.0),
                ("wrong dimension event", 3, [1.0, 0.0, 0.0], 1.0),
                ("legacy zero dim event", 0, [], 0.0),
            ],
            start=1,
        ):
            self._run(
                conn,
                [
                    "episodes",
                    "append",
                    "--scope",
                    "proj-dim",
                    "--session-id",
                    f"sess-{idx}",
                    "--agent-id",
                    "lyria",
                    "--type",
                    "conversation.user",
                    "--summary",
                    summary,
                    "--json",
                ],
            )
            conn.execute(
                "INSERT INTO episodic_event_embeddings (event_row_id, model, dim, vector, norm, search_text_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (idx, "test-model", dim, pack_f32(vec), norm, f"hash-{idx}", "2026-03-22T00:00:00+00:00"),
            )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        model_count = conn.execute("SELECT COUNT(*) FROM episodic_event_embeddings WHERE model = ?", ("test-model",)).fetchone()[0]
        dim_count = conn.execute("SELECT COUNT(*) FROM episodic_event_embeddings WHERE model = ? AND dim = ?", ("test-model", 2)).fetchone()[0]
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            out = _episodes_vector_rankings(
                conn,
                scope="proj-dim",
                query="semantic",
                query_en=None,
                model="test-model",
                candidate_limit=10,
                base_url="https://example.com/v1",
            )

        self.assertEqual(model_count, 3)
        self.assertEqual(dim_count, 1)
        self.assertEqual(out["vector_status"], "ok")
        self.assertEqual(out["vec_ids"], [1])
        conn.close()

    def test_episodes_vector_rankings_filters_separate_english_query_dimension(self):
        conn = _connect(":memory:")
        for idx, (summary, dim, vec, norm) in enumerate(
            [
                ("base semantic event", 2, [1.0, 0.0], 1.0),
                ("english semantic event", 3, [0.0, 1.0, 0.0], 1.0),
            ],
            start=1,
        ):
            self._run(
                conn,
                [
                    "episodes",
                    "append",
                    "--scope",
                    "proj-dim-en",
                    "--session-id",
                    f"sess-en-{idx}",
                    "--agent-id",
                    "lyria",
                    "--type",
                    "conversation.user",
                    "--summary",
                    summary,
                    "--json",
                ],
            )
            conn.execute(
                "INSERT INTO episodic_event_embeddings (event_row_id, model, dim, vector, norm, search_text_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (idx, "test-model", dim, pack_f32(vec), norm, f"hash-en-{idx}", "2026-03-22T00:00:00+00:00"),
            )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0], [0.0, 1.0, 0.0]][: len(texts)]

        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            out = _episodes_vector_rankings(
                conn,
                scope="proj-dim-en",
                query="semantic",
                query_en="semantic english",
                model="test-model",
                candidate_limit=10,
                base_url="https://example.com/v1",
            )

        self.assertEqual(out["vector_status"], "ok")
        self.assertEqual(out["vec_ids"], [1])
        self.assertEqual(out["vec_en_ids"], [2])
        conn.close()

    def test_episodes_search_hybrid_fails_open_to_lexical_when_vector_unavailable(self):
        conn = _connect(":memory:")

        self._run(
            conn,
            [
                "episodes",
                "append",
                "--scope",
                "proj-fallback",
                "--session-id",
                "sess-1",
                "--agent-id",
                "lyria",
                "--type",
                "conversation.user",
                "--summary",
                "graph readiness fallback",
                "--payload-json",
                json.dumps({"note": "episodes search fallback"}, ensure_ascii=False),
                "--json",
            ],
        )

        out = self._run(
            conn,
            [
                "episodes",
                "search",
                "fallback",
                "--scope",
                "proj-fallback",
                "--mode",
                "hybrid",
                "--json",
            ],
        )
        self.assertEqual(out["result"]["count"], 1)
        self.assertEqual(out["vector_status"], "missing_embeddings")
        self.assertEqual(out["result"]["sessions"][0]["session_id"], "sess-1")
        conn.close()

    def test_episodes_parser_accepts_embed_and_hybrid_flags(self):
        args = build_parser().parse_args(["episodes", "embed", "--scope", "proj-a", "--limit", "10", "--json"])
        self.assertEqual(args.cmd, "episodes")
        self.assertEqual(args.episodes_cmd, "embed")
        self.assertEqual(args.scope, "proj-a")
        self.assertEqual(args.limit, 10)
        self.assertTrue(args.json)

        args = build_parser().parse_args(["episodes", "search", "memory lane", "--scope", "proj-a", "--mode", "hybrid", "--query-en", "memory lane", "--trace", "--json"])
        self.assertEqual(args.episodes_cmd, "search")
        self.assertEqual(args.mode, "hybrid")
        self.assertEqual(args.query_en, "memory lane")
        self.assertTrue(args.trace)
        self.assertTrue(args.json)


if __name__ == "__main__":
    unittest.main()
