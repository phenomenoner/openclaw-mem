import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openclaw_mem.cli as mem_cli
from openclaw_mem.cli import _connect, build_parser, cmd_optimize_canary_advisory


class TestOptimizeCanaryAdvisory(unittest.TestCase):
    def test_optimize_parser_parses_canary_advisory_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "canary-advisory",
                "--runner-root",
                "/tmp/runner",
                "--posture-file",
                "/tmp/posture.json",
                "--verifier-file",
                "/tmp/verifier.json",
                "--window-hours",
                "24",
                "--top",
                "3",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "canary-advisory")
        self.assertEqual(args.runner_root, "/tmp/runner")
        self.assertEqual(args.posture_file, "/tmp/posture.json")
        self.assertEqual(args.verifier_file, "/tmp/verifier.json")
        self.assertEqual(args.window_hours, 24)
        self.assertEqual(args.top, 3)

    def test_canary_advisory_can_enable_when_posture_and_verifier_are_green(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            posture_path = root / "posture.json"
            verifier_path = root / "verifier.json"
            posture_path.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.posture-review.v0",
                        "summary": {
                            "near_ceiling_ready": True,
                            "importance_drift_gate_live": True,
                            "importance_drift_baseline_live": True,
                        },
                        "controller": {"mode": "auto_low_risk", "regression_strikes": 0},
                        "counts": {
                            "challengerGreenRuns": 1,
                            "quarantinedFamilies": 0,
                            "softArchiveActionsObserved": 1,
                        },
                        "families": {
                            "state": {
                                "soft_archive_candidate": {"enabled": True, "mode": "enabled", "reasons": []}
                            },
                            "verifier_applied_action_counts": {"set_soft_archive_candidate": 1},
                        },
                        "reasons": [],
                        "artifacts": {"latest_challenger_ref": "challenger.json"},
                    }
                ),
                encoding="utf-8",
            )
            verifier_path.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.verifier-bundle.v0",
                        "counts": {"items": 1},
                        "summary": {
                            "effect_receipt_missing_pct": 0.0,
                            "cap_integrity_pass": True,
                            "no_hard_delete_pass": True,
                            "rollback_replay_pass": True,
                            "applied_action_counts": {"set_soft_archive_candidate": 1},
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "runner_root": str(root),
                    "posture_file": str(posture_path),
                    "verifier_file": str(verifier_path),
                    "window_hours": 72,
                    "top": 20,
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_canary_advisory(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.canary-advisory.v0")
        self.assertEqual(out["policy"]["writes_performed"], 0)
        self.assertEqual(out["policy"]["working_set"], "disabled_frozen")
        self.assertEqual(out["policy"]["hard_delete"], "forbidden")
        self.assertEqual(out["overall_status"], "can_enable")
        self.assertEqual(out["features"]["soft_archive_canary"]["status"], "can_enable")
        self.assertEqual(out["features"]["lifecycle_mvp"]["status"], "can_enable")
        self.assertEqual(out["features"]["optimizer_gates"]["status"], "can_enable")
        self.assertIn(str(verifier_path), out["features"]["soft_archive_canary"]["evidence_refs"])
        conn.close()

    def test_canary_advisory_fails_closed_when_verifier_is_missing_or_unsafe(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            posture_path = root / "posture.json"
            posture_path.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.posture-review.v0",
                        "summary": {
                            "near_ceiling_ready": False,
                            "importance_drift_gate_live": False,
                            "importance_drift_baseline_live": False,
                        },
                        "controller": {"mode": "dry_run", "regression_strikes": 0},
                        "counts": {"challengerGreenRuns": 0, "quarantinedFamilies": 0},
                        "families": {"state": {"soft_archive_candidate": {"enabled": False, "mode": "disabled"}}},
                        "reasons": ["mode_not_auto_low_risk"],
                    }
                ),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "runner_root": str(root),
                    "posture_file": str(posture_path),
                    "verifier_file": None,
                    "window_hours": 72,
                    "top": 20,
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_canary_advisory(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["overall_status"], "not_ready")
        self.assertEqual(out["features"]["soft_archive_canary"]["status"], "not_ready")
        self.assertEqual(out["features"]["lifecycle_mvp"]["status"], "not_ready")
        self.assertIn("missing_verifier_bundle", out["features"]["soft_archive_canary"]["reasons"])
        self.assertIn("missing_verifier_bundle", out["features"]["lifecycle_mvp"]["reasons"])
        self.assertIn("verifier_not_green", out["features"]["optimizer_gates"]["reasons"])
        conn.close()

    def test_canary_advisory_fails_closed_when_no_hard_delete_is_inconclusive(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            posture_path = root / "posture.json"
            verifier_path = root / "verifier.json"
            posture_path.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.posture-review.v0",
                        "summary": {
                            "near_ceiling_ready": True,
                            "importance_drift_gate_live": True,
                            "importance_drift_baseline_live": True,
                        },
                        "controller": {"mode": "auto_low_risk", "regression_strikes": 0},
                        "counts": {"challengerGreenRuns": 1, "quarantinedFamilies": 0, "softArchiveActionsObserved": 1},
                        "families": {
                            "state": {"soft_archive_candidate": {"enabled": True, "mode": "enabled"}},
                            "verifier_applied_action_counts": {"set_soft_archive_candidate": 1},
                        },
                        "reasons": [],
                    }
                ),
                encoding="utf-8",
            )
            verifier_path.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.verifier-bundle.v0",
                        "counts": {"items": 1},
                        "summary": {
                            "effect_receipt_missing_pct": 0.0,
                            "cap_integrity_pass": True,
                            "rollback_replay_pass": True,
                            "applied_action_counts": {"set_soft_archive_candidate": 1},
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                runner_root=str(root),
                posture_file=str(posture_path),
                verifier_file=str(verifier_path),
                window_hours=72,
                top=20,
                json=True,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_canary_advisory(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["overall_status"], "monitor_only")
        self.assertEqual(out["features"]["soft_archive_canary"]["status"], "monitor_only")
        self.assertEqual(out["features"]["lifecycle_mvp"]["status"], "monitor_only")
        self.assertIn("no_hard_delete_inconclusive", out["features"]["soft_archive_canary"]["reasons"])
        self.assertIn("verifier_not_green", out["features"]["lifecycle_mvp"]["reasons"])
        self.assertIn("verifier_not_green", out["features"]["optimizer_gates"]["reasons"])
        conn.close()

    def test_cli_main_canary_advisory_skips_global_connect_side_effects(self):
        captured = {}

        def fake_func(conn, args):
            captured["db"] = getattr(args, "db", None)
            captured["json"] = getattr(args, "json", None)
            captured["conn_type"] = type(conn).__name__

        fake_args = SimpleNamespace(
            cmd="optimize",
            optimize_cmd="canary-advisory",
            db=None,
            db_global="/tmp/should-not-be-created.sqlite",
            json=False,
            json_global=True,
            func=fake_func,
        )
        fake_parser = SimpleNamespace(parse_args=lambda: fake_args)

        with patch("openclaw_mem.cli.build_parser", return_value=fake_parser), patch(
            "openclaw_mem.cli._connect", side_effect=AssertionError("_connect must not run for canary-advisory")
        ):
            mem_cli.main()

        self.assertIsNone(captured["db"])
        self.assertTrue(captured["json"])
        self.assertEqual(captured["conn_type"], "Connection")


if __name__ == "__main__":
    unittest.main()
