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
    def _event(
        *,
        event_id: str,
        ts_ms: int,
        session_id: str,
        event_type: str = "tool.result",
        payload=None,
        scope: str | None = "proj-ingest",
        summary: str | None = None,
    ):
        out = {
            "schema": "openclaw-mem.episodes.spool.v0",
            "event_id": event_id,
            "ts_ms": ts_ms,
            "session_id": session_id,
            "agent_id": "worker",
            "type": event_type,
            "summary": summary or f"event {event_id}",
        }
        if scope is not None:
            out["scope"] = scope
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

    def test_episodes_ingest_scope_derivation_from_summary_tag_or_global_default(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "episodes.jsonl"
            state = Path(td) / "state.json"
            rows = [
                self._event(
                    event_id="scope-1",
                    ts_ms=1000,
                    session_id="s-scope",
                    event_type="conversation.user",
                    scope=None,
                    summary="[SCOPE: Alpha/Beta] hello world",
                    payload={"text": "[SCOPE: Alpha/Beta] hello world"},
                ),
                self._event(
                    event_id="scope-2",
                    ts_ms=1001,
                    session_id="s-scope",
                    event_type="conversation.assistant",
                    scope=None,
                    summary="no explicit scope",
                    payload={"text": "plain"},
                ),
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

            alpha = self._run(
                conn,
                ["episodes", "query", "--scope", "alpha/beta", "--session-id", "s-scope", "--json"],
            )
            self.assertEqual(alpha["count"], 1)
            self.assertEqual(alpha["items"][0]["event_id"], "scope-1")

            global_rows = self._run(
                conn,
                ["episodes", "query", "--global", "--session-id", "s-scope", "--json"],
            )
            self.assertEqual(global_rows["count"], 1)
            self.assertEqual(global_rows["items"][0]["event_id"], "scope-2")
        conn.close()

    def test_episodes_ingest_second_pass_redacts_late_pii_payload(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "episodes.jsonl"
            state = Path(td) / "state.json"
            row = self._event(
                event_id="pii-1",
                ts_ms=1000,
                session_id="s-pii",
                event_type="conversation.user",
                scope="proj-ingest",
                summary="user shared contact",
                payload={"phone_number": 886912345678, "text": "reach me"},
            )
            spool.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

            receipt = self._run(
                conn,
                ["episodes", "ingest", "--file", str(spool), "--state", str(state), "--json"],
            )
            self.assertEqual(receipt["inserted"], 1)
            self.assertEqual(receipt["bounded"]["redacted_late"], 1)

            got = self._run(
                conn,
                [
                    "episodes",
                    "query",
                    "--scope",
                    "proj-ingest",
                    "--session-id",
                    "s-pii",
                    "--include-payload",
                    "--json",
                ],
            )
            self.assertEqual(got["count"], 1)
            self.assertTrue(got["items"][0]["redacted"])
            self.assertIsNone(got["items"][0]["payload"])
        conn.close()

    def test_episodes_ingest_second_pass_redacts_refs_also(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "episodes.jsonl"
            state = Path(td) / "state.json"
            row = self._event(
                event_id="refs-pii-1",
                ts_ms=1000,
                session_id="s-refs",
                event_type="conversation.assistant",
                scope="proj-ingest",
                summary="assistant response",
                payload={"text": "safe"},
            )
            row["refs"] = {"source": "x", "contact_number": 886912345678}
            spool.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

            receipt = self._run(
                conn,
                ["episodes", "ingest", "--file", str(spool), "--state", str(state), "--json"],
            )
            self.assertEqual(receipt["inserted"], 1)
            self.assertEqual(receipt["bounded"]["redacted_late"], 1)

            got = self._run(
                conn,
                [
                    "episodes",
                    "query",
                    "--scope",
                    "proj-ingest",
                    "--session-id",
                    "s-refs",
                    "--include-payload",
                    "--json",
                ],
            )
            self.assertEqual(got["count"], 1)
            self.assertTrue(got["items"][0]["redacted"])
            self.assertIsNone(got["items"][0]["payload"])
            self.assertIsNone(got["items"][0]["refs"])
        conn.close()

    def test_episodes_extract_sessions_fallback_generates_conversation_spool(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            sessions_root = Path(td) / "sessions"
            sessions_root.mkdir(parents=True)
            session_file = sessions_root / "s1.jsonl"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps({"ts_ms": 1000, "sessionKey": "sess-1", "agentId": "a", "role": "user", "content": "[SCOPE: demo] hi"}, ensure_ascii=False),
                        json.dumps({"ts_ms": 1001, "sessionKey": "sess-1", "agentId": "a", "role": "assistant", "content": [{"type": "text", "text": "hello"}]}, ensure_ascii=False),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            spool = Path(td) / "episodes.jsonl"
            extract_state = Path(td) / "extract-state.json"
            ingest_state = Path(td) / "ingest-state.json"

            extract_receipt = self._run(
                conn,
                [
                    "episodes",
                    "extract-sessions",
                    "--sessions-root",
                    str(sessions_root),
                    "--file",
                    str(spool),
                    "--state",
                    str(extract_state),
                    "--json",
                ],
            )
            self.assertEqual(extract_receipt["emitted"], 2)

            ingest_receipt = self._run(
                conn,
                [
                    "episodes",
                    "ingest",
                    "--file",
                    str(spool),
                    "--state",
                    str(ingest_state),
                    "--json",
                ],
            )
            self.assertEqual(ingest_receipt["inserted"], 2)

            convo = self._run(
                conn,
                ["episodes", "query", "--scope", "demo", "--session-id", "sess-1", "--json"],
            )
            self.assertEqual(convo["count"], 1)
            self.assertEqual(convo["items"][0]["type"], "conversation.user")

            convo_global = self._run(
                conn,
                ["episodes", "query", "--global", "--session-id", "sess-1", "--json"],
            )
            self.assertEqual(convo_global["count"], 1)
            self.assertEqual(convo_global["items"][0]["type"], "conversation.assistant")
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
