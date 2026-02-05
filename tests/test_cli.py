import io
import json
import sys
import unittest
from contextlib import redirect_stdout

from openclaw_mem.cli import _connect, cmd_ingest, cmd_search, cmd_get, cmd_timeline


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


if __name__ == "__main__":
    unittest.main()
