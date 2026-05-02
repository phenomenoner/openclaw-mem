#!/usr/bin/env python3
"""Deterministic Self Curator controller entrypoint for cron-runner.

This wrapper keeps cron shape stable and puts path/default policy in one place.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Run openclaw-mem Self Curator controller")
    p.add_argument("--repo", default="/root/.openclaw/workspace/openclaw-mem")
    p.add_argument("--workspace-root", default="/root/.openclaw/workspace")
    p.add_argument("--skill-root", default="/root/.openclaw/workspace/skills")
    p.add_argument("--out-root", default="/root/.openclaw/workspace/.state/self-curator/controller-runs")
    p.add_argument("--mode", choices=["dry_run", "unattended_apply"], default="unattended_apply")
    p.add_argument("--max-mutations", type=int, default=5)
    p.add_argument("--cron-output", action="store_true", help="Emit NO_REPLY on no-op, NEEDS_CK summary when changes are applied")
    args = p.parse_args()

    repo = Path(args.repo)
    cmd = [
        "uv",
        "run",
        "openclaw-mem",
        "self-curator",
        "controller",
        "--skill-root",
        args.skill_root,
        "--workspace-root",
        args.workspace_root,
        "--out-root",
        args.out_root,
        "--mode",
        args.mode,
        "--max-mutations",
        str(args.max_mutations),
        "--json",
    ]
    proc = subprocess.run(cmd, cwd=repo, text=True, capture_output=True)
    if proc.returncode != 0:
        print(json.dumps({"ok": False, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}, ensure_ascii=False, indent=2))
        raise SystemExit(proc.returncode)
    payload = json.loads(proc.stdout)
    if args.cron_output:
        writes = int(payload.get("writes_performed") or 0)
        if writes <= 0:
            print("NO_REPLY")
        else:
            print(
                "NEEDS_CK: Self Curator unattended_apply changed "
                f"{writes} file(s); report={payload.get('report_path')} rollback={payload.get('apply_receipt_path')}"
            )
        return
    print(json.dumps({"ok": True, "controller": payload}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
