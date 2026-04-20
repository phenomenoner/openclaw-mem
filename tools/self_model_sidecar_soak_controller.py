#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openclaw_mem.continuity_soak import SoakConfig, disable_cron_job, ensure_baseline, evaluate_soak, latest_receipt, run_one_cycle, write_receipt, write_status


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run one self-model-sidecar soak cycle and self-close after a healthy 72h window.")
    p.add_argument("--repo-root", default=str(REPO_ROOT))
    p.add_argument("--run-dir", default="/root/.openclaw/memory/openclaw-mem/self-model-sidecar")
    p.add_argument("--db", default=None)
    p.add_argument("--scope", default=None)
    p.add_argument("--session-id", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--persona-file", default=None)
    p.add_argument("--observations-file", default=None)
    p.add_argument("--episodes-file", default=None)
    p.add_argument("--cadence-seconds", type=int, default=300)
    p.add_argument("--target-hours", type=float, default=72.0)
    p.add_argument("--stale-factor", type=float, default=2.5)
    p.add_argument("--gap-factor", type=float, default=2.5)
    p.add_argument("--min-coverage-ratio", type=float, default=0.8)
    p.add_argument("--job-id", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        auto = run_one_cycle(
            repo_root=args.repo_root,
            run_dir=args.run_dir,
            db=args.db,
            scope=args.scope,
            session_id=args.session_id,
            limit=args.limit,
            persona_file=args.persona_file,
            observations_file=args.observations_file,
            episodes_file=args.episodes_file,
        )
    except Exception as exc:
        payload = {
            "schema": "openclaw-mem.self-model.soak-status.v0",
            "status": "warn",
            "reason": "autorun_failed",
            "warning": str(exc),
        }
        status_path = write_status(args.run_dir, payload)
        write_receipt(args.run_dir, {**payload, "status_path": status_path}, prefix="warning")
        print(f"WARNING self-model-sidecar soak blocked: autorun_failed, detail={str(exc)}")
        return 2

    if not bool(auto.get("ok")):
        payload = {
            "schema": "openclaw-mem.self-model.soak-status.v0",
            "status": "warn",
            "reason": "autorun_not_ok",
            "warning": str(auto.get("reason") or "continuity auto-run returned ok=false"),
            "autorun": auto,
        }
        status_path = write_status(args.run_dir, payload)
        write_receipt(args.run_dir, {**payload, "status_path": status_path}, prefix="warning")
        print(f"WARNING self-model-sidecar soak blocked: autorun_not_ok, detail={payload['warning']}")
        return 2

    runs = auto.get("runs") or []
    baseline = ensure_baseline(args.run_dir, runs[-1] if runs else None)
    summary = evaluate_soak(
        SoakConfig(
            run_dir=args.run_dir,
            cadence_seconds=args.cadence_seconds,
            target_hours=args.target_hours,
            stale_factor=args.stale_factor,
            gap_factor=args.gap_factor,
            min_coverage_ratio=args.min_coverage_ratio,
        ),
        baseline_started_at=baseline.get("started_at"),
    )
    summary["baseline"] = baseline
    summary["autorun"] = {
        "generated_at": auto.get("generated_at"),
        "ok": auto.get("ok"),
        "run_count": len(runs),
        "latest_receipt_path": (runs[-1].get("receipt_path") if runs else None),
    }
    status_path = write_status(args.run_dir, summary)

    if summary.get("status") == "hold":
        print("NO_REPLY")
        return 0

    if summary.get("status") == "warn":
        previous_warning = latest_receipt(args.run_dir, prefix="warning")
        warning_path = write_receipt(args.run_dir, {**summary, "status_path": status_path}, prefix="warning")
        if previous_warning and previous_warning.get("reason") == summary.get("reason"):
            print("NO_REPLY")
            return 0
        print(
            "WARNING self-model-sidecar soak blocked: "
            f"{summary.get('reason')}, window_hours={summary.get('window_hours')}, "
            f"coverage_ratio={summary.get('coverage_ratio')}, warning_path={warning_path}, "
            f"detail={summary.get('warning')}"
        )
        return 2

    disable_result = None
    disable_error = None
    if args.job_id:
        try:
            disable_result = disable_cron_job(args.job_id, workdir=args.repo_root)
        except Exception as exc:
            disable_error = str(exc)
    completion_payload = {**summary, "status_path": status_path, "cron_disable": disable_result, "cron_disable_error": disable_error}
    closure_path = write_receipt(args.run_dir, completion_payload, prefix="closure")
    message = (
        "COMPLETE self-model-sidecar 72h soak passed: "
        f"window_hours={summary.get('window_hours')}, coverage_ratio={summary.get('coverage_ratio')}, "
        f"receipt_count={summary.get('receipt_count')}, closure_path={closure_path}"
    )
    if disable_error:
        message += f", cron_disable_error={disable_error}"
    elif disable_result is not None:
        message += ", cron_disabled=true"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
