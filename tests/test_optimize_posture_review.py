import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
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
            now = datetime.now(timezone.utc).isoformat()
            (root / "controller-state.json").write_text(
                json.dumps(
                    {
                        "mode": "auto_low_risk",
                        "soak_green_cycles": 2,
                        "regression_strikes": 0,
                        "promotion_gates": {
                            "importance_drift_gate": {
                                "passed": True,
                                "profile": "balanced",
                                "persistent_drift_detected": False,
                                "baseline_comparator": {
                                    "persistent_drift_detected": False,
                                    "transient_spike_detected": False,
                                },
                                "policy_card": {
                                    "threshold_profile": "balanced",
                                    "profile": {"name": "balanced"},
                                },
                            }
                        },
                        "family_state": {
                            "stale_candidate": {"enabled": True, "mode": "enabled", "reasons": []},
                            "soft_archive_candidate": {"enabled": True, "mode": "enabled", "reasons": []},
                            "importance_downshift": {"enabled": True, "mode": "enabled", "reasons": []},
                            "score_label_alignment": {"enabled": False, "mode": "disabled", "reasons": ["disabled_by_flag"]},
                        },
                        "horizons": {
                            "short": {"status": "green"},
                            "medium": {"status": "green"},
                            "soak": {"status": "green"},
                        },
                        "updated_at": now,
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "2026-04-17" / "run-1"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "controller.json").write_text(
                json.dumps({
                    "ts": now,
                    "next_mode": "auto_low_risk",
                    "promotion_gates": {
                        "importance_drift_gate": {
                            "passed": True,
                            "profile": "balanced",
                            "persistent_drift_detected": False,
                            "baseline_comparator": {
                                "persistent_drift_detected": False,
                                "transient_spike_detected": False,
                            },
                            "policy_card": {
                                "threshold_profile": "balanced",
                                "profile": {"name": "balanced"},
                            },
                        }
                    },
                }),
                encoding="utf-8",
            )
            (run_dir / "challenger.json").write_text(
                json.dumps({"ts": now, "summary": {"agreement_pass": True}}),
                encoding="utf-8",
            )
            (run_dir / "verifier.json").write_text(
                json.dumps(
                    {
                        "ts": now,
                        "summary": {
                            "effect_receipt_missing_pct": 0.0,
                            "cap_integrity_pass": True,
                            "no_hard_delete_pass": True,
                            "rollback_replay_pass": True,
                            "applied_action_counts": {
                                "set_stale_candidate": 1,
                                "adjust_importance_score": 0,
                                "set_soft_archive_candidate": 1,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "assist-after.json").write_text(
                json.dumps({"ts": now, "result": "applied"}),
                encoding="utf-8",
            )
            args = type("Args", (), {"runner_root": str(root), "window_hours": 72, "top": 10, "json": True})()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_posture_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.posture-review.v0")
        self.assertTrue(out["summary"]["near_ceiling_ready"])
        self.assertTrue(out["summary"]["importance_drift_gate_live"])
        self.assertTrue(out["summary"]["importance_drift_baseline_live"])
        self.assertEqual(out["controller"]["mode"], "auto_low_risk")
        self.assertTrue(out["controller"]["importance_drift_gate_passed"])
        self.assertEqual(out["controller"]["importance_drift_profile"], "balanced")
        self.assertIn("importance_drift_baseline", out["controller"])
        self.assertEqual(out["counts"]["enabledFamilies"], 3)
        self.assertEqual(out["counts"]["softArchiveActionsObserved"], 1)
        self.assertEqual(out["families"]["verifier_applied_action_counts"]["set_soft_archive_candidate"], 1)
        self.assertGreaterEqual(out["counts"]["importanceDriftGateGreenRuns"], 1)
        self.assertGreaterEqual(out["counts"]["importanceDriftBaselineLiveRuns"], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
