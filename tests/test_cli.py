import io
import json
import sys
import unittest
from contextlib import redirect_stdout

from openclaw_mem.cli import _connect, cmd_ingest, cmd_search, cmd_get, cmd_timeline, cmd_triage, cmd_store, cmd_hybrid, cmd_status, cmd_backend


class TestCliM0(unittest.TestCase):
    def test_schema_contains_english_embeddings_table(self):
        conn = _connect(":memory:")
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertIn("observation_embeddings_en", tables)

        args = type("Args", (), {"db": ":memory:", "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_status(conn, args)
        out = json.loads(buf.getvalue())
        self.assertIn("embeddings_en", out)
        self.assertEqual(out["embeddings_en"]["count"], 0)
        conn.close()

    def test_backend_reports_slot_and_readiness(self):
        conn = _connect(":memory:")

        fake_cfg = {
            "plugins": {
                "slots": {"memory": "memory-lancedb"},
                "entries": {
                    "memory-core": {"enabled": True},
                    "memory-lancedb": {
                        "enabled": True,
                        "config": {"embedding": {"apiKey": "${OPENAI_API_KEY}"}},
                    },
                    "openclaw-mem": {"enabled": True},
                },
            }
        }

        from unittest.mock import patch

        args = type("Args", (), {"json": True})()
        buf = io.StringIO()
        with patch("openclaw_mem.cli._read_openclaw_config", return_value=fake_cfg), patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            with redirect_stdout(buf):
                cmd_backend(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["memory_slot"], "memory-lancedb")
        self.assertTrue(out["entries"]["memory-lancedb"]["embedding_api_key_ready"])
        conn.close()

    def test_ingest_preserves_extra_fields_into_detail_json(self):
        conn = _connect(":memory:")

        sample = json.dumps(
            {
                "ts": "2026-02-04T13:00:00Z",
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "Found memories",
                "detail": {"base": 1},
                "memory_backend": "memory-lancedb",
                "memory_backend_ready": True,
                "memory_operation": "recall",
            }
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        row = conn.execute("SELECT detail_json FROM observations WHERE id = 1").fetchone()
        detail = json.loads(row["detail_json"])
        self.assertEqual(detail["base"], 1)
        self.assertEqual(detail["memory_backend"], "memory-lancedb")
        self.assertEqual(detail["memory_operation"], "recall")
        conn.close()

    def test_ingest_search_timeline_get_json(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "tool",
                        "tool_name": "cron.list",
                        "summary": "cron list called",
                        "detail": {"ok": True},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "tool",
                        "tool_name": "gateway.config.get",
                        "summary": "read gateway config",
                        "detail": {"ok": True},
                    }
                ),
            ]
        )

        # Ingest via stdin
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_ingest(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["inserted"], 2)
            self.assertTrue(out["ids"])
        finally:
            sys.stdin = old_stdin

        # Search
        args = type("Args", (), {"query": "cron", "limit": 20, "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_search(conn, args)
        hits = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["tool_name"], "cron.list")

        # Timeline around ID 1
        args = type("Args", (), {"ids": [1], "window": 1, "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_timeline(conn, args)
        tl = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(tl), 1)

        # Get
        args = type("Args", (), {"ids": [1, 2], "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_get(conn, args)
        rows = json.loads(buf.getvalue())
        self.assertEqual([r["id"] for r in rows], [1, 2])

        conn.close()

    def test_cjk_search_fallback_when_fts_misses(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-04T13:00:00Z",
                        "kind": "tool",
                        "tool_name": "memorybench",
                        "summary": "我今天在台北開產品會議，晚上再整理筆記。",
                        "detail": {"session_id": "s-zh-1"},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-04T13:01:00Z",
                        "kind": "tool",
                        "tool_name": "memorybench",
                        "summary": "I booked a train ticket to Taichung for next week.",
                        "detail": {"session_id": "s-en-1"},
                    }
                ),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        # This query is semantically related but not an exact phrase; CJK fallback should recover it.
        args = type("Args", (), {"query": "今天會議在什麼城市", "limit": 10, "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_search(conn, args)

        hits = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("台北", hits[0]["summary"])
        conn.close()

    def test_triage_exit_code_and_json(self):
        conn = _connect(":memory:")

        # Ingest one normal and one error-ish observation
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps({"ts": now, "kind": "tool", "tool_name": "web_fetch", "summary": "ok", "detail": {}}),
                json.dumps({"ts": now, "kind": "tool", "tool_name": "exec", "summary": "Error: command failed", "detail": {}}),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "observations",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)

        # Should signal attention
        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertTrue(out["needs_attention"])
        self.assertGreaterEqual(out["observations"]["found_new"], 1)

        conn.close()

    def test_triage_tasks_mode_dedupes_by_state(self):
        import tempfile
        from datetime import datetime, timezone

        conn = _connect(":memory:")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sample = "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "kind": "task",
                        "tool_name": "memory_store",
                        "summary": "TODO: buy coffee this afternoon",
                        "detail": {"importance": 0.9},
                    }
                )
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, args)
        finally:
            sys.stdin = old_stdin

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "tasks",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": None,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        # First run: should alert
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)
        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["tasks"]["found_new"], 1)

        # Second run: should NOT alert again (state dedupe)
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            with self.assertRaises(SystemExit) as cm2:
                cmd_triage(conn, args)
        self.assertEqual(cm2.exception.code, 0)
        out2 = json.loads(buf2.getvalue())
        self.assertEqual(out2["tasks"]["found_new"], 0)

        conn.close()

    def test_triage_cron_errors_reads_jobs_json(self):
        import tempfile

        # Fake cron jobs store
        jobs = {
            "jobs": [
                {
                    "id": "job1",
                    "name": "Job 1",
                    "enabled": True,
                    "state": {"lastStatus": "ok", "lastRunAtMs": 9999999999999},
                },
                {
                    "id": "job2",
                    "name": "Job 2",
                    "enabled": True,
                    "state": {"lastStatus": "error", "lastRunAtMs": 9999999999999, "lastDurationMs": 1234},
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as tmp:
            json.dump(jobs, tmp)
            tmp_path = tmp.name

        conn = _connect(":memory:")
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as st:
            state_path = st.name

        args = type(
            "Args",
            (),
            {
                "mode": "cron-errors",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": tmp_path,
                "tasks_since_minutes": 1440,
                "importance_min": 0.7,
                "state_path": state_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)
        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["cron"]["found_new"], 1)
        self.assertEqual(out["cron"]["matches"][0]["id"], "job2")

        conn.close()

    def test_store_persists_dual_language_fields(self):
        conn = _connect(":memory:")

        args = type(
            "Args",
            (),
            {
                "text": "나는 커피를 좋아해",
                "text_en": "I like coffee",
                "lang": "ko",
                "category": "preference",
                "importance": 0.8,
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "workspace": None,
                "json": True,
            },
        )()

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value=None):
            with redirect_stdout(buf):
                cmd_store(conn, args)

        out = json.loads(buf.getvalue())
        self.assertTrue(out["ok"])
        row = conn.execute("SELECT summary, summary_en, lang FROM observations WHERE id = ?", (out["id"],)).fetchone()
        self.assertEqual(row["summary"], "나는 커피를 좋아해")
        self.assertEqual(row["summary_en"], "I like coffee")
        self.assertEqual(row["lang"], "ko")
        conn.close()

    def test_store_persists_english_embedding_when_text_en_present(self):
        conn = _connect(":memory:")

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                return [[1.0, 0.0] for _ in texts]

        args = type(
            "Args",
            (),
            {
                "text": "원문",
                "text_en": "english",
                "lang": "ko",
                "category": "fact",
                "importance": 0.7,
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "workspace": None,
                "json": True,
            },
        )()

        from unittest.mock import patch

        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(io.StringIO()):
                cmd_store(conn, args)

        orig = conn.execute("SELECT COUNT(*) FROM observation_embeddings").fetchone()[0]
        en = conn.execute("SELECT COUNT(*) FROM observation_embeddings_en").fetchone()[0]
        self.assertEqual(orig, 1)
        self.assertEqual(en, 1)
        conn.close()

    def test_hybrid_supports_query_en_route(self):
        conn = _connect(":memory:")

        sample = "\n".join(
            [
                json.dumps({"ts": "2026-02-04T13:00:00Z", "kind": "fact", "summary": "사과", "summary_en": "apple", "tool_name": "memory_store", "detail": {}}),
                json.dumps({"ts": "2026-02-04T13:01:00Z", "kind": "fact", "summary": "바나나", "summary_en": "banana", "tool_name": "memory_store", "detail": {}}),
            ]
        )

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            ingest_args = type("Args", (), {"file": None, "json": True})()
            with redirect_stdout(io.StringIO()):
                cmd_ingest(conn, ingest_args)
        finally:
            sys.stdin = old_stdin

        from openclaw_mem.vector import pack_f32, l2_norm

        # Original table: id=1 aligns with [1,0], id=2 aligns with [0,1]
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "test-model", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        # EN table intentionally reversed so we can detect table preference.
        conn.execute(
            "INSERT INTO observation_embeddings_en (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "test-model", 2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0]), "2026-02-05T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO observation_embeddings_en (observation_id, model, dim, vector, norm, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "test-model", 2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0]), "2026-02-05T00:00:00Z"),
        )
        conn.commit()

        class _FakeEmbedClient:
            def __init__(self, api_key: str, base_url: str = ""):
                pass

            def embed(self, texts, model):
                out = []
                for t in texts:
                    if t == "zzzz":
                        out.append([0.0, 0.0])
                    else:
                        out.append([1.0, 0.0])
                return out

        args = type(
            "Args",
            (),
            {
                "query": "zzzz",
                "query_en": "banana",
                "model": "test-model",
                "limit": 5,
                "k": 60,
                "base_url": "https://example.com/v1",
                "json": True,
            },
        )()

        from unittest.mock import patch

        buf = io.StringIO()
        with patch("openclaw_mem.cli._get_api_key", return_value="test-key"), patch("openclaw_mem.cli.OpenAIEmbeddingsClient", _FakeEmbedClient):
            with redirect_stdout(buf):
                cmd_hybrid(conn, args)

        out = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0]["id"], 2)
        self.assertIn("vector_en", out[0]["match"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
