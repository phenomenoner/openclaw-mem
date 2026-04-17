import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_assist_apply, cmd_optimize_verifier_bundle


class TestOptimizeVerifierBundle(unittest.TestCase):
    def test_optimize_parser_parses_verifier_bundle_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "verifier-bundle",
                "--run-dir",
                "/tmp/assist-runs",
                "--window-hours",
                "12",
                "--top",
                "4",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "verifier-bundle")
        self.assertEqual(args.run_dir, "/tmp/assist-runs")
        self.assertEqual(args.window_hours, 12)
        self.assertEqual(args.top, 4)

    def test_verifier_bundle_checks_effect_receipt_and_rollback_replay(self):
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
            governor_path = Path(td) / "governor.json"
            governor_path.write_text(json.dumps(packet), encoding="utf-8")
            apply_args = type(
                "Args",
                (),
                {
                    "from_file": str(governor_path),
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
            apply_buf = io.StringIO()
            with redirect_stdout(apply_buf):
                cmd_optimize_assist_apply(conn, apply_args)
            apply_out = json.loads(apply_buf.getvalue())
            verify_args = type(
                "Args",
                (),
                {
                    "run_dir": td,
                    "window_hours": 24,
                    "top": 10,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            verify_buf = io.StringIO()
            with redirect_stdout(verify_buf):
                cmd_optimize_verifier_bundle(conn, verify_args)
            out = json.loads(verify_buf.getvalue())

        self.assertEqual(out["kind"], "openclaw-mem.optimize.verifier-bundle.v0")
        self.assertEqual(out["counts"]["items"], 1)
        self.assertEqual(out["counts"]["effectReceiptPresent"], 1)
        self.assertEqual(out["counts"]["rollbackReplayPass"], 1)
        self.assertTrue(out["summary"]["cap_integrity_pass"])
        self.assertEqual(out["items"][0]["run_id"], apply_out["run_id"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
