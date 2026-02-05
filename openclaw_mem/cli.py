#!/usr/bin/env python3
"""openclaw-mem CLI

AI-native design:
- Non-interactive (no prompts)
- Structured output via --json
- Rich examples in help
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

DEFAULT_DB = os.path.expanduser("~/.openclaw/memory/openclaw-mem.sqlite")
DEFAULT_WORKSPACE = Path.cwd()  # Fallback if not in openclaw workspace


def _connect(db_path: str) -> sqlite3.Connection:
    # Allow in-memory DB and relative paths without a directory component.
    # (Useful for unit tests and quick experiments.)
    dir_ = os.path.dirname(db_path)
    if db_path not in (":memory:", "") and dir_:
        os.makedirs(dir_, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT,
            summary TEXT,
            tool_name TEXT,
            detail_json TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
        USING fts5(summary, tool_name, detail_json, content='observations', content_rowid='id');
        """
    )
    conn.commit()


def _insert_observation(conn: sqlite3.Connection, obs: Dict[str, Any]) -> int:
    ts = obs.get("ts") or datetime.utcnow().isoformat()
    kind = obs.get("kind")
    summary = obs.get("summary")
    tool_name = obs.get("tool_name") or obs.get("tool")
    detail = obs.get("detail") or obs.get("detail_json") or {}
    detail_json = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)

    cur = conn.execute(
        "INSERT INTO observations (ts, kind, summary, tool_name, detail_json) VALUES (?, ?, ?, ?, ?)",
        (ts, kind, summary, tool_name, detail_json),
    )
    rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO observations_fts (rowid, summary, tool_name, detail_json) VALUES (?, ?, ?, ?)",
        (rowid, summary, tool_name, detail_json),
    )
    return int(rowid)


