from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .self_model_sidecar import compare_snapshots, load_snapshot

STATUS_SCHEMA = "openclaw-mem.self-model.soak-status.v0"


@dataclass
class SoakConfig:
    run_dir: str
    cadence_seconds: int = 300
    target_hours: float = 72.0
    stale_factor: float = 2.5
    gap_factor: float = 2.5
    min_coverage_ratio: float = 0.8


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _soak_dir(run_dir: str) -> Path:
    root = Path(run_dir)
    path = root / "soak"
    path.mkdir(parents=True, exist_ok=True)
    return path


def baseline_path(run_dir: str) -> Path:
    return _soak_dir(run_dir) / "baseline.json"


def load_baseline(run_dir: str) -> Optional[Dict[str, Any]]:
    path = baseline_path(run_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_baseline(run_dir: str, latest_receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    existing = load_baseline(run_dir)
    if existing:
        return existing
    started_at = None
    snapshot_id = None
    if latest_receipt:
        started_at = latest_receipt.get("generated_at")
        snapshot_id = latest_receipt.get("snapshot_id")
    payload = {
        "schema": STATUS_SCHEMA,
        "started_at": started_at or _utcnow().isoformat(),
        "snapshot_id": snapshot_id,
    }
    path = baseline_path(run_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["path"] = str(path)
    return payload


def _iter_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    items: List[Dict[str, Any]] = []
    for file in sorted(path.glob("*.json")):
        try:
            items.append(json.loads(file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return items


def iter_autorun_receipts(run_dir: str) -> List[Dict[str, Any]]:
    receipts = _iter_json(Path(run_dir) / "autorun")
    receipts.sort(key=lambda item: str(item.get("generated_at") or ""))
    return receipts


def _is_benign_role_shift(before: Dict[str, Any], after: Dict[str, Any], diff: Dict[str, Any]) -> bool:
    changed = list(diff.get("changed") or [])
    if not changed or diff.get("added") or diff.get("removed"):
        return False
    risk_flags = list(diff.get("risk_flags") or [])
    if not risk_flags:
        return False

    before_map = {str(item.get("id")): item for item in list(before.get("attachments") or [])}
    after_map = {str(item.get("id")): item for item in list(after.get("attachments") or [])}
    changed_map = {str(item.get("id")): item for item in changed}

    flagged_ids = []
    for flag in risk_flags:
        head, _, rest = str(flag).partition(":")
        if head not in {"large_delta", "state_transition"}:
            return False
        if head == "large_delta":
            stance_id = rest
        else:
            parts = rest.split(":") if rest else []
            stance_id = ":".join(parts[:2]) if len(parts) >= 2 else ""
        if not stance_id.startswith("role:"):
            return False
        flagged_ids.append(stance_id)

    for stance_id in set(flagged_ids):
        item = changed_map.get(stance_id) or {}
        before_item = before_map.get(stance_id) or {}
        after_item = after_map.get(stance_id) or {}
        if int(before_item.get("contradiction_hits") or 0) > 0:
            return False
        if int(after_item.get("contradiction_hits") or 0) > 0:
            return False
        if str(item.get("before_state") or "") == "contested" or str(item.get("after_state") or "") == "contested":
            return False
    return True


def compute_drift_summary(run_dir: str, receipts: List[Dict[str, Any]]) -> Dict[str, Any]:
    snapshots_dir = Path(run_dir) / "snapshots"
    suspicious_pairs: List[Dict[str, Any]] = []
    ignored_pairs: List[Dict[str, Any]] = []
    checked_pairs = 0
    previous_snapshot: Optional[Dict[str, Any]] = None
    previous_receipt: Optional[Dict[str, Any]] = None
    for receipt in receipts:
        snapshot_id = receipt.get("snapshot_id")
        if not snapshot_id:
            continue
        snapshot_path = snapshots_dir / f"{snapshot_id}.json"
        if not snapshot_path.exists():
            continue
        current_snapshot = load_snapshot(str(snapshot_path))
        if previous_snapshot is not None and previous_receipt is not None:
            diff = compare_snapshots(previous_snapshot, current_snapshot)
            checked_pairs += 1
            if diff.get("drift_class") == "suspicious":
                pair = {
                    "from_snapshot_id": previous_receipt.get("snapshot_id"),
                    "to_snapshot_id": receipt.get("snapshot_id"),
                    "risk_flags": diff.get("risk_flags") or [],
                    "summary": diff.get("summary") or {},
                }
                if _is_benign_role_shift(previous_snapshot, current_snapshot, diff):
                    pair["ignored_reason"] = "role_shift_without_contradiction"
                    ignored_pairs.append(pair)
                else:
                    suspicious_pairs.append(pair)
        previous_snapshot = current_snapshot
        previous_receipt = receipt
    return {
        "checked_pairs": checked_pairs,
        "suspicious_pairs": suspicious_pairs,
        "suspicious_count": len(suspicious_pairs),
        "ignored_pairs": ignored_pairs,
        "ignored_count": len(ignored_pairs),
    }


def evaluate_soak(config: SoakConfig, *, now: Optional[datetime] = None, baseline_started_at: Optional[str] = None) -> Dict[str, Any]:
    now_dt = (now or _utcnow()).astimezone(timezone.utc)
    receipts = iter_autorun_receipts(config.run_dir)
    if baseline_started_at:
        baseline_dt = _parse_ts(baseline_started_at)
        receipts = [item for item in receipts if item.get("generated_at") and _parse_ts(item["generated_at"]) >= baseline_dt]
    summary: Dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "generated_at": now_dt.isoformat(),
        "run_dir": config.run_dir,
        "cadence_seconds": int(config.cadence_seconds),
        "target_hours": float(config.target_hours),
        "min_coverage_ratio": float(config.min_coverage_ratio),
        "receipt_count": len(receipts),
        "status": "hold",
        "reason": "waiting_for_receipts",
        "window_hours": 0.0,
        "coverage_ratio": 0.0,
        "largest_gap_seconds": 0.0,
        "stale_seconds": None,
        "latest_generated_at": None,
        "first_generated_at": None,
        "warning": None,
    }
    if not receipts:
        return summary

    timestamps = [_parse_ts(item["generated_at"]) for item in receipts if item.get("generated_at")]
    if not timestamps:
        summary["status"] = "warn"
        summary["reason"] = "receipts_missing_generated_at"
        summary["warning"] = "autorun receipts exist but generated_at is missing"
        return summary

    first_ts = min(timestamps)
    latest_ts = max(timestamps)
    window_seconds = max(0.0, (latest_ts - first_ts).total_seconds())
    stale_seconds = max(0.0, (now_dt - latest_ts).total_seconds())
    gaps = [max(0.0, (b - a).total_seconds()) for a, b in zip(timestamps, timestamps[1:])]
    largest_gap_seconds = max(gaps) if gaps else 0.0
    expected_runs = max(1, int(math.floor(window_seconds / max(1, int(config.cadence_seconds)))) + 1)
    coverage_ratio = min(1.0, len(receipts) / expected_runs) if expected_runs else 0.0

    summary.update(
        {
            "window_hours": round(window_seconds / 3600.0, 3),
            "coverage_ratio": round(coverage_ratio, 3),
            "largest_gap_seconds": round(largest_gap_seconds, 3),
            "stale_seconds": round(stale_seconds, 3),
            "latest_generated_at": latest_ts.isoformat(),
            "first_generated_at": first_ts.isoformat(),
            "expected_runs": expected_runs,
        }
    )

    gap_limit = float(config.cadence_seconds) * float(config.gap_factor)
    stale_limit = float(config.cadence_seconds) * float(config.stale_factor)
    if stale_seconds > stale_limit:
        summary["status"] = "warn"
        summary["reason"] = "stale_autorun"
        summary["warning"] = f"latest autorun receipt is stale by {int(stale_seconds)}s"
        return summary
    if largest_gap_seconds > gap_limit:
        summary["status"] = "warn"
        summary["reason"] = "receipt_gap"
        summary["warning"] = f"largest autorun receipt gap {int(largest_gap_seconds)}s exceeds limit {int(gap_limit)}s"
        return summary
    if coverage_ratio < float(config.min_coverage_ratio):
        summary["status"] = "warn"
        summary["reason"] = "coverage_drop"
        summary["warning"] = f"receipt coverage ratio {coverage_ratio:.3f} fell below floor {config.min_coverage_ratio:.3f}"
        return summary

    drift = compute_drift_summary(config.run_dir, receipts)
    summary["drift"] = drift
    if int(drift.get("suspicious_count") or 0) > 0:
        summary["status"] = "warn"
        summary["reason"] = "suspicious_drift"
        summary["warning"] = f"found {int(drift.get('suspicious_count') or 0)} suspicious drift pair(s) during soak"
        return summary

    if window_seconds >= float(config.target_hours) * 3600.0:
        summary["status"] = "complete"
        summary["reason"] = "target_window_satisfied"
        return summary

    summary["status"] = "hold"
    summary["reason"] = "window_incomplete"
    return summary


def write_status(run_dir: str, payload: Dict[str, Any]) -> str:
    soak_dir = _soak_dir(run_dir)
    path = soak_dir / "status.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def write_receipt(run_dir: str, payload: Dict[str, Any], *, prefix: str) -> str:
    soak_dir = _soak_dir(run_dir)
    ts = payload.get("generated_at") or _utcnow().isoformat()
    safe = str(ts).replace(":", "").replace("+", "_").replace("-", "")
    path = soak_dir / f"{prefix}-{safe}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def latest_receipt(run_dir: str, *, prefix: str) -> Optional[Dict[str, Any]]:
    soak_dir = _soak_dir(run_dir)
    files = sorted(soak_dir.glob(f"{prefix}-*.json"))
    if not files:
        return None
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    payload["path"] = str(files[-1])
    return payload


def run_one_cycle(*, repo_root: str, run_dir: str, db: Optional[str] = None, scope: Optional[str] = None, session_id: Optional[str] = None, limit: int = 50, persona_file: Optional[str] = None, observations_file: Optional[str] = None, episodes_file: Optional[str] = None) -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "openclaw_mem", "continuity", "auto-run", "--cycles", "1", "--run-dir", run_dir, "--limit", str(limit), "--json"]
    if db:
        cmd.extend(["--db", db])
    if scope:
        cmd.extend(["--scope", scope])
    if session_id:
        cmd.extend(["--session-id", session_id])
    if persona_file:
        cmd.extend(["--persona-file", persona_file])
    if observations_file:
        cmd.extend(["--observations-file", observations_file])
    if episodes_file:
        cmd.extend(["--episodes-file", episodes_file])
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"continuity auto-run exited {proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"continuity auto-run returned non-JSON stdout: {proc.stdout[:300]}") from exc


def disable_cron_job(job_id: str, *, workdir: str) -> Dict[str, Any]:
    proc = subprocess.run(["openclaw", "cron", "disable", job_id, "--json"], cwd=workdir, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"openclaw cron disable exited {proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"openclaw cron disable returned non-JSON stdout: {proc.stdout[:300]}") from exc
