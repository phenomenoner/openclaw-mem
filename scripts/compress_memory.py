#!/usr/bin/env python3
"""
Compress daily memory notes into MEMORY.md using OpenAI API.
Usage: python3 scripts/compress_memory.py [YYYY-MM-DD]
Defaults to yesterday's date if no argument provided.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
DEFAULT_MODEL = os.environ.get("OPENCLAW_MEM_MODEL", "gpt-4.1")
DEFAULT_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_MAX_TOKENS = int(os.environ.get("OPENCLAW_MEM_MAX_TOKENS", "700"))
DEFAULT_TEMPERATURE = float(os.environ.get("OPENCLAW_MEM_TEMPERATURE", "0.2"))
WORKSPACE = Path(__file__).resolve().parents[1]
MEMORY_DIR = WORKSPACE / "memory"
MEMORY_FILE = WORKSPACE / "MEMORY.md"
PROMPT_FILE = WORKSPACE / "scripts/prompts/compress_memory.txt"


def call_openai(prompt: str, model: str, base_url: str, max_tokens: int, temperature: float) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise memory compressor."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"OpenAI API error ({e.code}): {err_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error calling OpenAI API: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(body)
        content = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Error parsing OpenAI response: {e}", file=sys.stderr)
        print(body[:2000], file=sys.stderr)
        sys.exit(1)

    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="Compress daily notes to MEMORY.md")
    parser.add_argument("date", nargs="?", help="Date to process (YYYY-MM-DD)", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model (default: %(default)s)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI API base URL")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="Max output tokens")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Sampling temperature")
    parser.add_argument("--memory-file", default=str(MEMORY_FILE), help="MEMORY.md path")
    parser.add_argument("--prompt-file", default=str(PROMPT_FILE), help="Prompt file path")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    args = parser.parse_args()

    # Determine target date
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    target_file = MEMORY_DIR / f"{target_date}.md"

    if not target_file.exists():
        msg = f"No daily note found for {target_date} ({target_file})"
        if args.json:
            print(json.dumps({"ok": True, "skipped": True, "reason": msg, "date": target_date}))
        else:
            print(f"Skipping: {msg}")
        return

    # Check if already summarized
    memory_path = Path(args.memory_file)
    if memory_path.exists():
        mem_content = memory_path.read_text(encoding="utf-8")
        if f"## {target_date} Summary" in mem_content:
            msg = f"{target_date} already appears in {memory_path}"
            if args.json:
                print(json.dumps({"ok": True, "skipped": True, "reason": msg, "date": target_date}))
            else:
                print(f"Skipping: {msg}")
            return

    prompt_path = Path(args.prompt_file)
    if not prompt_path.exists():
        print(f"Error: Prompt file missing at {prompt_path}", file=sys.stderr)
        sys.exit(1)

    daily_content = target_file.read_text(encoding="utf-8")
    if not daily_content.strip():
        msg = "Daily note is empty"
        if args.json:
            print(json.dumps({"ok": True, "skipped": True, "reason": msg, "date": target_date}))
        else:
            print(f"Skipping: {msg}")
        return

    base_prompt = prompt_path.read_text(encoding="utf-8")
    full_prompt = f"{base_prompt}\n\n# Daily Notes ({target_date})\n{daily_content}"

    summary = call_openai(
        full_prompt,
        model=args.model,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    if not summary:
        print("Error: Empty summary returned", file=sys.stderr)
        sys.exit(1)

    header = f"## {target_date} Summary"
    entry = f"\n\n{header}\n{summary}"

    if args.dry_run:
        if args.json:
            print(json.dumps({"ok": True, "dry_run": True, "date": target_date, "summary": summary}))
        else:
            print("--- DRY RUN OUTPUT ---")
            print(entry)
        return

    with memory_path.open("a", encoding="utf-8") as f:
        f.write(entry)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "date": target_date,
                    "appended": True,
                    "memory_file": str(memory_path),
                    "summary": summary,
                }
            )
        )
    else:
        print(f"✅ Appended summary to {memory_path}")


if __name__ == "__main__":
    main()
