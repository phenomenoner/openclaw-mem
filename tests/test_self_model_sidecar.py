import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser


class TestSelfModelSidecarCli(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _connect(":memory:")
        self.conn.execute(
            "INSERT INTO observations (ts, kind, summary, summary_en, lang, tool_name, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-04-18T08:00:00Z",
                "conversation.user",
                "Ship the additive side-car, keep topology unchanged, and avoid anthropomorphism.",
                "",
                "en",
                "message",
                json.dumps({"scope": "proj-a", "session_id": "s1", "role": "engineer operator"}),
            ),
        )
        self.conn.execute(
            "INSERT INTO episodic_events (event_id, ts_ms, scope, session_id, agent_id, type, summary, payload_json, refs_json, redacted, schema_version, created_at, search_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "evt-1",
                1713427200000,
                "proj-a",
                "s1",
                "lyria",
                "conversation.assistant",
                "Use receipts, verifier checks, and release controls.",
                json.dumps({"goal": "ship_mvp", "style": "direct warm concise", "stance": "Nuwa is prior only"}),
                "[]",
                0,
                "v0",
                "2026-04-18T08:05:00Z",
                "Use receipts, verifier checks, and release controls.",
            ),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _run(self, argv):
        args = build_parser().parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            args.func(self.conn, args)
        return json.loads(buf.getvalue())

    def test_parser_continuity_current(self):
        args = build_parser().parse_args(["continuity", "current", "--json"])
        self.assertEqual(args.cmd, "continuity")
        self.assertEqual(args.self_cmd, "current")

        alias = build_parser().parse_args(["self", "current", "--json"])
        self.assertEqual(alias.cmd, "self")
        self.assertEqual(alias.self_cmd, "current")

    def test_current_persist_and_attachment_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            persona_path = Path(tmp) / "persona.json"
            persona_path.write_text(
                json.dumps(
                    {
                        "roles": {"engineer": 1.0, "operator": 0.8},
                        "goals": {"ship_mvp": 1.0},
                        "stances": {"sidecar_only": 1.0},
                        "style_commitments": {"evidence_first": 1.0},
                    }
                ),
                encoding="utf-8",
            )
            current = self._run(
                [
                    "continuity",
                    "current",
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--persona-file",
                    str(persona_path),
                    "--run-dir",
                    tmp,
                    "--persist",
                    "--json",
                ]
            )
            self.assertEqual(current["schema"], "openclaw-mem.self-model.snapshot.v0")
            self.assertIn("role:engineer", current["roles"])
            self.assertIn("goal:ship_mvp", current["goals"])
            self.assertTrue(current["evidence_summary"]["derived"])
            self.assertTrue(current["evidence_summary"]["non_authoritative"])
            self.assertEqual(current["evidence_summary"]["operator_surface"], "continuity")
            snapshot_path = current["persisted"]["snapshot_path"]
            amap = self._run(["continuity", "attachment-map", "--snapshot", snapshot_path, "--json"])
            self.assertEqual(amap["schema"], "openclaw-mem.self-model.attachment-map.v0")
            self.assertGreaterEqual(amap["counts"]["goal"], 1)

    def test_release_diff_and_compare_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "baseline.json"
            baseline.write_text(json.dumps({"style_commitments": {"warm": 1.0}}), encoding="utf-8")
            candidate = Path(tmp) / "candidate.json"
            candidate.write_text(json.dumps({"style_commitments": {"concise": 1.0}, "goals": {"verify": 1.0}}), encoding="utf-8")

            before = self._run(["continuity", "current", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--persist", "--json"])
            release = self._run(
                [
                    "continuity",
                    "release",
                    "--run-dir",
                    tmp,
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--stance",
                    "goal:ship_mvp",
                    "--reason",
                    "testing weakening flow",
                    "--mode",
                    "weaken",
                    "--factor",
                    "0.2",
                    "--json",
                ]
            )
            self.assertEqual(release["schema"], "openclaw-mem.self-model.release-receipt.v0")
            self.assertEqual(release["scope"], "proj-a")
            self.assertEqual(release["session_id"], "s1")
            after = self._run(["continuity", "current", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--persist", "--json"])
            diff = self._run(["continuity", "diff", "--from", before["persisted"]["snapshot_path"], "--to", after["persisted"]["snapshot_path"], "--json"])
            self.assertEqual(diff["schema"], "openclaw-mem.self-model.diff.v0")
            changed_ids = {item["id"] for item in diff["changed"]}
            self.assertIn("goal:ship_mvp", changed_ids)

            compare = self._run(
                [
                    "continuity",
                    "compare-migration",
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--run-dir",
                    tmp,
                    "--baseline-persona-file",
                    str(baseline),
                    "--candidate-persona-file",
                    str(candidate),
                    "--persist",
                    "--json",
                ]
            )
            self.assertEqual(compare["schema"], "openclaw-mem.self-model.compare-migration.v0")
            self.assertNotIn("latest_path", compare["baseline_paths"])
            self.assertNotIn("latest_path", compare["candidate_paths"])
            self.assertGreaterEqual(compare["diff"]["summary"]["changed"] + compare["diff"]["summary"]["added"], 1)

            threat = self._run(["continuity", "threat-feed", "--snapshot", after["persisted"]["snapshot_path"], "--json"])
            self.assertEqual(threat["schema"], "openclaw-mem.self-model.threat-feed.v0")

            enabled = self._run(["continuity", "enable", "--run-dir", tmp, "--cadence-seconds", "60", "--json"])
            self.assertTrue(enabled["enabled"])
            status = self._run(["continuity", "status", "--run-dir", tmp, "--json"])
            self.assertTrue(status["control"]["enabled"])
            autorun = self._run(["continuity", "auto-run", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--cycles", "1", "--json"])
            self.assertTrue(autorun["ok"])
            self.assertEqual(len(autorun["runs"]), 1)
            disabled = self._run(["continuity", "disable", "--run-dir", tmp, "--json"])
            self.assertFalse(disabled["enabled"])


if __name__ == "__main__":
    unittest.main()
