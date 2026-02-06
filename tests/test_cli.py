import io
import json
import sys
import unittest
from contextlib import redirect_stdout

from openclaw_mem.cli import _connect, cmd_ingest, cmd_search, cmd_get, cmd_timeline, cmd_triage


class TestCliM0(unittest.TestCase):
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

        args = type(
            "Args",
            (),
            {
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
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
        self.assertGreaterEqual(out["observations"]["found"], 1)

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
        args = type(
            "Args",
            (),
            {
                "mode": "cron-errors",
                "since_minutes": 60,
                "limit": 10,
                "keywords": None,
                "cron_jobs_path": tmp_path,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cmd_triage(conn, args)
        self.assertEqual(cm.exception.code, 10)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["cron"]["found"], 1)
        self.assertEqual(out["cron"]["matches"][0]["id"], "job2")

        conn.close()


if __name__ == "__main__":
    unittest.main()
