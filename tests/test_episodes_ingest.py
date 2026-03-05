import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser


class TestEpisodesIngestCli(unittest.TestCase):
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

    @staticmethod
    def _event(*, event_id: str, ts_ms: int, session_id: str, event_type: str = "tool.result", payload=None):
        out = {
            "schema": "openclaw-mem.episodes.spool.v0",
            "event_id": event_id,
            "ts_ms": ts_ms,
            "scope": "proj-ingest",
            "session_id": session_id,
            "agent_id": "worker",
            "type": event_type,
            "summary": f"event {event_id}",
        }
        if payload is not None:
            out["payload"] = payload
        return out

    def test_episodes_ingest_offset_state_and_partial_line(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "episodes.jsonl"
            state = Path(td) / "state.json"

            l1 = json.dumps(self._event(event_id="ev-1", ts_ms=1000, session_id="s1"), ensure_ascii=False)
            l2 = json.dumps(self._event(event_id="ev-2", ts_ms=2000, session_id="s1"), ensure_ascii=False)
            spool.write_text(f"{l1}\n{l2}", encoding="utf-8")  # second line intentionally has no trailing newline

            first = self._run(
                conn,
                [
                    "episodes",
                    "ingest",
                    "--file",
                    str(spool),
                    "--state",
                    str(state),
                    "--json",
                ],
            )
            self.assertEqual(first["inserted"], 1)
            self.assertEqual(first["source"]["trailing_partial_bytes"] > 0, True)

            # finish partial line + append one more complete line
            l3 = json.dumps(self._event(event_id="ev-3", ts_ms=3000, session_id="s1"), ensure_ascii=False)
            with spool.open("a", encoding="utf-8") as fp:
                fp.write("\n")
                fp.write(f"{l3}\n")

            second = self._run(
                conn,
                [
                    "episodes",
                    "ingest",
                    "--file",
                    str(spool),
                    "--state",
                    str(state),
                    "--json",
                ],
            )
            self.assertEqual(second["inserted"], 2)

            out = self._run(
                conn,
                ["episodes", "query", "--scope", "proj-ingest", "--session-id", "s1", "--json"],
            )
            self.assertEqual([x["event_id"] for x in out["items"]], ["ev-1", "ev-2", "ev-3"])
        conn.close()

    def test_episodes_ingest_skips_invalid_json_lines(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "episodes.jsonl"
            state = Path(td) / "state.json"
            l1 = json.dumps(self._event(event_id="ok-1", ts_ms=1000, session_id="s2"), ensure_ascii=False)
            l2 = "{not-json"
            l3 = json.dumps(self._event(event_id="ok-2", ts_ms=1001, session_id="s2"), ensure_ascii=False)
            spool.write_text(f"{l1}\n{l2}\n{l3}\n", encoding="utf-8")

            receipt = self._run(
                conn,
                [
                    "episodes",
                    "ingest",
                    "--file",
                    str(spool),
                    "--state",
                    str(state),
                    "--json",
                ],
            )
            self.assertEqual(receipt["inserted"], 2)
            self.assertEqual(receipt["lines"]["invalid_json"], 1)

            out = self._run(
                conn,
                ["episodes", "query", "--scope", "proj-ingest", "--session-id", "s2", "--json"],
            )
            self.assertEqual(out["count"], 2)
        conn.close()

    def test_episodes_ingest_bounds_large_payload(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "episodes.jsonl"
            state = Path(td) / "state.json"
            huge = "x" * 20000
            line = json.dumps(
                self._event(event_id="big-1", ts_ms=1234, session_id="s3", payload={"blob": huge}),
                ensure_ascii=False,
            )
            spool.write_text(f"{line}\n", encoding="utf-8")

            receipt = self._run(
                conn,
                [
                    "episodes",
                    "ingest",
                    "--file",
                    str(spool),
                    "--state",
                    str(state),
                    "--payload-cap-bytes",
                    "1024",
                    "--json",
                ],
            )
            self.assertEqual(receipt["inserted"], 1)

            row = conn.execute(
                "SELECT payload_json FROM episodic_events WHERE event_id = ?",
                ("big-1",),
            ).fetchone()
            self.assertIsNotNone(row)
            payload = json.loads(str(row["payload_json"]))
            if isinstance(payload, dict) and payload.get("_truncated"):
                self.assertTrue(payload["_truncated"])
            else:
                self.assertLessEqual(len(str(payload.get("blob", ""))), 321)
            self.assertLessEqual(len(str(row["payload_json"]).encode("utf-8")), 1024)
        conn.close()

    def test_episodes_ingest_deterministic_ordering(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "episodes.jsonl"
            state = Path(td) / "state.json"
            rows = [
                self._event(event_id="ev-1", ts_ms=2000, session_id="s4", event_type="tool.call"),
                self._event(event_id="ev-2", ts_ms=1000, session_id="s4", event_type="tool.result"),
                self._event(event_id="ev-3", ts_ms=2000, session_id="s4", event_type="ops.alert"),
            ]
            spool.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

            self._run(
                conn,
                [
                    "episodes",
                    "ingest",
                    "--file",
                    str(spool),
                    "--state",
                    str(state),
                    "--json",
                ],
            )

            out = self._run(
                conn,
                ["episodes", "query", "--scope", "proj-ingest", "--session-id", "s4", "--json"],
            )
            self.assertEqual([x["event_id"] for x in out["items"]], ["ev-2", "ev-1", "ev-3"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
