#!/usr/bin/env python3
"""Escape a text file for embedding into JSON config (e.g., OpenClaw cron agentTurn message).

Why: OpenClaw cron examples in this repo are often JSON. Multi-line prompt messages are easier
to maintain as normal text/markdown files, then JSON-escape at the last mile.

Usage:
  python3 scripts/json_escape.py docs/snippets/openclaw-agentturn-message.watchdog-readonly.md
  python3 scripts/json_escape.py --wrap object --key message docs/snippets/openclaw-agentturn-message.watchdog-readonly.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="json_escape.py",
        description="JSON-escape a text/markdown file for copy/paste into JSON config.",
    )
    ap.add_argument("path", help="Path to the input text/markdown file")
    ap.add_argument(
        "--wrap",
        choices=["string", "object"],
        default="string",
        help="Emit a JSON string (default) or an object {key: <string>}.",
    )
    ap.add_argument(
        "--key",
        default="message",
        help="Key name when --wrap object is used (default: message).",
    )
    ap.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation when --wrap object is used (default: 2).",
    )
    args = ap.parse_args()

    text = Path(args.path).read_text(encoding="utf-8")

    if args.wrap == "string":
        print(json.dumps(text))
        return

    obj = {args.key: text}
    print(json.dumps(obj, indent=args.indent, ensure_ascii=False))


if __name__ == "__main__":
    main()
