#!/usr/bin/env python3
"""Build a clean, link-rich durable-memory graph (Hub/Spoke) from openclaw-mem `store` outputs.

Why:
- `openclaw-mem store` appends durable memories to OpenClaw workspace Markdown files:
    <workspace>/memory/YYYY-MM-DD.md
  with lines like:
    - [PREFERENCE] Prefer concise bullet-point summaries (importance: 0.9)

- Those daily files are time-series logs. Great for audit, but not ideal for browsing
  or consistent recall triggers.

This script creates a *structured*, low-noise graph that only reflects **durable** memories
(approved / explicitly stored), not tool-result observations:

Output (under <workspace>/memory/durable/):
- DurableHub.md                      (top hub)
- categories/Category-<cat>.md       (category hubs)
- items/<YYYY-MM-DD>/<id>.md         (one memory per note)

Design:
- Deterministic + idempotent.
- No LLM required.
- Cross-links use Obsidian-style wiki links; helps human navigation and improves
  recall hit-rate via stable canonical keywords.

Run:
  uv run --python 3.13 -- python scripts/durable_structure.py --workspace ~/.openclaw/workspace
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


LINE_RE = re.compile(
    r"^\s*-\s*\[(?P<cat>[A-Z]+)\]\s+(?P<text>.+?)\s+\(importance:\s*(?P<imp>[0-9]*\.?[0-9]+)\)\s*$"
)
WIKILINK_RE = re.compile(r"\[\[(.+?)\]\]")


@dataclass(frozen=True)
class DurableItem:
    date: str  # YYYY-MM-DD
    category: str  # lowercase
    importance: float
    text: str
    item_id: str  # stable short hash


def _sha12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _iter_daily_files(memory_dir: Path) -> Iterable[Path]:
    for p in sorted(memory_dir.glob("????-??-??.md")):
        yield p


def _parse_items_from_file(p: Path) -> list[DurableItem]:
    date = p.stem
    items: list[DurableItem] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        m = LINE_RE.match(raw)
        if not m:
            continue
        cat = m.group("cat").strip().lower()
        text = m.group("text").strip()
        imp = float(m.group("imp"))
        item_id = _sha12(f"{date}|{cat}|{imp:.6f}|{text}")
        items.append(DurableItem(date=date, category=cat, importance=imp, text=text, item_id=item_id))
    return items


def _write(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _title_from_text(text: str, max_len: int = 70) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return (t[: max_len - 1] + "…") if len(t) > max_len else t


def _render_item_note(it: DurableItem) -> str:
    title = _title_from_text(it.text)
    links = sorted(set(WIKILINK_RE.findall(it.text)))
    link_lines = "\n".join([f"- [[{x}]]" for x in links]) if links else "- (none)"

    return (
        "---\n"
        f"id: {it.item_id}\n"
        f"date: {it.date}\n"
        f"category: {it.category}\n"
        f"importance: {it.importance}\n"
        "tags:\n"
        "  - openclaw\n"
        "  - openclaw-mem\n"
        "  - durable-memory\n"
        f"  - category/{it.category}\n"
        f"  - date/{it.date}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"- Category: [[Category-{it.category}]]\n"
        f"- Date: {it.date}\n"
        f"- Importance: {it.importance}\n"
        f"- Hub: [[DurableHub]]\n\n"
        "## Memory\n\n"
        f"{it.text}\n\n"
        "## Outgoing links found in text\n\n"
        f"{link_lines}\n"
    )


def _render_category_note(cat: str, items: list[DurableItem]) -> str:
    items = sorted(items, key=lambda x: (x.date, -x.importance, x.item_id))
    lines = [
        f"# Category: {cat}\n",
        "\n",
        "- Hub: [[DurableHub]]\n",
        f"- Total items: {len(items)}\n",
        "\n",
        "## Items\n\n",
    ]
    for it in items:
        title = _title_from_text(it.text)
        lines.append(f"- {it.date} · {it.importance:.2f} · [[items/{it.date}/{it.item_id}|{title}]]\n")
    return "".join(lines)


def _render_hub(items: list[DurableItem]) -> str:
    from collections import defaultdict

    by_cat: dict[str, list[DurableItem]] = defaultdict(list)
    by_date: dict[str, list[DurableItem]] = defaultdict(list)
    for it in items:
        by_cat[it.category].append(it)
        by_date[it.date].append(it)

    cats = sorted(by_cat.keys())
    dates = sorted(by_date.keys(), reverse=True)

    lines = [
        "# DurableHub\n\n",
        "Clean, human-approved (or explicitly stored) durable memories only.\n\n",
        "## By category\n\n",
    ]
    for c in cats:
        lines.append(f"- [[Category-{c}]] ({len(by_cat[c])})\n")

    lines += ["\n## Recent days\n\n"]
    for d in dates[:14]:
        # link to first few items
        day_items = sorted(by_date[d], key=lambda x: (-x.importance, x.item_id))
        lines.append(f"- {d} ({len(day_items)})\n")
        for it in day_items[:5]:
            title = _title_from_text(it.text)
            lines.append(f"  - {it.importance:.2f} · [[items/{it.date}/{it.item_id}|{title}]]\n")

    lines += [
        "\n## Notes\n\n",
        "- This graph is generated deterministically from `memory/YYYY-MM-DD.md` entries written by `openclaw-mem store`.\n",
        "- It is designed to stay low-noise (no raw observations).\n",
    ]
    return "".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="~/.openclaw/workspace", help="OpenClaw workspace root")
    args = ap.parse_args()

    ws = Path(args.workspace).expanduser().resolve()
    memory_dir = ws / "memory"
    if not memory_dir.exists():
        raise SystemExit(f"missing memory dir: {memory_dir}")

    out = memory_dir / "durable"
    items_dir = out / "items"

    # Collect + dedupe (a memory line may be stored multiple times across retries).
    # Key by stable item_id to keep the graph clean.
    items_by_id: dict[str, DurableItem] = {}
    for f in _iter_daily_files(memory_dir):
        for it in _parse_items_from_file(f):
            # keep the max-importance variant if duplicates occur
            prev = items_by_id.get(it.item_id)
            if prev is None or it.importance > prev.importance:
                items_by_id[it.item_id] = it

    items: list[DurableItem] = sorted(
        items_by_id.values(), key=lambda x: (x.date, x.category, -x.importance, x.item_id)
    )

    # Write item notes
    for it in items:
        p = items_dir / it.date / f"{it.item_id}.md"
        _write(p, _render_item_note(it))

    # Write categories
    from collections import defaultdict

    by_cat: dict[str, list[DurableItem]] = defaultdict(list)
    for it in items:
        by_cat[it.category].append(it)

    for cat, cat_items in by_cat.items():
        _write(out / f"Category-{cat}.md", _render_category_note(cat, cat_items))

    # Write hub
    _write(out / "DurableHub.md", _render_hub(items))

    print(f"ok: durable graph written to {out}")


if __name__ == "__main__":
    main()
