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
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class CompressError(Exception):
    """Raised when compression fails."""
    pass


class OpenAIClient:
    """Abstraction for OpenAI API calls (mockable for tests)."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", extra_headers: Optional[dict[str, str]] = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.extra_headers = extra_headers or {}

    def complete(self, prompt: str, model: str, max_tokens: int, temperature: float) -> str:
        url = self.base_url + "/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a precise memory compressor."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise CompressError(f"OpenAI API error ({e.code}): {err_body}") from e
        except Exception as e:
            raise CompressError(f"Error calling OpenAI API: {e}") from e

        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise CompressError(f"Error parsing OpenAI response: {e}\\n{body[:2000]}") from e

        if not content:
            raise CompressError("Empty summary returned from API")

        return content


def validate_date(date_str: str) -> str:
    """Validate date format (YYYY-MM-DD) and return normalized string."""
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        return parsed.strftime("%Y-%m-%d")
    except ValueError as e:
        raise CompressError(f"Invalid date format '{date_str}': expected YYYY-MM-DD") from e


def atomic_append(file_path: Path, content: str) -> None:
    """Append content to file atomically (write-to-temp + rename)."""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content
    existing = file_path.read_text(encoding="utf-8") if file_path.exists() else ""

    # Write combined content to temp file
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=file_path.parent,
        delete=False,
        prefix=".tmp_",
        suffix=".md",
    ) as tmp:
        tmp.write(existing + content)
        tmp_path = Path(tmp.name)

    # Atomic rename
    tmp_path.replace(file_path)


def compress_daily_note(
    date: str,
    memory_dir: Path,
    memory_file: Path,
    prompt_file: Path,
    client: OpenAIClient,
    model: str,
    max_tokens: int,
    temperature: float,
    dry_run: bool = False,
) -> dict:
    """Compress a daily note and optionally append to MEMORY.md."""
    target_date = validate_date(date)
    target_file = memory_dir / f"{target_date}.md"

    if not target_file.exists():
        return {
            "ok": True,
            "skipped": True,
            "reason": f"No daily note found for {target_date}",
            "date": target_date,
        }

    # Check if already summarized
    if memory_file.exists():
        mem_content = memory_file.read_text(encoding="utf-8")
        if f"## {target_date} Summary" in mem_content:
            return {
                "ok": True,
                "skipped": True,
                "reason": f"{target_date} already appears in {memory_file}",
                "date": target_date,
            }

    if not prompt_file.exists():
        raise CompressError(f"Prompt file missing at {prompt_file}")

    daily_content = target_file.read_text(encoding="utf-8")
    if not daily_content.strip():
        return {
            "ok": True,
            "skipped": True,
            "reason": "Daily note is empty",
            "date": target_date,
        }

    base_prompt = prompt_file.read_text(encoding="utf-8")
    full_prompt = f"{base_prompt}\\n\\n# Daily Notes ({target_date})\\n{daily_content}"

    summary = client.complete(full_prompt, model, max_tokens, temperature)

    header = f"## {target_date} Summary"
    entry = f"\\n\\n{header}\\n{summary}"

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "date": target_date,
            "summary": summary,
        }

    atomic_append(memory_file, entry)

    return {
        "ok": True,
        "date": target_date,
        "appended": True,
        "memory_file": str(memory_file),
        "summary": summary,
    }


def main() -> None:
    # Configuration defaults (overridable via env vars)
    workspace = Path(os.environ.get("OPENCLAW_MEM_WORKSPACE", Path(__file__).resolve().parents[1]))
    default_model = os.environ.get("OPENCLAW_MEM_MODEL", "gpt-4.1")
    default_base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    default_max_tokens = int(os.environ.get("OPENCLAW_MEM_MAX_TOKENS", "700"))
    default_temperature = float(os.environ.get("OPENCLAW_MEM_TEMPERATURE", "0.2"))
    default_memory_dir = workspace / "memory"
    default_memory_file = workspace / "MEMORY.md"
    default_prompt_file = workspace / "scripts/prompts/compress_memory.txt"

    parser = argparse.ArgumentParser(
        description="Compress daily notes to MEMORY.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compress yesterday's note
  python scripts/compress_memory.py

  # Compress specific date
  python scripts/compress_memory.py 2026-02-04

  # Dry run (don't write)
  python scripts/compress_memory.py --dry-run --json

Environment variables:
  OPENAI_API_KEY         OpenAI API key (required)
  OPENCLAW_MEM_WORKSPACE Workspace root (default: repo root)
  OPENCLAW_MEM_MODEL     Model name (default: gpt-4.1)
  OPENAI_BASE_URL        API base URL (default: https://api.openai.com/v1)
        """,
    )
    parser.add_argument("date", nargs="?", help="Date to process (YYYY-MM-DD)", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    parser.add_argument("--model", default=default_model, help="OpenAI model")
    parser.add_argument("--base-url", default=default_base_url, help="OpenAI API base URL")
    parser.add_argument("--max-tokens", type=int, default=default_max_tokens, help="Max output tokens")
    parser.add_argument("--temperature", type=float, default=default_temperature, help="Sampling temperature")
    parser.add_argument("--memory-dir", type=Path, default=default_memory_dir, help="Memory directory")
    parser.add_argument("--memory-file", type=Path, default=default_memory_file, help="MEMORY.md path")
    parser.add_argument("--prompt-file", type=Path, default=default_prompt_file, help="Prompt file path")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    args = parser.parse_args()

    # Determine target date
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Get API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable is not set", file=sys.stderr)
        print("Hint: export OPENAI_API_KEY=sk-...", file=sys.stderr)
        sys.exit(1)

    # Create client
    client = OpenAIClient(api_key, args.base_url)

    # Run compression
    try:
        result = compress_daily_note(
            date=target_date,
            memory_dir=args.memory_dir,
            memory_file=args.memory_file,
            prompt_file=args.prompt_file,
            client=client,
            model=args.model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            dry_run=args.dry_run,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result.get("skipped"):
                print(f"Skipping: {result['reason']}")
            elif result.get("dry_run"):
                print("--- DRY RUN OUTPUT ---")
                print(f"\\n\\n## {result['date']} Summary")
                print(result['summary'])
            else:
                print(f"✅ Appended summary to {result['memory_file']}")

    except CompressError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\\nInterrupted", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
