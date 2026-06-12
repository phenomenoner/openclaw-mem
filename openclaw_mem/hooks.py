"""Fail-open lifecycle hook helpers for host agents.

The hooks are intentionally small wrappers around JSONL observation capture and
Channel A pack production. They are safe to wire into Claude Code style hooks:
failures return JSON with ok=false but do not raise uncaught exceptions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from openclaw_mem.channel_a import run as run_channel_a
from openclaw_mem.cli import DEFAULT_DB


HOOK_RECEIPT_SCHEMA = "openclaw-mem.lifecycle-hook.receipt.v1"


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {"payload": parsed}


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def session_start(args: argparse.Namespace) -> dict[str, Any]:
    pack_path = Path(args.pack_path) if args.pack_path else Path(args.packs_dir) / args.agent / "latest.json"
    if not pack_path.exists():
        return {"schema": HOOK_RECEIPT_SCHEMA, "ok": True, "hook": "SessionStart", "packFound": False, "content": ""}
    text = pack_path.read_text(encoding="utf-8")
    return {"schema": HOOK_RECEIPT_SCHEMA, "ok": True, "hook": "SessionStart", "packFound": True, "packPath": str(pack_path), "content": text}


def post_tool_use(args: argparse.Namespace) -> dict[str, Any]:
    payload = _read_stdin_json()
    row = {
        "schema": "openclaw-mem.hook-observation.v1",
        "observationId": str(payload.get("observationId") or payload.get("id") or payload.get("toolUseId") or ""),
        "kind": str(payload.get("kind") or "tool.result"),
        "text": str(payload.get("text") or payload.get("summary") or payload.get("result") or "")[: int(args.max_chars)],
        "ts": payload.get("ts"),
        "agent": args.agent,
    }
    if not row["observationId"]:
        row["observationId"] = f"{args.agent}:hook:{abs(hash(json.dumps(payload, sort_keys=True, ensure_ascii=False)))}"
    _append_jsonl(Path(args.out_jsonl), row)
    return {"schema": HOOK_RECEIPT_SCHEMA, "ok": True, "hook": "PostToolUse", "outJsonl": args.out_jsonl, "observationId": row["observationId"]}


def session_end(args: argparse.Namespace) -> dict[str, Any]:
    producer_args = argparse.Namespace(
        db=args.db,
        input_jsonl=args.input_jsonl,
        packs_dir=args.packs_dir,
        agent=args.agent,
        query=args.query,
        limit=args.limit,
        budget_tokens=args.budget_tokens,
    )
    receipt = run_channel_a(producer_args)
    return {"schema": HOOK_RECEIPT_SCHEMA, "ok": True, "hook": "SessionEnd", "producer": receipt}


def install_config(args: argparse.Namespace) -> dict[str, Any]:
    config = {
        "schema": "openclaw-mem.lifecycle-hooks.config.v1",
        "SessionStart": ["openclaw-mem-hooks", "session-start", "--packs-dir", args.packs_dir, "--agent", args.agent],
        "PostToolUse": ["openclaw-mem-hooks", "post-tool-use", "--out-jsonl", args.out_jsonl, "--agent", args.agent],
        "SessionEnd": [
            "openclaw-mem-hooks",
            "session-end",
            "--db",
            args.db,
            "--input-jsonl",
            args.out_jsonl,
            "--packs-dir",
            args.packs_dir,
            "--agent",
            args.agent,
            "--query",
            args.query,
        ],
        "failOpen": True,
    }
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return config


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="openclaw-mem fail-open lifecycle hook helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("session-start")
    s.add_argument("--packs-dir", required=True)
    s.add_argument("--agent", default="main")
    s.add_argument("--pack-path")
    s.set_defaults(func=session_start)

    p = sub.add_parser("post-tool-use")
    p.add_argument("--out-jsonl", required=True)
    p.add_argument("--agent", default="main")
    p.add_argument("--max-chars", type=int, default=2000)
    p.set_defaults(func=post_tool_use)

    e = sub.add_parser("session-end")
    e.add_argument("--db", default=DEFAULT_DB)
    e.add_argument("--input-jsonl", required=True)
    e.add_argument("--packs-dir", required=True)
    e.add_argument("--agent", default="main")
    e.add_argument("--query", required=True)
    e.add_argument("--limit", type=int, default=8)
    e.add_argument("--budget-tokens", type=int, default=1200)
    e.set_defaults(func=session_end)

    i = sub.add_parser("install-config")
    i.add_argument("--db", default=DEFAULT_DB)
    i.add_argument("--out-jsonl", required=True)
    i.add_argument("--packs-dir", required=True)
    i.add_argument("--agent", default="main")
    i.add_argument("--query", default="current session memory")
    i.add_argument("--out")
    i.set_defaults(func=install_config)

    args = parser.parse_args(argv)
    try:
        _emit(args.func(args))
    except Exception as exc:
        _emit({"schema": HOOK_RECEIPT_SCHEMA, "ok": False, "error": str(exc)})


if __name__ == "__main__":
    main()
