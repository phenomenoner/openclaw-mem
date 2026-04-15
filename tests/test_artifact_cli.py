import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser


class TestArtifactCli(unittest.TestCase):
    @contextlib.contextmanager
    def _state_dir(self, value: str):
        old = os.environ.get("OPENCLAW_STATE_DIR")
        os.environ["OPENCLAW_STATE_DIR"] = value
        try:
            yield
        finally:
            if old is None:
                os.environ.pop("OPENCLAW_STATE_DIR", None)
            else:
                os.environ["OPENCLAW_STATE_DIR"] = old

    def _assert_exact_keys(self, payload: dict, expected: set[str], label: str):
        actual = set(payload.keys())
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            self.fail(f"{label} keys drifted: missing={missing} extra={extra}")

    def test_artifact_cli_commands_emit_stable_json_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            conn = _connect(":memory:")
            src = Path(td) / "artifact-source.txt"
            text = "A" * 500 + "\n" + "B" * 500
            src.write_text(text, encoding="utf-8")

            with self._state_dir(td):
                stash_args = build_parser().parse_args(
                    [
                        "artifact",
                        "stash",
                        "--from",
                        str(src),
                        "--kind",
                        "tool_output",
                        '--meta-json',
                        '{"step":"contract-test","scope":"cli"}',
                    ]
                )
                out_buf = io.StringIO()
                with contextlib.redirect_stdout(out_buf):
                    stash_args.func(conn, stash_args)

                stash_out = json.loads(out_buf.getvalue())
                self.assertEqual(stash_out["schema"], "openclaw-mem.artifact.stash.v1")
                self.assertEqual(stash_out["kind"], "tool_output")
                self._assert_exact_keys(
                    stash_out,
                    {"schema", "handle", "sha256", "bytes", "createdAt", "kind", "meta"},
                    "artifact.stash",
                )
                self.assertEqual(stash_out["meta"], {"step": "contract-test", "scope": "cli"})
                self.assertEqual(stash_out["bytes"], len(text.encode("utf-8")))

                handle = stash_out["handle"]

                fetch_args = build_parser().parse_args(["artifact", "fetch", handle, "--max-chars", "12", "--mode", "headtail"])
                fetch_buf = io.StringIO()
                with contextlib.redirect_stdout(fetch_buf):
                    fetch_args.func(conn, fetch_args)

                fetch_out = json.loads(fetch_buf.getvalue())
                self.assertEqual(fetch_out["schema"], "openclaw-mem.artifact.fetch.v1")
                self.assertEqual(fetch_out["handle"], handle)
                self.assertEqual(fetch_out["selector"], {"mode": "headtail", "maxChars": 12})
                self.assertLessEqual(len(fetch_out["text"]), 12)
                self._assert_exact_keys(
                    fetch_out,
                    {"schema", "handle", "selector", "text"},
                    "artifact.fetch",
                )

                peek_args = build_parser().parse_args(["artifact", "peek", handle, "--preview-chars", "20"])
                peek_buf = io.StringIO()
                with contextlib.redirect_stdout(peek_buf):
                    peek_args.func(conn, peek_args)

                peek_out = json.loads(peek_buf.getvalue())
                self.assertEqual(peek_out["schema"], "openclaw-mem.artifact.peek.v1")
                self.assertEqual(peek_out["handle"], handle)
                self.assertLessEqual(len(peek_out["preview"]), 20)
                self.assertEqual(peek_out["previewChars"], 20)
                self._assert_exact_keys(
                    peek_out,
                    {
                        "schema",
                        "handle",
                        "sha256",
                        "bytes",
                        "createdAt",
                        "kind",
                        "compression",
                        "meta",
                        "preview",
                        "previewChars",
                    },
                    "artifact.peek",
                )

                compact_args = build_parser().parse_args(
                    [
                        "artifact",
                        "compact-receipt",
                        "--command",
                        "git status",
                        "--rewritten-command",
                        "rtk git status",
                        "--tool",
                        "rtk",
                        "--compact-text",
                        "ok main",
                        "--raw-handle",
                        handle,
                        "--meta-json",
                        '{"scope":"cli","mode":"sideband"}',
                    ]
                )
                compact_buf = io.StringIO()
                with contextlib.redirect_stdout(compact_buf):
                    compact_args.func(conn, compact_args)

                compact_out = json.loads(compact_buf.getvalue())
                self.assertEqual(compact_out["schema"], "openclaw-mem.artifact.compaction-receipt.v1")
                self.assertEqual(compact_out["mode"], "sideband")
                self.assertEqual(compact_out["family"], "generic")
                self.assertEqual(compact_out["tool"], "rtk")
                self.assertEqual(compact_out["command"], "git status")
                self.assertEqual(compact_out["rewrittenCommand"], "rtk git status")
                self.assertEqual(compact_out["rawArtifact"]["handle"], handle)
                self.assertEqual(compact_out["compact"], {"text": "ok main", "bytes": len("ok main".encode("utf-8"))})
                self.assertEqual(compact_out["meta"], {"scope": "cli", "mode": "sideband"})
                self._assert_exact_keys(
                    compact_out,
                    {"schema", "createdAt", "mode", "family", "tool", "command", "rewrittenCommand", "rawArtifact", "compact", "meta"},
                    "artifact.compact-receipt",
                )

                rehydrate_args = build_parser().parse_args(
                    [
                        "artifact",
                        "rehydrate",
                        "--receipt-json",
                        compact_buf.getvalue(),
                        "--max-chars",
                        "18",
                    ]
                )
                rehydrate_buf = io.StringIO()
                with contextlib.redirect_stdout(rehydrate_buf):
                    rehydrate_args.func(conn, rehydrate_args)
                rehydrate_out = json.loads(rehydrate_buf.getvalue())
                self.assertEqual(rehydrate_out["schema"], "openclaw-mem.artifact.rehydrate.v1")
                self.assertEqual(rehydrate_out["handle"], handle)
                self.assertEqual(rehydrate_out["selector"], {"mode": "headtail", "maxChars": 18})
                self.assertLessEqual(len(rehydrate_out["text"]), 18)
                self._assert_exact_keys(
                    rehydrate_out,
                    {"schema", "handle", "selector", "artifact", "text"},
                    "artifact.rehydrate",
                )

                nojson_args = build_parser().parse_args(["artifact", "fetch", "--no-json", handle, "--max-chars", "16"])
                nojson_buf = io.StringIO()
                with contextlib.redirect_stdout(nojson_buf):
                    nojson_args.func(conn, nojson_args)
                self.assertLessEqual(len(nojson_buf.getvalue()), 16)

            conn.close()

    def test_artifact_cli_invalid_handle_exits_with_error(self):
        conn = _connect(":memory:")
        bad = build_parser().parse_args(["artifact", "fetch", "bad-handle", "--json"])
        bad_buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with contextlib.redirect_stdout(bad_buf):
                bad.func(conn, bad)
        self.assertEqual(cm.exception.code, 2)
        bad_out = json.loads(bad_buf.getvalue())
        self.assertIn("invalid", bad_out["error"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
