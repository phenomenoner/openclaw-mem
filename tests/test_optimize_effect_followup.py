import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_effect_followup


class TestOptimizeEffectFollowup(unittest.TestCase):
    def test_optimize_parser_parses_effect_followup_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "effect-followup",
                "--from-file",
                "/tmp/effect.json",
                "--lifecycle-limit",
                "80",
                "--top",
                "7",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "effect-followup")
        self.assertEqual(args.from_file, "/tmp/effect.json")
        self.assertEqual(args.lifecycle_limit, 80)
        self.assertEqual(args.top, 7)

    def test_effect_followup_marks_importance_adjustment_improved_when_score_holds(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.42, "label": "ignore"}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.assist.effect-batch.v0",
            "items": [
                {
                    "kind": "openclaw-mem.optimize.assist.effect.v0",
                    "proposal_id": f"importance-downshift-{obs_id}",
                    "observation_id": obs_id,
                    "effect_window": "24h",
                    "baseline_signals": {
                        "recent_use_count": 0,
                        "current_score": 0.52,
                        "next_score": 0.42,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "effect.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "lifecycle_limit": 50,
                    "top": 10,
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_effect_followup(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.effect-followup.v0")
        self.assertEqual(out["counts"]["improved"], 1)
        self.assertEqual(out["items"][0]["effect_summary"], "improved")
        self.assertEqual(out["items"][0]["quality_delta"]["score_delta_vs_followup_target"], 0.0)
        conn.close()

    def test_effect_followup_marks_stale_candidate_regressed_when_recent_use_resurfaces(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.32}, "lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
            },
        )
        conn.execute(
            """
            INSERT INTO pack_lifecycle_shadow_log (
                ts, query_hash, selection_signature, selected_count, citation_count, candidate_count, receipt_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "sha256:q",
                "sel-1",
                1,
                1,
                1,
                json.dumps({"selection": {"pack_selected_refs": [f"obs:{obs_id}"], "selection_signature": "sel-1"}}),
            ),
        )
        conn.commit()
        packet = {
            "kind": "openclaw-mem.optimize.assist.effect-batch.v0",
            "items": [
                {
                    "kind": "openclaw-mem.optimize.assist.effect.v0",
                    "proposal_id": f"stale-candidate-{obs_id}",
                    "observation_id": obs_id,
                    "effect_window": "24h",
                    "baseline_signals": {
                        "recent_use_count": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "effect.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "lifecycle_limit": 50,
                    "top": 10,
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_effect_followup(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["counts"]["regressed"], 1)
        self.assertEqual(out["items"][0]["effect_summary"], "regressed")
        self.assertEqual(out["items"][0]["quality_delta"]["recent_use_count"], 1)
        conn.close()

    def test_effect_followup_tracks_soft_archive_family_as_neutral_when_archive_persists(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        archived_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Soft-archived candidate memory",
                "detail": {
                    "scope": "team/alpha",
                    "importance": {"score": 0.18, "label": "ignore"},
                    "lifecycle": {
                        "soft_archive_candidate": True,
                        "archived_at": archived_at,
                        "archive_reason_code": "stale_low_importance",
                    },
                },
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.assist.effect-batch.v0",
            "items": [
                {
                    "kind": "openclaw-mem.optimize.assist.effect.v0",
                    "proposal_id": f"soft-archive-candidate-{obs_id}",
                    "observation_id": obs_id,
                    "effect_window": "24h",
                    "baseline_signals": {
                        "recent_use_count": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "effect.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "lifecycle_limit": 50,
                    "top": 10,
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_effect_followup(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["counts"]["neutral"], 1)
        self.assertEqual(out["items"][0]["family"], "set_soft_archive_candidate")
        self.assertEqual(out["items"][0]["effect_summary"], "neutral")
        self.assertIn("soft_archive_persisted_without_recent_use", out["items"][0]["reasons"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
