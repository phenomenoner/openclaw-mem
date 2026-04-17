import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openclaw_mem.cli import _connect, _insert_observation
from tools import optimize_assist_runner as runner


def _write_native_effect_history(root: Path, *, regressed: int = 0, neutral: int = 1) -> None:
    effect_dir = root / "assist-receipts" / "2026-04-17"
    effect_dir.mkdir(parents=True, exist_ok=True)
    effect_path = effect_dir / "history.effect.json"
    after_path = effect_dir / "history.after.json"
    items = ([{"effect_summary": "regressed"}] * regressed) + ([{"effect_summary": "neutral"}] * neutral)
    effect_path.write_text(json.dumps({
        "kind": "openclaw-mem.optimize.assist.effect-batch.v0",
        "items": items,
    }), encoding="utf-8")
    after_path.write_text(json.dumps({
        "kind": "openclaw-mem.optimize.assist.after.v1",
        "ts": runner._utcnow_iso(),
        "result": "applied",
        "artifacts": {"effect_ref": str(effect_path)},
    }), encoding="utf-8")


def _write_rollback_receipt(root: Path, *, passed: bool = True) -> Path:
    path = root / "rollback-replay.json"
    path.write_text(json.dumps({"rollback_replay_pass": passed}), encoding="utf-8")
    return path


