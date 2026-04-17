#!/usr/bin/env python3
"""Run the governed optimize-assist pipeline as one bounded worker.

Default posture is dry-run. Use --apply to allow bounded writes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_STATE_DIR = os.path.abspath(os.path.expanduser(os.getenv("OPENCLAW_STATE_DIR", "~/.openclaw")))
DEFAULT_DB = os.path.join(DEFAULT_STATE_DIR, "memory", "openclaw-mem.sqlite")
DEFAULT_RUNNER_ROOT = os.path.join(DEFAULT_STATE_DIR, "memory", "openclaw-mem", "optimize-assist-runner")
DEFAULT_CONTROLLER_STATE = "controller-state.json"
CONTROLLER_MODES = ("dry_run", "canary_apply", "auto_low_risk", "paused_regression")
FAMILY_NAMES = ("stale_candidate", "importance_downshift", "score_label_alignment")


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class RunnerError(RuntimeError):
    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_utc(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _run(argv: list[str]) -> CommandResult:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return CommandResult(argv=argv, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _load_json_text(label: str, raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception as e:
        raise RunnerError(f"{label} emitted invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise RunnerError(f"{label} emitted non-object JSON")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _candidate_family(item: dict[str, Any]) -> str:
    action = str(item.get("recommended_action") or item.get("action") or "").strip()
    patch = item.get("patch") if isinstance(item.get("patch"), dict) else {}
    if action == "set_stale_candidate":
        return "stale_candidate"
    if action == "adjust_importance_score":
        importance_patch = patch.get("importance") if isinstance(patch.get("importance"), dict) else {}
        reason_code = str(importance_patch.get("reason_code") or "").strip()
        if reason_code == "label_alignment":
            return "score_label_alignment"
        return "importance_downshift"
    return "unknown"


def _resolve_family_state(args: argparse.Namespace, prior_state: dict[str, Any]) -> dict[str, Any]:
    prior_family_state = prior_state.get("family_state") if isinstance(prior_state.get("family_state"), dict) else {}
    disable_families = {str(x).strip() for x in list(getattr(args, "disable_family", []) or []) if str(x).strip()}
    enable_families = {str(x).strip() for x in list(getattr(args, "enable_family", []) or []) if str(x).strip()}
    out: dict[str, Any] = {}
    for family in FAMILY_NAMES:
        previous = prior_family_state.get(family) if isinstance(prior_family_state.get(family), dict) else {}
        enabled = bool(previous.get("enabled", True))
        mode = str(previous.get("mode") or ("enabled" if enabled else "disabled")).strip() or ("enabled" if enabled else "disabled")
        reasons = [str(x) for x in list(previous.get("reasons") or []) if str(x)]
        if family in disable_families:
            enabled = False
            mode = "disabled"
            reasons = sorted(set(reasons + ["disabled_by_flag"]))
        if family in enable_families:
            enabled = True
            mode = "enabled"
            reasons = [reason for reason in reasons if reason != "disabled_by_flag"]
        out[family] = {
            "enabled": enabled,
            "mode": mode,
            "reasons": reasons,
        }
    return out


def _filter_governor_packet(
    governor_json: dict[str, Any],
    challenger_json: dict[str, Any],
    *,
    family_state: dict[str, Any],
    enforce_quarantine: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    out = json.loads(json.dumps(governor_json, ensure_ascii=False))
    items = out.get("items") if isinstance(out.get("items"), list) else []
    disagreements = challenger_json.get("disagreements") if isinstance(challenger_json.get("disagreements"), list) else []
    quarantined_candidate_ids = {
        str(item.get("candidate_id") or "")
        for item in disagreements
        if isinstance(item, dict) and bool(item.get("quarantine_recommended")) and str(item.get("candidate_id") or "")
    }
    challenged_families = {
        str(item.get("action_family") or "").strip()
        for item in disagreements
        if isinstance(item, dict) and bool(item.get("quarantine_recommended"))
    }

    blocked_by_family: dict[str, int] = {family: 0 for family in FAMILY_NAMES}
    blocked_by_quarantine = 0
    approved_after_filter = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        family = _candidate_family(item)
        item["action_family"] = family
        reasons = [str(x) for x in list(item.get("reasons") or []) if str(x)]
        family_slot = family_state.get(family) if isinstance(family_state.get(family), dict) else {}
        candidate_id = str(item.get("candidate_id") or "")
        family_quarantined = enforce_quarantine and family in challenged_families
        candidate_quarantined = enforce_quarantine and candidate_id in quarantined_candidate_ids
        if family in blocked_by_family and not bool(family_slot.get("enabled", True)):
            item["decision"] = "proposal_only"
            item["reasons"] = sorted(set(reasons + [f"family_disabled:{family}"]))
            blocked_by_family[family] += 1
            continue
        if family_quarantined or candidate_quarantined:
            item["decision"] = "proposal_only"
            quarantine_reason = f"challenger_quarantine:{family}" if family_quarantined else "challenger_quarantine:candidate"
            item["reasons"] = sorted(set(reasons + [quarantine_reason]))
            blocked_by_quarantine += 1
            continue
        if str(item.get("decision") or "") == "approved_for_apply":
            approved_after_filter += 1

    counts = out.get("counts") if isinstance(out.get("counts"), dict) else {}
    counts["approvedForApply"] = approved_after_filter
    counts["proposalOnly"] = sum(1 for item in items if isinstance(item, dict) and str(item.get("decision") or "") == "proposal_only")
    counts["blockedByFamily"] = sum(blocked_by_family.values())
    counts["blockedByChallengerQuarantine"] = blocked_by_quarantine
    out["counts"] = counts
    out["family_policy"] = {
        "state": family_state,
        "challenger_enforce_quarantine": bool(enforce_quarantine),
        "challenged_families": sorted(x for x in challenged_families if x),
        "quarantined_candidate_ids": sorted(x for x in quarantined_candidate_ids if x),
    }
    return out, blocked_by_family, {
        "challenged_families": sorted(x for x in challenged_families if x),
        "quarantined_candidate_ids": sorted(x for x in quarantined_candidate_ids if x),
        "blocked_by_quarantine": blocked_by_quarantine,
        "approved_after_filter": approved_after_filter,
    }


def _controller_state_path(args: argparse.Namespace) -> Path:
    raw = str(getattr(args, "controller_state_path", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(args.runner_root).expanduser() / DEFAULT_CONTROLLER_STATE


def _resolve_controller_mode(args: argparse.Namespace, state: dict[str, Any]) -> str:
    requested = str(getattr(args, "controller_mode", "") or "").strip()
    if requested in CONTROLLER_MODES:
        return requested
    stored = str(state.get("mode") or "").strip()
    if stored in CONTROLLER_MODES:
        return stored
    return "canary_apply" if bool(getattr(args, "allow_apply", False)) else "dry_run"


def _watchdog_window_hours(args: argparse.Namespace) -> int:
    try:
        return max(1, int(getattr(args, "watchdog_window_hours", 24) or 24))
    except Exception:
        return 24


def _collect_watchdog_stats(runner_root: Path, *, since_ts: datetime) -> dict[str, Any]:
    assist_root = runner_root / "assist-receipts"
    applied_runs = 0
    missing_effect_receipts = 0
    regressed_effect_items = 0
    effect_items_total = 0
    for path in assist_root.rglob("*.after.json"):
        payload = _load_json_file(path)
        if str(payload.get("kind") or "") != "openclaw-mem.optimize.assist.after.v1":
            continue
        ts = _parse_iso_utc(payload.get("ts"))
        if ts is None or ts < since_ts:
            continue
        if str(payload.get("result") or "") != "applied":
            continue
        applied_runs += 1
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
        effect_ref = str(artifacts.get("effect_ref") or "").strip()
        if not effect_ref:
            missing_effect_receipts += 1
            continue
        effect_path = Path(effect_ref).expanduser()
        effect_payload = _load_json_file(effect_path)
        if str(effect_payload.get("kind") or "") != "openclaw-mem.optimize.assist.effect-batch.v0":
            missing_effect_receipts += 1
            continue
        items = effect_payload.get("items") if isinstance(effect_payload.get("items"), list) else []
        effect_items_total += len(items)
        regressed_effect_items += sum(1 for item in items if isinstance(item, dict) and str(item.get("effect_summary") or "") == "regressed")
    return {
        "applied_runs": applied_runs,
        "missing_effect_receipts": missing_effect_receipts,
        "effect_items_total": effect_items_total,
        "regressed_effect_items": regressed_effect_items,
        "effect_receipt_missing_pct": round((missing_effect_receipts / applied_runs) * 100.0, 2) if applied_runs > 0 else 0.0,
    }


def _rollback_replay_gate(args: argparse.Namespace) -> dict[str, Any]:
    path_value = str(getattr(args, "rollback_replay_receipt", "") or "").strip()
    if not path_value:
        return {
            "present": False,
            "rollback_replay_pass": None,
            "reason": "missing_receipt",
        }
    payload = _load_json_file(Path(path_value).expanduser())
    passed = payload.get("rollback_replay_pass")
    if isinstance(passed, bool):
        return {
            "present": True,
            "rollback_replay_pass": passed,
            "reason": "receipt_loaded",
            "receipt_path": str(Path(path_value).expanduser()),
        }
    return {
        "present": True,
        "rollback_replay_pass": None,
        "reason": "invalid_receipt",
        "receipt_path": str(Path(path_value).expanduser()),
    }


def _evaluate_promotion_gates(
    args: argparse.Namespace,
    *,
    watchdog: dict[str, Any],
    verifier: Optional[dict[str, Any]] = None,
    challenger: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    path_value = str(getattr(args, "promotion_gate_receipt", "") or "").strip()
    payload = _load_json_file(Path(path_value).expanduser()) if path_value else {}
    manual_precision = payload.get("manual_review_sample_precision")
    repeated_miss_regression_pct = payload.get("repeated_miss_regression_pct")
    verifier_summary = verifier.get("summary") if isinstance((verifier or {}).get("summary"), dict) else {}
    rollback_replay_pass = payload.get("rollback_replay_pass")
    if rollback_replay_pass is None:
        rollback_replay_pass = verifier_summary.get("rollback_replay_pass")
    reasons: list[str] = []

    try:
        precision_ok = float(manual_precision) >= float(getattr(args, "promotion_min_manual_precision", 0.9) or 0.9)
    except Exception:
        precision_ok = False
        reasons.append("manual_review_sample_precision_missing")

    try:
        repeated_miss_ok = float(repeated_miss_regression_pct) <= float(getattr(args, "promotion_max_repeated_miss_regression_pct", 5.0) or 5.0)
    except Exception:
        repeated_miss_ok = False
        reasons.append("repeated_miss_regression_pct_missing")

    if not isinstance(rollback_replay_pass, bool):
        rollback_ok = False
        reasons.append("rollback_replay_pass_missing")
    else:
        rollback_ok = rollback_replay_pass is True
        if not rollback_ok:
            reasons.append("rollback_replay_failed")

    effect_missing_pct = float(verifier_summary.get("effect_receipt_missing_pct") if verifier_summary.get("effect_receipt_missing_pct") is not None else ((watchdog.get("stats") or {}).get("effect_receipt_missing_pct") or 0.0))
    effect_missing_ok = effect_missing_pct <= float(getattr(args, "watchdog_max_missing_effect_receipts_pct", 0.0) or 0.0)
    if not effect_missing_ok:
        reasons.append("effect_receipt_missing_pct_exceeded")

    cap_integrity_pass = verifier_summary.get("cap_integrity_pass")
    if cap_integrity_pass is False:
        reasons.append("verifier_cap_integrity_failed")

    challenger_counts = (challenger or {}).get("counts") if isinstance((challenger or {}).get("counts"), dict) else {}
    challenger_summary = (challenger or {}).get("summary") if isinstance((challenger or {}).get("summary"), dict) else {}
    challenger_disagreements = int(challenger_counts.get("disagreements") or 0)
    challenger_max_disagreements = int(getattr(args, "challenger_max_disagreements_for_promotion", 0) or 0)
    challenger_required = bool(getattr(args, "challenger_require_agreement_for_promotion", False))
    challenger_ok = True
    if challenger_required:
        challenger_ok = challenger_disagreements <= challenger_max_disagreements and bool(challenger_summary.get("agreement_pass", challenger_disagreements == 0))
        if challenger_disagreements > challenger_max_disagreements:
            reasons.append("challenger_disagreement_threshold_exceeded")
        if not bool(challenger_summary.get("agreement_pass", challenger_disagreements == 0)):
            reasons.append("challenger_agreement_required")

    passed = precision_ok and repeated_miss_ok and rollback_ok and effect_missing_ok and challenger_ok
    return {
        "receipt_present": bool(path_value),
        "receipt_path": str(Path(path_value).expanduser()) if path_value else None,
        "metrics": {
            "manual_review_sample_precision": manual_precision,
            "repeated_miss_regression_pct": repeated_miss_regression_pct,
            "rollback_replay_pass": rollback_replay_pass,
            "effect_receipt_missing_pct": effect_missing_pct,
            "cap_integrity_pass": cap_integrity_pass,
            "challenger_disagreements": challenger_disagreements,
            "challenger_agreement_pass": bool(challenger_summary.get("agreement_pass", challenger_disagreements == 0)),
        },
        "thresholds": {
            "manual_review_sample_precision_gte": float(getattr(args, "promotion_min_manual_precision", 0.9) or 0.9),
            "repeated_miss_regression_pct_lte": float(getattr(args, "promotion_max_repeated_miss_regression_pct", 5.0) or 5.0),
            "effect_receipt_missing_pct_lte": float(getattr(args, "watchdog_max_missing_effect_receipts_pct", 0.0) or 0.0),
            "challenger_disagreements_lte": challenger_max_disagreements,
        },
        "challenger": {
            "required_for_promotion": challenger_required,
            "receipt_present": challenger is not None,
            "agreement_pass": bool(challenger_summary.get("agreement_pass", challenger_disagreements == 0)),
            "promotion_ready": bool(challenger_summary.get("promotion_ready", challenger_disagreements == 0)),
            "disagreements": challenger_disagreements,
            "quarantine_recommended": bool(challenger_summary.get("quarantine_recommended", False)),
        },
        "native_verifier_present": verifier is not None,
        "passed": passed and cap_integrity_pass is not False,
        "reasons": sorted(set(reasons)),
    }


def _controller_counter(raw: Any, *, default: int = 0) -> int:
    try:
        return max(0, int(raw))
    except Exception:
        return default


def _evaluate_watchdog(args: argparse.Namespace, *, runner_root: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    since_ts = now - timedelta(hours=_watchdog_window_hours(args))
    stats = _collect_watchdog_stats(runner_root, since_ts=since_ts)
    rollback_gate = _rollback_replay_gate(args)
    reasons: list[str] = []
    if float(stats.get("effect_receipt_missing_pct") or 0.0) > float(getattr(args, "watchdog_max_missing_effect_receipts_pct", 0.0) or 0.0):
        reasons.append("missing_effect_receipts")
    if int(stats.get("regressed_effect_items") or 0) > int(getattr(args, "watchdog_max_regressed_effect_items", 0) or 0):
        reasons.append("quality_regression_detected")
    if rollback_gate.get("present") and rollback_gate.get("rollback_replay_pass") is False:
        reasons.append("rollback_replay_failed")
    if rollback_gate.get("present") and rollback_gate.get("rollback_replay_pass") is None:
        reasons.append("rollback_replay_receipt_invalid")
    return {
        "window_hours": _watchdog_window_hours(args),
        "stats": stats,
        "rollback_replay": rollback_gate,
        "pause_reasons": reasons,
        "should_pause": bool(reasons),
        "evaluated_at": _utcnow_iso(),
    }


def _build_verifier_cmd(args: argparse.Namespace) -> list[str]:
    return [
        args.python,
        "-m",
        "openclaw_mem",
        "optimize",
        "verifier-bundle",
        "--db",
        args.db,
        "--run-dir",
        str(Path(args.runner_root) / "assist-receipts"),
        "--window-hours",
        str(max(1, int(getattr(args, "watchdog_window_hours", 24) or 24))),
        "--top",
        str(max(1, int(args.top))),
        "--json",
    ]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run openclaw-mem optimize assist pipeline as one scheduled worker")
    p.add_argument("--python", default=sys.executable, help="Python executable to use (default: current interpreter)")
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path")
    p.add_argument("--runner-root", default=DEFAULT_RUNNER_ROOT, help="Root directory for runner receipts and packet files")
    p.add_argument("--operator", default="openclaw-cron", help="Operator label recorded in assist receipts")
    p.add_argument("--allow-apply", dest="allow_apply", action="store_true", help="Allow bounded apply instead of dry-run")
    p.add_argument("--approve-importance", dest="approve_importance", action="store_true", default=True, help="Approve bounded low-risk importance adjustments at governor stage (default: true)")
    p.add_argument("--no-approve-importance", dest="approve_importance", action="store_false", help="Keep low-risk importance adjustments as proposal_only")
    p.add_argument("--approve-stale", dest="approve_stale", action="store_true", default=True, help="Approve stale candidates at governor stage (default: true)")
    p.add_argument("--no-approve-stale", dest="approve_stale", action="store_false", help="Keep stale candidates as proposal_only")
    p.add_argument("--scope", default=None, help="Optional normalized detail.scope filter")
    p.add_argument("--limit", type=int, default=1000, help="Max observation rows to scan in evolution-review")
    p.add_argument("--stale-days", type=int, default=60, help="Staleness threshold in days")
    p.add_argument("--lifecycle-limit", type=int, default=200, help="Max lifecycle-shadow rows scanned")
    p.add_argument("--top", type=int, default=10, help="Max governed candidates emitted")
    p.add_argument("--challenger-policy-mode", default="strict_v1", help="Shadow challenger policy mode (default: strict_v1)")
    p.add_argument("--challenger-max-disagreement-clusters", type=int, default=10, help="Max disagreement clusters written into challenger receipts (default: 10)")
    p.add_argument("--challenger-enforce-quarantine", dest="challenger_enforce_quarantine", action="store_true", default=True, help="Fail closed by quarantining challenger-disagreed families/candidates before assist apply (default: true)")
    p.add_argument("--no-challenger-enforce-quarantine", dest="challenger_enforce_quarantine", action="store_false", help="Keep challenger lane advisory-only for apply filtering")
    p.add_argument("--challenger-require-agreement-for-promotion", action="store_true", help="Require challenger agreement before promotion can pass")
    p.add_argument("--challenger-max-disagreements-for-promotion", type=int, default=0, help="Promotion fails when challenger disagreements exceed this count (default: 0)")
    p.add_argument("--disable-family", action="append", choices=FAMILY_NAMES, default=[], help="Disable a bounded apply family at the controller level (repeatable)")
    p.add_argument("--enable-family", action="append", choices=FAMILY_NAMES, default=[], help="Re-enable a bounded apply family at the controller level (repeatable)")
    p.add_argument("--max-rows-per-run", type=int, default=5, help="Assist apply cap per run")
    p.add_argument("--max-rows-per-24h", type=int, default=20, help="Assist apply rolling 24h cap")
    p.add_argument("--max-importance-adjustments-per-run", type=int, default=3, help="Assist apply importance-adjustment cap per run")
    p.add_argument("--max-importance-adjustments-per-24h", type=int, default=10, help="Assist apply rolling 24h importance-adjustment cap")
    p.add_argument("--controller-mode", choices=CONTROLLER_MODES, default=None, help="Controller state machine mode override")
    p.add_argument("--controller-state-path", default=None, help="JSON path for persisted controller state (default: <runner-root>/controller-state.json)")
    p.add_argument("--watchdog-window-hours", type=int, default=24, help="Recent receipt window inspected by watchdog (default: 24)")
    p.add_argument("--watchdog-max-missing-effect-receipts-pct", type=float, default=0.0, help="Pause when missing effect receipt rate exceeds this pct (default: 0)")
    p.add_argument("--watchdog-max-regressed-effect-items", type=int, default=0, help="Pause when regressed effect items exceed this count (default: 0)")
    p.add_argument("--rollback-replay-receipt", default=None, help="Optional JSON receipt path with rollback_replay_pass bool for watchdog gating")
    p.add_argument("--promotion-gate-receipt", default=None, help="Optional JSON receipt path carrying promotion gate metrics")
    p.add_argument("--promote-when-gates-green", action="store_true", help="Promote next controller mode to auto_low_risk when promotion gates are green")
    p.add_argument("--promotion-min-manual-precision", type=float, default=0.9, help="Promotion gate threshold for manual review precision (default: 0.9)")
    p.add_argument("--promotion-max-repeated-miss-regression-pct", type=float, default=5.0, help="Promotion gate threshold for repeated miss regression pct (default: 5)")
    p.add_argument("--soak-cycles-for-auto-low-risk", type=int, default=3, help="Promotion requires at least this many consecutive green soak cycles (default: 3)")
    p.add_argument("--regression-strikes-for-demotion", type=int, default=2, help="Demote active modes when regression strikes reach this threshold (default: 2)")
    p.add_argument("--lane", default="observations.assist", help="Assist apply lane label")
    p.add_argument("--json", action="store_true", help="Emit machine-readable runner summary")
    return p


def _build_evolution_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [
        args.python,
        "-m",
        "openclaw_mem",
        "optimize",
        "evolution-review",
        "--db",
        args.db,
        "--limit",
        str(args.limit),
        "--stale-days",
        str(args.stale_days),
        "--lifecycle-limit",
        str(args.lifecycle_limit),
        "--top",
        str(args.top),
        "--json",
    ]
    if args.scope:
        cmd.extend(["--scope", args.scope])
    return cmd


def _build_governor_cmd(args: argparse.Namespace, evolution_path: Path) -> list[str]:
    cmd = [
        args.python,
        "-m",
        "openclaw_mem",
        "optimize",
        "governor-review",
        "--db",
        args.db,
        "--from-file",
        str(evolution_path),
        "--governor",
        args.operator,
        "--json",
    ]
    if args.approve_importance:
        cmd.append("--approve-importance")
    if args.approve_stale:
        cmd.append("--approve-stale")
    return cmd


def _build_challenger_cmd(args: argparse.Namespace, evolution_path: Path) -> list[str]:
    return [
        args.python,
        "-m",
        "openclaw_mem",
        "optimize",
        "challenger-review",
        "--db",
        args.db,
        "--from-file",
        str(evolution_path),
        "--policy-mode",
        str(getattr(args, "challenger_policy_mode", "strict_v1") or "strict_v1"),
        "--max-disagreement-clusters",
        str(int(getattr(args, "challenger_max_disagreement_clusters", 10) or 10)),
        "--top",
        str(args.top),
        "--json",
    ]


def _build_assist_cmd(args: argparse.Namespace, governor_path: Path) -> list[str]:
    cmd = [
        args.python,
        "-m",
        "openclaw_mem",
        "optimize",
        "assist-apply",
        "--db",
        args.db,
        "--from-file",
        str(governor_path),
        "--operator",
        args.operator,
        "--lane",
        args.lane,
        "--run-dir",
        str(Path(args.runner_root) / "assist-receipts"),
        "--max-rows-per-run",
        str(args.max_rows_per_run),
        "--max-rows-per-24h",
        str(args.max_rows_per_24h),
        "--max-importance-adjustments-per-run",
        str(args.max_importance_adjustments_per_run),
        "--max-importance-adjustments-per-24h",
        str(args.max_importance_adjustments_per_24h),
        "--json",
    ]
    if not args.allow_apply:
        cmd.append("--dry-run")
    return cmd


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    ts = _utcnow_iso()
    runner_root = Path(args.runner_root).expanduser()
    run_dir = runner_root / datetime.now(timezone.utc).strftime("%Y-%m-%d") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    controller_state_path = _controller_state_path(args)
    prior_controller_state = _load_json_file(controller_state_path)
    effective_controller_mode = _resolve_controller_mode(args, prior_controller_state)
    family_state = _resolve_family_state(args, prior_controller_state)
    allow_apply = effective_controller_mode in {"canary_apply", "auto_low_risk"}
    controller_receipt_path = run_dir / "controller.json"

    pre_watchdog = _evaluate_watchdog(args, runner_root=runner_root)
    if effective_controller_mode == "paused_regression":
        allow_apply = False
    elif pre_watchdog.get("should_pause"):
        effective_controller_mode = "paused_regression"
        allow_apply = False

    evolution_cmd = _build_evolution_cmd(args)
    evolution_res = _run(evolution_cmd)
    if evolution_res.returncode != 0:
        raise RunnerError(f"evolution-review failed: {evolution_res.stderr.strip() or evolution_res.stdout.strip()}")
    evolution_json = _load_json_text("evolution-review", evolution_res.stdout)
    evolution_path = run_dir / "evolution.json"
    _write_json(evolution_path, evolution_json)

    governor_cmd = _build_governor_cmd(args, evolution_path)
    governor_res = _run(governor_cmd)
    if governor_res.returncode != 0:
        raise RunnerError(f"governor-review failed: {governor_res.stderr.strip() or governor_res.stdout.strip()}")
    governor_json = _load_json_text("governor-review", governor_res.stdout)
    governor_path = run_dir / "governor.json"
    _write_json(governor_path, governor_json)

    challenger_cmd = _build_challenger_cmd(args, evolution_path)
    challenger_res = _run(challenger_cmd)
    if challenger_res.returncode != 0:
        raise RunnerError(f"challenger-review failed: {challenger_res.stderr.strip() or challenger_res.stdout.strip()}")
    challenger_json = _load_json_text("challenger-review", challenger_res.stdout)
    challenger_path = run_dir / "challenger.json"
    _write_json(challenger_path, challenger_json)

    filtered_governor_json, blocked_by_family, challenger_filter = _filter_governor_packet(
        governor_json,
        challenger_json,
        family_state=family_state,
        enforce_quarantine=bool(getattr(args, "challenger_enforce_quarantine", True)),
    )
    filtered_governor_path = run_dir / "governor-filtered.json"
    _write_json(filtered_governor_path, filtered_governor_json)

    assist_cmd = _build_assist_cmd(args, filtered_governor_path)
    if allow_apply:
        assist_cmd = [arg for arg in assist_cmd if arg != "--dry-run"]
    elif "--dry-run" not in assist_cmd:
        assist_cmd.append("--dry-run")
    assist_res = _run(assist_cmd)
    if assist_res.returncode != 0:
        raise RunnerError(f"assist-apply failed: {assist_res.stderr.strip() or assist_res.stdout.strip()}")
    assist_json = _load_json_text("assist-apply", assist_res.stdout)
    assist_path = run_dir / "assist-after.json"
    _write_json(assist_path, assist_json)

    verifier_cmd = _build_verifier_cmd(args)
    verifier_res = _run(verifier_cmd)
    if verifier_res.returncode != 0:
        raise RunnerError(f"verifier-bundle failed: {verifier_res.stderr.strip() or verifier_res.stdout.strip()}")
    verifier_json = _load_json_text("verifier-bundle", verifier_res.stdout)
    verifier_path = run_dir / "verifier.json"
    _write_json(verifier_path, verifier_json)

    post_watchdog = _evaluate_watchdog(args, runner_root=runner_root)
    promotion_gates = _evaluate_promotion_gates(args, watchdog=post_watchdog, verifier=verifier_json, challenger=challenger_json)
    prior_soak_green_cycles = _controller_counter(prior_controller_state.get('soak_green_cycles'))
    prior_regression_strikes = _controller_counter(prior_controller_state.get('regression_strikes'))
    if post_watchdog.get('should_pause'):
        soak_green_cycles = 0
        regression_strikes = prior_regression_strikes + 1
    elif promotion_gates.get('passed'):
        soak_green_cycles = prior_soak_green_cycles + 1
        regression_strikes = max(0, prior_regression_strikes - 1)
    else:
        soak_green_cycles = 0
        regression_strikes = prior_regression_strikes
    next_controller_mode = effective_controller_mode
    if post_watchdog.get("should_pause"):
        next_controller_mode = "paused_regression"
    elif regression_strikes >= int(getattr(args, 'regression_strikes_for_demotion', 2) or 2):
        if effective_controller_mode == 'auto_low_risk':
            next_controller_mode = 'canary_apply'
        elif effective_controller_mode == 'canary_apply':
            next_controller_mode = 'dry_run'
    elif bool(getattr(args, "promote_when_gates_green", False)) and promotion_gates.get("passed") and soak_green_cycles >= int(getattr(args, 'soak_cycles_for_auto_low_risk', 3) or 3):
        next_controller_mode = "auto_low_risk"
    elif effective_controller_mode == 'auto_low_risk' and not promotion_gates.get('passed'):
        next_controller_mode = 'canary_apply'

    verifier_summary = verifier_json.get("summary") if isinstance(verifier_json.get("summary"), dict) else {}
    challenger_summary = challenger_json.get("summary") if isinstance(challenger_json.get("summary"), dict) else {}
    horizons = {
        "short": {
            "status": "green" if not post_watchdog.get("should_pause") else "red",
            "pause_reasons": list(post_watchdog.get("pause_reasons") or []),
        },
        "medium": {
            "status": "green" if verifier_summary.get("cap_integrity_pass", True) and verifier_summary.get("rollback_replay_pass") is not False and bool(challenger_summary.get("agreement_pass", True)) else "red",
            "verifier": verifier_summary,
            "challenger": challenger_summary,
        },
        "soak": {
            "status": "green" if bool(promotion_gates.get("passed")) and soak_green_cycles >= int(getattr(args, 'soak_cycles_for_auto_low_risk', 3) or 3) else "hold",
            "soak_green_cycles": soak_green_cycles,
            "required_cycles": int(getattr(args, 'soak_cycles_for_auto_low_risk', 3) or 3),
        },
    }

    updated_family_state = json.loads(json.dumps(family_state, ensure_ascii=False))
    for family in challenger_filter.get("challenged_families", []):
        if family in updated_family_state and bool(getattr(args, "challenger_enforce_quarantine", True)):
            updated_family_state[family]["enabled"] = False
            updated_family_state[family]["mode"] = "quarantined"
            updated_family_state[family]["reasons"] = sorted(set(list(updated_family_state[family].get("reasons") or []) + ["challenger_quarantine"]))

    controller_state = {
        "kind": "openclaw-mem.optimize.assist.controller-state.v0",
        "updated_at": _utcnow_iso(),
        "mode": next_controller_mode,
        "previous_mode": str(prior_controller_state.get("mode") or "") or None,
        "requested_mode": str(getattr(args, "controller_mode", None) or "") or None,
        "effective_mode": effective_controller_mode,
        "family_state": updated_family_state,
        'soak_green_cycles': soak_green_cycles,
        'regression_strikes': regression_strikes,
        "horizons": horizons,
        "watchdog": post_watchdog,
        "promotion_gates": promotion_gates,
        "challenger": {
            "policy_mode": str(getattr(args, "challenger_policy_mode", "strict_v1") or "strict_v1"),
            "receipt_ref": str(challenger_path),
            "summary": challenger_json.get("summary") if isinstance(challenger_json.get("summary"), dict) else {},
            "counts": challenger_json.get("counts") if isinstance(challenger_json.get("counts"), dict) else {},
            "quarantine_filter": challenger_filter,
        },
        "last_run": {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "assist_result": assist_json.get("result"),
        },
    }
    _write_json(controller_state_path, controller_state)
    controller_receipt = {
        "kind": "openclaw-mem.optimize.assist.controller.v0",
        "ts": _utcnow_iso(),
        "run_id": run_id,
        "requested_mode": str(getattr(args, "controller_mode", None) or "") or None,
        "previous_mode": str(prior_controller_state.get("mode") or "") or None,
        "effective_mode": effective_controller_mode,
        "next_mode": next_controller_mode,
        "allow_apply": allow_apply,
        "family_state": updated_family_state,
        'soak_green_cycles': soak_green_cycles,
        'regression_strikes': regression_strikes,
        "horizons": horizons,
        "pre_watchdog": pre_watchdog,
        "post_watchdog": post_watchdog,
        "verifier": verifier_json,
        "promotion_gates": promotion_gates,
        "challenger": {
            "policy_mode": str(getattr(args, "challenger_policy_mode", "strict_v1") or "strict_v1"),
            "receipt_ref": str(challenger_path),
            "summary": challenger_json.get("summary") if isinstance(challenger_json.get("summary"), dict) else {},
            "counts": challenger_json.get("counts") if isinstance(challenger_json.get("counts"), dict) else {},
            "quarantine_filter": challenger_filter,
        },
        "controller_state_ref": str(controller_state_path),
    }
    _write_json(controller_receipt_path, controller_receipt)

    return {
        "kind": "openclaw-mem.optimize.assist-runner.v0",
        "ts": ts,
        "run_id": run_id,
        "mode": "apply" if allow_apply else "dry_run",
        "operator": args.operator,
        "db": args.db,
        "runner_root": str(runner_root),
        "controller": {
            "effective_mode": effective_controller_mode,
            "next_mode": next_controller_mode,
            "state_ref": str(controller_state_path),
            "receipt_ref": str(controller_receipt_path),
            "paused": next_controller_mode == "paused_regression",
            "promotion_gates_passed": bool(promotion_gates.get("passed")),
            'soak_green_cycles': soak_green_cycles,
            'regression_strikes': regression_strikes,
        },
        "artifacts": {
            "run_dir": str(run_dir),
            "evolution_packet": str(evolution_path),
            "governor_packet": str(governor_path),
            "governor_filtered_packet": str(filtered_governor_path),
            "challenger_packet": str(challenger_path),
            "assist_after": str(assist_path),
            "verifier_bundle": str(verifier_path),
            "controller": str(controller_receipt_path),
        },
        "counts": {
            "evolution_candidates": int(((evolution_json.get("counts") or {}).get("items") or 0)),
            "governor_approved": int(((governor_json.get("counts") or {}).get("approvedForApply") or 0)),
            "governor_approved_after_family_filter": int(((filtered_governor_json.get("counts") or {}).get("approvedForApply") or 0)),
            "challenger_disagreements": int(((challenger_json.get("counts") or {}).get("disagreements") or 0)),
            "assist_applied_rows": int(assist_json.get("applied_rows") or 0),
            "assist_skipped_rows": int(assist_json.get("skipped_rows") or 0),
        },
        "results": {
            "evolution_kind": evolution_json.get("kind"),
            "governor_kind": governor_json.get("kind"),
            "challenger_kind": challenger_json.get("kind"),
            "assist_kind": assist_json.get("kind"),
            "verifier_kind": verifier_json.get("kind"),
            "assist_result": assist_json.get("result"),
            "blocked_by_caps": list(assist_json.get("blocked_by_caps") or []),
            "blocked_by_family": blocked_by_family,
            "watchdog_pause_reasons": list((post_watchdog.get("pause_reasons") or [])),
            "promotion_gate_reasons": list((promotion_gates.get("reasons") or [])),
            "challenger_quarantine_recommended": bool(((challenger_json.get("summary") or {}).get("quarantine_recommended"))),
        },
        "commands": {
            "evolution_review": evolution_cmd,
            "governor_review": governor_cmd,
            "challenger_review": challenger_cmd,
            "assist_apply": assist_cmd,
            "verifier_bundle": verifier_cmd,
        },
    }


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run_pipeline(args)
    except RunnerError as e:
        error_payload = {
            "kind": "openclaw-mem.optimize.assist-runner.v0",
            "ts": _utcnow_iso(),
            "result": "aborted",
            "error": str(e),
        }
        print(json.dumps(error_payload, ensure_ascii=False, indent=2))
        return 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "openclaw-mem optimize assist runner "
            f"mode={payload['mode']} approved={payload['counts']['governor_approved']} "
            f"assist_result={payload['results']['assist_result']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
