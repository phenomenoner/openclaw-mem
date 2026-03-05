import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser


class TestEpisodesExtractSessionsCli(unittest.TestCase):
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
    def _session_line(*, ts: str, role: str, text: str, session_key: str = "sess-1", agent_id: str = "main"):
        return {
            "timestamp": ts,
            "sessionKey": session_key,
            "agentId": agent_id,
            "message": {
                "role": role,
                "content": [{"type": "text", "text": text}],
            },
        }

    def test_extract_sessions_scope_and_pii_redaction_with_summary_only_default(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sessions_root = root / "sessions"
            sessions_root.mkdir(parents=True, exist_ok=True)
            session_file = sessions_root / "thread-1.jsonl"
            spool = root / "episodes.jsonl"
            extract_state = root / "extract-state.json"
            ingest_state = root / "ingest-state.json"

            lines = [
                self._session_line(
                    ts="2026-03-05T00:00:00Z",
                    role="user",
                    text="[SCOPE: proj-x] my email is test@example.com",
                ),
                self._session_line(
                    ts="2026-03-05T00:00:01Z",
                    role="assistant",
                    text="[SCOPE: proj-x] call me at +1 (555) 222-3333",
                ),
            ]
            session_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")

            extract_out = self._run(
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
            self.assertEqual(extract_out["emitted"], 2)

            ingest_out = self._run(
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
            self.assertEqual(ingest_out["inserted"], 2)

            q_default = self._run(
                conn,
                ["episodes", "query", "--scope", "proj-x", "--session-id", "sess-1", "--json"],
            )
            self.assertEqual(q_default["count"], 2)
            self.assertNotIn("payload", q_default["items"][0])

            q_payload = self._run(
                conn,
                [
                    "episodes",
                    "query",
                    "--scope",
                    "proj-x",
                    "--session-id",
                    "sess-1",
                    "--include-payload",
                    "--json",
                ],
            )
            payload_texts = []
            for item in q_payload["items"]:
                payload = item.get("payload")
                self.assertIsInstance(payload, dict)
                payload_texts.append(str(payload.get("text", "")))
            joined = "\n".join(payload_texts)
            self.assertIn("[REDACTED_EMAIL]", joined)
            self.assertIn("[REDACTED_PHONE]", joined)

        conn.close()

    def test_extract_sessions_secret_or_tool_dump_marks_redacted_and_null_payload(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sessions_root = root / "sessions"
            sessions_root.mkdir(parents=True, exist_ok=True)
            session_file = sessions_root / "thread-2.jsonl"
            spool = root / "episodes.jsonl"
            extract_state = root / "extract-state.json"
            ingest_state = root / "ingest-state.json"

            lines = [
                self._session_line(
                    ts="2026-03-05T00:10:00Z",
                    role="user",
                    text="[SCOPE: proj-y] password=abc123456",
                    session_key="sess-2",
                ),
                self._session_line(
                    ts="2026-03-05T00:10:01Z",
                    role="assistant",
                    text="[SCOPE: proj-y] ```json\n{\"stdout\":\"hello\"}\n```",
                    session_key="sess-2",
                ),
            ]
            session_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")

            extract_out = self._run(
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
            self.assertEqual(extract_out["payload_redacted"], 2)

            ingest_out = self._run(
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
            self.assertEqual(ingest_out["inserted"], 2)

            q_payload = self._run(
                conn,
                [
                    "episodes",
                    "query",
                    "--scope",
                    "proj-y",
                    "--session-id",
                    "sess-2",
                    "--include-payload",
                    "--json",
                ],
            )
            self.assertEqual(q_payload["count"], 2)
            for item in q_payload["items"]:
                self.assertTrue(item["redacted"])
                self.assertIsNone(item["payload"])

        conn.close()

    def test_extract_sessions_truncates_large_payload_by_cap(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sessions_root = root / "sessions"
            sessions_root.mkdir(parents=True, exist_ok=True)
            session_file = sessions_root / "thread-3.jsonl"
            spool = root / "episodes.jsonl"
            extract_state = root / "extract-state.json"
            ingest_state = root / "ingest-state.json"

            huge = "x" * 12000
            lines = [
                self._session_line(
                    ts="2026-03-05T01:00:00Z",
                    role="assistant",
                    text=f"[SCOPE: proj-z] {huge}",
                    session_key="sess-3",
                )
            ]
            session_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")

            extract_out = self._run(
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
                    "--payload-cap-bytes",
                    "1024",
                    "--json",
                ],
            )
            self.assertEqual(extract_out["payload_truncated"], 1)

            ingest_out = self._run(
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
            self.assertEqual(ingest_out["inserted"], 1)

            q_payload = self._run(
                conn,
                [
                    "episodes",
                    "query",
                    "--scope",
                    "proj-z",
                    "--session-id",
                    "sess-3",
                    "--include-payload",
                    "--json",
                ],
            )
            payload = q_payload["items"][0]["payload"]
            self.assertIsInstance(payload, dict)
            self.assertTrue(payload.get("_truncated"))

            row = conn.execute(
                "SELECT LENGTH(CAST(payload_json AS BLOB)) AS n FROM episodic_events WHERE scope = ? AND session_id = ?",
                ("proj-z", "sess-3"),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertLessEqual(int(row["n"]), 1024)

        conn.close()


if __name__ == "__main__":
    unittest.main()