class TestOptimizeAssistRunner(unittest.TestCase):
    def test_build_parser_parses_apply_flags(self):
        args = runner.build_parser().parse_args(
            [
                "--python",
                "python3",
                "--db",
                "/tmp/openclaw-mem.sqlite",
                "--runner-root",
                "/tmp/runner",
                "--operator",
                "lyria",
                "--allow-apply",
                "--no-approve-importance",
                "--scope",
                "team/alpha",
                "--limit",
                "400",
                "--stale-days",
                "45",
                "--lifecycle-limit",
                "80",
                "--top",
                "4",
                "--challenger-policy-mode",
                "strict_v1",
                "--challenger-max-disagreement-clusters",
                "6",
                "--disable-family",
                "score_label_alignment",
                "--enable-family",
                "score_label_alignment",
                "--challenger-require-agreement-for-promotion",
                "--challenger-max-disagreements-for-promotion",
                "0",
                "--max-rows-per-run",
                "2",
                "--max-rows-per-24h",
                "6",
                "--max-importance-adjustments-per-run",
                "1",
                "--max-importance-adjustments-per-24h",
                "4",
                "--controller-mode",
                "auto_low_risk",
                "--watchdog-window-hours",
                "12",
                "--watchdog-max-regressed-effect-items",
                "0",
                "--promotion-gate-receipt",
                "/tmp/promotion.json",
                "--promote-when-gates-green",
                "--soak-cycles-for-auto-low-risk",
                "2",
                "--regression-strikes-for-demotion",
                "3",
                "--lane",
                "observations.assist",
                "--json",
            ]
        )
        self.assertEqual(args.python, "python3")
        self.assertTrue(args.allow_apply)
        self.assertFalse(args.approve_importance)
        self.assertEqual(args.scope, "team/alpha")
        self.assertEqual(args.challenger_policy_mode, "strict_v1")
        self.assertEqual(args.challenger_max_disagreement_clusters, 6)
        self.assertTrue(args.challenger_enforce_quarantine)
        self.assertEqual(args.disable_family, ["score_label_alignment"])
        self.assertEqual(args.enable_family, ["score_label_alignment"])
        self.assertTrue(args.challenger_require_agreement_for_promotion)
        self.assertEqual(args.challenger_max_disagreements_for_promotion, 0)
        self.assertEqual(args.max_rows_per_run, 2)
        self.assertEqual(args.max_importance_adjustments_per_run, 1)
        self.assertEqual(args.max_importance_adjustments_per_24h, 4)
        self.assertEqual(args.controller_mode, "auto_low_risk")
        self.assertEqual(args.watchdog_window_hours, 12)
        self.assertEqual(args.promotion_gate_receipt, "/tmp/promotion.json")
        self.assertTrue(args.promote_when_gates_green)
        self.assertEqual(args.soak_cycles_for_auto_low_risk, 2)
        self.assertEqual(args.regression_strikes_for_demotion, 3)
        self.assertTrue(args.json)

    def test_run_pipeline_writes_packet_files_and_summary(self):
        with tempfile.TemporaryDirectory() as td:
            _write_native_effect_history(Path(td), regressed=0, neutral=2)
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=False,
                approve_importance=True,
                approve_stale=True,
                scope="team/alpha",
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode=None,
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=None,
                promotion_gate_receipt=None,
                promote_when_gates_green=False,
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=3,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(
                    argv=["evolution"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 2}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["governor"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["challenger"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["assist"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "result": "dry_run", "applied_rows": 0, "skipped_rows": 1, "blocked_by_caps": []}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["verifier"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}),
                    stderr="",
                ),
            ]

            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertEqual(out["mode"], "dry_run")
            self.assertEqual(out["controller"]["effective_mode"], "dry_run")
            self.assertEqual(out["controller"]["next_mode"], "dry_run")
            self.assertEqual(out["controller"]["soak_green_cycles"], 0)
            self.assertEqual(out["controller"]["regression_strikes"], 0)
            self.assertEqual(out["counts"]["evolution_candidates"], 2)
            self.assertEqual(out["counts"]["governor_approved"], 1)
            self.assertEqual(out["results"]["assist_result"], "dry_run")
            run_dir = Path(out["artifacts"]["run_dir"])
            self.assertTrue((run_dir / "evolution.json").exists())
            self.assertTrue((run_dir / "governor.json").exists())
            self.assertTrue((run_dir / "challenger.json").exists())
            self.assertTrue((run_dir / "governor-filtered.json").exists())
            self.assertTrue((run_dir / "assist-after.json").exists())
            self.assertTrue((run_dir / "verifier.json").exists())
            self.assertTrue((run_dir / "promotion-gates.json").exists())
            self.assertTrue((run_dir / "controller.json").exists())
            self.assertIn("--dry-run", out["commands"]["assist_apply"])
            self.assertIn("--max-importance-adjustments-per-run", out["commands"]["assist_apply"])
            self.assertIn("--approve-importance", out["commands"]["governor_review"])
            self.assertIn("--policy-mode", out["commands"]["challenger_review"])
            self.assertIn("verifier_bundle", out["commands"])
            state = json.loads(Path(out["controller"]["state_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(state["schema_version"], runner.CONTROLLER_STATE_SCHEMA_VERSION)
            self.assertEqual(state["revision"], 1)
            self.assertTrue(state["state_digest"])

    def test_run_pipeline_raises_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=False,
                approve_importance=True,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode=None,
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=None,
                promotion_gate_receipt=None,
                promote_when_gates_green=False,
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=3,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(argv=["evolution"], returncode=0, stdout="not-json", stderr=""),
            ]
            with patch.object(runner, "_run", side_effect=outputs):
                with self.assertRaises(runner.RunnerError):
                    runner.run_pipeline(args)

    def test_run_pipeline_pauses_controller_on_regressed_effect(self):
        with tempfile.TemporaryDirectory() as td:
            rollback_receipt = _write_rollback_receipt(Path(td))
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=True,
                approve_importance=True,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode="auto_low_risk",
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=str(rollback_receipt),
                promotion_gate_receipt=None,
                promote_when_gates_green=False,
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=3,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            effect_dir = Path(td) / "assist-receipts" / "2026-04-17"
            effect_dir.mkdir(parents=True, exist_ok=True)
            effect_path = effect_dir / "r1.effect.json"
            after_path = effect_dir / "r1.after.json"
            now_ts = runner._utcnow_iso()
            effect_path.write_text(json.dumps({
                "kind": "openclaw-mem.optimize.assist.effect-batch.v0",
                "items": [{"effect_summary": "regressed"}],
            }), encoding="utf-8")
            after_path.write_text(json.dumps({
                "kind": "openclaw-mem.optimize.assist.after.v1",
                "ts": now_ts,
                "result": "applied",
                "artifacts": {"effect_ref": str(effect_path)},
            }), encoding="utf-8")
            outputs = [
                runner.CommandResult(
                    argv=["evolution"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 1}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["governor"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["challenger"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["assist"],
                    returncode=0,
                    stdout=json.dumps({
                        "kind": "openclaw-mem.optimize.assist.after.v1",
                        "ts": now_ts,
                        "result": "applied",
                        "applied_rows": 1,
                        "skipped_rows": 0,
                        "blocked_by_caps": [],
                        "artifacts": {"effect_ref": str(effect_path)},
                    }),
                    stderr="",
                ),
                runner.CommandResult(
                    argv=["verifier"],
                    returncode=0,
                    stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}),
                    stderr="",
                ),
            ]
            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertTrue(out["controller"]["paused"])
            self.assertEqual(out["controller"]["next_mode"], "paused_regression")
            self.assertEqual(out["controller"]["regression_strikes"], 1)
            self.assertIn("quality_regression_detected", out["results"]["watchdog_pause_reasons"])
            state = json.loads(Path(out["controller"]["state_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(state["mode"], "paused_regression")

    def test_run_pipeline_promotes_to_auto_low_risk_when_gates_are_green(self):
        with tempfile.TemporaryDirectory() as td:
            _write_native_effect_history(Path(td), regressed=0, neutral=2)
            rollback_receipt = _write_rollback_receipt(Path(td))
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=True,
                approve_importance=True,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode="canary_apply",
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=str(rollback_receipt),
                promotion_gate_receipt=None,
                promote_when_gates_green=True,
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=1,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(argv=["evolution"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 1}}), stderr=""),
                runner.CommandResult(argv=["governor"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}), stderr=""),
                runner.CommandResult(argv=["challenger"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}), stderr=""),
                runner.CommandResult(argv=["assist"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "ts": runner._utcnow_iso(), "result": "applied", "applied_rows": 1, "skipped_rows": 0, "blocked_by_caps": [], "artifacts": {"effect_ref": ""}}), stderr=""),
                runner.CommandResult(argv=["verifier"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}), stderr=""),
            ]
            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertEqual(out["controller"]["effective_mode"], "canary_apply")
            self.assertEqual(out["controller"]["next_mode"], "auto_low_risk")
            self.assertTrue(out["controller"]["promotion_gates_passed"])
            self.assertEqual(out["controller"]["soak_green_cycles"], 1)
            state = json.loads(Path(out["controller"]["state_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(state["mode"], "auto_low_risk")

    def test_run_pipeline_demotes_auto_low_risk_to_canary_after_failed_promotion_gates(self):
        with tempfile.TemporaryDirectory() as td:
            rollback_receipt = _write_rollback_receipt(Path(td))
            state_path = Path(td) / runner.DEFAULT_CONTROLLER_STATE
            state_path.write_text(json.dumps({"mode": "auto_low_risk", "soak_green_cycles": 3, "regression_strikes": 0}), encoding="utf-8")
            _write_native_effect_history(Path(td), regressed=0, neutral=2)
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=True,
                approve_importance=True,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode=None,
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=str(rollback_receipt),
                promotion_gate_receipt=None,
                promote_when_gates_green=True,
                promotion_min_manual_precision=1.1,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=3,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(argv=["evolution"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 1}}), stderr=""),
                runner.CommandResult(argv=["governor"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}), stderr=""),
                runner.CommandResult(argv=["challenger"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}), stderr=""),
                runner.CommandResult(argv=["assist"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "ts": runner._utcnow_iso(), "result": "applied", "applied_rows": 1, "skipped_rows": 0, "blocked_by_caps": [], "artifacts": {"effect_ref": ""}}), stderr=""),
                runner.CommandResult(argv=["verifier"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}), stderr=""),
            ]
            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertEqual(out["controller"]["effective_mode"], "auto_low_risk")
            self.assertEqual(out["controller"]["next_mode"], "canary_apply")

    def test_run_pipeline_blocks_promotion_when_challenger_agreement_required(self):
        with tempfile.TemporaryDirectory() as td:
            _write_native_effect_history(Path(td), regressed=0, neutral=2)
            rollback_receipt = _write_rollback_receipt(Path(td))
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=True,
                approve_importance=True,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=True,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode="canary_apply",
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=str(rollback_receipt),
                promotion_gate_receipt=None,
                promote_when_gates_green=True,
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=1,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(argv=["evolution"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 1}}), stderr=""),
                runner.CommandResult(argv=["governor"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}), stderr=""),
                runner.CommandResult(argv=["challenger"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 1}, "summary": {"agreement_pass": False, "promotion_ready": False, "quarantine_recommended": True}, "disagreements": [{"candidate_id": "importance-downshift-1", "action_family": "importance_downshift", "quarantine_recommended": True}]}), stderr=""),
                runner.CommandResult(argv=["assist"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "ts": runner._utcnow_iso(), "result": "dry_run", "applied_rows": 0, "skipped_rows": 1, "blocked_by_caps": [], "artifacts": {"effect_ref": ""}}), stderr=""),
                runner.CommandResult(argv=["verifier"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}), stderr=""),
            ]

            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertEqual(out["controller"]["next_mode"], "canary_apply")
            self.assertFalse(out["controller"]["promotion_gates_passed"])
            self.assertEqual(out["counts"]["challenger_disagreements"], 1)
            self.assertIn("challenger_agreement_required", out["results"]["promotion_gate_reasons"])

    def test_filter_governor_packet_quarantines_entire_importance_family(self):
        governor_json = {
            "items": [
                {
                    "candidate_id": "importance-downshift-1",
                    "action": "adjust_importance_score",
                    "patch": {"importance": {"score": 0.25, "label": "reference", "delta": -0.05, "reason_code": "stale_pressure"}},
                    "decision": "approved_for_apply",
                    "reasons": [],
                }
            ],
            "counts": {"approvedForApply": 1},
        }
        challenger_json = {
            "disagreements": [
                {
                    "candidate_id": "different-candidate",
                    "action_family": "importance_downshift",
                    "quarantine_recommended": True,
                }
            ]
        }
        filtered, blocked_by_family, challenger_filter = runner._filter_governor_packet(
            governor_json,
            challenger_json,
            family_state={
                "stale_candidate": {"enabled": True, "mode": "enabled", "reasons": []},
                "importance_downshift": {"enabled": True, "mode": "enabled", "reasons": []},
                "score_label_alignment": {"enabled": True, "mode": "enabled", "reasons": []},
            },
            enforce_quarantine=True,
        )
        self.assertEqual(blocked_by_family["importance_downshift"], 0)
        self.assertEqual(challenger_filter["blocked_by_quarantine"], 1)
        self.assertEqual(filtered["counts"]["approvedForApply"], 0)
        self.assertEqual(filtered["items"][0]["decision"], "proposal_only")
        self.assertIn("challenger_quarantine:importance_downshift", filtered["items"][0]["reasons"])

    def test_load_controller_state_rejects_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / runner.DEFAULT_CONTROLLER_STATE
            payload = {
                "kind": "openclaw-mem.optimize.assist.controller-state.v0",
                "schema_version": runner.CONTROLLER_STATE_SCHEMA_VERSION,
                "revision": 1,
                "mode": "dry_run",
                "state_digest": "bogus",
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(runner.RunnerError):
                runner._load_controller_state(path)

    def test_run_pipeline_ignores_external_promotion_receipt_input(self):
        with tempfile.TemporaryDirectory() as td:
            _write_native_effect_history(Path(td), regressed=0, neutral=2)
            rollback_receipt = _write_rollback_receipt(Path(td))
            bogus_path = Path(td) / "promotion.json"
            bogus_path.write_text(json.dumps({
                "manual_review_sample_precision": 0.0,
                "repeated_miss_regression_pct": 99.0,
                "rollback_replay_pass": False,
            }), encoding="utf-8")
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=True,
                approve_importance=True,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode="canary_apply",
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=str(rollback_receipt),
                promotion_gate_receipt=str(bogus_path),
                promote_when_gates_green=True,
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=1,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            outputs = [
                runner.CommandResult(argv=["evolution"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 1}}), stderr=""),
                runner.CommandResult(argv=["governor"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}), stderr=""),
                runner.CommandResult(argv=["challenger"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}), stderr=""),
                runner.CommandResult(argv=["assist"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "ts": runner._utcnow_iso(), "result": "applied", "applied_rows": 1, "skipped_rows": 0, "blocked_by_caps": [], "artifacts": {"effect_ref": ""}}), stderr=""),
                runner.CommandResult(argv=["verifier"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}), stderr=""),
            ]
            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertTrue(out["controller"]["promotion_gates_passed"])
            emitted = json.loads(bogus_path.read_text(encoding="utf-8"))
            self.assertEqual(emitted["metrics"]["manual_review_sample_precision"], 1.0)
            self.assertTrue(emitted["passed"])

    def test_run_pipeline_rejects_malformed_controller_state_json(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / runner.DEFAULT_CONTROLLER_STATE
            state_path.write_text("{not-json", encoding="utf-8")
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=False,
                approve_importance=True,
                approve_stale=True,
                scope=None,
                limit=100,
                stale_days=60,
                lifecycle_limit=50,
                top=5,
                challenger_policy_mode="strict_v1",
                challenger_max_disagreement_clusters=10,
                challenger_enforce_quarantine=True,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                disable_family=[],
                enable_family=[],
                max_rows_per_run=5,
                max_rows_per_24h=20,
                max_importance_adjustments_per_run=3,
                max_importance_adjustments_per_24h=10,
                controller_mode=None,
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=None,
                promotion_gate_receipt=None,
                promote_when_gates_green=False,
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                soak_cycles_for_auto_low_risk=3,
                regression_strikes_for_demotion=2,
                lane="observations.assist",
                json=True,
            )
            with self.assertRaises(runner.RunnerError):
                runner.run_pipeline(args)

    def test_collect_watchdog_stats_counts_invalid_effect_receipts_as_missing(self):
        with tempfile.TemporaryDirectory() as td:
            effect_dir = Path(td) / "assist-receipts" / "2026-04-17"
            effect_dir.mkdir(parents=True, exist_ok=True)
            after_path = effect_dir / "history.after.json"
            effect_path = effect_dir / "history.effect.json"
            effect_path.write_text("{bad-json", encoding="utf-8")
            after_path.write_text(json.dumps({
                "kind": "openclaw-mem.optimize.assist.after.v1",
                "ts": runner._utcnow_iso(),
                "result": "applied",
                "artifacts": {"effect_ref": str(effect_path)},
            }), encoding="utf-8")
            stats = runner._collect_watchdog_stats(Path(td), since_ts=datetime.now(timezone.utc) - timedelta(hours=24))

            self.assertEqual(stats["applied_runs"], 1)
            self.assertEqual(stats["missing_effect_receipts"], 1)
            self.assertEqual(stats["invalid_effect_receipts"], 1)
            self.assertEqual(stats["effect_receipt_missing_pct"], 100.0)

    def test_watchdog_pauses_when_rollback_replay_receipt_missing_in_canary_apply(self):
        with tempfile.TemporaryDirectory() as td:
            watchdog = runner._evaluate_watchdog(
                SimpleNamespace(
                    watchdog_window_hours=24,
                    watchdog_max_missing_effect_receipts_pct=0.0,
                    watchdog_max_regressed_effect_items=0,
                    rollback_replay_receipt=None,
                ),
                runner_root=Path(td),
                controller_mode="canary_apply",
            )

            self.assertTrue(watchdog["should_pause"])
            self.assertIn("rollback_replay_receipt_missing", watchdog["pause_reasons"])


