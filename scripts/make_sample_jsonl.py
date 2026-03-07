"""Generate a tiny synthetic JSONL file for openclaw-mem quickstart demos.

This is intentionally synthetic (no private/user data).

Usage:
  python3 ./scripts/make_sample_jsonl.py --out ./sample.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="sample.jsonl", help="Output path (default: sample.jsonl)")
    args = ap.parse_args()

    rows = [
        {
            "ts": "2026-02-05T10:00:00Z",
            "kind": "tool",
            "tool_name": "web_search",
            "summary": "searched for OpenClaw",
            "detail": {"results": 5},
        },
        {
            "ts": "2026-02-05T10:01:00Z",
            "kind": "tool",
            "tool_name": "web_fetch",
            "summary": "fetched openclaw.ai",
            "detail": {"ok": True},
        },
        {
            "ts": "2026-02-05T10:02:00Z",
            "kind": "tool",
            "tool_name": "exec",
            "summary": "ran git status",
            "detail": {"exit_code": 0},
        },
    ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