def _iter_jsonl(fp) -> Iterable[Dict[str, Any]]:
    for line in fp:
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def cmd_status(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    row = conn.execute("SELECT COUNT(*) AS n, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM observations").fetchone()
    data = {
        "db": args.db,
        "count": row["n"],
        "min_ts": row["min_ts"],
        "max_ts": row["max_ts"],
    }
    _emit(data, args.json)


def cmd_ingest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    if args.file:
        fp = open(args.file, "r", encoding="utf-8")
    else:
        fp = sys.stdin

    inserted: List[int] = []
    for obs in _iter_jsonl(fp):
        inserted.append(_insert_observation(conn, obs))

    conn.commit()
    if args.file:
        fp.close()

    _emit({"inserted": len(inserted), "ids": inserted[:50]}, args.json)


def cmd_search(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    q = args.query.strip()
    if not q:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    rows = conn.execute(
        """
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary,
               snippet(observations_fts, 0, '[', ']', '…', 12) AS snippet,
               bm25(observations_fts) AS score
        FROM observations_fts
        JOIN observations o ON o.id = observations_fts.rowid
        WHERE observations_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?;
        """,
        (q, args.limit),
    ).fetchall()

    out = [dict(r) for r in rows]
    _emit(out, args.json)


def cmd_get(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    ids = args.ids
    rows = conn.execute(
        f"SELECT * FROM observations WHERE id IN ({','.join(['?']*len(ids))}) ORDER BY id",
        ids,
    ).fetchall()
    _emit([dict(r) for r in rows], args.json)


def cmd_timeline(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    window = args.window
    seen = set()
    out = []
    for id_ in args.ids:
        lo, hi = id_ - window, id_ + window
        rows = conn.execute(
            "SELECT * FROM observations WHERE id BETWEEN ? AND ? ORDER BY id",
            (lo, hi),
        ).fetchall()
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            out.append(dict(r))
    out.sort(key=lambda x: x["id"])
    _emit(out, args.json)


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, list):
        for item in payload:
            _print_row(item)
        return
    if isinstance(payload, dict):
        for k, v in payload.items():
            print(f"{k}: {v}")
        return
    print(payload)


def _print_row(item: Dict[str, Any]) -> None:
    _id = item.get("id")
    ts = item.get("ts")
    kind = item.get("kind")
    tool = item.get("tool_name")
    summary = item.get("summary") or item.get("snippet")
    print(f"#{_id} {ts} [{kind}] {tool} :: {summary}")


def cmd_summarize(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Run AI compression on observations (requires compress_memory.py)."""
    try:
        # Import compress_memory module
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from compress_memory import OpenAIClient, compress_daily_note, CompressError
    except ImportError as e:
        _emit({"error": f"Failed to import compress_memory: {e}"}, args.json)
        sys.exit(1)

    # Get API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        _emit({"error": "OPENAI_API_KEY environment variable not set"}, args.json)
        sys.exit(1)

    # Determine workspace
    workspace = Path(args.workspace) if hasattr(args, "workspace") and args.workspace else DEFAULT_WORKSPACE
    memory_dir = workspace / "memory"
    memory_file = workspace / "MEMORY.md"
    prompt_file = workspace / "scripts/prompts/compress_memory.txt"

    # Determine date
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Create client
    client = OpenAIClient(
        api_key=api_key,
        base_url=args.base_url if hasattr(args, "base_url") else "https://api.openai.com/v1",
    )

    # Run compression
    try:
        result = compress_daily_note(
            date=target_date,
            memory_dir=memory_dir,
            memory_file=memory_file,
            prompt_file=prompt_file,
            client=client,
            model=args.model if hasattr(args, "model") else "gpt-4.1",
            max_tokens=args.max_tokens if hasattr(args, "max_tokens") else 700,
            temperature=args.temperature if hasattr(args, "temperature") else 0.2,
            dry_run=args.dry_run if hasattr(args, "dry_run") else False,
        )
        _emit(result, args.json)
    except CompressError as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Export observation summaries to MEMORY.md (placeholder for now)."""
    # TODO: Implement export logic that reads summaries from DB and writes to MEMORY.md
    # For now, this is a placeholder that directs users to use summarize command
    _emit(
        {
            "error": "Export not yet implemented. Use 'openclaw-mem summarize' to compress daily notes.",
            "hint": "Phase 2 in progress",
        },
        args.json,
    )
    sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Examples:\n"
        "  # Observation store\n"
        "  openclaw-mem status --json\n"
        "  openclaw-mem ingest --file observations.jsonl --json\n"
        "\n"
        "  # Progressive disclosure search\n"
        "  openclaw-mem search \"gateway timeout\" --limit 20 --json\n"
        "  openclaw-mem timeline 23 41 57 --window 4 --json\n"
        "  openclaw-mem get 23 41 57 --json\n"
        "\n"
        "  # AI compression (requires OPENAI_API_KEY)\n"
        "  export OPENAI_API_KEY=sk-...\n"
        "  openclaw-mem summarize --json  # yesterday's notes\n"
        "  openclaw-mem summarize 2026-02-04 --dry-run\n"
        "\n"
        "Global flags also work before the command:\n"
        "  openclaw-mem --db /tmp/mem.sqlite --json status\n"
        "\n"
        "Input JSONL (one per line) for ingest:\n"
        "  {\"ts\":\"2026-02-04T13:00:00Z\", \"kind\":\"tool\", \"tool_name\":\"cron.list\", \"summary\":\"cron list called\", \"detail\":{...}}\n"
    )

    p = argparse.ArgumentParser(
        prog="openclaw-mem",
        description="OpenClaw memory CLI (M0 prototype).",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags (before the subcommand). These are merged with per-command flags.
    p.add_argument("--db", dest="db_global", default=None, help="SQLite DB path")
    p.add_argument("--json", dest="json_global", action="store_true", help="Structured JSON output")

    def add_common(sp: argparse.ArgumentParser) -> None:
        # Allow flags after the subcommand too.
        sp.add_argument("--db", default=None, help="SQLite DB path")
        sp.add_argument("--json", action="store_true", help="Structured JSON output")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="Show store stats")
    add_common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("ingest", help="Ingest observations (JSONL via --file or stdin)")
    add_common(sp)
    sp.add_argument("--file", help="JSONL file path (default: stdin)")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("search", help="FTS search over observations")
    add_common(sp)
    sp.add_argument("query", help="Search query (FTS5 syntax)")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("timeline", help="Windowed timeline around IDs")
    add_common(sp)
    sp.add_argument("ids", type=int, nargs="+", help="Observation IDs")
    sp.add_argument("--window", type=int, default=4, help="±N rows around each id")
    sp.set_defaults(func=cmd_timeline)

    sp = sub.add_parser("get", help="Get full observations by ID")
    add_common(sp)
    sp.add_argument("ids", type=int, nargs="+", help="Observation IDs")
    sp.set_defaults(func=cmd_get)

    sp = sub.add_parser("summarize", help="Run AI compression on daily notes (requires OPENAI_API_KEY)")
    add_common(sp)
    sp.add_argument("date", nargs="?", help="Date to compress (YYYY-MM-DD, default: yesterday)")
    sp.add_argument("--workspace", type=Path, help="Workspace root (default: cwd)")
    sp.add_argument("--model", default="gpt-4.1", help="OpenAI model")
    sp.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI API base URL")
    sp.add_argument("--max-tokens", type=int, default=700, help="Max output tokens")
    sp.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    sp.add_argument("--dry-run", action="store_true", help="Preview without writing")
    sp.set_defaults(func=cmd_summarize)

    sp = sub.add_parser("export", help="Export summaries to MEMORY.md (Phase 2, coming soon)")
    add_common(sp)
    sp.add_argument("--to", required=True, help="Target file (e.g., MEMORY.md)")
    sp.add_argument("--yes", action="store_true", help="Skip confirmation")
    sp.set_defaults(func=cmd_export)

    return p


def main() -> None:
    args = build_parser().parse_args()

    # Merge global flags (before subcommand) + per-command flags (after subcommand)
    base_db = os.environ.get("OPENCLAW_MEM_DB", DEFAULT_DB)
    args.db = getattr(args, "db", None) or getattr(args, "db_global", None) or base_db
    args.json = bool(getattr(args, "json", False) or getattr(args, "json_global", False))

    conn = _connect(args.db)
    args.func(conn, args)


if __name__ == "__main__":
    main()
