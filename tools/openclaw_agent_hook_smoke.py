#!/usr/bin/env python3
"""Smoke-test OpenClaw agent production-path prompt hooks.

This verifier intentionally uses an explicit --session-id. Running
`openclaw agent --message ...` without --to/--session-id/--agent fails before a
turn is selected, which can look like a hook/runtime timeout in higher-level
harnesses.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOOK_MARKERS = (
    "registered before_prompt_build prompt hook",
    "registered before_agent_start prompt hook",
)


def _default_out_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path.home() / ".openclaw" / "workspace" / ".state" / "openclaw-agent-hook-smoke" / stamp


def _parse_json_or_none(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a non-delivering openclaw agent hook smoke with an explicit session id.")
    parser.add_argument("--session-id", default=None, help="Explicit verifier session id. Defaults to hook-smoke-<epoch>.")
    parser.add_argument("--message", default="ACK only", help="Message sent to the agent.")
    parser.add_argument("--timeout", type=int, default=45, help="openclaw agent --timeout seconds.")
    parser.add_argument("--wall-timeout", type=int, default=75, help="Subprocess wall timeout seconds.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Directory for stdout/stderr/receipt artifacts.")
    parser.add_argument("--openclaw-bin", default="openclaw", help="OpenClaw CLI binary.")
    parser.add_argument("--require-hook-marker", action="store_true", help="Fail if stderr does not show a prompt-hook registration marker.")
    parser.add_argument("--json", action="store_true", help="Emit receipt JSON only.")
    args = parser.parse_args(argv)

    session_id = args.session_id or f"hook-smoke-{int(time.time())}"
    out_dir = args.out_dir or _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = out_dir / "stdout.json"
    stderr_path = out_dir / "stderr.log"
    receipt_path = out_dir / "receipt.json"

    cmd = [
        args.openclaw_bin,
        "agent",
        "--session-id",
        session_id,
        "--message",
        args.message,
        "--json",
        "--timeout",
        str(args.timeout),
    ]

    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=args.wall_timeout, check=False)
        duration_ms = int((time.monotonic() - started) * 1000)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        proc = None
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
    else:
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")

    parsed = _parse_json_or_none(stdout)
    hook_markers = [marker for marker in HOOK_MARKERS if marker in stderr]
    agent_status = parsed.get("status") if isinstance(parsed, dict) else None
    payload_text = ""
    try:
        payload_text = str(parsed["result"]["payloads"][0].get("text") or "") if isinstance(parsed, dict) else ""
    except Exception:
        payload_text = ""

    ok = (not timed_out) and proc is not None and proc.returncode == 0 and agent_status == "ok" and bool(payload_text.strip())
    if args.require_hook_marker:
        ok = ok and bool(hook_markers)

    receipt = {
        "schema": "openclaw-mem.openclaw-agent-hook-smoke.v0",
        "ok": ok,
        "session_id": session_id,
        "duration_ms": duration_ms,
        "timed_out": timed_out,
        "returncode": None if proc is None else proc.returncode,
        "agent_status": agent_status,
        "payload_text_preview": payload_text[:80],
        "hook_markers": hook_markers,
        "required_hook_marker": bool(args.require_hook_marker),
        "artifacts": {
            "out_dir": str(out_dir),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "receipt": str(receipt_path),
        },
        "command": cmd,
        "note": "Uses --session-id explicitly so the CLI selects a non-delivering verifier session before prompt hooks run.",
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(f"ok={str(ok).lower()} session_id={session_id} duration_ms={duration_ms} out_dir={out_dir}")
        if not ok:
            print(f"receipt={receipt_path}", file=sys.stderr)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