class TestOptimizeAssistRunnerE2E(unittest.TestCase):
    def _seed_db(self, db_path: Path, *, importance_score: float = 0.32) -> None:
        conn = _connect(str(db_path))
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": importance_score}},
            },
        )
        conn.commit()
        conn.close()

    def _run_runner(self, db_path: Path, runner_root: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)
        cmd = [
            sys.executable,
            "tools/optimize_assist_runner.py",
            "--db",
            str(db_path),
            "--runner-root",
            str(runner_root),
            "--scope",
            "team/alpha",
            "--json",
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, env=env)

    def _rollback_arg(self, root: Path) -> list[str]:
        return ["--rollback-replay-receipt", str(_write_rollback_receipt(root))]

    def test_runner_subprocess_promotes_with_native_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)

            proc = self._run_runner(
                db_path,
                runner_root,
                "--controller-mode",
                "canary_apply",
                "--allow-apply",
                "--promote-when-gates-green",
                "--soak-cycles-for-auto-low-risk",
                "1",
                *self._rollback_arg(td_path),
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertTrue(out["controller"]["promotion_gates_passed"])
            self.assertEqual(out["controller"]["next_mode"], "auto_low_risk")
            self.assertTrue(Path(out["artifacts"]["verifier_bundle"]).exists())
            self.assertTrue(Path(out["artifacts"]["promotion_gates"]).exists())
            state = json.loads(Path(out["controller"]["state_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(state["mode"], "auto_low_risk")
            self.assertEqual(state["revision"], 1)
            self.assertTrue(state["state_digest"])

    def test_runner_subprocess_pauses_on_invalid_effect_history(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)
            history_dir = runner_root / "assist-receipts" / "2026-04-17"
            history_dir.mkdir(parents=True, exist_ok=True)
            (history_dir / "bad.effect.json").write_text("{bad-json", encoding="utf-8")
            (history_dir / "bad.after.json").write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.assist.after.v1",
                        "ts": runner._utcnow_iso(),
                        "result": "applied",
                        "artifacts": {"effect_ref": str(history_dir / "bad.effect.json")},
                    }
                ),
                encoding="utf-8",
            )

            proc = self._run_runner(
                db_path,
                runner_root,
                "--controller-mode",
                "auto_low_risk",
                "--allow-apply",
                *self._rollback_arg(td_path),
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertTrue(out["controller"]["paused"])
            self.assertEqual(out["controller"]["next_mode"], "paused_regression")
            self.assertIn("missing_effect_receipts", out["results"]["watchdog_pause_reasons"])

    def test_runner_subprocess_aborts_on_malformed_controller_state(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)
            runner_root.mkdir(parents=True, exist_ok=True)
            (runner_root / runner.DEFAULT_CONTROLLER_STATE).write_text("{not-json", encoding="utf-8")

            proc = self._run_runner(db_path, runner_root)

            self.assertEqual(proc.returncode, 2)
            out = json.loads(proc.stdout)
            self.assertEqual(out["result"], "aborted")
            self.assertIn("controller state", out["error"])


if __name__ == "__main__":
    unittest.main()
