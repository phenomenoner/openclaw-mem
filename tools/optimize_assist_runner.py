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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_STATE_DIR = os.path.abspath(os.path.expanduser(os.getenv("OPENCLAW_STATE_DIR", "~/.openclaw")))
DEFAULT_DB = os.path.join(DEFAULT_STATE_DIR, "memory", "openclaw-mem.sqlite")
DEFAULT_RUNNER_ROOT = os.path.join(DEFAULT_STATE_DIR, "memory", "openclaw-mem", "optimize-assist-runner")


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
    p.add_argument("--max-rows-per-run", type=int, default=5, help="Assist apply cap per run")
    p.add_argument("--max-rows-per-24h", type=int, default=20, help="Assist apply rolling 24h cap")
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
        "--json",
    ]
    if not args.allow_apply:
        cmd.append("--dry-run")
    return cmd


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    ts = _utcnow_iso()
    run_dir = Path(args.runner_root).expanduser() / datetime.now(timezone.utc).strftime("%Y-%m-%d") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

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

    assist_cmd = _build_assist_cmd(args, governor_path)
    assist_res = _run(assist_cmd)
    if assist_res.returncode != 0:
        raise RunnerError(f"assist-apply failed: {assist_res.stderr.strip() or assist_res.stdout.strip()}")
    assist_json = _load_json_text("assist-apply", assist_res.stdout)
    assist_path = run_dir / "assist-after.json"
    _write_json(assist_path, assist_json)

    return {
        "kind": "openclaw-mem.optimize.assist-runner.v0",
        "ts": ts,
        "run_id": run_id,
        "mode": "apply" if args.allow_apply else "dry_run",
        "operator": args.operator,
        "db": args.db,
        "runner_root": str(Path(args.runner_root).expanduser()),
        "artifacts": {
            "run_dir": str(run_dir),
            "evolution_packet": str(evolution_path),
            "governor_packet": str(governor_path),
            "assist_after": str(assist_path),
        },
        "counts": {
            "evolution_candidates": int(((evolution_json.get("counts") or {}).get("items") or 0)),
            "governor_approved": int(((governor_json.get("counts") or {}).get("approvedForApply") or 0)),
            "assist_applied_rows": int(assist_json.get("applied_rows") or 0),
            "assist_skipped_rows": int(assist_json.get("skipped_rows") or 0),
        },
        "results": {
            "evolution_kind": evolution_json.get("kind"),
            "governor_kind": governor_json.get("kind"),
            "assist_kind": assist_json.get("kind"),
            "assist_result": assist_json.get("result"),
            "blocked_by_caps": list(assist_json.get("blocked_by_caps") or []),
        },
        "commands": {
            "evolution_review": evolution_cmd,
            "governor_review": governor_cmd,
            "assist_apply": assist_cmd,
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
