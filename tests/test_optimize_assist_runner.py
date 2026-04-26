import json
import os
import signal
import subprocess
import sys
import tempfile
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from openclaw_mem.cli import _connect, _insert_observation
from openclaw_mem.optimization import build_importance_drift_policy_card
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


def _write_signed_controller_state(path: Path, payload: dict[str, object], *, prior_state: dict[str, object] | None = None) -> None:
    prepared = runner._prepare_controller_state(payload, prior_state=prior_state or {})
    path.write_text(json.dumps(prepared), encoding="utf-8")


def _write_controller_receipt(root: Path, *, name: str, passed: bool, profile: str = "strict") -> Path:
    ts = runner._utcnow_iso()
    policy_card = build_importance_drift_policy_card(
        rows_scanned=50,
        score_label_mismatch_count=0 if passed else 2,
        missing_or_unparseable_count=0,
        high_risk_underlabel_count=0,
        profile=profile,
    )
    if not passed:
        policy_card["acceptable_for_promotion_apply"] = False
        policy_card["status"] = "hold"
    payload = {
        "ts": ts,
        "promotion_gates": {
            "importance_drift_gate": {
                "passed": passed,
                "profile": profile,
                "policy_card": policy_card,
            }
        },
    }
    path = root / "history" / name / "controller.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _evolution_payload(
    *,
    items: int = 1,
    rows_scanned: int = 20,
    score_label_mismatch_count: int = 0,
    missing_or_unparseable_count: int = 0,
    high_risk_content_mismatch_count: int = 0,
) -> dict[str, object]:
    return {
        "kind": "openclaw-mem.optimize.evolution-review.v0",
        "source": {"rows_scanned": rows_scanned},
        "counts": {
            "items": items,
            "importanceDriftLabelMismatches": score_label_mismatch_count,
            "importanceDriftMissingOrUnparseable": missing_or_unparseable_count,
            "importanceDriftHighRiskContent": high_risk_content_mismatch_count,
        },
        "importance_drift_policy": build_importance_drift_policy_card(
            rows_scanned=rows_scanned,
            score_label_mismatch_count=score_label_mismatch_count,
            missing_or_unparseable_count=missing_or_unparseable_count,
            high_risk_underlabel_count=high_risk_content_mismatch_count,
        ),
    }


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
                "--importance-drift-profile",
                "balanced",
                "--importance-drift-baseline-limit",
                "8",
                "--importance-drift-baseline-min-samples",
                "4",
                "--importance-drift-persistent-hold-rate",
                "0.75",
                "--importance-drift-baseline-max-evidence",
                "2",
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
                "--migrate-unsigned-controller-state",
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
        self.assertFalse(args.approve_soft_archive)
        self.assertEqual(args.scope, "team/alpha")
        self.assertEqual(args.importance_drift_profile, "balanced")
        self.assertEqual(args.importance_drift_baseline_limit, 8)
        self.assertEqual(args.importance_drift_baseline_min_samples, 4)
        self.assertEqual(args.importance_drift_persistent_hold_rate, 0.75)
        self.assertEqual(args.importance_drift_baseline_max_evidence, 2)
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
        self.assertEqual(args.subprocess_timeout_secs, runner.DEFAULT_SUBPROCESS_TIMEOUT_SECS)
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
            self.assertTrue(out["controller"]["importance_drift_gate_passed"])
            self.assertEqual(out["controller"]["importance_drift_profile"], "strict")
            self.assertFalse(out["controller"]["importance_drift_persistent_drift_detected"])
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
            promotion_gates = json.loads((run_dir / "promotion-gates.json").read_text(encoding="utf-8"))
            self.assertIn("importance_drift_gate", promotion_gates)
            self.assertEqual(promotion_gates["importance_drift_gate"]["policy_card"]["kind"], "openclaw-mem.optimize.importance-drift-policy-card.v0")
            self.assertEqual(promotion_gates["importance_drift_gate"]["profile"], "strict")
            self.assertIn("baseline_comparator", promotion_gates["importance_drift_gate"])
            self.assertIn("persistent_drift_detected", promotion_gates["importance_drift_gate"])
            self.assertIn("--dry-run", out["commands"]["assist_apply"])
            self.assertIn("--max-importance-adjustments-per-run", out["commands"]["assist_apply"])
            self.assertIn("--approve-importance", out["commands"]["governor_review"])
            self.assertIn("--policy-mode", out["commands"]["challenger_review"])
            self.assertIn("--importance-drift-profile", out["commands"]["evolution_review"])
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

    def test_run_pipeline_releases_controller_lock_after_timeout_abort(self):
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

            with patch.object(runner, "_run", side_effect=runner.RunnerError("subprocess timed out after 300s: evolution-review")):
                with self.assertRaises(runner.RunnerError):
                    runner.run_pipeline(args)

            outputs = [
                runner.CommandResult(argv=["evolution"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 1}}), stderr=""),
                runner.CommandResult(argv=["governor"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 0}}), stderr=""),
                runner.CommandResult(argv=["challenger"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}), stderr=""),
                runner.CommandResult(argv=["assist"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "result": "dry_run", "applied_rows": 0, "skipped_rows": 0, "blocked_by_caps": []}), stderr=""),
                runner.CommandResult(argv=["verifier"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}), stderr=""),
            ]
            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertEqual(out["controller"]["effective_mode"], "dry_run")
            state = json.loads(Path(out["controller"]["state_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(state["revision"], 1)

    def test_run_aborts_when_subprocess_times_out(self):
        popen = Mock()
        popen.pid = 4321
        popen.communicate.side_effect = [subprocess.TimeoutExpired(cmd=["python3", "-m", "openclaw_mem"], timeout=7), ("", "")]
        popen.returncode = -signal.SIGKILL
        with patch.object(runner.subprocess, "Popen", return_value=popen), patch.object(runner.os, "killpg") as killpg:
            with self.assertRaises(runner.RunnerError) as ctx:
                runner._run(["python3", "-m", "openclaw_mem"])

        self.assertIn("subprocess timed out", str(ctx.exception))
        killpg.assert_called_once_with(4321, signal.SIGKILL)

    def test_run_timeout_second_communicate_does_not_hang(self):
        popen = Mock()
        popen.pid = 4321
        popen.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["python3", "-m", "openclaw_mem"], timeout=7),
            subprocess.TimeoutExpired(cmd=["python3", "-m", "openclaw_mem"], timeout=5),
        ]
        popen.returncode = -signal.SIGKILL
        with patch.object(runner.subprocess, "Popen", return_value=popen), patch.object(runner.os, "killpg") as killpg:
            with self.assertRaises(runner.RunnerError) as ctx:
                runner._run(["python3", "-m", "openclaw_mem"])

        self.assertIn("subprocess timed out", str(ctx.exception))
        killpg.assert_called_once_with(4321, signal.SIGKILL)
        self.assertEqual(popen.communicate.call_count, 2)

    def test_run_timeout_handles_permission_error_from_killpg(self):
        popen = Mock()
        popen.pid = 4321
        popen.communicate.side_effect = [subprocess.TimeoutExpired(cmd=["python3", "-m", "openclaw_mem"], timeout=7), ("", "")]
        popen.returncode = -signal.SIGKILL
        with patch.object(runner.subprocess, "Popen", return_value=popen), patch.object(runner.os, "killpg", side_effect=PermissionError("denied")):
            with self.assertRaises(runner.RunnerError) as ctx:
                runner._run(["python3", "-m", "openclaw_mem"])

        self.assertIn("subprocess timed out", str(ctx.exception))

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
            _write_signed_controller_state(
                state_path,
                {"kind": "openclaw-mem.optimize.assist.controller-state.v0", "mode": "auto_low_risk", "soak_green_cycles": 3, "regression_strikes": 0},
            )
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

    def test_run_pipeline_blocks_promotion_when_importance_drift_gate_holds(self):
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
                runner.CommandResult(argv=["evolution"], returncode=0, stdout=json.dumps(_evolution_payload(items=1, rows_scanned=50, high_risk_content_mismatch_count=1)), stderr=""),
                runner.CommandResult(argv=["governor"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}), stderr=""),
                runner.CommandResult(argv=["challenger"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}), stderr=""),
                runner.CommandResult(argv=["assist"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "ts": runner._utcnow_iso(), "result": "applied", "applied_rows": 1, "skipped_rows": 0, "blocked_by_caps": [], "artifacts": {"effect_ref": ""}}), stderr=""),
                runner.CommandResult(argv=["verifier"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}), stderr=""),
            ]

            with patch.object(runner, "_run", side_effect=outputs):
                out = runner.run_pipeline(args)

            self.assertFalse(out["controller"]["promotion_gates_passed"])
            self.assertFalse(out["controller"]["importance_drift_gate_passed"])
            self.assertIn("importance_drift_policy_hold", out["results"]["promotion_gate_reasons"])
            promotion_receipt = json.loads(Path(out["artifacts"]["promotion_gates"]).read_text(encoding="utf-8"))
            self.assertFalse(promotion_receipt["importance_drift_gate"]["passed"])

    def test_importance_drift_baseline_comparator_distinguishes_transient_vs_persistent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = SimpleNamespace(
                promotion_min_manual_precision=0.9,
                promotion_max_repeated_miss_regression_pct=5.0,
                watchdog_max_missing_effect_receipts_pct=0.0,
                challenger_require_agreement_for_promotion=False,
                challenger_max_disagreements_for_promotion=0,
                importance_drift_profile="strict",
                importance_drift_baseline_limit=6,
                importance_drift_baseline_min_samples=3,
                importance_drift_persistent_hold_rate=0.6,
                importance_drift_baseline_max_evidence=3,
            )
            watchdog = {
                "stats": {
                    "effect_items_total": 10,
                    "regressed_effect_items": 0,
                    "applied_runs": 1,
                    "effect_receipt_missing_pct": 0.0,
                }
            }
            verifier = {
                "summary": {
                    "rollback_replay_pass": True,
                    "effect_receipt_missing_pct": 0.0,
                    "cap_integrity_pass": True,
                }
            }
            challenger = {
                "counts": {"disagreements": 0},
                "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False},
            }
            current_evolution = _evolution_payload(items=1, rows_scanned=50, score_label_mismatch_count=2)

            _write_controller_receipt(root, name="run-1", passed=True)
            _write_controller_receipt(root, name="run-2", passed=True)
            _write_controller_receipt(root, name="run-3", passed=True)
            transient = runner._evaluate_promotion_gates(
                args,
                watchdog=watchdog,
                verifier=verifier,
                challenger=challenger,
                evolution=current_evolution,
                runner_root=root,
            )

            self.assertFalse(transient["importance_drift_gate"]["passed"])
            self.assertTrue(transient["importance_drift_gate"]["baseline_comparator"]["transient_spike_detected"])
            self.assertFalse(transient["importance_drift_gate"]["baseline_comparator"]["persistent_drift_detected"])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_controller_receipt(root, name="run-1", passed=False)
            _write_controller_receipt(root, name="run-2", passed=False)
            _write_controller_receipt(root, name="run-3", passed=True)
            persistent = runner._evaluate_promotion_gates(
                args,
                watchdog=watchdog,
                verifier=verifier,
                challenger=challenger,
                evolution=current_evolution,
                runner_root=root,
            )

            self.assertFalse(persistent["importance_drift_gate"]["passed"])
            self.assertTrue(persistent["importance_drift_gate"]["baseline_comparator"]["persistent_drift_detected"])
            self.assertFalse(persistent["importance_drift_gate"]["baseline_comparator"]["transient_spike_detected"])

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

    def test_atomic_write_json_cleans_tmp_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "receipt.json"
            tmp_path = target.with_name(".receipt.json.deadbeef.tmp")
            with patch.object(runner.uuid, "uuid4", return_value=SimpleNamespace(hex="deadbeef")), patch.object(
                runner.os, "replace", side_effect=OSError("replace failed")
            ):
                with self.assertRaises(OSError):
                    runner._atomic_write_json(target, {"ok": True})

            self.assertFalse(target.exists())
            self.assertFalse(tmp_path.exists())

    def test_atomic_write_json_preserves_replace_error_when_tmp_cleanup_also_fails(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "receipt.json"
            tmp_path = target.with_name(".receipt.json.deadbeef.tmp")
            real_exists = Path.exists
            real_unlink = Path.unlink

            def fake_exists(path: Path) -> bool:
                if path == tmp_path:
                    return True
                return real_exists(path)

            def fake_unlink(path: Path, missing_ok: bool = False) -> None:
                if path == tmp_path:
                    raise PermissionError("cleanup denied")
                return real_unlink(path, missing_ok=missing_ok)

            with patch.object(runner.uuid, "uuid4", return_value=SimpleNamespace(hex="deadbeef")), patch.object(
                runner.os, "replace", side_effect=OSError("replace failed")
            ), patch.object(Path, "exists", fake_exists), patch.object(Path, "unlink", fake_unlink):
                with self.assertRaises(OSError) as ctx:
                    runner._atomic_write_json(target, {"ok": True})

            self.assertIn("replace failed", str(ctx.exception))

    def test_run_pipeline_uses_atomic_writes_for_cross_process_receipts(self):
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
                runner.CommandResult(argv=["evolution"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.evolution-review.v0", "counts": {"items": 2}}), stderr=""),
                runner.CommandResult(argv=["governor"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.governor-review.v0", "counts": {"approvedForApply": 1}}), stderr=""),
                runner.CommandResult(argv=["challenger"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.challenger-review.v0", "counts": {"disagreements": 0}, "summary": {"agreement_pass": True, "promotion_ready": True, "quarantine_recommended": False}}), stderr=""),
                runner.CommandResult(argv=["assist"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.assist.after.v1", "result": "dry_run", "applied_rows": 0, "skipped_rows": 1, "blocked_by_caps": []}), stderr=""),
                runner.CommandResult(argv=["verifier"], returncode=0, stdout=json.dumps({"kind": "openclaw-mem.optimize.verifier-bundle.v0", "summary": {"effect_receipt_missing_pct": 0.0, "cap_integrity_pass": True, "rollback_replay_pass": True}}), stderr=""),
            ]
            seen_paths: list[str] = []
            real_atomic_write = runner._atomic_write_json

            def recording_atomic_write(path: Path, payload: dict[str, object]) -> None:
                seen_paths.append(path.name)
                real_atomic_write(path, payload)

            with patch.object(runner, "_run", side_effect=outputs), patch.object(runner, "_atomic_write_json", side_effect=recording_atomic_write):
                runner.run_pipeline(args)

            self.assertTrue(
                {
                    "evolution.json",
                    "governor.json",
                    "challenger.json",
                    "governor-filtered.json",
                    "assist-after.json",
                    "verifier.json",
                    "promotion-gates.json",
                    "controller.json",
                    runner.DEFAULT_CONTROLLER_STATE,
                }.issubset(set(seen_paths))
            )

    def test_run_pipeline_atomic_receipts_leave_no_tmp_files(self):
        with tempfile.TemporaryDirectory() as td:
            _write_native_effect_history(Path(td), regressed=0, neutral=2)
            emit_path = Path(td) / "emitted-promotion.json"
            args = SimpleNamespace(
                python="python3",
                db="/tmp/openclaw-mem.sqlite",
                runner_root=td,
                operator="lyria",
                allow_apply=True,
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
                controller_mode="canary_apply",
                controller_state_path=None,
                watchdog_window_hours=24,
                watchdog_max_missing_effect_receipts_pct=0.0,
                watchdog_max_regressed_effect_items=0,
                rollback_replay_receipt=str(_write_rollback_receipt(Path(td))),
                promotion_gate_receipt=str(emit_path),
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

            self.assertEqual(json.loads(emit_path.read_text(encoding="utf-8"))["passed"], True)
            self.assertEqual(json.loads(Path(out["artifacts"]["promotion_gates"]).read_text(encoding="utf-8"))["passed"], True)
            self.assertEqual(list(Path(td).rglob("*.tmp")), [])

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

    def test_load_controller_state_rejects_unsigned_legacy_without_migration(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / runner.DEFAULT_CONTROLLER_STATE
            path.write_text(json.dumps({"mode": "auto_low_risk", "soak_green_cycles": 3, "regression_strikes": 0}), encoding="utf-8")
            with self.assertRaises(runner.RunnerError):
                runner._load_controller_state(path)

    def test_load_controller_state_allows_unsigned_legacy_for_migration(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / runner.DEFAULT_CONTROLLER_STATE
            path.write_text(json.dumps({"mode": "auto_low_risk", "soak_green_cycles": 3, "regression_strikes": 0}), encoding="utf-8")
            payload = runner._load_controller_state(path, allow_unsigned_legacy=True)

            self.assertEqual(payload["mode"], "auto_low_risk")
            self.assertNotIn("schema_version", payload)

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

    def _run_runner(self, db_path: Path, runner_root: Path, *extra_args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)
        if extra_env:
            env.update(extra_env)
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

    def _normalized_json(self, path: Path) -> dict:
        def normalize(value):
            if isinstance(value, dict):
                out = {}
                for key, inner in value.items():
                    if key in {
                        "ts",
                        "updated_at",
                        "run_id",
                        "run_dir",
                        "run_root",
                        "fromFile",
                        "state_ref",
                        "receipt_ref",
                        "receipt_path",
                        "emitted_receipt_path",
                        "controller_state_ref",
                        "evolution_packet",
                        "governor_packet",
                        "governor_filtered_packet",
                        "challenger_packet",
                        "assist_after",
                        "verifier_bundle",
                        "promotion_gates",
                        "controller",
                    } or key.endswith("_path") or key.endswith("_ref") or key.endswith("_at"):
                        continue
                    out[key] = normalize(inner)
                return out
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        payload = json.loads(path.read_text(encoding="utf-8"))
        return normalize(payload)

    def _write_python_shim(self, root: Path, *, challenger_stdout: dict | None = None) -> Path:
        shim = root / "python-shim.py"
        payload = repr(challenger_stdout) if challenger_stdout is not None else "None"
        shim.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import subprocess\n"
            "import sys\n"
            f"CHALLENGER = {payload}\n"
            "if CHALLENGER is not None and sys.argv[1:5] == ['-m', 'openclaw_mem', 'optimize', 'challenger-review']:\n"
            "    print(json.dumps(CHALLENGER))\n"
            "    raise SystemExit(0)\n"
            f"proc = subprocess.run([{json.dumps(sys.executable)}, *sys.argv[1:]])\n"
            "raise SystemExit(proc.returncode)\n",
            encoding="utf-8",
        )
        shim.chmod(0o755)
        return shim

    def _write_sleeping_python_shim(self, root: Path, *, sleep_on_subcommand: str, seconds: int) -> Path:
        shim = root / f"python-sleep-{sleep_on_subcommand}.py"
        shim.write_text(
            "#!/usr/bin/env python3\n"
            "import subprocess\n"
            "import sys\n"
            "import time\n"
            f"TARGET = {sleep_on_subcommand!r}\n"
            f"SECONDS = {seconds!r}\n"
            "if len(sys.argv) >= 5 and sys.argv[1:4] == ['-m', 'openclaw_mem', 'optimize'] and sys.argv[4] == TARGET:\n"
            "    time.sleep(SECONDS)\n"
            f"proc = subprocess.run([{json.dumps(sys.executable)}, *sys.argv[1:]])\n"
            "raise SystemExit(proc.returncode)\n",
            encoding="utf-8",
        )
        shim.chmod(0o755)
        return shim

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

    def test_runner_subprocess_atomic_receipts_leave_no_tmp_files(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            emit_path = td_path / "promotion-out.json"
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
                "--promotion-gate-receipt",
                str(emit_path),
                *self._rollback_arg(td_path),
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertTrue(emit_path.exists())
            self.assertEqual(list(runner_root.rglob("*.tmp")), [])
            self.assertEqual(list(td_path.rglob("*.tmp")), [])
            self.assertTrue(Path(out["artifacts"]["controller"]).exists())
            self.assertTrue(Path(out["artifacts"]["promotion_gates"]).exists())

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

    def test_runner_subprocess_quarantines_importance_family_on_challenger_disagreement(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)
            shim = self._write_python_shim(
                td_path,
                challenger_stdout={
                    "kind": "openclaw-mem.optimize.challenger-review.v0",
                    "counts": {"items": 2, "disagreements": 1, "disagreementClusters": 1, "quarantineRecommended": 1},
                    "summary": {"agreement_pass": False, "promotion_ready": False, "quarantine_recommended": True},
                    "disagreements": [
                        {
                            "candidate_id": "synthetic-importance-review",
                            "action_family": "importance_downshift",
                            "quarantine_recommended": True,
                        }
                    ],
                    "disagreement_clusters": [
                        {
                            "action_family": "importance_downshift",
                            "reason": "higher_value_memory_requires_review",
                            "count": 1,
                            "candidate_ids": ["synthetic-importance-review"],
                            "quarantine_recommended": True,
                        }
                    ],
                    "items": [],
                },
            )

            proc = self._run_runner(
                db_path,
                runner_root,
                "--python",
                str(shim),
                "--controller-mode",
                "canary_apply",
                "--allow-apply",
                *self._rollback_arg(td_path),
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(out["counts"]["challenger_disagreements"], 1)
            self.assertTrue(out["results"]["challenger_quarantine_recommended"])
            self.assertEqual(out["results"]["blocked_by_family"]["importance_downshift"], 0)

            filtered = json.loads(Path(out["artifacts"]["governor_filtered_packet"]).read_text(encoding="utf-8"))
            importance_item = next(item for item in filtered["items"] if item.get("action_family") == "importance_downshift")
            self.assertEqual(importance_item["decision"], "proposal_only")
            self.assertIn("challenger_quarantine:importance_downshift", importance_item["reasons"])
            self.assertEqual(filtered["counts"]["blockedByChallengerQuarantine"], 1)

            state = json.loads(Path(out["controller"]["state_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(state["family_state"]["importance_downshift"]["mode"], "quarantined")
            self.assertIn("challenger_quarantine", state["family_state"]["importance_downshift"]["reasons"])

    def test_runner_subprocess_honors_small_timeout_flag(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)
            shim = self._write_sleeping_python_shim(td_path, sleep_on_subcommand="evolution-review", seconds=5)

            proc = self._run_runner(
                db_path,
                runner_root,
                "--python",
                str(shim),
                "--subprocess-timeout-secs",
                "1",
            )

            self.assertEqual(proc.returncode, 2)
            out = json.loads(proc.stdout)
            self.assertEqual(out["result"], "aborted")
            self.assertIn("subprocess timed out after 1s", out["error"])

    def test_runner_subprocess_rerun_is_deterministic_for_stable_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db1 = td_path / "mem1.sqlite"
            db2 = td_path / "mem2.sqlite"
            runner1 = td_path / "runner1"
            runner2 = td_path / "runner2"
            self._seed_db(db1, importance_score=0.32)
            shutil.copyfile(db1, db2)

            proc1 = self._run_runner(
                db1,
                runner1,
                "--controller-mode",
                "canary_apply",
                "--allow-apply",
                "--promote-when-gates-green",
                "--soak-cycles-for-auto-low-risk",
                "1",
                *self._rollback_arg(td_path),
            )
            proc2 = self._run_runner(
                db2,
                runner2,
                "--controller-mode",
                "canary_apply",
                "--allow-apply",
                "--promote-when-gates-green",
                "--soak-cycles-for-auto-low-risk",
                "1",
                *self._rollback_arg(td_path),
            )

            self.assertEqual(proc1.returncode, 0, proc1.stderr)
            self.assertEqual(proc2.returncode, 0, proc2.stderr)
            out1 = json.loads(proc1.stdout)
            out2 = json.loads(proc2.stdout)

            self.assertEqual(self._normalized_json(Path(out1["artifacts"]["evolution_packet"])), self._normalized_json(Path(out2["artifacts"]["evolution_packet"])))
            self.assertEqual(self._normalized_json(Path(out1["artifacts"]["governor_packet"])), self._normalized_json(Path(out2["artifacts"]["governor_packet"])))
            self.assertEqual(self._normalized_json(Path(out1["artifacts"]["governor_filtered_packet"])), self._normalized_json(Path(out2["artifacts"]["governor_filtered_packet"])))
            self.assertEqual(self._normalized_json(Path(out1["artifacts"]["challenger_packet"])), self._normalized_json(Path(out2["artifacts"]["challenger_packet"])))
            self.assertEqual(self._normalized_json(Path(out1["artifacts"]["verifier_bundle"])), self._normalized_json(Path(out2["artifacts"]["verifier_bundle"])))
            self.assertEqual(self._normalized_json(Path(out1["artifacts"]["promotion_gates"])), self._normalized_json(Path(out2["artifacts"]["promotion_gates"])))

            state1 = self._normalized_json(Path(out1["controller"]["state_ref"]))
            state2 = self._normalized_json(Path(out2["controller"]["state_ref"]))
            self.assertEqual(state1["mode"], state2["mode"])
            self.assertEqual(state1["effective_mode"], state2["effective_mode"])
            self.assertEqual(state1["family_state"], state2["family_state"])
            self.assertEqual(state1["horizons"], state2["horizons"])
            self.assertEqual(state1["watchdog"], state2["watchdog"])

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

    def test_runner_subprocess_rejects_unsigned_legacy_controller_state_without_migration(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)
            runner_root.mkdir(parents=True, exist_ok=True)
            (runner_root / runner.DEFAULT_CONTROLLER_STATE).write_text(
                json.dumps({"mode": "auto_low_risk", "soak_green_cycles": 3, "regression_strikes": 0}),
                encoding="utf-8",
            )

            proc = self._run_runner(db_path, runner_root)

            self.assertEqual(proc.returncode, 2)
            out = json.loads(proc.stdout)
            self.assertIn("migrate-unsigned-controller-state", out["error"])

    def test_runner_subprocess_migrates_unsigned_legacy_controller_state(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)
            runner_root.mkdir(parents=True, exist_ok=True)
            state_path = runner_root / runner.DEFAULT_CONTROLLER_STATE
            state_path.write_text(
                json.dumps({"mode": "auto_low_risk", "soak_green_cycles": 3, "regression_strikes": 0}),
                encoding="utf-8",
            )

            proc = self._run_runner(
                db_path,
                runner_root,
                "--migrate-unsigned-controller-state",
                *self._rollback_arg(td_path),
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(state["legacy_unsigned_state_migrated"])
            self.assertEqual(state["schema_version"], runner.CONTROLLER_STATE_SCHEMA_VERSION)
            self.assertTrue(state["state_digest"])
            self.assertGreaterEqual(state["revision"], 1)
            self.assertTrue(Path(out["controller"]["state_ref"]).exists())

    def test_runner_subprocess_serializes_overlapping_controller_revisions(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db_path = td_path / "mem.sqlite"
            runner_root = td_path / "runner"
            self._seed_db(db_path, importance_score=0.32)

            repo_root = Path(__file__).resolve().parents[1]
            env1 = os.environ.copy()
            env1["PYTHONPATH"] = str(repo_root)
            env1["OPENCLAW_MEM_TEST_CONTROLLER_LOCK_HOLD_SECS"] = "1.0"
            env2 = os.environ.copy()
            env2["PYTHONPATH"] = str(repo_root)
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
            ]

            proc1 = subprocess.Popen(cmd, cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env1)
            proc2 = subprocess.Popen(cmd, cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env2)
            stdout1, stderr1 = proc1.communicate(timeout=30)
            stdout2, stderr2 = proc2.communicate(timeout=30)

            self.assertEqual(proc1.returncode, 0, stderr1)
            self.assertEqual(proc2.returncode, 0, stderr2)
            out1 = json.loads(stdout1)
            out2 = json.loads(stdout2)
            receipt1 = json.loads(Path(out1["artifacts"]["controller"]).read_text(encoding="utf-8"))
            receipt2 = json.loads(Path(out2["artifacts"]["controller"]).read_text(encoding="utf-8"))
            self.assertEqual(sorted([receipt1["controller_state_revision"], receipt2["controller_state_revision"]]), [1, 2])
            final_state = json.loads((runner_root / runner.DEFAULT_CONTROLLER_STATE).read_text(encoding="utf-8"))
            self.assertEqual(final_state["revision"], 2)
            self.assertTrue(final_state["state_digest"])


if __name__ == "__main__":
    unittest.main()
