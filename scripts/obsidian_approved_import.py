#!/usr/bin/env python3
"""Import human-approved Obsidian items into openclaw-mem.

Minimal closed loop (v0):
- Human approves items by adding bullet lines to a shared vault file:
  OpenClaw/Approved/approved_memories.md
- This script reads the `## Queue` section, stores each item via `openclaw-mem store`,
  and moves successfully processed items to `## Done`.

Design goals:
- Deterministic/idempotent: keeps state under OpenClaw/.agent_state/
- Safe by default: use --apply to actually mutate the markdown file

Run (from repo root):
  uv run --python 3.13 -- python scripts/obsidian_approved_import.py \
    --vault /home/agent/.LyriaClaw-MemVault --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUEUE_HDR = "## Queue"
DONE_HDR = "## Done"


@dataclass
class QueueItem:
    raw_line: str
    category: str
    importance: float
    text: str
    text_en: str | None


_ITEM_RE = re.compile(r"^\s*-\s*\[(?P<cat>[a-zA-Z_-]+)\|(?P<imp>[0-9]*\.?[0-9]+)\]\s*(?P<body>.+?)\s*$")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _load_state(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {"processed": {}}
    try:
        return json.loads(_read_text(p))
    except Exception:
        return {"processed": {}}


def _save_state(p: Path, state: dict[str, Any], *, apply: bool) -> None:
    if not apply:
        return
    _write_text(p, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _split_sections(md: str) -> tuple[list[str], list[str], list[str]]:
    """Return (before_queue, queue_lines, after_queue).

    queue_lines includes the header line itself and content until next header.
    """
    lines = md.splitlines(keepends=True)
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == QUEUE_HDR:
            idx = i
            break
    if idx is None:
        raise ValueError(f"Missing {QUEUE_HDR} section")

    # queue starts at idx, ends before next '## ' header (excluding DONE is handled later)
    j = idx + 1
    while j < len(lines):
        s = lines[j].lstrip()
        if s.startswith("## ") and lines[j].strip() != QUEUE_HDR:
            break
        j += 1

    return lines[:idx], lines[idx:j], lines[j:]


def _extract_done_block(md: str) -> tuple[str, str]:
    """Return (md_without_done_entries, done_block_text).

    done_block_text includes the DONE header and its following lines until next header.
    If DONE header missing, returns original md and empty done_block_text.
    """
    lines = md.splitlines(keepends=True)
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == DONE_HDR:
            idx = i
            break
    if idx is None:
        return md, ""

    j = idx + 1
    while j < len(lines):
        if lines[j].lstrip().startswith("## ") and lines[j].strip() != DONE_HDR:
            break
        j += 1

    done_block = "".join(lines[idx:j])
    without = "".join(lines[:idx] + lines[j:])
    return without, done_block


def _parse_queue_items(queue_block: list[str]) -> list[QueueItem]:
    items: list[QueueItem] = []
    for ln in queue_block[1:]:  # skip header line
        stripped = ln.strip()
        if not stripped.startswith("-"):
            continue
        m = _ITEM_RE.match(stripped)
        if not m:
            continue
        cat = m.group("cat").strip().lower()
        imp = float(m.group("imp"))
        body = m.group("body").strip()

        text_en = None
        if "||" in body:
            left, right = [x.strip() for x in body.split("||", 1)]
            body = left
            if right.lower().startswith("en:"):
                text_en = right[3:].strip() or None

        items.append(
            QueueItem(
                raw_line=stripped,
                category=cat,
                importance=imp,
                text=body,
                text_en=text_en,
            )
        )
    return items


def _run_store(item: QueueItem, *, workspace: Path | None) -> dict[str, Any]:
    # openclaw-mem's installed console script may not exist in some uv setups
    # (e.g., when the project isn't packaged). So we call the module directly
    # using the current interpreter (expected: `uv run ... python ...`).

    # Map vault-friendly aliases to openclaw-mem categories.
    cat = item.category.strip().lower()
    if cat == "note":
        cat = "other"

    cmd = [
        sys.executable,
        "-m",
        "openclaw_mem",
        "store",
        item.text,
        "--category",
        cat,
        "--importance",
        str(item.importance),
        "--json",
    ]

    if workspace is not None:
        cmd += ["--workspace", str(workspace)]

    if item.text_en:
        cmd += ["--text-en", item.text_en]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"store failed ({p.returncode}): {p.stderr.strip() or p.stdout.strip()}")

    # openclaw-mem prints warnings to stderr; JSON result should be on stdout.
    stdout = (p.stdout or "").strip()
    stderr = (p.stderr or "").strip()
    if not stdout:
        raise RuntimeError(f"store produced no stdout (expected JSON). stderr={stderr[:400]}")

    try:
        return json.loads(stdout)
    except Exception as e:
        # If stdout contains extra non-JSON lines, attempt to salvage the last JSON block.
        s = stdout
        start = s.rfind("{")
        if start != -1:
            tail = s[start:]
            try:
                return json.loads(tail)
            except Exception:
                pass
        raise RuntimeError(
            "store stdout was not valid JSON: "
            + str(e)
            + f" | stdout_head={stdout[:200]!r} | stderr_head={stderr[:200]!r}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="Path to shared vault root")
    ap.add_argument(
        "--approved-file",
        default="OpenClaw/Approved/approved_memories.md",
        help="Relative path inside vault",
    )
    ap.add_argument(
        "--state-file",
        default="OpenClaw/.agent_state/approved_memories_state.json",
        help="Relative path inside vault",
    )
    ap.add_argument("--apply", action="store_true", help="Actually modify files/state")
    ap.add_argument("--limit", type=int, default=50, help="Max items per run")
    ap.add_argument(
        "--workspace",
        default="~/.openclaw/workspace",
        help="OpenClaw workspace root for writing memory/YYYY-MM-DD.md (default: ~/.openclaw/workspace)",
    )

    args = ap.parse_args()

    vault = Path(args.vault)
    approved_path = vault / args.approved_file
    state_path = vault / args.state_file
    workspace = Path(args.workspace).expanduser()

    if not approved_path.exists():
        print(json.dumps({"ok": False, "error": f"missing approved file: {approved_path}"}))
        sys.exit(2)

    md = _read_text(approved_path)
    before, queue_block, after = _split_sections(md)
    items = _parse_queue_items(queue_block)

    state = _load_state(state_path)
    processed: dict[str, Any] = state.get("processed", {})

    to_process: list[QueueItem] = []
    for it in items:
        h = _sha(it.raw_line)
        if h in processed:
            continue
        to_process.append(it)
        if len(to_process) >= args.limit:
            break

    results: list[dict[str, Any]] = []
    done_lines: list[str] = []

    for it in to_process:
        h = _sha(it.raw_line)

        # Dry-run mode: do NOT write to openclaw-mem; just report what would happen.
        if not args.apply:
            results.append(
                {
                    "ok": True,
                    "hash": h,
                    "planned": True,
                    "category": it.category,
                    "importance": it.importance,
                    "raw": it.raw_line,
                }
            )
            continue

        try:
            res = _run_store(it, workspace=workspace)
            processed[h] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "id": res.get("id"),
                "category": it.category,
                "importance": it.importance,
                "text": it.text,
            }
            results.append({"ok": True, "hash": h, "store": res, "raw": it.raw_line})
            done_lines.append(f"- {it.raw_line}  <!-- imported {processed[h]['ts']} id={res.get('id')} -->\n")
        except Exception as e:
            results.append({"ok": False, "hash": h, "error": str(e), "raw": it.raw_line})

    # If apply, rewrite markdown: remove processed items from Queue, append them under Done.
    if args.apply and done_lines:
        # Remove already-imported bullets from queue by exact raw match
        kept_queue_lines: list[str] = [queue_block[0]]  # header
        imported_raw = {r["raw"] for r in results if r.get("ok")}
        for ln in queue_block[1:]:
            stripped = ln.strip()
            if stripped in imported_raw:
                continue
            kept_queue_lines.append(ln)

        new_md = "".join(before + kept_queue_lines + after)

        # Ensure DONE block exists; append if missing.
        if DONE_HDR not in new_md:
            if not new_md.endswith("\n"):
                new_md += "\n"
            new_md += f"\n{DONE_HDR}\n\n<!-- importer moves processed items here -->\n"

        # Append done lines just after DONE header (simple: at end of file)
        if not new_md.endswith("\n"):
            new_md += "\n"
        new_md += "\n" + "".join(done_lines)

        _write_text(approved_path, new_md)

    state["processed"] = processed
    _save_state(state_path, state, apply=args.apply)

    print(
        json.dumps(
            {
                "ok": True,
                "vault": str(vault),
                "approved_file": str(approved_path),
                "apply": bool(args.apply),
                "queued": len(items),
                "attempted": len(to_process),
                "results": results,
                "state_file": str(state_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
