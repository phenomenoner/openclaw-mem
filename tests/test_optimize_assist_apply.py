import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_assist_apply


class TestOptimizeAssistApply(unittest.TestCase):
    def test_optimize_parser_parses_assist_apply_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "assist-apply",
                "--from-file",
                "/tmp/governor.json",
                "--operator",
                "lyria",
                "--lane",
                "observations.assist",
                "--run-dir",
                "/tmp/assist-runs",
                "--max-rows-per-run",
                "3",
                "--max-rows-per-24h",
                "9",
                "--max-importance-adjustments-per-run",
                "2",
                "--max-importance-adjustments-per-24h",
                "7",
                "--dry-run",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "assist-apply")
        self.assertEqual(args.from_file, "/tmp/governor.json")
        self.assertEqual(args.operator, "lyria")
        self.assertEqual(args.lane, "observations.assist")
        self.assertEqual(args.run_dir, "/tmp/assist-runs")
        self.assertEqual(args.max_rows_per_run, 3)
        self.assertEqual(args.max_rows_per_24h, 9)
        self.assertEqual(args.max_importance_adjustments_per_run, 2)
        self.assertEqual(args.max_importance_adjustments_per_24h, 7)
        self.assertTrue(args.dry_run)

    def test_assist_apply_updates_importance_score_and_label(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.52, "label": "nice_to_have"}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"importance-downshift-{obs_id}",
                    "recommended_action": "adjust_importance_score",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"importance": {"score": 0.42, "label": "ignore", "delta": -0.1, "reason_code": "stale_pressure"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["result"], "applied")
            self.assertEqual(out["applied_rows"], 1)
            self.assertEqual(out["applied_action_counts"]["adjust_importance_score"], 1)
            self.assertTrue(any(x["path"] == "/importance/score" for x in out["diff_summary"]))
            self.assertTrue(any(x["path"] == "/importance/label" for x in out["diff_summary"]))
            self.assertTrue(Path(out["artifacts"]["effect_ref"]).exists())
            effect = json.loads(Path(out["artifacts"]["effect_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(effect["kind"], "openclaw-mem.optimize.assist.effect-batch.v0")
            self.assertEqual(effect["items"][0]["effect_summary"], "insufficient_data")

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail = json.loads(row["detail_json"])
        self.assertEqual(detail["importance"]["score"], 0.42)
        self.assertEqual(detail["importance"]["label"], "ignore")
        self.assertEqual(detail["importance"]["method"], "optimize_assist")
        self.assertEqual(detail["optimization"]["assist"]["effect"]["effect_summary"], "insufficient_data")
        conn.close()

    def test_assist_apply_dry_run_emits_receipts_and_skips_write(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.32}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"stale-candidate-{obs_id}",
                    "recommended_action": "set_stale_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": True,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["kind"], "openclaw-mem.optimize.assist.after.v1")
            self.assertEqual(out["result"], "dry_run")
            self.assertEqual(out["applied_rows"], 0)
            self.assertEqual(out["skipped_rows"], 1)
            self.assertTrue(Path(out["artifacts"]["before_ref"]).exists())
            self.assertTrue(Path(out["artifacts"]["after_ref"]).exists())
            self.assertTrue(Path(out["artifacts"]["rollback_ref"]).exists())
            self.assertTrue(Path(out["artifacts"]["effect_ref"]).exists())

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail = json.loads(row["detail_json"])
        self.assertNotIn("lifecycle", detail)
        conn.close()

    def test_assist_apply_updates_observation_detail_json(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.32}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"stale-candidate-{obs_id}",
                    "recommended_action": "set_stale_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["result"], "applied")
            self.assertEqual(out["applied_rows"], 1)
            self.assertEqual(len(out["diff_summary"]), 2)

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail = json.loads(row["detail_json"])
        self.assertTrue(detail["lifecycle"]["stale_candidate"])
        self.assertEqual(detail["lifecycle"]["stale_reason_code"], "age_threshold")
        self.assertEqual(detail["optimization"]["assist"]["proposal_id"], f"stale-candidate-{obs_id}")
        conn.close()

    def test_assist_apply_blocks_second_attempt_for_same_packet(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.32}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"stale-candidate-{obs_id}",
                    "recommended_action": "set_stale_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": True,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                cmd_optimize_assist_apply(conn, args)
            second_buf = io.StringIO()
            with redirect_stdout(second_buf):
                cmd_optimize_assist_apply(conn, args)

            first = json.loads(first_buf.getvalue())
            second = json.loads(second_buf.getvalue())

        self.assertEqual(first["result"], "dry_run")
        self.assertEqual(second["result"], "aborted")
        self.assertIn("max_retries_per_packet_exceeded", second["blocked_by_caps"])
        conn.close()

    def test_assist_apply_blocks_when_importance_family_cap_is_exceeded(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_ids = [
            _insert_observation(
                conn,
                {
                    "ts": stale_ts,
                    "kind": "note",
                    "tool_name": "memory_store",
                    "summary": f"Candidate memory {i}",
                    "detail": {"scope": "team/alpha", "importance": {"score": 0.42, "label": "ignore"}},
                },
            )
            for i in range(4)
        ]
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"importance-downshift-{obs_id}",
                    "recommended_action": "adjust_importance_score",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"importance": {"score": 0.32, "label": "ignore", "delta": -0.1, "reason_code": "stale_pressure"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
                for obs_id in obs_ids
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "max_importance_adjustments_per_run": 3,
                    "max_importance_adjustments_per_24h": 10,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())

        self.assertEqual(out["result"], "aborted")
        self.assertIn("max_importance_adjustments_per_run_exceeded", out["blocked_by_caps"])
        self.assertEqual(out["applied_action_counts"]["adjust_importance_score"], 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
