import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser, cmd_optimize_posture_review


class TestOptimizePostureReview(unittest.TestCase):
    def test_optimize_parser_parses_posture_review_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "posture-review",
                "--runner-root",
                "/tmp/optimize-assist-runner",
                "--window-hours",
                "48",
                "--top",
                "7",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "posture-review")
        self.assertEqual(args.runner_root, "/tmp/optimize-assist-runner")
        self.assertEqual(args.window_hours, 48)
        self.assertEqual(args.top, 7)

    def test_posture_review_emits_near_ceiling_ready_when_controller_and_native_receipts_are_green(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "controller-state.json").write_text(
                json.dumps(
                    {
                        "mode": "auto_low_risk",
                        "soak_green_cycles": 2,
                        "regression_strikes": 0,
                        "family_state": {
                            "stale_candidate": {"enabled": True, "mode": "enabled", "reasons": []},
                            "importance_downshift": {"enabled": True, "mode": "enabled", "reasons": []},
                            "score_label_alignment": {"enabled": False, "mode": "disabled", "reasons": ["disabled_by_flag"]},
                        },
                        "horizons": {
                            "short": {"status": "green"},
                            "medium": {"status": "green"},
                            "soak": {"status": "green"},
                        },
                        "updated_at": "2026-04-17T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "2026-04-17" / "run-1"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "controller.json").write_text(
                json.dumps({"ts": "2026-04-17T00:00:00+00:00", "next_mode": "auto_low_risk"}),
                encoding="utf-8",
            )
            (run_dir / "challenger.json").write_text(
                json.dumps({"ts": "2026-04-17T00:00:00+00:00", "summary": {"agreement_pass": True}}),
                encoding="utf-8",
            )
            (run_dir / "verifier.json").write_text(
                json.dumps(
                    {
                        "ts": "2026-04-17T00:00:00+00:00",
                        "summary": {
                            "effect_receipt_missing_pct": 0.0,
                            "cap_integrity_pass": True,
                            "rollback_replay_pass": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "assist-after.json").write_text(
                json.dumps({"ts": "2026-04-17T00:00:00+00:00", "result": "applied"}),
                encoding="utf-8",
            )
            args = type("Args", (), {"runner_root": str(root), "window_hours": 72, "top": 10, "json": True})()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_posture_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.posture-review.v0")
        self.assertTrue(out["summary"]["near_ceiling_ready"])
        self.assertEqual(out["controller"]["mode"], "auto_low_risk")
        self.assertEqual(out["counts"]["enabledFamilies"], 2)
        conn.close()


if __name__ == "__main__":
    unittest.main()
