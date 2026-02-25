#!/usr/bin/env python3
"""openclaw-mem CLI

AI-native design:
- Non-interactive (no prompts)
- Structured output via --json
- Rich examples in help
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional, Tuple

from openclaw_mem import __version__
from openclaw_mem import defaults
from openclaw_mem import pack_trace_v1
from openclaw_mem.vector import l2_norm, pack_f32, rank_cosine, rank_rrf

def _resolve_home_dir() -> str:
    """Best-effort OpenClaw-style home resolution.

    - OPENCLAW_HOME wins
    - then OS/user home (~)
    """

    explicit = (os.getenv("OPENCLAW_HOME") or "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.abspath(os.path.expanduser("~"))


def _resolve_state_dir() -> str:
    """Resolve OpenClaw state dir (best-effort).

    If the user overrides OpenClaw with OPENCLAW_STATE_DIR, openclaw-mem should
    follow it to avoid splitting state across directories.
    """

    override = (os.getenv("OPENCLAW_STATE_DIR") or os.getenv("CLAWDBOT_STATE_DIR") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(_resolve_home_dir(), ".openclaw")


def _resolve_openclaw_config_path() -> str:
    override = (os.getenv("OPENCLAW_CONFIG_PATH") or os.getenv("CLAWDBOT_CONFIG_PATH") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(_resolve_state_dir(), "openclaw.json")


STATE_DIR = _resolve_state_dir()
DEFAULT_INDEX_PATH = os.path.join(STATE_DIR, "memory", "openclaw-mem", "observations-index.md")
DEFAULT_GRAPH_CAPTURE_STATE_PATH = os.path.join(
    STATE_DIR,
    "memory",
    "openclaw-mem",
    "graph-capture-state.json",
)
DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH = os.path.join(
    STATE_DIR,
    "memory",
    "openclaw-mem",
    "graph-capture-md-state.json",
)
DEFAULT_DB = os.path.join(STATE_DIR, "memory", "openclaw-mem.sqlite")
DEFAULT_WORKSPACE = Path.cwd()  # Fallback if not in openclaw workspace
DEFAULT_GRAPH_CAPTURE_MD_INCLUDES = (".md",)
DEFAULT_GRAPH_CAPTURE_MD_EXCLUDES = (
    "**/node_modules/**",
    "**/.venv/**",
    "**/.git/**",
    "**/dist/**",
)
_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _utcnow_iso() -> str:
    """Return UTC timestamp in ISO format with timezone info."""

    return datetime.now(timezone.utc).isoformat()


@dataclass
class IngestRunSummary:
    """Aggregate ingest/harvest stats for importance autograde.

    These are intended for ops receipts and trend-friendly dashboards.
    """

    total_seen: int = 0
    graded_filled: int = 0
    skipped_existing: int = 0
    skipped_disabled: int = 0
    scorer_errors: int = 0
    label_counts: Dict[str, int] = field(default_factory=dict)

    def bump_label(self, label: str) -> None:
        key = (label or "").strip().lower() or "unknown"
        self.label_counts[key] = int(self.label_counts.get(key, 0)) + 1


def _apply_importance_scorer_override(args: argparse.Namespace) -> None:
    """Optionally override importance autograde scorer for this process.

    Precedence:
    - If the subcommand provides --importance-scorer, it wins.
    - Otherwise the env var OPENCLAW_MEM_IMPORTANCE_SCORER is used (existing behavior).

    Supported values:
    - heuristic-v1: enable deterministic heuristic grading
    - off|none: disable autograde even if env var is set

    Notes:
    - This is process-local (does not mutate any config files).
    - _insert_observation reads OPENCLAW_MEM_IMPORTANCE_SCORER at insert time.
    """

    raw = getattr(args, "importance_scorer", None)
    if raw is None:
        return

    v = str(raw).strip().lower()
    if not v:
        return

    if v in {"off", "none", "disable", "disabled", "0"}:
        os.environ.pop("OPENCLAW_MEM_IMPORTANCE_SCORER", None)
        return

    os.environ["OPENCLAW_MEM_IMPORTANCE_SCORER"] = v


def _read_openclaw_config() -> Dict[str, Any]:
    """Read OpenClaw config (cached).

    Prefers OPENCLAW_CONFIG_PATH when set; otherwise reads from the resolved
    OpenClaw state dir.
    """

    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    try:
        config_path = _resolve_openclaw_config_path()
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                _CONFIG_CACHE = json.load(f)
                return _CONFIG_CACHE
    except Exception:
        pass

    _CONFIG_CACHE = {}
    return _CONFIG_CACHE


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
            summary_en TEXT,
            lang TEXT,
            tool_name TEXT,
            detail_json TEXT
        );
        """
    )

    # Backward-compatible migration for existing DBs.
    obs_cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)").fetchall()}
    if "summary_en" not in obs_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN summary_en TEXT")
    if "lang" not in obs_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN lang TEXT")

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
        USING fts5(summary, summary_en, tool_name, detail_json, content='observations', content_rowid='id');
        """
    )

    # If this DB already had an older FTS schema, rebuild once with summary_en included.
    fts_cols = [r[1] for r in conn.execute("PRAGMA table_info(observations_fts)").fetchall()]
    if "summary_en" not in fts_cols:
        conn.execute("DROP TABLE IF EXISTS observations_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE observations_fts
            USING fts5(summary, summary_en, tool_name, detail_json, content='observations', content_rowid='id');
            """
        )
        conn.execute(
            """
            INSERT INTO observations_fts(rowid, summary, summary_en, tool_name, detail_json)
            SELECT id, summary, summary_en, tool_name, detail_json
            FROM observations;
            """
        )

    # Phase 3: vector embeddings (stored as float32 BLOB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observation_embeddings (
            observation_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_embeddings_model ON observation_embeddings(model);")

    # Backward-compatible parallel table for English embeddings.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observation_embeddings_en (
            observation_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_embeddings_en_model ON observation_embeddings_en(model);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_capture_git_seen (
            repo TEXT NOT NULL,
            sha TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            PRIMARY KEY(repo, sha)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_capture_md_seen (
            fingerprint TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            mtime REAL NOT NULL
        );
        """
    )

    conn.commit()


_SURROGATE_MIN = 0xD800
_SURROGATE_MAX = 0xDFFF


def _sanitize_str_surrogates(s: str) -> str:
    """Replace any lone surrogate codepoints to keep SQLite bindings UTF-8 safe.

    Python's json decoder can legally produce unpaired surrogate codepoints when
    the input contains an invalid unicode escape (e.g. "\\ud83d"). Those values
    cannot be encoded to UTF-8 for SQLite, so we replace them with U+FFFD.
    """

    if not s:
        return s
    # Fast path
    for ch in s:
        o = ord(ch)
        if _SURROGATE_MIN <= o <= _SURROGATE_MAX:
            return "".join(
                ("\ufffd" if _SURROGATE_MIN <= ord(c) <= _SURROGATE_MAX else c) for c in s
            )
    return s


def _sanitize_jsonable_surrogates(x: Any) -> Any:
    if isinstance(x, str):
        return _sanitize_str_surrogates(x)
    if isinstance(x, dict):
        out: Dict[Any, Any] = {}
        for k, v in x.items():
            kk = _sanitize_str_surrogates(k) if isinstance(k, str) else k
            out[kk] = _sanitize_jsonable_surrogates(v)
        return out
    if isinstance(x, list):
        return [_sanitize_jsonable_surrogates(v) for v in x]
    return x


def _insert_observation(conn: sqlite3.Connection, obs: Dict[str, Any], run_summary: IngestRunSummary | None = None) -> int:
    ts = obs.get("ts") or _utcnow_iso()

    kind = obs.get("kind")
    kind = _sanitize_str_surrogates(str(kind)) if kind is not None else None

    summary = obs.get("summary")
    summary = _sanitize_str_surrogates(str(summary)) if summary is not None else None

    summary_en = obs.get("summary_en") or obs.get("text_en")
    summary_en = _sanitize_str_surrogates(str(summary_en)) if summary_en is not None else None

    lang = obs.get("lang")
    lang = _sanitize_str_surrogates(str(lang)) if lang is not None else None

    tool_name = obs.get("tool_name") or obs.get("tool")
    tool_name = _sanitize_str_surrogates(str(tool_name)) if tool_name is not None else None

    base_detail = obs.get("detail")
    if base_detail is None:
        base_detail = obs.get("detail_json") or {}

    if isinstance(base_detail, str):
        try:
            detail_obj: Dict[str, Any] = json.loads(base_detail)
            if not isinstance(detail_obj, dict):
                detail_obj = {"_raw_detail": base_detail}
        except Exception:
            detail_obj = {"_raw_detail": base_detail}
    elif isinstance(base_detail, dict):
        detail_obj = dict(base_detail)
    else:
        detail_obj = {"_detail": base_detail}

    known_keys = {
        "ts",
        "kind",
        "summary",
        "summary_en",
        "text_en",
        "lang",
        "tool_name",
        "tool",
        "detail",
        "detail_json",
    }
    extras = {k: v for k, v in obs.items() if k not in known_keys}
    if extras:
        detail_obj.update(extras)

    # Sanitize any invalid unicode surrogate codepoints before binding to SQLite.
    detail_obj = _sanitize_jsonable_surrogates(detail_obj)

    if run_summary is not None:
        run_summary.total_seen += 1

    had_importance = "importance" in detail_obj
    if run_summary is not None and had_importance:
        run_summary.skipped_existing += 1
        try:
            from openclaw_mem.importance import parse_importance_score, label_from_score

            existing = detail_obj.get("importance")
            if isinstance(existing, dict) and isinstance(existing.get("label"), str) and existing.get("label").strip():
                run_summary.bump_label(existing.get("label"))
            else:
                run_summary.bump_label(label_from_score(parse_importance_score(existing)))
        except Exception:
            # Never break ingestion for reporting.
            run_summary.bump_label("unknown")

    # Optional: auto-grade importance behind a feature flag (non-destructive).
    #
    # MVP rules:
    # - default OFF
    # - only populate missing `detail_json.importance`
    # - fail-open on any grading error
    scorer = (os.environ.get("OPENCLAW_MEM_IMPORTANCE_SCORER") or "").strip().lower()

    if scorer == "heuristic-v1":
        if not had_importance:
            try:
                # Test hook: force a grading failure to prove fail-open behavior.
                if (os.environ.get("OPENCLAW_MEM_IMPORTANCE_TEST_RAISE") or "").strip() == "1":
                    raise RuntimeError("forced importance autograde failure (test)")

                from openclaw_mem.heuristic_v1 import grade_observation

                r = grade_observation(
                    {
                        "ts": ts,
                        "kind": kind,
                        "summary": summary,
                        "summary_en": summary_en,
                        "lang": lang,
                        "tool_name": tool_name,
                        "detail": detail_obj,
                    }
                )
                imp = r.as_importance()
                detail_obj["importance"] = imp

                if run_summary is not None:
                    run_summary.graded_filled += 1
                    run_summary.bump_label(str(imp.get("label") or "unknown"))
            except Exception as e:
                if run_summary is not None:
                    run_summary.scorer_errors += 1
                print(f"Warning: importance autograde failed: {e}", file=sys.stderr)
    else:
        if run_summary is not None and not had_importance:
            run_summary.skipped_disabled += 1

    detail_json = json.dumps(detail_obj, ensure_ascii=False)

    cur = conn.execute(
        "INSERT INTO observations (ts, kind, summary, summary_en, lang, tool_name, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, kind, summary, summary_en, lang, tool_name, detail_json),
    )
    rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO observations_fts (rowid, summary, summary_en, tool_name, detail_json) VALUES (?, ?, ?, ?, ?)",
        (rowid, summary, summary_en, tool_name, detail_json),
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
    emb_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings").fetchone()
    emb_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings GROUP BY model ORDER BY n DESC"
    ).fetchall()
    emb_en_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings_en").fetchone()
    emb_en_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings_en GROUP BY model ORDER BY n DESC"
    ).fetchall()

    data = {
        "db": args.db,
        "count": row["n"],
        "min_ts": row["min_ts"],
        "max_ts": row["max_ts"],
        "embeddings": {
            "count": emb_row["n"],
            "models": [{"model": r["model"], "count": r["n"]} for r in emb_models],
        },
        "embeddings_en": {
            "count": emb_en_row["n"],
            "models": [{"model": r["model"], "count": r["n"]} for r in emb_en_models],
        },
    }
    _emit(data, args.json)


def cmd_profile(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Ops-friendly profile surface (counts, ranges, labels, recent rows).

    This stays deterministic/local-first and does not call remote services.
    """

    recent_limit = max(1, min(200, int(getattr(args, "recent_limit", 10) or 10)))
    tool_limit = max(1, min(200, int(getattr(args, "tool_limit", 10) or 10)))
    kind_limit = max(1, min(200, int(getattr(args, "kind_limit", 10) or 10)))

    row = conn.execute("SELECT COUNT(*) AS n, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM observations").fetchone()

    kinds = conn.execute(
        """
        SELECT coalesce(kind, '') AS kind, COUNT(*) AS n
        FROM observations
        GROUP BY kind
        ORDER BY n DESC, kind ASC
        LIMIT ?
        """,
        (kind_limit,),
    ).fetchall()

    tools = conn.execute(
        """
        SELECT coalesce(tool_name, '') AS tool_name, COUNT(*) AS n
        FROM observations
        GROUP BY tool_name
        ORDER BY n DESC, tool_name ASC
        LIMIT ?
        """,
        (tool_limit,),
    ).fetchall()

    recent_rows = conn.execute(
        """
        SELECT id, ts, kind, tool_name, summary
        FROM observations
        ORDER BY id DESC
        LIMIT ?
        """,
        (recent_limit,),
    ).fetchall()

    emb_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings").fetchone()
    emb_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings GROUP BY model ORDER BY n DESC"
    ).fetchall()

    emb_en_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings_en").fetchone()
    emb_en_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings_en GROUP BY model ORDER BY n DESC"
    ).fetchall()

    from openclaw_mem.importance import is_parseable_importance, parse_importance_score, label_from_score

    label_counts: Dict[str, int] = {
        "must_remember": 0,
        "nice_to_have": 0,
        "ignore": 0,
        "unknown": 0,
    }
    importance_present = 0
    score_total = 0.0

    for r in conn.execute("SELECT detail_json FROM observations"):
        raw = r["detail_json"]
        try:
            detail_obj = json.loads(raw or "{}")
        except Exception:
            label_counts["unknown"] += 1
            continue

        if not isinstance(detail_obj, dict) or "importance" not in detail_obj:
            label_counts["unknown"] += 1
            continue

        importance_present += 1

        importance_value = detail_obj.get("importance")
        if not is_parseable_importance(importance_value):
            label_counts["unknown"] += 1
            continue

        score = parse_importance_score(importance_value)
        label = label_from_score(score)
        label_counts[label] = int(label_counts.get(label, 0)) + 1
        score_total += float(score)

    scored_count = int(label_counts["must_remember"] + label_counts["nice_to_have"] + label_counts["ignore"])
    total_count = int(row["n"] or 0)

    data = {
        "db": args.db,
        "observations": {
            "count": total_count,
            "min_ts": row["min_ts"],
            "max_ts": row["max_ts"],
            "kinds": [{"kind": r["kind"], "count": int(r["n"])} for r in kinds],
            "tools": [{"tool_name": r["tool_name"], "count": int(r["n"])} for r in tools],
        },
        "importance": {
            "present": importance_present,
            "missing": max(0, total_count - importance_present),
            "label_counts": label_counts,
            "avg_score": (score_total / scored_count) if scored_count else None,
        },
        "embeddings": {
            "original": {
                "count": int(emb_row["n"] or 0),
                "models": [{"model": r["model"], "count": int(r["n"])} for r in emb_models],
            },
            "english": {
                "count": int(emb_en_row["n"] or 0),
                "models": [{"model": r["model"], "count": int(r["n"])} for r in emb_en_models],
            },
        },
        "recent": [dict(r) for r in recent_rows],
    }

    _emit(data, args.json)


def _resolve_memory_slot(config: Dict[str, Any]) -> str:
    slot = config.get("plugins", {}).get("slots", {}).get("memory")
    if isinstance(slot, str) and slot:
        return slot
    return "memory-core"


def _is_enabled_entry(config: Dict[str, Any], plugin_id: str) -> bool:
    entry = config.get("plugins", {}).get("entries", {}).get(plugin_id)
    if not isinstance(entry, dict):
        return False
    return entry.get("enabled", True) is not False


def _lancedb_api_key_ready(config: Dict[str, Any]) -> bool:
    entry = config.get("plugins", {}).get("entries", {}).get("memory-lancedb")
    if not isinstance(entry, dict):
        return False
    cfg = entry.get("config", {})
    if not isinstance(cfg, dict):
        return False
    embedding = cfg.get("embedding", {})
    if not isinstance(embedding, dict):
        return False

    api_key = embedding.get("apiKey")
    if not isinstance(api_key, str) or not api_key.strip():
        return False

    if "${" in api_key and "}" in api_key:
        # Supports ${OPENAI_API_KEY}-style expansion in memory-lancedb.
        var_name = api_key.strip().removeprefix("${").removesuffix("}").strip()
        return bool(var_name and os.environ.get(var_name))

    return True


def cmd_backend(_conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    cfg = _read_openclaw_config()

    slot = _resolve_memory_slot(cfg)
    memory_core_enabled = _is_enabled_entry(cfg, "memory-core")
    memory_lancedb_enabled = _is_enabled_entry(cfg, "memory-lancedb")
    openclaw_mem_enabled = _is_enabled_entry(cfg, "openclaw-mem")

    out = {
        "memory_slot": slot,
        "entries": {
            "memory-core": {"enabled": memory_core_enabled},
            "memory-lancedb": {
                "enabled": memory_lancedb_enabled,
                "embedding_api_key_ready": _lancedb_api_key_ready(cfg),
            },
            "openclaw-mem": {"enabled": openclaw_mem_enabled},
        },
        "fallback": {
            "recommended_slot": "memory-core",
            "reason": "Fast rollback path if memory-lancedb has runtime issues",
        },
    }

    _emit(out, args.json)


def cmd_ingest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _apply_importance_scorer_override(args)

    if args.file:
        fp = open(args.file, "r", encoding="utf-8")
    else:
        fp = sys.stdin

    summary = IngestRunSummary()

    inserted: List[int] = []
    for obs in _iter_jsonl(fp):
        inserted.append(_insert_observation(conn, obs, summary))

    conn.commit()
    if args.file:
        fp.close()

    _emit(
        {
            "inserted": len(inserted),
            "ids": inserted[:50],
            "total_seen": summary.total_seen,
            "graded_filled": summary.graded_filled,
            "skipped_existing": summary.skipped_existing,
            "skipped_disabled": summary.skipped_disabled,
            "scorer_errors": summary.scorer_errors,
            "label_counts": summary.label_counts,
        },
        args.json,
    )


def _has_cjk(text: str) -> bool:
    import re

    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def _cjk_terms(query: str, max_terms: int = 16) -> List[str]:
    """Extract CJK-aware fallback terms for LIKE matching.

    Strategy:
    - keep CJK runs (length>=2)
    - add overlapping bigrams for longer runs
    """
    import re

    runs = re.findall(r"[\u3400-\u9fff]+", query or "")
    terms: List[str] = []

    for run in runs:
        if len(run) < 2:
            continue
        terms.append(run)
        if len(run) > 2:
            terms.extend(run[i : i + 2] for i in range(len(run) - 1))

    # stable de-dup
    out: List[str] = []
    seen = set()
    for t in terms:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_terms:
            break
    return out


def _search_cjk_fallback(conn: sqlite3.Connection, query: str, limit: int) -> List[sqlite3.Row]:
    terms = _cjk_terms(query)
    if not terms:
        return []

    like_vals = [f"%{t}%" for t in terms]

    # score = negative matched-term count (so more matches = smaller score = higher rank)
    score_expr = " + ".join(["CASE WHEN o.summary LIKE ? THEN 1 ELSE 0 END" for _ in like_vals])
    where_expr = " OR ".join(["o.summary LIKE ?" for _ in like_vals])

    sql = f"""
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               o.summary AS snippet,
               o.summary_en AS snippet_en,
               -1.0 * ({score_expr}) AS score
        FROM observations o
        WHERE {where_expr}
        ORDER BY score ASC, o.id DESC
        LIMIT ?;
    """

    params = [*like_vals, *like_vals, int(limit)]
    return conn.execute(sql, params).fetchall()


def cmd_search(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    q = args.query.strip()
    if not q:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    rows = conn.execute(
        """
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               snippet(observations_fts, 0, '[', ']', '…', 12) AS snippet,
               snippet(observations_fts, 1, '[', ']', '…', 12) AS snippet_en,
               bm25(observations_fts) AS score
        FROM observations_fts
        JOIN observations o ON o.id = observations_fts.rowid
        WHERE observations_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?;
        """,
        (q, args.limit),
    ).fetchall()

    # Fallback for CJK keyword queries when FTS5 tokenizer cannot split terms well.
    if not rows and _has_cjk(q):
        rows = _search_cjk_fallback(conn, q, args.limit)

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


def _get_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    """Get API key from env or ~/.openclaw/openclaw.json."""
    # 1. Try env
    api_key = os.environ.get(env_var)
    if api_key:
        return api_key

    # 2. Try config file
    data = _read_openclaw_config()
    # Traversing: agents -> defaults -> memorySearch -> remote -> apiKey
    key = (
        data.get("agents", {})
        .get("defaults", {})
        .get("memorySearch", {})
        .get("remote", {})
        .get("apiKey")
    )
    if key and isinstance(key, str):
        return key

    return None


def _get_gateway_config(args: argparse.Namespace, *, want_v1: bool = True) -> Dict[str, str]:
    """Resolve Gateway connection details (URL, token, agent_id).

    want_v1:
      - True: returns base URL ending with /v1
      - False: returns raw gateway base URL (no forced /v1)
    """
    config = _read_openclaw_config()

    # 1. URL
    url = getattr(args, "gateway_url", None)
    if not url:
        url = os.environ.get("OPENCLAW_GATEWAY_URL")
    if not url:
        # Construct from config port
        port = config.get("gateway", {}).get("http", {}).get("port") or config.get("gateway", {}).get("port", 18789)
        url = f"http://127.0.0.1:{port}"

    url = url.rstrip("/")
    if want_v1 and not url.endswith("/v1"):
        url = f"{url}/v1"

    # 2. Token
    token = getattr(args, "gateway_token", None)
    if not token:
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if not token:
        token = config.get("gateway", {}).get("auth", {}).get("token")

    # 3. Agent ID
    agent_id = getattr(args, "agent_id", None)
    if not agent_id:
        agent_id = os.environ.get("OPENCLAW_AGENT_ID", "main")

    return {
        "url": url,
        "token": token or "",
        "agent_id": agent_id,
    }


def _gateway_tools_invoke(
    args: argparse.Namespace,
    *,
    tool: str,
    tool_args: Dict[str, Any],
    session_key: str = "main",
    timeout: int = 120,
) -> Any:
    """Call OpenClaw Gateway `POST /tools/invoke`.

    This is the recommended black-box path for embeddings/memorySearch.
    """
    gw = _get_gateway_config(args, want_v1=False)
    if not gw["token"]:
        raise RuntimeError("Gateway token not found (set OPENCLAW_GATEWAY_TOKEN or configure gateway.auth.token)")

    url = gw["url"].rstrip("/") + "/tools/invoke"
    payload = {
        "tool": tool,
        "args": tool_args,
        "sessionKey": session_key,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {gw['token']}",
            "Content-Type": "application/json",
            "x-openclaw-agent-id": gw["agent_id"],
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gateway tools/invoke error ({e.code}): {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"Error calling Gateway tools/invoke: {e}") from e

    data = json.loads(body)
    if not isinstance(data, dict) or not data.get("ok"):
        raise RuntimeError(f"tools/invoke returned error: {body[:2000]}")
    return data.get("result")


def cmd_summarize(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Run AI compression on observations (requires compress_memory.py)."""
    try:
        # Import compress_memory module
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from compress_memory import OpenAIClient, compress_daily_note, CompressError
    except ImportError as e:
        _emit({"error": f"Failed to import compress_memory: {e}"}, args.json)
        sys.exit(1)

    use_gateway = bool(getattr(args, "gateway", False) or os.environ.get("OPENCLAW_MEM_USE_GATEWAY") == "1")

    api_key: Optional[str] = None
    base_url: str = defaults.openai_base_url()
    extra_headers: Dict[str, str] = {}
    model = args.model if hasattr(args, "model") else defaults.summary_model()

    if use_gateway:
        gw_conf = _get_gateway_config(args)
        base_url = gw_conf["url"]
        api_key = gw_conf["token"]
        extra_headers["x-openclaw-agent-id"] = gw_conf["agent_id"]
        
        # Switch default model if user didn't override it (heuristic: check against default)
        # If model is the configured default, we can switch to "openclaw:<agent>".
        if model == defaults.summary_model():
             model = f"openclaw:{gw_conf['agent_id']}"
             
        if not api_key:
             _emit({"error": "Gateway token not found (check ~/.openclaw/openclaw.json or use --gateway-token)"}, args.json)
             sys.exit(1)
    else:
        # Get API key (standard OpenAI path)
        api_key = _get_api_key()
        if not api_key:
            _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"}, args.json)
            sys.exit(1)
        base_url = args.base_url if hasattr(args, "base_url") else defaults.openai_base_url()

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
        base_url=base_url,
        extra_headers=extra_headers,
    )

    # Run compression
    try:
        result = compress_daily_note(
            date=target_date,
            memory_dir=memory_dir,
            memory_file=memory_file,
            prompt_file=prompt_file,
            client=client,
            model=model,
            max_tokens=args.max_tokens if hasattr(args, "max_tokens") else 700,
            temperature=args.temperature if hasattr(args, "temperature") else 0.2,
            dry_run=args.dry_run if hasattr(args, "dry_run") else False,
        )
        _emit(result, args.json)
    except CompressError as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)


def _atomic_append_file(path_: Path, content: str) -> None:
    """Append to a file atomically (write-to-temp + replace)."""
    path_.parent.mkdir(parents=True, exist_ok=True)
    existing = path_.read_text(encoding="utf-8") if path_.exists() else ""

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".txt",
    ) as tmp:
        tmp.write(existing + content)
        tmp_path = Path(tmp.name)

    tmp_path.replace(path_)


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Export observations to a file (Markdown by default).

    Safety:
    - Writing to MEMORY.md requires --yes.
    """
    out_path = Path(args.to)

    # Safety: exporting to MEMORY.md requires explicit confirmation
    if out_path.name == "MEMORY.md" and not args.yes:
        _emit(
            {
                "error": "Export to MEMORY.md requires --yes flag",
                "hint": "See docs/privacy-export-rules.md",
            },
            args.json,
        )
        sys.exit(2)

    ids: Optional[List[int]] = getattr(args, "ids", None)
    limit: int = int(getattr(args, "limit", 50))
    include_detail: bool = bool(getattr(args, "include_detail", False))

    if ids:
        q = f"SELECT * FROM observations WHERE id IN ({','.join(['?']*len(ids))}) ORDER BY id"
        rows = conn.execute(q, ids).fetchall()
    else:
        rows = conn.execute("SELECT * FROM observations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        rows = list(reversed(rows))

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = f"\n\n## Exported observations ({ts})\n"

    md = [header]
    for r in rows:
        rid = r["id"]
        rts = r["ts"]
        kind = r["kind"] or ""
        tool = r["tool_name"] or ""
        summary = (r["summary"] or "").strip()
        md.append(f"- #{rid} {rts} [{kind}] {tool} :: {summary}\n")
        if include_detail:
            md.append("\n```json\n")
            md.append((r["detail_json"] or "{}").strip() + "\n")
            md.append("```\n")

    _atomic_append_file(out_path, "".join(md))

    _emit(
        {
            "ok": True,
            "exported": len(rows),
            "to": str(out_path),
            "include_detail": include_detail,
        },
        args.json,
    )


class OpenAIEmbeddingsClient:
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = (base_url or defaults.openai_base_url()).rstrip("/")

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        url = self.base_url + "/embeddings"
        payload = {"model": model, "input": texts}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI embeddings API error ({e.code}): {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"Error calling OpenAI embeddings API: {e}") from e

        data = json.loads(body)
        out: List[List[float]] = []
        for item in data.get("data", []):
            out.append(item["embedding"])
        return out


def _embed_targets(field: str) -> List[Dict[str, str]]:
    if field == "original":
        return [{"name": "original", "text_col": "summary", "table": "observation_embeddings"}]
    if field == "english":
        return [{"name": "english", "text_col": "summary_en", "table": "observation_embeddings_en"}]
    return [
        {"name": "original", "text_col": "summary", "table": "observation_embeddings"},
        {"name": "english", "text_col": "summary_en", "table": "observation_embeddings_en"},
    ]


def cmd_embed(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Compute/store embeddings for observations."""
    api_key = _get_api_key()
    if not api_key:
        _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"}, args.json)
        sys.exit(1)

    model = args.model
    limit = int(args.limit)
    batch = int(args.batch)
    base_url = args.base_url
    field = getattr(args, "field", "original")

    client = OpenAIEmbeddingsClient(api_key=api_key, base_url=base_url)

    per_field: Dict[str, Dict[str, Any]] = {}
    inserted_total = 0
    ids: List[int] = []
    now = _utcnow_iso()

    for target in _embed_targets(field):
        _warn_embedding_model_mismatch(
            conn,
            table=target["table"],
            requested_model=model,
            label=target["name"],
        )

        rows = conn.execute(
            f"""
            SELECT id, tool_name, {target['text_col']} AS text_value
            FROM observations
            WHERE id NOT IN (
                SELECT observation_id FROM {target['table']} WHERE model = ?
            )
            AND trim(coalesce({target['text_col']}, '')) <> ''
            ORDER BY id
            LIMIT ?
            """,
            (model, limit),
        ).fetchall()

        todo = [dict(r) for r in rows]
        inserted = 0
        field_ids: List[int] = []

        for i in range(0, len(todo), batch):
            chunk = todo[i : i + batch]
            texts = []
            chunk_ids = []
            for r in chunk:
                tid = int(r["id"])
                tool = (r.get("tool_name") or "").strip()
                summary = (r.get("text_value") or "").strip()
                text = f"{tool}: {summary}".strip(": ")
                texts.append(text)
                chunk_ids.append(tid)

            vecs = client.embed(texts, model=model)
            for tid, vec in zip(chunk_ids, vecs):
                blob = pack_f32(vec)
                norm = l2_norm(vec)
                dim = len(vec)
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {target['table']}
                    (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tid, model, dim, blob, norm, now),
                )
                inserted += 1
                inserted_total += 1
                field_ids.append(tid)
                ids.append(tid)

            conn.commit()

        per_field[target["name"]] = {
            "embedded": inserted,
            "ids": field_ids[:50],
            "total_candidates": len(todo),
        }

    _emit(
        {
            "ok": True,
            "model": model,
            "field": field,
            "embedded": inserted_total,
            "ids": ids[:50],
            "per_field": per_field,
        },
        args.json,
    )


def _warn_embedding_model_availability(
    conn: sqlite3.Connection,
    *,
    table: str,
    requested_model: str,
    label: str,
) -> None:
    try:
        rows = conn.execute(
            f"SELECT model, COUNT(*) AS n FROM {table} GROUP BY model ORDER BY n DESC"
        ).fetchall()
    except Exception:
        return

    if not rows:
        return

    available = {str(r[0]): int(r[1]) for r in rows}
    if requested_model in available:
        return

    preview = ", ".join([f"{m}({n})" for m, n in list(available.items())[:5]])
    print(
        f"[openclaw-mem] Warning: requested {label} embedding model '{requested_model}' not found; "
        f"available: {preview}",
        file=sys.stderr,
    )


def _warn_embedding_model_mismatch(
    conn: sqlite3.Connection,
    *,
    table: str,
    requested_model: str,
    label: str,
) -> None:
    """Warn when multiple embedding models exist in the same table.

    This is not an error, but it is a common source of silent quality drift:
    operators change the default model and later wonder why recall differs.
    """

    try:
        rows = conn.execute(
            f"SELECT model, COUNT(*) AS n FROM {table} GROUP BY model ORDER BY n DESC"
        ).fetchall()
    except Exception:
        return

    if not rows:
        return

    available = {str(r[0]): int(r[1]) for r in rows}
    if requested_model not in available:
        return

    others = {m: n for m, n in available.items() if m != requested_model and n > 0}
    if not others:
        return

    preview = ", ".join([f"{m}({n})" for m, n in list(others.items())[:5]])
    print(
        f"[openclaw-mem] Warning: {label} embeddings include multiple models. "
        f"Using '{requested_model}', but also saw: {preview}",
        file=sys.stderr,
    )


def cmd_vsearch(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Vector search over stored embeddings (cosine similarity)."""
    model = args.model
    limit = int(args.limit)

    _warn_embedding_model_availability(
        conn,
        table="observation_embeddings",
        requested_model=model,
        label="original",
    )

    # Get query vector from file/json or via OpenAI API
    query_vec: Optional[List[float]] = None

    if getattr(args, "query_vector_json", None):
        query_vec = json.loads(args.query_vector_json)
    elif getattr(args, "query_vector_file", None):
        query_vec = json.loads(Path(args.query_vector_file).read_text(encoding="utf-8"))
    else:
        api_key = _get_api_key()
        if not api_key:
            _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json (or provide --query-vector-json/--query-vector-file)"}, args.json)
            sys.exit(1)
        client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
        query_vec = client.embed([args.query], model=model)[0]

    # Load embeddings
    items = conn.execute(
        "SELECT observation_id, vector, norm FROM observation_embeddings WHERE model = ?",
        (model,),
    ).fetchall()

    ranked = rank_cosine(
        query_vec=query_vec,
        items=((int(r[0]), r[1], float(r[2])) for r in items),
        limit=limit,
    )

    if not ranked:
        _emit([], args.json)
        return

    ids = [rid for rid, _ in ranked]
    q = f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?']*len(ids))})"
    rows = conn.execute(q, ids).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    out = []
    for rid, score in ranked:
        r = obs_map.get(rid)
        if not r:
            continue
        r["score"] = score
        out.append(r)

    _emit(out, args.json)


def _resolve_rerank_api_key(provider: str, args: argparse.Namespace) -> Optional[str]:
    cli_key = getattr(args, "rerank_api_key", None)
    if cli_key:
        return str(cli_key)

    env_map = {
        "jina": "JINA_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    env_key = env_map.get(provider)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val

    return None


def _default_rerank_url(provider: str) -> str:
    if provider == "jina":
        return "https://api.jina.ai/v1/rerank"
    if provider == "cohere":
        return "https://api.cohere.com/v2/rerank"
    raise ValueError(f"unsupported rerank provider: {provider}")


def _call_rerank_provider(
    *,
    provider: str,
    query: str,
    documents: List[str],
    model: str,
    top_n: int,
    api_key: str,
    base_url: Optional[str] = None,
    timeout_sec: int = 15,
) -> List[Tuple[int, float]]:
    url = (base_url or _default_rerank_url(provider)).rstrip("/")

    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": int(top_n),
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
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"rerank HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"rerank network error: {e}") from e

    parsed = json.loads(raw)
    rows = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return []

    out: List[Tuple[int, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        score = row.get("relevance_score", row.get("score", 0.0))
        try:
            out.append((int(idx), float(score)))
        except Exception:
            continue

    return out


def _hybrid_retrieve(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    *,
    candidate_limit_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Shared Hybrid retrieval core (FTS + Vector + RRF + optional rerank)."""
    model = str(getattr(args, "model", defaults.embed_model()))
    limit = max(1, int(getattr(args, "limit", 20)))
    k = int(getattr(args, "k", 60))
    query = (getattr(args, "query", None) or "").strip()
    query_en = (getattr(args, "query_en", None) or "").strip() or None

    rerank_provider = str(getattr(args, "rerank_provider", "none") or "none").lower()
    rerank_enabled = rerank_provider != "none"

    _warn_embedding_model_availability(
        conn,
        table="observation_embeddings",
        requested_model=model,
        label="original",
    )
    _warn_embedding_model_mismatch(
        conn,
        table="observation_embeddings",
        requested_model=model,
        label="original",
    )
    if query_en:
        _warn_embedding_model_availability(
            conn,
            table="observation_embeddings_en",
            requested_model=model,
            label="english",
        )
        _warn_embedding_model_mismatch(
            conn,
            table="observation_embeddings_en",
            requested_model=model,
            label="english",
        )
    rerank_topn = max(1, int(getattr(args, "rerank_topn", limit) or limit))

    candidate_limit = int(candidate_limit_override) if candidate_limit_override is not None else limit * 2
    candidate_limit = max(1, candidate_limit)
    if rerank_enabled:
        # Keep a wider candidate pool before final rerank.
        candidate_limit = max(candidate_limit, rerank_topn * 3)

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json")

    client = OpenAIEmbeddingsClient(
        api_key=api_key,
        base_url=getattr(args, "base_url", defaults.openai_base_url()),
    )
    try:
        embed_inputs = [query] + ([query_en] if query_en else [])
        embed_vecs = client.embed(embed_inputs, model=model)
        query_vec = embed_vecs[0]
        query_en_vec = embed_vecs[1] if query_en else None
    except Exception as e:
        raise RuntimeError(str(e)) from e

    vec_rows = conn.execute(
        "SELECT observation_id, vector, norm FROM observation_embeddings WHERE model = ?",
        (model,),
    ).fetchall()

    vec_ranked = rank_cosine(
        query_vec=query_vec,
        items=((int(r[0]), r[1], float(r[2])) for r in vec_rows),
        limit=candidate_limit,
    )
    vec_ids = [rid for rid, _ in vec_ranked]

    vec_en_ids: List[int] = []
    if query_en_vec is not None:
        vec_en_rows = conn.execute(
            "SELECT observation_id, vector, norm FROM observation_embeddings_en WHERE model = ?",
            (model,),
        ).fetchall()

        # Backward-compatible fallback when dedicated EN table is not populated.
        search_rows = vec_en_rows if vec_en_rows else vec_rows

        vec_en_ranked = rank_cosine(
            query_vec=query_en_vec,
            items=((int(r[0]), r[1], float(r[2])) for r in search_rows),
            limit=candidate_limit,
        )
        vec_en_ids = [rid for rid, _ in vec_en_ranked]

    fts_rows = []
    try:
        fts_rows = conn.execute(
            """
            SELECT rowid
            FROM observations_fts
            WHERE observations_fts MATCH ?
            ORDER BY bm25(observations_fts) ASC
            LIMIT ?;
            """,
            (query, candidate_limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        # FTS syntax can fail for edge-case query strings (e.g. hyphens/operators).
        if "no such column: matches" in str(e):
            print(
                f"[openclaw-mem] FTS query parse failed; skipping FTS lane (query={query!r}).",
                file=sys.stderr,
            )
        else:
            raise
    fts_ids = [int(r["rowid"]) for r in fts_rows]

    ranked_lists = [fts_ids, vec_ids]
    if vec_en_ids:
        ranked_lists.append(vec_en_ids)

    rrf_ranking = rank_rrf(ranked_lists, k=k, limit=candidate_limit)
    if not rrf_ranking:
        return {
            "ordered_ids": [],
            "obs_map": {},
            "rrf_scores": {},
            "fts_ids": fts_ids,
            "vec_ids": vec_ids,
            "vec_en_ids": vec_en_ids,
            "rerank_scores": {},
            "rerank_applied": False,
            "rerank_provider": rerank_provider,
            "rerank_enabled": rerank_enabled,
            "candidate_limit": candidate_limit,
        }

    rrf_scores = {rid: score for rid, score in rrf_ranking}
    ordered_ids = [rid for rid, _ in rrf_ranking]

    q_sql = f"SELECT id, ts, kind, tool_name, summary, summary_en, lang FROM observations WHERE id IN ({','.join(['?']*len(ordered_ids))})"
    rows = conn.execute(q_sql, ordered_ids).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    rerank_scores: Dict[int, float] = {}
    rerank_applied = False

    if rerank_enabled and ordered_ids:
        if rerank_provider not in {"jina", "cohere"}:
            print(
                f"[openclaw-mem] rerank provider '{rerank_provider}' unsupported; using base RRF ranking.",
                file=sys.stderr,
            )
        else:
            rerank_api_key = _resolve_rerank_api_key(rerank_provider, args)
            if not rerank_api_key:
                print(
                    f"[openclaw-mem] rerank provider '{rerank_provider}' enabled but API key missing; using base RRF ranking.",
                    file=sys.stderr,
                )
            else:
                docs = [
                    (obs_map.get(rid, {}).get("summary_en") or obs_map.get(rid, {}).get("summary") or "")
                    for rid in ordered_ids
                ]
                try:
                    rerank_rows = _call_rerank_provider(
                        provider=rerank_provider,
                        query=query_en or query,
                        documents=docs,
                        model=str(getattr(args, "rerank_model", defaults.rerank_model())),
                        top_n=min(rerank_topn, len(docs)),
                        api_key=rerank_api_key,
                        base_url=getattr(args, "rerank_base_url", None),
                        timeout_sec=int(getattr(args, "rerank_timeout_sec", 15) or 15),
                    )
                    if rerank_rows:
                        seen: set[int] = set()
                        reranked: List[int] = []

                        for idx, score in rerank_rows:
                            if idx < 0 or idx >= len(ordered_ids):
                                continue
                            rid = ordered_ids[idx]
                            if rid in seen:
                                continue
                            seen.add(rid)
                            reranked.append(rid)
                            rerank_scores[rid] = float(score)

                        for rid in ordered_ids:
                            if rid not in seen:
                                reranked.append(rid)

                        ordered_ids = reranked
                        rerank_applied = True
                except Exception as e:
                    print(
                        f"[openclaw-mem] rerank failed ({type(e).__name__}: {e}); using base RRF ranking.",
                        file=sys.stderr,
                    )

    return {
        "ordered_ids": ordered_ids,
        "obs_map": obs_map,
        "rrf_scores": rrf_scores,
        "fts_ids": fts_ids,
        "vec_ids": vec_ids,
        "vec_en_ids": vec_en_ids,
        "rerank_scores": rerank_scores,
        "rerank_applied": rerank_applied,
        "rerank_provider": rerank_provider,
        "rerank_enabled": rerank_enabled,
        "candidate_limit": candidate_limit,
    }


def cmd_hybrid(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Hybrid search (FTS + Vector) using RRF.

    Optional post-retrieval rerank (opt-in):
    - provider: none|jina|cohere
    - fail-open: rerank errors do not break search
    """
    limit = int(args.limit)

    try:
        state = _hybrid_retrieve(conn, args)
    except RuntimeError as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)

    ordered_ids = state["ordered_ids"]
    if not ordered_ids:
        _emit([], args.json)
        return

    out = []
    for rid in ordered_ids[:limit]:
        r = state["obs_map"].get(rid)
        if not r:
            continue

        r["rrf_score"] = float(state["rrf_scores"].get(rid, 0.0))
        r["match"] = []
        if rid in state["fts_ids"]:
            r["match"].append("text")
        if rid in state["vec_ids"]:
            r["match"].append("vector")
        if rid in state["vec_en_ids"]:
            r["match"].append("vector_en")

        if state["rerank_enabled"]:
            r["rerank_provider"] = state["rerank_provider"]
            if rid in state["rerank_scores"]:
                r["rerank_score"] = float(state["rerank_scores"][rid])
            if state["rerank_applied"]:
                r["rank_stage"] = "rerank" if rid in state["rerank_scores"] else "rrf-fallback"

        out.append(r)

    _emit(out, args.json)


def _pack_item_text(row: Dict[str, Any]) -> str:
    return ((row.get("summary_en") or row.get("summary") or "").replace("\n", " ").strip())


def _pack_parse_detail_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_importance_label(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None

    key = raw.strip().lower()
    if not key:
        return None

    aliases = {
        "must remember": "must_remember",
        "must-remember": "must_remember",
        "nice to have": "nice_to_have",
        "nice-to-have": "nice_to_have",
        "low": "ignore",
        "medium": "nice_to_have",
        "high": "must_remember",
    }
    key = aliases.get(key, key)
    key = key.replace("-", "_").replace(" ", "_")

    if key in {"must_remember", "nice_to_have", "ignore", "unknown"}:
        return key
    return None


def _pack_importance_label(detail_obj: Dict[str, Any]) -> str:
    if not isinstance(detail_obj, dict) or "importance" not in detail_obj:
        return "unknown"

    importance = detail_obj.get("importance")
    normalized_label = None

    if isinstance(importance, dict):
        normalized_label = _normalize_importance_label(importance.get("label"))
        if normalized_label:
            return normalized_label

        score = importance.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            from openclaw_mem.importance import label_from_score

            return label_from_score(float(score))
        return "unknown"

    if isinstance(importance, (int, float)) and not isinstance(importance, bool):
        from openclaw_mem.importance import label_from_score

        return label_from_score(float(importance))

    return "unknown"


def _normalize_trust_tier(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None

    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "quarantine": "quarantined",
    }
    key = aliases.get(key, key)

    if key in {"trusted", "untrusted", "quarantined"}:
        return key
    return None


def _pack_trust_tier(detail_obj: Dict[str, Any]) -> str:
    if not isinstance(detail_obj, dict):
        return "unknown"

    candidates: List[Any] = [
        detail_obj.get("trust"),
        detail_obj.get("trust_tier"),
        detail_obj.get("trustTier"),
    ]

    provenance = detail_obj.get("provenance")
    if isinstance(provenance, dict):
        candidates.extend(
            [
                provenance.get("trust"),
                provenance.get("trust_tier"),
                provenance.get("trustTier"),
            ]
        )

    for value in candidates:
        normalized = _normalize_trust_tier(value)
        if normalized:
            return normalized

    return "unknown"


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def cmd_pack(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Build a compact, cited L1-style bundle from hybrid retrieval."""
    query = (args.query or "").strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    limit = max(1, int(args.limit))
    budget_tokens = max(1, int(args.budget_tokens))
    max_l2_items = 0
    nice_cap = 100

    started = time.perf_counter()

    retrieval_args = argparse.Namespace(
        query=query,
        query_en=getattr(args, "query_en", None),
        limit=limit,
        k=60,
        model=defaults.embed_model(),
        base_url=defaults.openai_base_url(),
        rerank_provider="none",
        rerank_topn=limit,
        rerank_model=defaults.rerank_model(),
        rerank_api_key=None,
        rerank_base_url=None,
        rerank_timeout_sec=15,
    )

    try:
        state = _hybrid_retrieve(
            conn,
            retrieval_args,
            candidate_limit_override=max(limit * 3, limit + 8),
        )
    except RuntimeError as e:
        _emit({"error": str(e)}, True)
        sys.exit(1)

    ordered_ids = state["ordered_ids"]
    obs_map = state["obs_map"]

    detail_map: Dict[int, Dict[str, Any]] = {}
    if ordered_ids:
        q_detail = f"SELECT id, detail_json FROM observations WHERE id IN ({','.join(['?']*len(ordered_ids))})"
        detail_rows = conn.execute(q_detail, ordered_ids).fetchall()
        detail_map = {int(r["id"]): _pack_parse_detail_json(r["detail_json"]) for r in detail_rows}

    selected_items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    candidate_trace: List[pack_trace_v1.PackTraceV1Candidate] = []

    used_tokens = 0
    for rid in ordered_ids:
        row = obs_map.get(rid)
        detail_obj = detail_map.get(rid, {})
        importance_label = _pack_importance_label(detail_obj)
        trust_tier = _pack_trust_tier(detail_obj)

        record_ref = f"obs:{rid}"
        text = _pack_item_text(row or {})
        token_estimate = _estimate_tokens(text) if text else 0

        include = False
        reasons: List[str] = []

        if row is None:
            reasons.append("missing_row")
        elif not text:
            reasons.append("missing_summary")
        elif len(selected_items) >= limit:
            reasons.append("max_items_reached")
        elif used_tokens + token_estimate > budget_tokens:
            reasons.append("budget_tokens_exceeded")
        else:
            include = True
            used_tokens += token_estimate
            reasons.extend(["within_item_limit", "within_budget"])
            if rid in state["fts_ids"]:
                reasons.append("matched_fts")
            if rid in state["vec_ids"] or rid in state["vec_en_ids"]:
                reasons.append("matched_vector")

            selected_items.append(
                {
                    "recordRef": record_ref,
                    "layer": "L1",
                    "id": rid,
                    "summary": text,
                    "kind": row.get("kind"),
                    "lang": row.get("lang"),
                }
            )
            citations.append({"recordRef": record_ref, "url": None})

        candidate_trace.append(
            pack_trace_v1.PackTraceV1Candidate(
                id=record_ref,
                layer="L1",
                importance=importance_label,
                trust=trust_tier,
                scores=pack_trace_v1.PackTraceV1CandidateScores(
                    rrf=float(state["rrf_scores"].get(rid, 0.0)),
                    fts=float(1.0 if rid in state["fts_ids"] else 0.0),
                    semantic=float(1.0 if (rid in state["vec_ids"] or rid in state["vec_en_ids"]) else 0.0),
                ),
                decision=pack_trace_v1.PackTraceV1Decision(
                    included=include,
                    reason=list(reasons),
                    rationale=list(reasons),
                    caps=pack_trace_v1.PackTraceV1DecisionCaps(
                        niceCapHit=False,
                        l2CapHit=False,
                    ),
                ),
                citations=pack_trace_v1.PackTraceV1CandidateCitations(
                    url=None,
                    recordRef=record_ref,
                ),
            )
        )

    bundle_lines = [f"- [{item['recordRef']}] {item['summary']}" for item in selected_items]
    bundle_text = "\n".join(bundle_lines)

    payload: Dict[str, Any] = {
        "bundle_text": bundle_text,
        "items": selected_items,
        "citations": citations,
    }

    if bool(args.trace):
        duration_ms = int((time.perf_counter() - started) * 1000)
        included_refs = [item["recordRef"] for item in selected_items]
        included_candidates = [c for c in candidate_trace if bool(getattr(c.decision, "included", False))]
        rationale_missing_count = sum(1 for c in included_candidates if not list(getattr(c.decision, "reason", []) or []))
        citation_missing_count = sum(1 for c in included_candidates if not str(getattr(c.citations, "recordRef", "") or "").strip())
        all_included_have_rationale = rationale_missing_count == 0
        all_included_have_citations = citation_missing_count == 0
        trace = pack_trace_v1.PackTraceV1(
            kind=pack_trace_v1.PACK_TRACE_V1_KIND,
            ts=_utcnow_iso(),
            version=pack_trace_v1.PackTraceV1Version(openclaw_mem=__version__),
            query=pack_trace_v1.PackTraceV1Query(
                text=query,
                scope=None,
                intent=None,
            ),
            budgets=pack_trace_v1.PackTraceV1Budgets(
                budgetTokens=budget_tokens,
                maxItems=limit,
                maxL2Items=max_l2_items,
                niceCap=nice_cap,
            ),
            lanes=[
                pack_trace_v1.PackTraceV1Lane(
                    name="hot",
                    source="session/recent",
                    searched=False,
                    retrievers=[],
                ),
                pack_trace_v1.PackTraceV1Lane(
                    name="warm",
                    source="sqlite-observations",
                    searched=True,
                    retrievers=[
                        pack_trace_v1.PackTraceV1Retriever(kind="fts5", topK=int(state["candidate_limit"])),
                        pack_trace_v1.PackTraceV1Retriever(kind="vector", topK=int(state["candidate_limit"])),
                        pack_trace_v1.PackTraceV1Retriever(kind="rrf", k=60),
                    ],
                ),
                pack_trace_v1.PackTraceV1Lane(
                    name="cold",
                    source="curated/durable",
                    searched=False,
                    retrievers=[],
                ),
            ],
            candidates=candidate_trace,
            output=pack_trace_v1.PackTraceV1Output(
                includedCount=len(selected_items),
                excludedCount=max(0, len(candidate_trace) - len(selected_items)),
                l2IncludedCount=0,
                citationsCount=len(citations),
                refreshedRecordRefs=included_refs,
                coverage=pack_trace_v1.PackTraceV1Coverage(
                    rationaleMissingCount=rationale_missing_count,
                    citationMissingCount=citation_missing_count,
                    allIncludedHaveRationale=all_included_have_rationale,
                    allIncludedHaveCitations=all_included_have_citations,
                ),
            ),
            timing=pack_trace_v1.PackTraceV1Timing(durationMs=duration_ms),
        )
        payload["trace"] = pack_trace_v1.to_dict(trace)

    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(bundle_text)



def _atomic_write(path_: Path, content: str) -> None:
    path_.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".txt",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path_)


def _format_index_line(row: sqlite3.Row) -> str:
    rid = int(row["id"])
    ts = (row["ts"] or "").strip()
    tool = (row["tool_name"] or "").strip()
    kind = (row["kind"] or "").strip()
    summary = (row["summary"] or "").replace("\n", " ").strip()
    return f"- obs#{rid} {ts} [{kind}] {tool} :: {summary}\n"


def _build_index(conn: sqlite3.Connection, out_path: Path, limit: int) -> int:
    rows = conn.execute(
        "SELECT id, ts, kind, tool_name, summary FROM observations ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    rows = list(reversed(rows))

    header = (
        "# openclaw-mem observations index\n\n"
        "This file is auto-generated. It is safe to embed and search via OpenClaw memorySearch.\n\n"
    )
    body = "".join(_format_index_line(r) for r in rows)
    _atomic_write(out_path, header + body)
    return len(rows)


def cmd_index(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Build a Markdown index file that OpenClaw memorySearch can embed (Route A)."""
    out_path = Path(args.to or DEFAULT_INDEX_PATH)
    limit = int(args.limit)

    n = _build_index(conn, out_path, limit)
    _emit({"ok": True, "to": str(out_path), "rows": n}, args.json)


def _extract_obs_ids(text: str) -> List[int]:
    import re

    ids = set()
    for m in re.finditer(r"\bobs#(\d+)\b", text or ""):
        try:
            ids.add(int(m.group(1)))
        except Exception:
            continue
    return sorted(ids)


def _tokenize_query(q: str) -> List[str]:
    import re

    q = (q or "").lower().strip()
    if not q:
        return []
    parts = re.split(r"[^a-z0-9_#]+", q)
    toks = [p for p in parts if len(p) >= 3 or p.startswith("obs#")]
    return toks[:20]


def _rank_obs_ids_from_snippet(snippet: str, query: str, base_score: float = 0.0) -> List[tuple[int, float]]:
    """Heuristically map a memory_search snippet back to obs IDs.

    memory_search returns chunk-level matches; a snippet may contain multiple obs lines.
    We score each obs line by simple token overlap with the query.
    """
    import re

    toks = _tokenize_query(query)
    if not snippet:
        return []

    ranked: List[tuple[int, float]] = []
    for line in str(snippet).splitlines():
        m = re.search(r"\bobs#(\d+)\b", line)
        if not m:
            continue
        try:
            oid = int(m.group(1))
        except Exception:
            continue

        line_l = line.lower()
        overlap = sum(1 for t in toks if t in line_l)
        # Strongly prefer exact obs# queries
        exact = 5 if f"obs#{oid}" in (query or "").lower() else 0
        score = overlap + exact + (base_score * 2.0)
        ranked.append((oid, float(score)))

    # Highest score first
    ranked.sort(key=lambda x: (-x[1], x[0]))
    return ranked


def cmd_semantic(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Semantic recall via OpenClaw memory_search (black-box embeddings).

    Steps:
      1) Call Gateway /tools/invoke for memory_search
      2) Parse obs#IDs from snippets
      3) Resolve IDs back into openclaw-mem SQLite observations
    """
    query = args.query.strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    # Call OpenClaw's built-in memory_search tool
    tool_args = {
        "query": query,
        "maxResults": int(args.max_results),
        "minScore": float(args.min_score),
    }
    try:
        result = _gateway_tools_invoke(args, tool="memory_search", tool_args=tool_args, session_key=args.session_key)
    except Exception as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)

    # Parse results
    results: Any = None
    if isinstance(result, dict):
        # /tools/invoke wraps tool details
        details = result.get("details")
        if isinstance(details, dict) and isinstance(details.get("results"), list):
            results = details.get("results")
        elif isinstance(result.get("results"), list):
            results = result.get("results")
    elif isinstance(result, list):
        results = result

    if not isinstance(results, list):
        _emit({"error": f"unexpected memory_search result shape: {type(result).__name__}"}, args.json)
        sys.exit(1)

    scores: Dict[int, float] = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        snippet = str(r.get("snippet") or "")
        base = float(r.get("score") or 0.0)
        for oid, sc in _rank_obs_ids_from_snippet(snippet, query, base_score=base):
            scores[oid] = max(scores.get(oid, 0.0), sc)

    if not scores:
        _emit({"ok": True, "query": query, "matches": [], "raw": results[: int(args.raw_limit)]}, args.json)
        return

    ids_ranked = [oid for oid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]

    # Resolve observations
    q = f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?']*len(ids_ranked))})"
    rows = conn.execute(q, ids_ranked).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    out = []
    for oid in ids_ranked[: int(args.limit)]:
        r = obs_map.get(oid)
        if not r:
            continue
        out.append(r)

    _emit(
        {
            "ok": True,
            "query": query,
            "ids": ids_ranked[: int(args.limit)],
            "matches": out,
            "raw": results[: int(args.raw_limit)],
        },
        args.json,
    )


def _triage_observations(conn: sqlite3.Connection, since_ts: str, keywords: List[str], limit: int) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = [since_ts]
    for k in keywords:
        like = f"%{k}%"
        clauses.append("(lower(coalesce(summary,'')) LIKE ? OR lower(coalesce(tool_name,'')) LIKE ? OR lower(coalesce(detail_json,'')) LIKE ?)")
        params.extend([like, like, like])

    where_kw = " OR ".join(clauses) if clauses else "1=0"
    q = f"""
        SELECT id, ts, kind, tool_name, summary
        FROM observations
        WHERE ts >= ? AND ({where_kw})
        ORDER BY ts DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _triage_cron_errors(*, since_ms: int, cron_jobs_path: str, limit: int) -> List[Dict[str, Any]]:
    """Detect cron jobs whose lastStatus != ok.

    Reads OpenClaw cron store (jobs.json). Deterministic and no LLM calls.
    """
    p = Path(os.path.expanduser(cron_jobs_path))
    if not p.exists():
        return []

    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception:
        return []

    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []

    bad: List[Dict[str, Any]] = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        state = j.get("state") if isinstance(j.get("state"), dict) else {}
        last_status = state.get("lastStatus")
        last_run = state.get("lastRunAtMs")
        if last_status in (None, "ok"):
            continue
        if isinstance(last_run, (int, float)) and int(last_run) < int(since_ms):
            continue
        bad.append(
            {
                "id": j.get("id"),
                "name": j.get("name"),
                "enabled": j.get("enabled"),
                "lastStatus": last_status,
                "lastRunAtMs": last_run,
                "lastDurationMs": state.get("lastDurationMs"),
                "nextRunAtMs": (state.get("nextRunAtMs") if isinstance(state, dict) else None),
            }
        )

    bad.sort(key=lambda x: (-(int(x.get("lastRunAtMs") or 0)), str(x.get("name") or "")))
    return bad[:limit]


def _summary_has_task_marker(summary: str) -> bool:
    """Return True when summary begins with a task marker.

    Accepted prefixes (case-insensitive): TODO, TASK, REMINDER.

    Matching is width-normalized (NFKC) first, so full-width variants like
    `ＴＯＤＯ` / `ＴＡＳＫ` / `ＲＥＭＩＮＤＥＲ` are accepted.

    Accepted forms:
    - plain marker: `TODO ...`
    - bracketed marker: `[TODO] ...` or `(TODO) ...`

    Optional leading markdown wrappers are tolerated before markers:
    - blockquotes: `>` (repeatable; supports spaced `> > ...` and compact `>> ...` forms when followed by whitespace)
    - list bullets: `-`, `*`, `+`, `•`, `‣`, `∙`, `·` (when followed by whitespace)
    - markdown checkboxes: `[ ]` / `[x]` / `[✓]` / `[✔]` (when followed by whitespace)
    - ordered-list prefixes: `1.` / `1)` / `(1)` / `a.` / `a)` / `(a)` / `iv.` / `iv)` / `(iv)` (when followed by whitespace)

    A marker is considered valid when followed by:
    - ':' (including full-width '：')
    - whitespace
    - '-' / '－' / '–' / '—' / '−'
    - end-of-string

    Example formats:
    - TODO: rotate runbook
    - task- check alerts
    - (TASK): review PR
    - - [ ] TODO file patch
    """

    s = unicodedata.normalize("NFKC", (summary or "")).lstrip()
    if not s:
        return False

    markers = ("TODO", "TASK", "REMINDER")
    separators = {":", "：", "-", "－", "–", "—", "−"}
    bullet_prefixes = {"-", "*", "+", "•", "‣", "∙", "·"}
    checkbox_markers = {" ", "x", "X", "✓", "✔"}

    def _has_valid_suffix(text: str, idx: int) -> bool:
        if len(text) == idx:
            return True
        nxt = text[idx]
        return nxt in separators or nxt.isspace()

    def _matches_marker_prefix(text: str) -> bool:
        up = text.upper()
        for marker in markers:
            if not up.startswith(marker):
                continue
            if _has_valid_suffix(text, len(marker)):
                return True

        if not text:
            return False

        close_by_open = {"[": "]", "(": ")", "【": "】"}
        close = close_by_open.get(text[0])
        if close is None:
            return False

        rest_up = text[1:].upper()
        for marker in markers:
            if not rest_up.startswith(marker):
                continue

            close_idx = 1 + len(marker)
            if close_idx >= len(text) or text[close_idx] != close:
                continue

            if _has_valid_suffix(text, close_idx + 1):
                return True

        return False

    def _strip_list_prefix(text: str) -> str:
        t = text

        def _strip_ordered_prefix(value: str) -> str:
            def _is_roman_token(token: str) -> bool:
                if not token:
                    return False

                # Canonical Roman numerals (1-3999): reject permissive false
                # positives such as `IC`/`IIV` while still accepting `iv`/`IX`.
                return re.fullmatch(
                    r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})",
                    token.upper(),
                ) is not None

            if len(value) >= 4 and value[0] == "(":
                j = 1
                while j < len(value) and value[j].isdigit():
                    j += 1
                if j > 1 and j + 1 < len(value) and value[j] == ")" and value[j + 1].isspace():
                    return value[j + 1 :].lstrip()

                k = 1
                while k < len(value) and ("a" <= value[k] <= "z" or "A" <= value[k] <= "Z"):
                    k += 1
                if k > 1 and k + 1 < len(value) and value[k] == ")" and value[k + 1].isspace():
                    token = value[1:k]
                    if len(token) == 1 or _is_roman_token(token):
                        return value[k + 1 :].lstrip()

            i = 0
            while i < len(value) and value[i].isdigit():
                i += 1
            if i > 0:
                if i + 1 >= len(value):
                    return value
                if value[i] not in {".", ")"}:
                    return value
                if not value[i + 1].isspace():
                    return value
                return value[i + 1 :].lstrip()

            j = 0
            while j < len(value) and ("a" <= value[j] <= "z" or "A" <= value[j] <= "Z"):
                j += 1
            if j > 0 and j + 1 < len(value) and value[j] in {".", ")"} and value[j + 1].isspace():
                token = value[:j]
                if len(token) == 1 or _is_roman_token(token):
                    return value[j + 1 :].lstrip()

            return value

        changed = True
        while changed:
            changed = False

            block_depth = 0
            while block_depth < len(t) and t[block_depth] == ">":
                block_depth += 1

            if block_depth == 1 and len(t) >= 2 and t[1].isspace():
                t = t[1:].lstrip()
                changed = True
            elif block_depth >= 2 and block_depth < len(t) and t[block_depth].isspace():
                t = t[block_depth:].lstrip()
                changed = True

            if len(t) >= 2 and t[0] in bullet_prefixes and t[1].isspace():
                t = t[1:].lstrip()
                changed = True

            if len(t) >= 4 and t[0] == "[" and t[2] == "]" and t[1] in checkbox_markers and t[3].isspace():
                t = t[3:].lstrip()
                changed = True

            stripped_ordered = _strip_ordered_prefix(t)
            if stripped_ordered != t:
                t = stripped_ordered
                changed = True

        return t

    candidates = [s]
    stripped = _strip_list_prefix(s)
    if stripped and stripped != s:
        candidates.append(stripped)

    for cand in candidates:
        if _matches_marker_prefix(cand):
            return True

    return False


def _triage_tasks(conn: sqlite3.Connection, *, since_ts: str, importance_min: float, limit: int) -> List[Dict[str, Any]]:
    """Scan proactively stored items (tool_name=memory_store) for tasks.

    Deterministic: all logic is local.

    Matching rules:
    - kind == 'task' OR
    - summary starts with TODO/TASK/REMINDER marker
      (case-insensitive; width-normalized via NFKC; supports plain or
      bracketed forms like `[TODO]`/`(TASK)`, plus optional leading
      markdown wrappers like `>` blockquotes, list/checklist prefixes
      (`-`/`*`/`+`/`•`, `[ ]`/`[x]`/`[✓]`/`[✔]`), and ordered-list prefixes like
      `1.`/`1)`/`(1)`/`a.`/`a)`/`(a)`/`iv.`/`iv)`/`(iv)`;
      accepts ':', whitespace, '-', '－', '–', '—', '−', or marker-only)

    Importance is best-effort parsed from detail_json.importance.
    """
    rows = conn.execute(
        """
        SELECT id, ts, kind, tool_name, summary, detail_json
        FROM observations
        WHERE ts >= ? AND tool_name = 'memory_store'
        ORDER BY id DESC
        LIMIT ?
        """,
        (since_ts, max(50, limit * 20)),
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        kind = (r["kind"] or "").strip().lower()
        summary = (r["summary"] or "").strip()
        if not summary:
            continue

        is_task = kind == "task" or _summary_has_task_marker(summary)
        if not is_task:
            continue

        imp = 0.0
        try:
            dj = json.loads(r["detail_json"] or "{}")
            from openclaw_mem.importance import parse_importance_score

            imp = parse_importance_score(dj.get("importance"))
        except Exception:
            imp = 0.0

        if imp < float(importance_min):
            continue

        out.append({"id": int(r["id"]), "ts": r["ts"], "kind": r["kind"], "tool_name": r["tool_name"], "summary": summary, "importance": imp})
        if len(out) >= limit:
            break

    return out


def _load_triage_state(path_: Path) -> Dict[str, Any]:
    try:
        if not path_.exists():
            return {}
        return json.loads(path_.read_text("utf-8"))
    except Exception:
        return {}


def _atomic_write_json(path_: Path, data: Dict[str, Any]) -> None:
    path_.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".json",
    ) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path_)


def cmd_triage(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Deterministic local triage.

    Modes:
    - heartbeat (default): observations + cron-errors + tasks (new-only)
    - observations: observations only
    - cron-errors: cron store only
    - tasks: tasks only (new-only)

    Exit codes:
      0 = no new issues
      10 = needs attention (new matches found)
      2 = invalid args / error
    """
    try:
        since_minutes = int(getattr(args, "since_minutes", 60))
        limit = int(getattr(args, "limit", 10))
    except Exception:
        _emit({"error": "invalid since/limit"}, True)
        sys.exit(2)

    mode = str(getattr(args, "mode", "heartbeat") or "heartbeat").strip().lower()
    if mode not in {"heartbeat", "observations", "cron-errors", "tasks"}:
        _emit({"error": f"invalid mode: {mode}"}, True)
        sys.exit(2)

    since_minutes = max(0, since_minutes)
    limit = max(1, min(200, limit))

    kw_raw = getattr(args, "keywords", None)
    if kw_raw:
        keywords = [k.strip().lower() for k in str(kw_raw).split(",") if k.strip()]
    else:
        keywords = [
            "error",
            "failed",
            "exception",
            "traceback",
            "timeout",
            "rate_limit",
            "unauthorized",
            "forbidden",
            "not allowed",
            "db locked",
        ]

    cron_jobs_path = getattr(args, "cron_jobs_path", None) or "~/.openclaw/cron/jobs.json"

    # Tasks scan is typically longer-lived than a 30m error window.
    tasks_since_minutes = int(getattr(args, "tasks_since_minutes", 24 * 60))
    importance_min = float(getattr(args, "importance_min", 0.7))

    state_path = Path(os.path.expanduser(getattr(args, "state_path", None) or "~/.openclaw/memory/openclaw-mem/triage-state.json"))
    state = _load_triage_state(state_path)

    last_obs_id = int(((state.get("observations") or {}).get("last_alerted_id") or 0))
    last_task_id = int(((state.get("tasks") or {}).get("last_alerted_id") or 0))
    last_cron_ms = int(((state.get("cron") or {}).get("last_alerted_bad_run_at_ms") or 0))

    from datetime import timezone

    since_dt = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    since_utc = since_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    since_ms = int(since_dt.timestamp() * 1000)

    tasks_since_dt = datetime.now(timezone.utc) - timedelta(minutes=max(0, tasks_since_minutes))
    tasks_since_utc = tasks_since_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    obs_all: List[Dict[str, Any]] = []
    cron_all: List[Dict[str, Any]] = []
    tasks_all: List[Dict[str, Any]] = []

    if mode in {"heartbeat", "observations"}:
        obs_all = _triage_observations(conn, since_utc, keywords, limit)

    if mode in {"heartbeat", "cron-errors"}:
        cron_all = _triage_cron_errors(since_ms=since_ms, cron_jobs_path=str(cron_jobs_path), limit=limit)

    if mode in {"heartbeat", "tasks"}:
        tasks_all = _triage_tasks(conn, since_ts=tasks_since_utc, importance_min=importance_min, limit=limit)

    # Dedupe: only alert on *new* items
    obs_new = [m for m in obs_all if int(m.get("id") or 0) > last_obs_id]
    tasks_new = [m for m in tasks_all if int(m.get("id") or 0) > last_task_id]
    cron_new = [m for m in cron_all if int(m.get("lastRunAtMs") or 0) > last_cron_ms]

    needs_attention = (len(obs_new) > 0) or (len(cron_new) > 0) or (len(tasks_new) > 0)

    out = {
        "kind": "openclaw-mem.triage.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "mode": mode,
        "since_minutes": since_minutes,
        "since_utc": since_utc,
        "keywords": keywords,
        "cron_jobs_path": os.path.expanduser(str(cron_jobs_path)),
        "tasks_since_minutes": tasks_since_minutes,
        "tasks_since_utc": tasks_since_utc,
        "importance_min": importance_min,
        "state_path": str(state_path),
        "needs_attention": needs_attention,
        "observations": {
            "found_total": len(obs_all),
            "found_new": len(obs_new),
            "matches": obs_new,
        },
        "cron": {
            "found_total": len(cron_all),
            "found_new": len(cron_new),
            "matches": cron_new,
        },
        "tasks": {
            "found_total": len(tasks_all),
            "found_new": len(tasks_new),
            "matches": tasks_new,
        },
    }

    if needs_attention:
        # Update state maxima
        if obs_new:
            last_obs_id = max(last_obs_id, max(int(m.get("id") or 0) for m in obs_new))
        if tasks_new:
            last_task_id = max(last_task_id, max(int(m.get("id") or 0) for m in tasks_new))
        if cron_new:
            last_cron_ms = max(last_cron_ms, max(int(m.get("lastRunAtMs") or 0) for m in cron_new))

        new_state = dict(state) if isinstance(state, dict) else {}
        new_state["observations"] = {"last_alerted_id": last_obs_id}
        new_state["tasks"] = {"last_alerted_id": last_task_id}
        new_state["cron"] = {"last_alerted_bad_run_at_ms": last_cron_ms}
        _atomic_write_json(state_path, new_state)

    _emit(out, True)

    if needs_attention:
        sys.exit(10)
    sys.exit(0)


def cmd_harvest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Auto-ingest and embed observations from log file.

    Hardening goals:
    - Recover orphaned `*.processing` files after crashes.
    - Emit exactly ONE JSON payload when `--json` is used.
    - Keep fail-open semantics: missing API key should not block ingest/archival.
    """

    _apply_importance_scorer_override(args)

    default_source = os.path.expanduser("~/.openclaw/memory/openclaw-mem-observations.jsonl")
    source = Path(args.source or default_source)
    summary = IngestRunSummary()

    # 1) Collect any orphaned processing files first (crash recovery).
    processing_files = sorted(source.parent.glob(f"{source.name}.*.processing"))
    recovered = bool(processing_files)

    # 2) Rotate current source (if present) into a new processing file.
    rotated = False
    if source.exists() and source.stat().st_size > 0:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        processing = source.with_suffix(f".jsonl.{ts}.processing")
        try:
            source.rename(processing)
            processing_files.append(processing)
            processing_files.sort()
            rotated = True
        except OSError as e:
            _emit({"error": f"Failed to rotate log: {e}"}, args.json)
            sys.exit(1)

    if not processing_files:
        _emit(
            {
                "kind": "openclaw-mem.harvest.v0",
                "ts": _utcnow_iso(),
                "version": {"openclaw_mem": __version__, "schema": "v0"},
                "ok": True,
                "processed_files": 0,
                "ingested": 0,
                "reason": "source empty/missing",
                "total_seen": summary.total_seen,
                "graded_filled": summary.graded_filled,
                "skipped_existing": summary.skipped_existing,
                "skipped_disabled": summary.skipped_disabled,
                "scorer_errors": summary.scorer_errors,
                "label_counts": summary.label_counts,
            },
            args.json,
        )
        return

    # 3) Ingest all processing files (oldest first).
    inserted_ids: List[int] = []
    for processing in processing_files:
        try:
            with open(processing, "r", encoding="utf-8") as fp:
                for obs in _iter_jsonl(fp):
                    inserted_ids.append(_insert_observation(conn, obs, summary))
            conn.commit()
        except Exception as e:
            _emit({"error": f"Ingest failed: {e}", "file": str(processing)}, args.json)
            sys.exit(1)

    # 4) Update index (Route A) (best-effort).
    if getattr(args, "update_index", True):
        try:
            out_path = Path(getattr(args, "index_to", None) or DEFAULT_INDEX_PATH)
            _build_index(conn, out_path, int(getattr(args, "index_limit", 5000)))
        except Exception as e:
            print(f"Warning: failed to update index: {e}", file=sys.stderr)

    # 5) Embed (Optional, best-effort, quiet).
    embedded = 0
    embed_error: Optional[str] = None
    if args.embed:
        api_key = _get_api_key()
        if not api_key:
            embed_error = "missing_api_key"
        else:
            try:
                client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
                model = args.model
                limit = 500
                batch = 64
                now = _utcnow_iso()

                target = _embed_targets("original")[0]
                _warn_embedding_model_mismatch(
                    conn,
                    table=target["table"],
                    requested_model=model,
                    label=target["name"],
                )

                rows = conn.execute(
                    f"""
                    SELECT id, tool_name, {target['text_col']} AS text_value
                    FROM observations
                    WHERE id NOT IN (
                        SELECT observation_id FROM {target['table']} WHERE model = ?
                    )
                    AND trim(coalesce({target['text_col']}, '')) <> ''
                    ORDER BY id
                    LIMIT ?
                    """,
                    (model, limit),
                ).fetchall()

                todo = [dict(r) for r in rows]
                for i in range(0, len(todo), batch):
                    chunk = todo[i : i + batch]
                    texts = []
                    chunk_ids = []
                    for r in chunk:
                        tid = int(r["id"])
                        tool = (r.get("tool_name") or "").strip()
                        summary_text = (r.get("text_value") or "").strip()
                        text = f"{tool}: {summary_text}".strip(": ")
                        texts.append(text)
                        chunk_ids.append(tid)

                    vecs = client.embed(texts, model=model)
                    for tid, vec in zip(chunk_ids, vecs):
                        blob = pack_f32(vec)
                        norm = l2_norm(vec)
                        dim = len(vec)
                        conn.execute(
                            f"""
                            INSERT OR REPLACE INTO {target['table']}
                            (observation_id, model, dim, vector, norm, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (tid, model, dim, blob, norm, now),
                        )
                        embedded += 1

                    conn.commit()
            except Exception as e:
                embed_error = str(e)

    # 6) Archive or delete processed files.
    try:
        if args.archive_dir:
            archive_dir = Path(args.archive_dir)
            archive_dir.mkdir(parents=True, exist_ok=True)
            for processing in processing_files:
                dest = archive_dir / processing.name
                processing.rename(dest)
        else:
            for processing in processing_files:
                processing.unlink()
    except Exception as e:
        _emit({"error": f"Failed to archive/delete processing files: {e}"}, args.json)
        sys.exit(1)

    # Emit ONE harvest result payload.
    out: Dict[str, Any] = {
        "kind": "openclaw-mem.harvest.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "ingested": len(inserted_ids),
        "processed_files": len(processing_files),
        "files": [p.name for p in processing_files[:20]],
        "recovered": recovered,
        "rotated": rotated,
        "source": str(source),
        "archive": str(args.archive_dir) if args.archive_dir else "deleted",
        "total_seen": summary.total_seen,
        "graded_filled": summary.graded_filled,
        "skipped_existing": summary.skipped_existing,
        "skipped_disabled": summary.skipped_disabled,
        "scorer_errors": summary.scorer_errors,
        "label_counts": summary.label_counts,
        "embedded": embedded,
    }
    if embed_error:
        out["embed_error"] = embed_error

    _emit(out, args.json)


# Regex patterns for writeback extraction.
_LANCEDB_ID_RE = re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")
_LANCEDB_FORCE_FIELDS = (
    "importance",
    "importance_label",
    "scope",
    "trust_tier",
    "category",
)
_LANCEDB_FORCE_FIELDS_SET = set(_LANCEDB_FORCE_FIELDS)
_LANCEDB_FORCE_FIELDS_DEFAULT = (
    "importance",
    "importance_label",
    "scope",
    "category",
)

_LANCEDB_WRITEBACK_NODE_SCRIPT = r"""import { readFile } from 'node:fs/promises';
import { connect } from '@lancedb/lancedb';

const ALLOWED_IMPORTANCE_LABELS = new Set(['must_remember', 'nice_to_have', 'ignore', 'unknown']);
const ALLOWED_TRUST_TIERS = new Set(['trusted', 'untrusted', 'quarantined']);
const ALLOWED_FORCE_FIELDS = new Set(['importance', 'importance_label', 'scope', 'category', 'trust_tier']);

function normalizeForceFieldList(rawValue) {
  if (typeof rawValue === 'string') {
    return rawValue
      .split(',')
      .map((value) => String(value ?? '').trim().toLowerCase())
      .filter((value) => ALLOWED_FORCE_FIELDS.has(value));
  }

  if (!Array.isArray(rawValue)) {
    return [];
  }

  return rawValue
    .map((value) => String(value ?? '').trim().toLowerCase())
    .filter((value) => ALLOWED_FORCE_FIELDS.has(value));
}

function normalizeFieldSet(values) {
  const unique = [];
  const seen = new Set();
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    unique.push(value);
  }
  return new Set(unique);
}

function hasMeaningfulValue(value) {
  if (value === null || value === undefined) {
    return false;
  }

  if (typeof value === 'number') {
    return Number.isFinite(value);
  }

  if (typeof value === 'string') {
    return value.trim().length > 0;
  }

  return true;
}

function hasColumn(columns, name) {
  return columns.has(name);
}

function clamp01(value) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized)) return undefined;
  if (normalized < 0) return 0;
  if (normalized > 1) return 1;
  return normalized;
}

function safeIdentifier(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  return raw.replace(/'/g, "''");
}

function allowedLabel(value) {
  const normalized = String(value ?? '').trim();
  return ALLOWED_IMPORTANCE_LABELS.has(normalized) ? normalized : null;
}

function allowedTrust(value) {
  const normalized = String(value ?? '').trim();
  return ALLOWED_TRUST_TIERS.has(normalized) ? normalized : null;
}

const payloadPath = process.argv[2];
if (!payloadPath) {
  console.error('missing payload path');
  process.exit(1);
}

(async () => {
  const rawPayload = await readFile(payloadPath, 'utf8');
  const payload = JSON.parse(rawPayload);

  const dbPath = String(payload.dbPath || '').trim();
  const tableName = String(payload.tableName || '').trim();
  const dryRun = Boolean(payload.dryRun);
  const forceOverwrite = Boolean(payload.forceOverwrite);
  const requestedForceFields = normalizeForceFieldList(payload.forceFields);
  const overwriteFields = forceOverwrite ? normalizeFieldSet(requestedForceFields) : new Set();
  const updates = Array.isArray(payload.updates) ? payload.updates : [];

  const summary = {
    checked: 0,
    updated: 0,
    overwritten: 0,
    overwrittenFields: 0,
    skipped: 0,
    missingIds: [],
    errors: 0,
    errorIds: [],
  };

  function canOverwriteField(name) {
    return forceOverwrite && overwriteFields.has(name);
  }

  if (!dbPath) {
    throw new Error('missing dbPath');
  }

  const db = await connect(dbPath);
  const table = await db.openTable(tableName);
  const schema = await table.schema();
  const columns = new Set((schema?.fields || []).map((field) => String(field?.name || '').trim()));

  for (const item of updates) {
    const candidateId = String(item?.id || '').trim();
    const incoming = item?.updates || {};

    if (!candidateId) {
      summary.skipped += 1;
      continue;
    }

    const where = `id = '${safeIdentifier(candidateId)}'`;
    const rows = await table.query().where(where).limit(1).toArray();
    if (!rows || rows.length === 0) {
      summary.missingIds.push(candidateId);
      continue;
    }

    const row = rows[0] || {};
    const current = {
      importance: row.importance,
      importance_label: row.importance_label,
      scope: row.scope,
      trust_tier: row.trust_tier,
      category: row.category,
    };

    const patch = {};
    let overwrittenFields = 0;
    let rowOverwritten = false;

    const incomingImportance = clamp01(incoming.importance);
    const hasCurrentImportance = hasMeaningfulValue(current.importance);
    if (incomingImportance !== undefined && hasColumn(columns, 'importance') && (!hasCurrentImportance || canOverwriteField('importance'))) {
      const currentImportance = clamp01(current.importance);
      if (currentImportance !== incomingImportance) {
        patch.importance = incomingImportance;
        if (canOverwriteField('importance') && hasMeaningfulValue(current.importance)) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!hasCurrentImportance) {
        patch.importance = incomingImportance;
      }
    }

    const incomingLabel = allowedLabel(incoming.importance_label);
    const currentLabel = String(current.importance_label || '').trim();
    if (incomingLabel && hasColumn(columns, 'importance_label') && (!hasMeaningfulValue(currentLabel) || canOverwriteField('importance_label'))) {
      if (currentLabel !== incomingLabel) {
        patch.importance_label = incomingLabel;
        if (canOverwriteField('importance_label') && currentLabel) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentLabel) {
        patch.importance_label = incomingLabel;
      }
    }

    const incomingScope = String(incoming.scope || '').trim();
    if (incomingScope && hasColumn(columns, 'scope') && (!hasMeaningfulValue(current.scope) || canOverwriteField('scope'))) {
      const currentScope = String(current.scope || '').trim();
      if (currentScope !== incomingScope) {
        patch.scope = incomingScope;
        if (canOverwriteField('scope') && currentScope) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentScope) {
        patch.scope = incomingScope;
      }
    }

    const incomingTrust = allowedTrust(incoming.trust_tier);
    const currentTrust = String(current.trust_tier || '').trim();
    if (incomingTrust && hasColumn(columns, 'trust_tier') && (!hasMeaningfulValue(currentTrust) || canOverwriteField('trust_tier'))) {
      if (currentTrust !== incomingTrust) {
        patch.trust_tier = incomingTrust;
        if (canOverwriteField('trust_tier') && currentTrust) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentTrust) {
        patch.trust_tier = incomingTrust;
      }
    }

    const incomingCategory = String(incoming.category || '').trim();
    if (incomingCategory && hasColumn(columns, 'category') && (!hasMeaningfulValue(current.category) || canOverwriteField('category'))) {
      const currentCategory = String(current.category || '').trim();
      if (currentCategory !== incomingCategory) {
        patch.category = incomingCategory;
        if (canOverwriteField('category') && currentCategory) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentCategory) {
        patch.category = incomingCategory;
      }
    }

    summary.checked += 1;
    if (Object.keys(patch).length === 0) {
      summary.skipped += 1;
      continue;
    }

    if (!dryRun) {
      try {
        await table.update({ where, values: patch });
      } catch (err) {
        summary.errors += 1;
        summary.errorIds.push(candidateId);
        continue;
      }
    }

    summary.updated += 1;
    if (rowOverwritten) {
      summary.overwritten += 1;
      summary.overwrittenFields += overwrittenFields;
    }
  }

  console.log(JSON.stringify({ success: true, summary }));
  await db.close?.();
})().catch((error) => {
  console.error(String(error?.stack || error));
  process.exit(1);
});
"""

def _coerce_lancedb_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None

    m = _LANCEDB_ID_RE.search(value)
    if not m:
        return None

    return m.group(0).strip()


def _extract_lancedb_id_from_obj(value: Any, *, hint_keys: Optional[Tuple[str, ...]] = None) -> Optional[str]:
    keys = set(k.lower() for k in (hint_keys or ("memory_id", "memoryid", "memory_uuid", "memoryuuid", "lancedb_id", "lancedbid", "lancedb", "lance_id")))

    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                continue

            if key.lower() in keys:
                candidate = _coerce_lancedb_id(nested)
                if candidate:
                    return candidate

            if isinstance(nested, (dict, list)):
                candidate = _extract_lancedb_id_from_obj(nested, hint_keys=hint_keys)
                if candidate:
                    return candidate

        return None

    if isinstance(value, list):
        for item in value:
            candidate = _extract_lancedb_id_from_obj(item, hint_keys=hint_keys)
            if candidate:
                return candidate

    return _coerce_lancedb_id(value)


def _extract_lancedb_id(row: sqlite3.Row, detail_obj: Dict[str, Any]) -> Optional[str]:
    for src in (
        detail_obj,
        detail_obj.get("result"),
        detail_obj.get("response"),
        detail_obj.get("output"),
        detail_obj.get("payload"),
        detail_obj.get("memory"),
        detail_obj.get("data"),
    ):
        if not isinstance(src, dict):
            continue

        direct = _extract_lancedb_id_from_obj(src)
        if direct:
            return direct

    summary = str(row["summary"] or "").strip()
    summary_en = str(row["summary_en"] or "").strip()

    for raw in (summary, summary_en):
        if not raw:
            continue

        m = _LANCEDB_ID_RE.search(raw)
        if m:
            return m.group(0).strip()

    return None


def _extract_importance_from_detail(detail_obj: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    from openclaw_mem.importance import label_from_score

    if not isinstance(detail_obj, dict):
        return (None, None)

    raw = detail_obj.get("importance")
    score: Optional[float] = None
    label: Optional[str] = None

    if isinstance(raw, dict):
        label = _normalize_importance_label(raw.get("label"))
        candidate = raw.get("score")
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            score = max(0.0, min(1.0, float(candidate)))
        elif isinstance(candidate, str):
            try:
                candidate_score = float(candidate.strip())
            except ValueError:
                candidate_score = None
            if candidate_score is not None:
                score = max(0.0, min(1.0, float(candidate_score)))

    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        score = max(0.0, min(1.0, float(raw)))
    elif isinstance(raw, str):
        if raw.strip():
            try:
                score = max(0.0, min(1.0, float(raw.strip())))
            except ValueError:
                score = None

    if score is None and label is None:
        return (None, None)

    if label not in {"must_remember", "nice_to_have", "ignore", "unknown"}:
        label = None

    if score is None:
        score_map = {
            "must_remember": 0.9,
            "nice_to_have": 0.7,
            "ignore": 0.2,
            "unknown": 0.0,
        }
        if not label:
            return (None, None)
        score = score_map.get(label, 0.0)
    elif not label:
        label = _normalize_importance_label(label_from_score(score))

    return (score, label)


def _extract_writeback_updates(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    detail_obj = _pack_parse_detail_json(row["detail_json"])

    lancedb_id = _extract_lancedb_id(row, detail_obj)
    if not lancedb_id:
        return None

    updates: Dict[str, Any] = {}

    score, label = _extract_importance_from_detail(detail_obj)
    if score is not None:
        updates["importance"] = score

    if label:
        updates["importance_label"] = label

    scope = str(detail_obj.get("scope") or row["kind"] or "").strip()
    if scope:
        updates["scope"] = scope

    trust = _pack_trust_tier(detail_obj)
    if trust != "unknown":
        updates["trust_tier"] = trust

    if isinstance(detail_obj.get("category"), str):
        updates["category"] = (detail_obj.get("category") or "").strip()
    elif isinstance(row["kind"], str):
        updates["category"] = str(row["kind"]).strip()

    return {"id": lancedb_id, "updates": updates}


def cmd_writeback_lancedb(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Write governance metadata from SQLite ledger rows back to LanceDB."""

    dry_run = bool(args.dry_run)
    limit = max(1, int(args.limit))
    batch = max(1, int(getattr(args, "batch", 50)))
    force_overwrite = bool(getattr(args, "force", False))

    force_fields: List[str] = []
    if force_overwrite:
        raw_force_fields = str(getattr(args, "force_fields", "")).strip() if getattr(args, "force_fields", None) is not None else ""
        if raw_force_fields:
            requested = [f.strip().lower() for f in raw_force_fields.split(",") if f.strip()]
            bad_fields = [f for f in requested if f not in _LANCEDB_FORCE_FIELDS_SET]
            if bad_fields:
                _emit(
                    {
                        "error": "invalid --force-fields value(s)",
                        "invalidFields": sorted(set(bad_fields)),
                        "allowedFields": sorted(_LANCEDB_FORCE_FIELDS_SET),
                    },
                    args.json,
                )
                sys.exit(1)

            # Preserve order, de-dupe
            force_fields = list(dict.fromkeys([f for f in requested if f in _LANCEDB_FORCE_FIELDS_SET]))
        else:
            force_fields = list(_LANCEDB_FORCE_FIELDS_DEFAULT)

    lancedb_path = os.path.expanduser(str(getattr(args, "lancedb", "")).strip())
    table = (getattr(args, "table", "") or "").strip()
    if not lancedb_path:
        _emit({"error": "missing --lancedb"}, args.json)
        sys.exit(1)

    if not table:
        _emit({"error": "missing --table"}, args.json)
        sys.exit(1)

    engine_path = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine"
    if not engine_path.exists():
        _emit({"error": f"openclaw-mem-engine path not found: {engine_path}"}, args.json)
        sys.exit(1)

    rows = conn.execute(
        """
        SELECT id, kind, summary, summary_en, detail_json
        FROM observations
        WHERE tool_name = 'memory_store'
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    prepared: List[Dict[str, Any]] = []
    skipped_no_id = 0

    for row in rows:
        payload = _extract_writeback_updates(row)
        if not payload:
            skipped_no_id += 1
            continue

        prepared.append(payload)

    if not prepared:
        _emit(
            {
                "ok": True,
                "dryRun": dry_run,
                "db": lancedb_path,
                "table": table,
                "limit": limit,
                "batch": batch,
                "forceOverwrite": force_overwrite,
                "forceFields": force_fields,
                "checked": skipped_no_id,
                "updated": 0,
                "overwritten": 0,
                "overwrittenFields": 0,
                "skipped": skipped_no_id,
                "missing": 0,
                "missingIds": [],
            },
            args.json,
        )
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False, dir=str(engine_path)) as script_file:
        script_file.write(_LANCEDB_WRITEBACK_NODE_SCRIPT)

    total_updated = 0
    total_overwritten = 0
    total_overwritten_fields = 0
    total_skipped = skipped_no_id
    total_checked = skipped_no_id
    missing_ids: List[str] = []
    total_errors = 0
    error_ids: List[str] = []

    try:
        for i in range(0, len(prepared), batch):
            chunk = prepared[i : i + batch]
            payload = {
                "dbPath": lancedb_path,
                "tableName": table,
                "dryRun": dry_run,
                "forceOverwrite": force_overwrite,
                "forceFields": force_fields,
                "updates": chunk,
            }

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as payload_file:
                json.dump(payload, payload_file, ensure_ascii=False)
                payload_path = payload_file.name

            proc = subprocess.run(
                ["node", script_file.name, payload_path],
                capture_output=True,
                text=True,
                cwd=str(engine_path),
                check=False,
            )
            os.unlink(payload_path)

            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                _emit({"error": "lancedb writeback execution failed", "detail": detail}, args.json)
                sys.exit(1)

            try:
                parsed = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                _emit({"error": "lancedb writeback returned invalid JSON"}, args.json)
                sys.exit(1)

            summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
            if not isinstance(summary, dict):
                _emit({"error": "lancedb writeback returned malformed summary"}, args.json)
                sys.exit(1)

            total_checked += int(summary.get("checked", 0))
            total_updated += int(summary.get("updated", 0))
            total_overwritten += int(summary.get("overwritten", 0))
            total_overwritten_fields += int(summary.get("overwrittenFields", 0))
            total_skipped += int(summary.get("skipped", 0))
            missing_ids.extend(summary.get("missingIds", []))

            chunk_errors = int(summary.get("errors", 0))
            total_errors += chunk_errors
            for error_id in summary.get("errorIds", []):
                if isinstance(error_id, str):
                    error_ids.append(error_id)

    finally:
        os.unlink(script_file.name)

    out = {
        "ok": total_errors == 0,
        "dryRun": dry_run,
        "db": lancedb_path,
        "table": table,
        "limit": limit,
        "batch": batch,
        "forceOverwrite": force_overwrite,
        "forceFields": force_fields,
        "checked": total_checked,
        "updated": total_updated,
        "overwritten": total_overwritten,
        "overwrittenFields": total_overwritten_fields,
        "skipped": total_skipped,
        "missing": len(missing_ids),
        "missingIds": missing_ids,
    }

    if total_errors:
        out["error_count"] = total_errors
        out["errorIds"] = error_ids

    _emit(out, args.json)

    if total_errors:
        sys.exit(1)

def cmd_store(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Proactive memory storage (SQLite + Vector + Markdown)."""
    text = args.text.strip()
    if not text:
        _emit({"error": "empty text"}, args.json)
        sys.exit(1)

    text_en = (getattr(args, "text_en", None) or "").strip() or None
    lang = (getattr(args, "lang", None) or "").strip() or None

    from openclaw_mem.importance import make_importance

    importance_obj = make_importance(
        float(args.importance),
        method="manual-via-cli",
        rationale="Provided via openclaw-mem store --importance.",
        version=1,
    )

    # 1. Insert into SQLite
    obs = {
        "kind": args.category,  # e.g., 'fact', 'preference'
        "summary": text,
        "summary_en": text_en,
        "lang": lang,
        "tool_name": "memory_store",
        "detail": {"importance": importance_obj},
    }
    rowid = _insert_observation(conn, obs)

    # 2. Embed and store vector
    api_key = _get_api_key()
    if api_key:
        try:
            client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
            created_at = _utcnow_iso()

            vec = client.embed([text], model=args.model)[0]
            blob = pack_f32(vec)
            norm = l2_norm(vec)
            conn.execute(
                """
                INSERT OR REPLACE INTO observation_embeddings
                (observation_id, model, dim, vector, norm, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rowid, args.model, len(vec), blob, norm, created_at),
            )

            if text_en:
                vec_en = client.embed([text_en], model=args.model)[0]
                blob_en = pack_f32(vec_en)
                norm_en = l2_norm(vec_en)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO observation_embeddings_en
                    (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (rowid, args.model, len(vec_en), blob_en, norm_en, created_at),
                )

            conn.commit()
        except Exception as e:
            # Non-fatal: storage succeeded, vector failed
            print(f"Warning: Failed to embed memory: {e}", file=sys.stderr)
    else:
        conn.commit()
        print("Warning: No API key, skipping embedding", file=sys.stderr)

    # 3. Append to memory/YYYY-MM-DD.md
    workspace = Path(args.workspace) if hasattr(args, "workspace") and args.workspace else DEFAULT_WORKSPACE

    # Fallback logic for workspace memory dir
    memory_dir = workspace / "memory"
    if not memory_dir.exists():
         alt = Path(os.path.expanduser("~/.openclaw/memory"))
         if alt.exists():
             memory_dir = alt

    date_str = datetime.now().strftime("%Y-%m-%d")
    md_file = memory_dir / f"{date_str}.md"

    md_entry = f"- [{args.category.upper()}] {text} (importance: {importance_obj['score']:.2f}, {importance_obj['label']})\n"

    try:
        _atomic_append_file(md_file, md_entry)
        stored_path = str(md_file)
    except Exception as e:
        stored_path = f"failed ({e})"

    _emit({"ok": True, "id": rowid, "file": stored_path, "embedded": bool(api_key)}, args.json)




# --- Graphic memory (GraphRAG-lite) — v0 skeleton (index-first + progressive disclosure) ---
#
# v0 design goals:
# - deterministic and local-only
# - safe-by-default (summary/snippet only; no detail_json dumps)
# - budgeted injection payloads (IndexPack / ContextPack)
#
# v0 implementation note:
# - this is NOT a full entity/KG system. It is a minimal link-graph using
#   timeline adjacency as the neighborhood expansion primitive.


def _graph_record_ref(obs_id: int) -> str:
    return f"obs:{int(obs_id)}"


def _graph_parse_record_ref(token: str) -> int:
    t = (token or "").strip()
    if not t:
        raise ValueError("empty record ref")
    if t.startswith("obs:"):
        t = t.split(":", 1)[1]
    return int(t)


def _graph_fts_sanitize_query(q: str) -> str:
    """Make ad-hoc keyword queries safer for SQLite FTS.

    Why:
    - FTS query syntax treats '-' specially. A query like `auto-capture` or
      `capture-md` can throw `sqlite3.OperationalError: no such column: capture`.
    - For "search bar" usage, we prefer a best-effort match over crashing.

    Strategy:
    - Quote tokens that contain '-' (turn them into phrase queries).
    - Preserve common boolean operators (OR/AND/NOT) and parentheses.
    """

    parts = []
    for raw in (q or "").split():
        if not raw:
            continue

        upper = raw.upper()
        if upper in {"OR", "AND", "NOT"}:
            parts.append(upper)
            continue

        # Peel parentheses + lightweight trailing punctuation.
        tok = raw
        prefix = ""
        while tok.startswith("("):
            prefix += "("
            tok = tok[1:]

        suffix = ""
        while tok.endswith(")"):
            suffix = ")" + suffix
            tok = tok[:-1]

        trail = ""
        while tok and tok[-1] in ",.;:":
            trail = tok[-1] + trail
            tok = tok[:-1]

        if tok and "-" in tok and not (tok.startswith('"') and tok.endswith('"')):
            tok = f'"{tok}"'

        parts.append(prefix + tok + trail + suffix)

    return " ".join(parts).strip()


def _graph_search_rows(conn: sqlite3.Connection, query: str, limit: int) -> List[sqlite3.Row]:
    q = (query or "").strip()
    if not q:
        return []

    def _run(match_q: str) -> List[sqlite3.Row]:
        return conn.execute(
            """
            SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
                   snippet(observations_fts, 0, '[', ']', '…', 12) AS snippet,
                   snippet(observations_fts, 1, '[', ']', '…', 12) AS snippet_en,
                   bm25(observations_fts) AS score
            FROM observations_fts
            JOIN observations o ON o.id = observations_fts.rowid
            WHERE observations_fts MATCH ?
            ORDER BY score ASC
            LIMIT ?;
            """,
            (match_q, int(limit)),
        ).fetchall()

    try:
        rows = _run(q)
    except sqlite3.OperationalError:
        # Common failure mode: hyphenated terms in a "search bar" style query.
        q2 = _graph_fts_sanitize_query(q)
        if q2 and q2 != q:
            try:
                rows = _run(q2)
            except sqlite3.OperationalError:
                rows = []
        else:
            rows = []

    # Fallback for CJK keyword queries when FTS5 tokenizer cannot split terms well.
    if not rows and _has_cjk(q):
        rows = _search_cjk_fallback(conn, q, int(limit))

    return rows


def _graph_row_title(r: sqlite3.Row) -> str:
    # Prefer human-friendly summary; fallback to snippet.
    summary = (r["summary"] or "").replace("\n", " ").strip()
    if summary:
        s = summary
    else:
        s = (r["snippet"] or "").replace("\n", " ").strip()

    if not s:
        kind = (r["kind"] or "obs").strip()
        tool = (r["tool_name"] or "").strip()
        s = f"{kind}:{tool}".strip(":")

    # Hard cap for safety in index packs.
    if len(s) > 180:
        s = s[:177] + "…"
    return s


def _graph_index_payload(
    conn: sqlite3.Connection,
    *,
    query: str,
    scope: Optional[str],
    limit: int,
    window: int,
    suggest_limit: int,
    budget_tokens: int,
) -> Dict[str, Any]:
    rows = _graph_search_rows(conn, query, limit)

    # Candidate list (L0)
    candidates: List[Dict[str, Any]] = []
    cand_ids: List[int] = []
    for r in rows:
        oid = int(r["id"])
        cand_ids.append(oid)
        candidates.append(
            {
                "recordRef": _graph_record_ref(oid),
                "id": oid,
                "ts": r["ts"],
                "kind": r["kind"],
                "tool_name": r["tool_name"],
                "score": float(r["score"]) if r["score"] is not None else None,
                "title": _graph_row_title(r),
                "why_relevant": "fts_match",
            }
        )

    # Neighborhood suggestions (simple deterministic link-graph): timeline adjacency.
    neighbor_support: Dict[int, List[int]] = {}
    if window and cand_ids:
        seen = set(cand_ids)
        for oid in cand_ids:
            lo, hi = oid - window, oid + window
            nrows = conn.execute(
                "SELECT id FROM observations WHERE id BETWEEN ? AND ? ORDER BY id",
                (lo, hi),
            ).fetchall()
            for nr in nrows:
                nid = int(nr[0])
                if nid in seen:
                    continue
                neighbor_support.setdefault(nid, []).append(oid)

    suggested_next: List[Dict[str, Any]] = []
    if suggest_limit and neighbor_support:
        for nid, supports in sorted(neighbor_support.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:suggest_limit]:
            suggested_next.append(
                {
                    "recordRef": _graph_record_ref(nid),
                    "id": nid,
                    "reason": "timeline_adjacent",
                    "support": {
                        "from": [_graph_record_ref(x) for x in supports[:5]],
                        "count": len(supports),
                    },
                }
            )

    # Build index_text (the injection payload) and enforce budget.
    lines: List[str] = []
    lines.append("[GRAPH_INDEX v0]")
    lines.append(f"Query: {query}")
    if scope:
        lines.append(f"Scope: {scope}")
    lines.append("")
    lines.append("Top candidates:")

    included: List[Dict[str, Any]] = []
    for c in candidates:
        line = f"- {c['recordRef']} [{c.get('kind')}] {c.get('tool_name') or ''} :: {c.get('title') or ''}".strip()
        new_est = _estimate_tokens("\n".join(lines + [line]))
        if new_est > budget_tokens and included:
            break
        lines.append(line)
        included.append(c)

    # Suggested expansions section (best-effort under budget)
    if suggested_next:
        lines.append("")
        lines.append("Suggested next expansions:")
        for s in suggested_next:
            line = f"- {s['recordRef']} reason={s['reason']} from={','.join(s['support']['from'])}".strip()
            new_est = _estimate_tokens("\n".join(lines + [line]))
            if new_est > budget_tokens:
                break
            lines.append(line)

    index_text = "\n".join(lines).strip() + "\n"

    # Defensive hard truncation to satisfy strict budgets (even for tiny budgets).
    max_chars = max(0, int(budget_tokens) * 4 - 3)
    if len(index_text) > max_chars:
        index_text = index_text[:max_chars].rstrip() + "\n"

    return {
        "kind": "openclaw-mem.graph.index.v0",
        "ts": _utcnow_iso(),
        "query": {"text": query, "scope": scope},
        "budget": {
            "budgetTokens": budget_tokens,
            "estimatedTokens": _estimate_tokens(index_text),
            "window": window,
        },
        "top_candidates": included,
        "suggested_next_expansions": suggested_next,
        "index_text": index_text,
    }


def cmd_graph_index(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (args.query or "").strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    payload = _graph_index_payload(
        conn,
        query=query,
        scope=(getattr(args, "scope", None) or "").strip() or None,
        limit=max(1, int(getattr(args, "limit", 12))),
        window=max(0, int(getattr(args, "window", 2))),
        suggest_limit=max(0, int(getattr(args, "suggest_limit", 6))),
        budget_tokens=max(1, int(getattr(args, "budget_tokens", 900))),
    )

    if bool(args.json):
        _emit(payload, True)
        return
    print(payload["index_text"], end="")


def _graph_pack_payload(
    conn: sqlite3.Connection,
    *,
    raw_ids: List[str],
    budget_tokens: int,
    max_items: int,
    allow_empty: bool = False,
) -> Dict[str, Any]:
    if not raw_ids:
        if allow_empty:
            return {
                "kind": "openclaw-mem.graph.pack.v0",
                "ts": _utcnow_iso(),
                "budget": {
                    "budgetTokens": budget_tokens,
                    "estimatedTokens": 0,
                },
                "items": [],
                "bundle_text": "",
            }
        raise ValueError("no ids")

    ids: List[int] = []
    for t in raw_ids:
        try:
            ids.append(_graph_parse_record_ref(t))
        except Exception as e:
            raise ValueError(f"bad id: {t}") from e

    # Dedupe while preserving order
    uniq: List[int] = []
    seen: set[int] = set()
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        uniq.append(i)
    uniq = uniq[:max_items]

    rows = conn.execute(
        f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?']*len(uniq))})",
        uniq,
    ).fetchall()

    row_map = {int(r["id"]): r for r in rows}
    items: List[Dict[str, Any]] = []
    for oid in uniq:
        r = row_map.get(int(oid))
        if r is None:
            continue
        items.append(
            {
                "recordRef": _graph_record_ref(oid),
                "id": oid,
                "ts": r["ts"],
                "kind": r["kind"],
                "tool_name": r["tool_name"],
                "summary": (r["summary"] or "").replace("\n", " ").strip(),
            }
        )

    lines: List[str] = []
    lines.append("[GRAPH_CONTEXT v0]")
    lines.append(f"Items: {len(items)}")
    lines.append("")

    included_items: List[Dict[str, Any]] = []
    for idx, it in enumerate(items, 1):
        line = f"{idx}) {it['recordRef']} ts={it.get('ts')} [{it.get('kind')}] {it.get('tool_name') or ''} :: {it.get('summary') or ''}".strip()
        new_est = _estimate_tokens("\n".join(lines + [line]))
        if new_est > budget_tokens and included_items:
            break
        lines.append(line)
        included_items.append(it)

    bundle_text = "\n".join(lines).strip() + "\n"

    # Defensive hard truncation to satisfy strict budgets (even for tiny budgets).
    max_chars = max(0, int(budget_tokens) * 4 - 3)
    if len(bundle_text) > max_chars:
        bundle_text = bundle_text[:max_chars].rstrip() + "\n"

    return {
        "kind": "openclaw-mem.graph.pack.v0",
        "ts": _utcnow_iso(),
        "budget": {
            "budgetTokens": budget_tokens,
            "estimatedTokens": _estimate_tokens(bundle_text),
        },
        "items": included_items,
        "bundle_text": bundle_text,
    }


def cmd_graph_pack(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    raw_ids = list(getattr(args, "ids", []) or [])
    budget_tokens = max(1, int(getattr(args, "budget_tokens", 1500)))
    max_items = max(1, int(getattr(args, "max_items", 20)))

    try:
        payload = _graph_pack_payload(
            conn,
            raw_ids=raw_ids,
            budget_tokens=budget_tokens,
            max_items=max_items,
        )
    except ValueError as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    if bool(args.json):
        _emit(payload, True)
        return
    print(payload["bundle_text"], end="")


def _graph_preflight_selection(index_payload: Dict[str, Any], take: int) -> List[str]:
    refs: List[str] = []
    for c in list(index_payload.get("top_candidates") or []):
        ref = (c or {}).get("recordRef")
        if isinstance(ref, str) and ref.strip():
            refs.append(ref.strip())

    for s in list(index_payload.get("suggested_next_expansions") or []):
        ref = (s or {}).get("recordRef")
        if isinstance(ref, str) and ref.strip():
            refs.append(ref.strip())

    deduped: List[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        deduped.append(ref)
        if len(deduped) >= take:
            break

    return deduped


def cmd_graph_preflight(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (args.query or "").strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    scope = (getattr(args, "scope", None) or "").strip() or None
    limit = max(1, int(getattr(args, "limit", 12)))
    window = max(0, int(getattr(args, "window", 2)))
    suggest_limit = max(0, int(getattr(args, "suggest_limit", 6)))
    budget_tokens = max(1, int(getattr(args, "budget_tokens", 1200)))
    take = max(1, int(getattr(args, "take", 12)))

    index_payload = _graph_index_payload(
        conn,
        query=query,
        scope=scope,
        limit=limit,
        window=window,
        suggest_limit=suggest_limit,
        budget_tokens=budget_tokens,
    )

    selected_refs = _graph_preflight_selection(index_payload, take=take)

    pack_payload = _graph_pack_payload(
        conn,
        raw_ids=selected_refs,
        budget_tokens=budget_tokens,
        max_items=max(1, take),
        allow_empty=True,
    )

    payload = {
        "kind": "openclaw-mem.graph.preflight.v0",
        "ts": _utcnow_iso(),
        "query": {"text": query, "scope": scope},
        "selection": {
            "take": take,
            "recordRefs": selected_refs,
            "selectedCount": len(selected_refs),
        },
        "budget": {
            "budgetTokens": budget_tokens,
            "estimatedTokens": _estimate_tokens(pack_payload["bundle_text"]),
        },
        "index": {
            "kind": index_payload.get("kind"),
            "budget": index_payload.get("budget"),
            "top_candidates": index_payload.get("top_candidates", []),
            "suggested_next_expansions": index_payload.get("suggested_next_expansions", []),
        },
        "pack": pack_payload,
        "items": pack_payload.get("items", []),
        "bundle_text": pack_payload.get("bundle_text", ""),
    }

    if bool(args.json):
        _emit(payload, True)
        return
    print(pack_payload.get("bundle_text", ""), end="")


def _graph_env_bool_status(name: str, *, default: bool = False) -> Dict[str, Any]:
    raw = os.getenv(name)
    if raw is None:
        return {
            "present": False,
            "raw": None,
            "normalized": None,
            "enabled": bool(default),
            "valid": True,
            "default": bool(default),
            "reason": "unset_default",
        }

    normalized = str(raw).strip().lower()
    truthy = {"1", "true", "on", "yes", "y", "t"}
    falsy = {"0", "false", "off", "no", "n", "f", ""}

    if normalized in truthy:
        enabled = True
        valid = True
    elif normalized in falsy:
        enabled = False
        valid = True
    else:
        enabled = bool(default)
        valid = False

    reason = "invalid_fallback_default"
    if valid and enabled:
        reason = "parsed_truthy"
    elif valid and not enabled:
        reason = "parsed_falsy"

    return {
        "present": True,
        "raw": str(raw),
        "normalized": normalized,
        "enabled": enabled,
        "valid": valid,
        "default": bool(default),
        "reason": reason,
    }


def cmd_graph_auto_status(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _ = conn
    flags = {
        "OPENCLAW_MEM_GRAPH_AUTO_RECALL": _graph_env_bool_status("OPENCLAW_MEM_GRAPH_AUTO_RECALL", default=False),
        "OPENCLAW_MEM_GRAPH_AUTO_CAPTURE": _graph_env_bool_status("OPENCLAW_MEM_GRAPH_AUTO_CAPTURE", default=False),
        "OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD": _graph_env_bool_status("OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD", default=False),
    }

    payload = {
        "kind": "openclaw-mem.graph.auto-status.v0",
        "ts": _utcnow_iso(),
        "flags": flags,
    }

    if bool(args.json):
        _emit(payload, True)
        return

    for name, st in flags.items():
        raw = st.get("raw")
        raw_show = raw if isinstance(raw, str) else "(unset)"
        print(
            f"{name}: enabled={str(bool(st.get('enabled'))).lower()} "
            f"valid={str(bool(st.get('valid'))).lower()} raw={raw_show}"
        )


def _graph_capture_md_norm_ext(ext: str) -> str:
    v = str(ext or "").strip().lower()
    if not v:
        return ""
    if not v.startswith("."):
        v = "." + v
    return v


def _graph_capture_md_includes(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for raw in list(values or []):
        ext = _graph_capture_md_norm_ext(raw)
        if not ext or ext in out:
            continue
        out.append(ext)
    if out:
        return out
    return [*DEFAULT_GRAPH_CAPTURE_MD_INCLUDES]


def _graph_capture_md_excludes(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for raw in list(values or []):
        pat = str(raw or "").strip()
        if not pat or pat in out:
            continue
        out.append(pat)
    if out:
        return out
    return [*DEFAULT_GRAPH_CAPTURE_MD_EXCLUDES]


def _graph_capture_md_is_excluded(path: Path, patterns: List[str]) -> bool:
    raw = path.as_posix()
    for pat in patterns:
        if fnmatch.fnmatch(raw, pat):
            return True
    return False


def _graph_capture_md_collect_files(
    raw_paths: List[str],
    *,
    includes: List[str],
    excludes: List[str],
    max_files: int,
) -> Tuple[List[Path], int]:
    selected: List[Path] = []
    seen: set[str] = set()
    errors = 0

    for raw in raw_paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            errors += 1
            continue

        candidates: List[Path] = []
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            candidates = [x for x in p.rglob("*") if x.is_file()]
        else:
            errors += 1
            continue

        for fp in sorted(candidates):
            if len(selected) >= max_files:
                return selected, errors

            abs_key = str(fp)
            if abs_key in seen:
                continue

            ext = fp.suffix.lower()
            if ext not in includes:
                continue

            if _graph_capture_md_is_excluded(fp, excludes):
                continue

            seen.add(abs_key)
            selected.append(fp)

    return selected, errors


def _graph_capture_md_parse_sections(
    text: str,
    *,
    min_heading_level: int,
    max_sections: int,
) -> List[Dict[str, Any]]:
    if max_sections <= 0:
        return []

    heading_re = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
    fence_re = re.compile(r"^\s{0,3}(```+|~~~+)")

    lines = text.splitlines()
    sections: List[Dict[str, Any]] = []
    active: Optional[Dict[str, Any]] = None
    in_code = False

    for idx, line in enumerate(lines, 1):
        if fence_re.match(line):
            in_code = not in_code
            continue

        if in_code:
            continue

        m = heading_re.match(line)
        if not m:
            continue

        if active is not None:
            active["end_line"] = idx - 1
            sections.append(active)
            active = None

        level = len(m.group(1))
        heading = re.sub(r"\s+#+\s*$", "", (m.group(2) or "").strip()).strip() or "(untitled)"

        if level >= min_heading_level:
            active = {
                "heading": heading,
                "heading_level": level,
                "start_line": idx,
                "end_line": len(lines),
            }

    if active is not None:
        active["end_line"] = len(lines)
        sections.append(active)

    return sections[:max_sections]


def _graph_capture_md_first_lines_for_fingerprint(
    lines: List[str],
    *,
    start_line: int,
    end_line: int,
) -> List[str]:
    fence_re = re.compile(r"^\s{0,3}(```+|~~~+)")
    out: List[str] = []
    in_code = False

    begin = max(start_line + 1, 1)
    end = min(end_line, len(lines))
    for i in range(begin, end + 1):
        raw = lines[i - 1]
        if fence_re.match(raw):
            in_code = not in_code
            continue
        if in_code:
            continue

        v = raw.strip()
        if not v:
            continue

        out.append(v)
        if len(out) >= 5:
            break

    return out


def _graph_capture_md_summary(path: Path, heading: str) -> str:
    heading_text = re.sub(r"\s+", " ", (heading or "").replace("\n", " ")).strip() or "(untitled)"
    summary = f"[MD] {path.name}#{heading_text}"
    if len(summary) > 180:
        return summary[:177] + "…"
    return summary


def _graph_capture_md_git_root(file_path: Path, cache: Dict[str, Optional[Path]]) -> Optional[Path]:
    dir_key = str(file_path.parent.resolve())
    if dir_key in cache:
        return cache[dir_key]

    p = subprocess.run(
        ["git", "-C", str(file_path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        cache[dir_key] = None
        return None

    raw = (p.stdout or "").strip()
    if not raw:
        cache[dir_key] = None
        return None

    root = Path(raw).expanduser().resolve()
    cache[dir_key] = root
    return root


def _graph_capture_md_seen(conn: sqlite3.Connection, fingerprint: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM graph_capture_md_seen WHERE fingerprint = ? LIMIT 1",
        (fingerprint,),
    ).fetchone()
    return row is not None


def _graph_capture_md_mark_seen(
    conn: sqlite3.Connection,
    *,
    fingerprint: str,
    source_path: str,
    mtime: float,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO graph_capture_md_seen (fingerprint, source_path, mtime) VALUES (?, ?, ?)",
        (fingerprint, source_path, float(mtime)),
    )


def cmd_graph_capture_md(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    raw_paths = list(getattr(args, "path", []) or [])
    if not raw_paths:
        _emit({"error": "missing --path"}, True)
        sys.exit(2)

    includes = _graph_capture_md_includes(getattr(args, "include", None))
    excludes = _graph_capture_md_excludes(getattr(args, "exclude_glob", None))
    max_files = max(1, int(getattr(args, "max_files", 200) or 200))
    max_sections_per_file = max(1, int(getattr(args, "max_sections_per_file", 50) or 50))
    min_heading_level = max(1, int(getattr(args, "min_heading_level", 2) or 2))
    since_hours = max(0.0, float(getattr(args, "since_hours", 24) or 24))

    state_path = Path(
        os.path.expanduser(
            getattr(args, "state", None) or DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH
        )
    )

    state = _load_triage_state(state_path)
    if not isinstance(state, dict):
        state = {}
    files_state = state.get("files") if isinstance(state.get("files"), dict) else {}

    since_ts = datetime.now(timezone.utc).timestamp() - (since_hours * 3600.0)

    files, collect_errors = _graph_capture_md_collect_files(
        raw_paths,
        includes=includes,
        excludes=excludes,
        max_files=max_files,
    )

    totals = {
        "scanned_files": 0,
        "changed_files": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "errors": int(collect_errors),
    }

    per_path: List[Dict[str, Any]] = []
    for raw in raw_paths:
        p = Path(raw).expanduser().resolve()
        per_path.append(
            {
                "path": str(p),
                "scanned_files": 0,
                "changed_files": 0,
                "inserted": 0,
                "skipped_existing": 0,
                "errors": 0 if p.exists() else 1,
            }
        )

    git_root_cache: Dict[str, Optional[Path]] = {}
    file_to_group_idx: Dict[str, int] = {}
    for idx, item in enumerate(per_path):
        group_path = Path(item["path"])
        for fp in files:
            try:
                if fp == group_path or fp.is_relative_to(group_path):
                    file_to_group_idx[str(fp)] = idx
            except Exception:
                continue

    for fp in files:
        abs_path = str(fp.resolve())
        totals["scanned_files"] += 1

        group_idx = file_to_group_idx.get(abs_path)
        if group_idx is not None:
            per_path[group_idx]["scanned_files"] += 1

        try:
            st = fp.stat()
            mtime = float(st.st_mtime)
        except Exception:
            totals["errors"] += 1
            if group_idx is not None:
                per_path[group_idx]["errors"] += 1
            continue

        prev = files_state.get(abs_path) if isinstance(files_state.get(abs_path), dict) else None
        prev_mtime = None
        if isinstance(prev, dict) and isinstance(prev.get("mtime"), (int, float)):
            prev_mtime = float(prev.get("mtime"))

        if prev_mtime is None:
            should_scan = mtime >= since_ts
        else:
            should_scan = mtime > prev_mtime

        if not should_scan:
            continue

        totals["changed_files"] += 1
        if group_idx is not None:
            per_path[group_idx]["changed_files"] += 1

        try:
            text = fp.read_text(encoding="utf-8")
            raw_bytes = text.encode("utf-8")
            lines = text.splitlines()
            file_hash = hashlib.sha1(raw_bytes).hexdigest()

            sections = _graph_capture_md_parse_sections(
                text,
                min_heading_level=min_heading_level,
                max_sections=max_sections_per_file,
            )

            for sec in sections:
                heading = str(sec.get("heading") or "(untitled)")
                first_lines = _graph_capture_md_first_lines_for_fingerprint(
                    lines,
                    start_line=int(sec.get("start_line") or 1),
                    end_line=int(sec.get("end_line") or len(lines)),
                )
                material = "\n".join([heading, *first_lines])
                fingerprint = hashlib.sha1(material.encode("utf-8")).hexdigest()

                if _graph_capture_md_seen(conn, fingerprint):
                    totals["skipped_existing"] += 1
                    if group_idx is not None:
                        per_path[group_idx]["skipped_existing"] += 1
                    continue

                git_root = _graph_capture_md_git_root(fp, git_root_cache)
                rel_path = None
                if git_root is not None:
                    try:
                        rel_path = fp.resolve().relative_to(git_root).as_posix()
                    except Exception:
                        rel_path = None

                obs = {
                    "kind": "note",
                    "tool_name": "graph.capture-md",
                    "summary": _graph_capture_md_summary(fp, heading),
                    "detail": {
                        "source_path": abs_path,
                        "rel_path": rel_path,
                        "heading": heading,
                        "heading_level": int(sec.get("heading_level") or 0),
                        "start_line": int(sec.get("start_line") or 1),
                        "end_line": int(sec.get("end_line") or len(lines)),
                        "mtime": mtime,
                        "file_hash": file_hash,
                        "section_fingerprint": fingerprint,
                    },
                }
                _insert_observation(conn, obs)
                _graph_capture_md_mark_seen(
                    conn,
                    fingerprint=fingerprint,
                    source_path=abs_path,
                    mtime=mtime,
                )

                totals["inserted"] += 1
                if group_idx is not None:
                    per_path[group_idx]["inserted"] += 1

            files_state[abs_path] = {
                "mtime": mtime,
                "updated_at": _utcnow_iso(),
            }
        except Exception:
            totals["errors"] += 1
            if group_idx is not None:
                per_path[group_idx]["errors"] += 1

    conn.commit()

    state["files"] = files_state
    _atomic_write_json(state_path, state)

    payload = {
        "kind": "openclaw-mem.graph.capture-md.v0",
        "ts": _utcnow_iso(),
        "state_path": str(state_path),
        "since_hours": since_hours,
        "scanned_files": totals["scanned_files"],
        "changed_files": totals["changed_files"],
        "inserted": totals["inserted"],
        "skipped_existing": totals["skipped_existing"],
        "errors": totals["errors"],
    }

    if bool(args.json):
        payload["paths"] = per_path
        _emit(payload, True)
    else:
        print(
            " ".join(
                [
                    f"scanned_files={payload['scanned_files']}",
                    f"changed_files={payload['changed_files']}",
                    f"inserted={payload['inserted']}",
                    f"skipped_existing={payload['skipped_existing']}",
                    f"errors={payload['errors']}",
                ]
            )
        )

    if int(totals["errors"]) > 0:
        sys.exit(1)



def _graph_capture_git_default_since_iso(hours: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=max(0.0, float(hours)))
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _graph_capture_git_run_log(repo_path: Path, *, since_iso: str, max_commits: int) -> List[Dict[str, Any]]:
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "log",
        f"--since={since_iso}",
        f"--max-count={max(1, int(max_commits))}",
        "--date=iso-strict",
        "--pretty=format:%H%x1f%aI%x1f%s%x1e",
        "--name-only",
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "git log failed").strip())

    out: List[Dict[str, Any]] = []
    raw = p.stdout or ""
    for chunk in raw.split("\x1e"):
        part = chunk.strip("\n")
        if not part.strip():
            continue
        lines = part.splitlines()
        if not lines:
            continue
        header = lines[0]
        cols = header.split("\x1f", 2)
        if len(cols) < 3:
            continue
        sha, author_ts, subject = cols

        files: List[str] = []
        seen_files: set[str] = set()
        for f in lines[1:]:
            ff = f.strip()
            if not ff or ff in seen_files:
                continue
            seen_files.add(ff)
            files.append(ff)

        out.append(
            {
                "sha": sha.strip(),
                "author_ts": author_ts.strip(),
                "subject": subject.strip(),
                "files": files,
            }
        )

    return out

def _graph_capture_git_is_repo(path: Path) -> bool:
    p = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return p.returncode == 0 and (p.stdout or "").strip() == "true"


def _graph_capture_git_seen(conn: sqlite3.Connection, repo: str, sha: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM graph_capture_git_seen WHERE repo = ? AND sha = ? LIMIT 1",
        (repo, sha),
    ).fetchone()
    return row is not None


def _graph_capture_git_mark_seen(conn: sqlite3.Connection, repo: str, sha: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO graph_capture_git_seen (repo, sha, captured_at) VALUES (?, ?, ?)",
        (repo, sha, _utcnow_iso()),
    )


def _graph_capture_git_observation_exists(conn: sqlite3.Connection, repo: str, sha: str) -> bool:
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM observations
            WHERE tool_name = 'graph.capture-git'
              AND json_extract(detail_json, '$.repo') = ?
              AND json_extract(detail_json, '$.sha') = ?
            LIMIT 1
            """,
            (repo, sha),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT detail_json FROM observations WHERE tool_name = 'graph.capture-git'"
        ).fetchall()
        for r in rows:
            try:
                obj = json.loads(r["detail_json"] or "{}")
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            if str(obj.get("repo") or "") == repo and str(obj.get("sha") or "") == sha:
                return True
        return False


def cmd_graph_capture_git(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    repos = list(getattr(args, "repo", []) or [])
    if not repos:
        _emit({"error": "missing --repo"}, True)
        sys.exit(2)

    since_hours = max(0.0, float(getattr(args, "since", 24) or 24))
    max_commits = max(1, int(getattr(args, "max_commits", 50) or 50))
    state_path = Path(
        os.path.expanduser(
            getattr(args, "state", None) or DEFAULT_GRAPH_CAPTURE_STATE_PATH
        )
    )

    state = _load_triage_state(state_path)
    if not isinstance(state, dict):
        state = {}
    repos_state = state.get("repos") if isinstance(state.get("repos"), dict) else {}

    results: List[Dict[str, Any]] = []
    had_errors = False

    for repo_raw in repos:
        repo_path = Path(repo_raw).expanduser().resolve()
        repo_key = str(repo_path)
        repo_label = repo_path.name or repo_key

        summary = {
            "repo": repo_key,
            "inserted": 0,
            "skipped_existing": 0,
            "errors": 0,
        }

        if not repo_path.exists():
            summary["errors"] = 1
            had_errors = True
            results.append(summary)
            continue

        if not _graph_capture_git_is_repo(repo_path):
            summary["errors"] = 1
            had_errors = True
            results.append(summary)
            continue

        repo_prev = repos_state.get(repo_key) if isinstance(repos_state.get(repo_key), dict) else {}
        since_iso = str(repo_prev.get("last_author_ts") or _graph_capture_git_default_since_iso(since_hours))

        try:
            commits = _graph_capture_git_run_log(
                repo_path,
                since_iso=since_iso,
                max_commits=max_commits,
            )
        except Exception:
            summary["errors"] = 1
            had_errors = True
            results.append(summary)
            continue

        newest_author_ts = str(repo_prev.get("last_author_ts") or "")
        newest_sha = str(repo_prev.get("last_sha") or "")

        # Process old->new for deterministic accumulation.
        for c in reversed(commits):
            sha = str(c.get("sha") or "").strip()
            if not sha:
                continue
            author_ts = str(c.get("author_ts") or "").strip() or _utcnow_iso()
            subject = str(c.get("subject") or "").strip() or "(no subject)"
            files = list(c.get("files") or [])

            already_seen = _graph_capture_git_seen(conn, repo_key, sha)
            if not already_seen and _graph_capture_git_observation_exists(conn, repo_key, sha):
                _graph_capture_git_mark_seen(conn, repo_key, sha)
                already_seen = True

            if already_seen:
                summary["skipped_existing"] += 1
            else:
                obs = {
                    "ts": author_ts,
                    "kind": "note",
                    "tool_name": "graph.capture-git",
                    "summary": f"[GIT] {repo_label} {sha[:7]} {subject}",
                    "detail": {
                        "repo": repo_key,
                        "sha": sha,
                        "author_ts": author_ts,
                        "files": files,
                    },
                }
                _insert_observation(conn, obs)
                _graph_capture_git_mark_seen(conn, repo_key, sha)
                summary["inserted"] += 1

            if author_ts > newest_author_ts:
                newest_author_ts = author_ts
                newest_sha = sha

        repos_state[repo_key] = {
            "last_author_ts": newest_author_ts or since_iso,
            "last_sha": newest_sha,
            "updated_at": _utcnow_iso(),
        }

        conn.commit()
        results.append(summary)

    state["repos"] = repos_state
    _atomic_write_json(state_path, state)

    totals = {
        "inserted": sum(int(r["inserted"]) for r in results),
        "skipped_existing": sum(int(r["skipped_existing"]) for r in results),
        "errors": sum(int(r["errors"]) for r in results),
    }

    payload = {
        "kind": "openclaw-mem.graph.capture-git.v0",
        "ts": _utcnow_iso(),
        "state_path": str(state_path),
        "since_hours": since_hours,
        "max_commits": max_commits,
        "repos": results,
        "totals": totals,
    }

    if bool(args.json):
        _emit(payload, True)
    else:
        for r in results:
            print(
                f"{r['repo']}: inserted={r['inserted']} skipped_existing={r['skipped_existing']} errors={r['errors']}"
            )

    if had_errors:
        sys.exit(1)


def cmd_graph_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (args.query or "").strip()
    to_path = (args.to or "").strip()
    scope = (getattr(args, "scope", None) or "").strip() or None

    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)
    if not to_path:
        _emit({"error": "missing --to"}, True)
        sys.exit(2)

    limit = max(1, int(getattr(args, "limit", 12)))
    window = max(0, int(getattr(args, "window", 2)))

    rows = _graph_search_rows(conn, query, limit)
    cand_ids = [int(r["id"]) for r in rows]

    nodes: Dict[int, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def add_node(oid: int) -> None:
        if oid in nodes:
            return
        r = conn.execute(
            "SELECT id, ts, kind, tool_name, summary FROM observations WHERE id=?",
            (oid,),
        ).fetchone()
        if not r:
            return
        nodes[oid] = {
            "id": _graph_record_ref(oid),
            "type": "observation",
            "project": scope,
            "title": (r["summary"] or "").replace("\n", " ").strip()[:180],
            "provenance": {"ts": r["ts"], "kind": r["kind"], "tool_name": r["tool_name"]},
        }

    for oid in cand_ids:
        add_node(oid)

    if window and cand_ids:
        for oid in cand_ids:
            lo, hi = oid - window, oid + window
            nrows = conn.execute(
                "SELECT id FROM observations WHERE id BETWEEN ? AND ? ORDER BY id",
                (lo, hi),
            ).fetchall()
            for nr in nrows:
                nid = int(nr[0])
                add_node(nid)
                if nid == oid:
                    continue
                edges.append(
                    {
                        "src": _graph_record_ref(oid),
                        "dst": _graph_record_ref(nid),
                        "type": "timeline_adjacent",
                        "provenance": {"window": window},
                    }
                )

    graph = {
        "kind": "openclaw-mem.graph.export.v0",
        "ts": _utcnow_iso(),
        "query": {"text": query, "scope": scope},
        "nodes": list(nodes.values()),
        "edges": edges,
    }

    out_path = Path(to_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload = {"ok": True, "to": str(out_path), "nodes": len(graph["nodes"]), "edges": len(edges)}
    _emit(payload, bool(args.json))


def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Examples:\n"
        "  # Observation store\n"
        "  openclaw-mem status --json\n"
        "  openclaw-mem profile --json --recent-limit 15\n"
        "  openclaw-mem backend --json\n"
        "  openclaw-mem ingest --file observations.jsonl --json\n"
        "\n"
        "  # Progressive disclosure search\n"
        "  openclaw-mem search \"gateway timeout\" --limit 20 --json\n"
        "  openclaw-mem timeline 23 41 57 --window 4 --json\n"
        "  openclaw-mem get 23 41 57 --json\n"
        "\n"
        "  # AI compression (requires API key via env or ~/.openclaw/openclaw.json)\n"
        "  export OPENAI_API_KEY=sk-...\n"
        "  openclaw-mem summarize --json  # yesterday's notes\n"
        "  openclaw-mem summarize 2026-02-04 --dry-run\n"
        "\n"
        "  # Export observations (Markdown)\n"
        "  openclaw-mem export --to /tmp/export.md --limit 20 --json\n"
        "  openclaw-mem export --to MEMORY.md --yes --limit 20\n"
        "\n"
        "  # Vector search (Phase 3)\n"
        "  export OPENAI_API_KEY=sk-...\n"
        "  openclaw-mem embed --limit 500 --json\n"
        "  openclaw-mem vsearch \"gateway timeout\" --limit 10 --json\n"
        "\n"
        "  # Recall/writeback (Phase 5)\n"
        "  openclaw-mem writeback-lancedb --db mem.sqlite --lancedb ~/.openclaw/memory/lancedb --table memories --limit 50 --dry-run\n"
        "\n"
        "  # Hybrid Search & Store (Phase 4)\n"
        "  openclaw-mem hybrid \"python error\" --limit 5 --json\n"
        "  openclaw-mem hybrid \"python error\" --rerank-provider jina --rerank-topn 20 --json\n"
        "  openclaw-mem store \"Prefer tabs over spaces\" --category preference --importance 0.9 --json\n"
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

    sp = sub.add_parser("profile", help="Show ops profile (counts/ranges/labels/recent)")
    add_common(sp)
    sp.add_argument("--recent-limit", type=int, default=10, help="Number of recent rows to include (default: 10)")
    sp.add_argument("--tool-limit", type=int, default=10, help="Max top tools to include (default: 10)")
    sp.add_argument("--kind-limit", type=int, default=10, help="Max top kinds to include (default: 10)")
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser("backend", help="Inspect active OpenClaw memory backend + fallback posture")
    add_common(sp)
    sp.set_defaults(func=cmd_backend)

    sp = sub.add_parser("ingest", help="Ingest observations (JSONL via --file or stdin)")
    add_common(sp)
    sp.add_argument("--file", help="JSONL file path (default: stdin)")
    sp.add_argument(
        "--importance-scorer",
        dest="importance_scorer",
        default=None,
        help=(
            "Override importance autograde scorer for this run (env fallback: OPENCLAW_MEM_IMPORTANCE_SCORER). "
            "Use 'heuristic-v1' to enable, or 'off' to disable."
        ),
    )
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

    sp = sub.add_parser("summarize", help="Run AI compression on daily notes (requires API key)")
    add_common(sp)
    sp.add_argument("date", nargs="?", help="Date to compress (YYYY-MM-DD, default: yesterday)")
    sp.add_argument("--workspace", type=Path, help="Workspace root (default: cwd)")
    sp.add_argument("--model", default=defaults.summary_model(), help="OpenAI model (env: OPENCLAW_MEM_SUMMARY_MODEL)")
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--max-tokens", type=int, default=700, help="Max output tokens")
    sp.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    sp.add_argument("--dry-run", action="store_true", help="Preview without writing")
    # Gateway options
    sp.add_argument("--gateway", action="store_true", help="Use OpenClaw Gateway for model routing")
    sp.add_argument("--gateway-url", help="OpenClaw Gateway base URL (auto-detected if unset)")
    sp.add_argument("--gateway-token", help="OpenClaw Gateway token (auto-detected from ~/.openclaw/openclaw.json)")
    sp.add_argument("--agent-id", default="main", help="Target agent ID for Gateway (default: main)")
    sp.set_defaults(func=cmd_summarize)

    sp = sub.add_parser("export", help="Export observations to a Markdown file")
    add_common(sp)
    sp.add_argument("--to", required=True, help="Target file (e.g., MEMORY.md)")
    sp.add_argument("--yes", action="store_true", help="Required when exporting to MEMORY.md")
    sp.add_argument("--ids", type=int, nargs="+", help="Specific observation IDs to export")
    sp.add_argument("--limit", type=int, default=50, help="Export last N observations (default: 50)")
    sp.add_argument("--include-detail", action="store_true", help="Include detail_json blocks")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("embed", help="Compute/store embeddings for observations (requires API key)")
    add_common(sp)
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--limit", type=int, default=500, help="Max observations to embed (default: 500)")
    sp.add_argument("--batch", type=int, default=64, help="Batch size per API call (default: 64)")
    sp.add_argument("--field", choices=["original", "english", "both"], default="original", help="Embedding source field (default: original)")
    sp.set_defaults(func=cmd_embed)

    sp = sub.add_parser("vsearch", help="Vector search over embeddings (cosine similarity)")
    add_common(sp)
    sp.add_argument("query", help="Query text")
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--query-vector-json", help="Provide query vector as JSON array (testing/offline)")
    sp.add_argument("--query-vector-file", help="Provide query vector from JSON file (testing/offline)")
    sp.set_defaults(func=cmd_vsearch)

    sp = sub.add_parser("hybrid", help="Hybrid search (Vector + FTS) using RRF")
    add_common(sp)
    sp.add_argument("query", help="Query text")
    sp.add_argument("--query-en", help="Optional English query for additional vector route")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--k", type=int, default=60, help="RRF constant (default: 60)")
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument(
        "--rerank-provider",
        choices=["none", "jina", "cohere"],
        default="none",
        help="Optional post-retrieval rerank provider (default: none)",
    )
    sp.add_argument(
        "--rerank-model",
        default=defaults.rerank_model(),
        help="Reranker model name (provider-specific) (env: OPENCLAW_MEM_RERANK_MODEL)",
    )
    sp.add_argument(
        "--rerank-topn",
        type=int,
        default=20,
        help="Top-N reranked items to prioritize before RRF fallback",
    )
    sp.add_argument("--rerank-api-key", help="Reranker API key (or env: JINA_API_KEY/COHERE_API_KEY)")
    sp.add_argument("--rerank-base-url", help="Optional reranker endpoint override")
    sp.add_argument("--rerank-timeout-sec", type=int, default=15, help="Reranker HTTP timeout in seconds")
    sp.set_defaults(func=cmd_hybrid)

    sp = sub.add_parser("pack", help="Build a compact, cited bundle from hybrid retrieval")
    sp.add_argument("--db", default=None, help="SQLite DB path")
    sp.add_argument(
        "--json",
        dest="json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Structured JSON output (default: true). Use --no-json for bundle_text only.",
    )
    sp.add_argument("--query", required=True, help="Pack query text")
    sp.add_argument("--query-en", help="Optional English query for bilingual retrieval")
    sp.add_argument("--limit", type=int, default=12, help="Max packed items (default: 12)")
    sp.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=1200, help="Token budget for bundle text (default: 1200)")
    sp.add_argument("--trace", action="store_true", help="Include redaction-safe retrieval trace (`openclaw-mem.pack.trace.v1`) with include/exclude decisions")
    sp.set_defaults(func=cmd_pack)


    # Graphic memory (GraphRAG-lite) — v0 command group
    sp = sub.add_parser("graph", help="Graphic memory helpers (index-first graph recall + packing)")
    sp.add_argument("--db", default=None, help="SQLite DB path")
    sp.add_argument(
        "--json",
        dest="json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Structured JSON output (default: true). Use --no-json for text-only payload.",
    )
    gsub = sp.add_subparsers(dest="graph_cmd", required=True)

    g = gsub.add_parser("index", help="Build an L0 IndexPack for a query (budgeted, injection-ready)")
    g.add_argument("query", help="Query text")
    g.add_argument("--scope", help="Optional project/scope hint (string; v0 is advisory)")
    g.add_argument("--limit", type=int, default=12, help="Max candidate hits to consider (default: 12)")
    g.add_argument("--window", type=int, default=2, help="Timeline window for neighborhood suggestions (default: 2)")
    g.add_argument("--suggest-limit", dest="suggest_limit", type=int, default=6, help="Max suggested expansions (default: 6)")
    g.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=900, help="Token budget for index_text (default: 900)")
    g.set_defaults(func=cmd_graph_index)

    g = gsub.add_parser("pack", help="Build an L1 ContextPack from selected recordRefs/ids (safe-by-default)")
    g.add_argument("ids", nargs="+", help="Record refs (e.g., obs:123) or numeric ids")
    g.add_argument("--max-items", dest="max_items", type=int, default=20, help="Max items to include (default: 20)")
    g.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=1500, help="Token budget for bundle_text (default: 1500)")
    g.set_defaults(func=cmd_graph_pack)

    g = gsub.add_parser("preflight", help="Run index+selection+pack in one deterministic step")
    g.add_argument("query", help="Query text")
    g.add_argument("--scope", help="Optional project/scope hint (string; v0 is advisory)")
    g.add_argument("--limit", type=int, default=12, help="Max candidate hits to consider (default: 12)")
    g.add_argument("--window", type=int, default=2, help="Timeline window for neighborhood suggestions (default: 2)")
    g.add_argument("--suggest-limit", dest="suggest_limit", type=int, default=6, help="Max suggested expansions (default: 6)")
    g.add_argument("--take", type=int, default=12, help="Max selected refs to pack (default: 12)")
    g.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=1200, help="Token budget for bundle_text (default: 1200)")
    g.set_defaults(func=cmd_graph_preflight, json=False)

    g = gsub.add_parser("auto-status", help="Show effective Graphic Memory automation env toggles")
    g.set_defaults(func=cmd_graph_auto_status)

    g = gsub.add_parser("capture-git", help="Capture recent git commits as observations (idempotent)")
    g.add_argument("--repo", action="append", required=True, help="Git repository path (repeatable)")
    g.add_argument("--since", type=float, default=24, help="Fallback lookback window in hours (default: 24)")
    g.add_argument("--state", default=DEFAULT_GRAPH_CAPTURE_STATE_PATH, help=f"Capture state file (default: {DEFAULT_GRAPH_CAPTURE_STATE_PATH})")
    g.add_argument("--max-commits", dest="max_commits", type=int, default=50, help="Max commits per repo per run (default: 50)")
    g.set_defaults(func=cmd_graph_capture_git)

    g = gsub.add_parser("capture-md", help="Capture Markdown heading sections as index-only observations (idempotent)")
    g.add_argument("--path", action="append", required=True, help="Markdown file/directory path (repeatable)")
    g.add_argument("--include", action="append", default=None, help="File extension filter (repeatable, default: .md)")
    g.add_argument("--exclude-glob", dest="exclude_glob", action="append", default=None, help="Exclude glob pattern (repeatable)")
    g.add_argument("--max-files", dest="max_files", type=int, default=200, help="Max files to inspect per run (default: 200)")
    g.add_argument("--max-sections-per-file", dest="max_sections_per_file", type=int, default=50, help="Max heading sections captured per file (default: 50)")
    g.add_argument("--min-heading-level", dest="min_heading_level", type=int, default=2, help="Capture headings at this level or deeper (default: 2)")
    g.add_argument("--state", default=DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH, help=f"Capture state file (default: {DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH})")
    g.add_argument("--since-hours", dest="since_hours", type=float, default=24, help="Fallback lookback window in hours for first scan (default: 24)")
    g.set_defaults(func=cmd_graph_capture_md)

    g = gsub.add_parser("export", help="Export a small graph.json artifact around query hits (portable artifact)")
    g.add_argument("--query", required=True, help="Query text")
    g.add_argument("--scope", help="Optional project/scope hint (string; v0 is advisory)")
    g.add_argument("--to", required=True, help="Output path for graph.json")
    g.add_argument("--limit", type=int, default=12)
    g.add_argument("--window", type=int, default=2)
    g.set_defaults(func=cmd_graph_export)


    sp = sub.add_parser("store", help="Proactively store a memory")
    add_common(sp)
    sp.add_argument("text", help="Memory content")
    sp.add_argument("--text-en", help="Optional English translation/summary")
    sp.add_argument("--lang", help="Original text language code (e.g., ko, ja, es)")
    sp.add_argument("--category", default="fact", choices=["fact", "preference", "decision", "entity", "task", "other"])
    sp.add_argument("--importance", type=float, default=0.7)
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--workspace", type=Path, help="Workspace root (default: cwd)")
    sp.set_defaults(func=cmd_store)

    sp = sub.add_parser("index", help="Build Markdown index for OpenClaw memory_search (Route A)")
    add_common(sp)
    sp.add_argument("--to", help=f"Output path (default: {DEFAULT_INDEX_PATH})")
    sp.add_argument("--limit", type=int, default=5000, help="Max observations to include")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("semantic", help="Semantic recall via OpenClaw memory_search (black-box embeddings)")
    add_common(sp)
    sp.add_argument("query", help="Search query")
    sp.add_argument("--limit", type=int, default=10, help="Max matched observation IDs to resolve")
    sp.add_argument("--max-results", type=int, default=8, help="memory_search maxResults")
    sp.add_argument("--min-score", type=float, default=0.0, help="memory_search minScore")
    sp.add_argument("--raw-limit", type=int, default=8, help="Include first N raw memory_search hits")
    sp.add_argument("--session-key", default="main", help="Gateway sessionKey for tools/invoke")
    sp.add_argument("--gateway-url", help="OpenClaw Gateway base URL (auto-detected if unset)")
    sp.add_argument("--gateway-token", help="OpenClaw Gateway token (auto-detected from ~/.openclaw/openclaw.json)")
    sp.add_argument("--agent-id", default="main", help="Target agent ID for Gateway (default: main)")
    sp.set_defaults(func=cmd_semantic)

    sp = sub.add_parser("triage", help="Deterministic local scan (heartbeat/cron)"
    )
    add_common(sp)
    sp.add_argument(
        "--mode",
        default="heartbeat",
        choices=["heartbeat", "observations", "cron-errors", "tasks"],
        help="Scan mode (default: heartbeat)",
    )
    sp.add_argument("--since-minutes", type=int, default=60, help="Look back window in minutes")
    sp.add_argument("--limit", type=int, default=10, help="Max matches to return")
    sp.add_argument("--keywords", help="Comma-separated keywords override (observations modes)")
    sp.add_argument(
        "--cron-jobs-path",
        dest="cron_jobs_path",
        help="Path to OpenClaw cron jobs store (default: ~/.openclaw/cron/jobs.json)",
    )
    sp.add_argument(
        "--tasks-since-minutes",
        dest="tasks_since_minutes",
        type=int,
        default=24 * 60,
        help="Tasks lookback window in minutes (default: 1440)",
    )
    sp.add_argument(
        "--importance-min",
        dest="importance_min",
        type=float,
        default=0.7,
        help="Min importance for tasks mode (default: 0.7)",
    )
    sp.add_argument(
        "--state-path",
        dest="state_path",
        help="State file for dedupe (default: ~/.openclaw/memory/openclaw-mem/triage-state.json)",
    )
    sp.set_defaults(func=cmd_triage)

    sp = sub.add_parser("harvest", help="Auto-ingest and embed observations from log file")
    add_common(sp)
    sp.add_argument("--source", help="JSONL source file (default: ~/.openclaw/memory/openclaw-mem-observations.jsonl)")
    sp.add_argument(
        "--importance-scorer",
        dest="importance_scorer",
        default=None,
        help=(
            "Override importance autograde scorer for this run (env fallback: OPENCLAW_MEM_IMPORTANCE_SCORER). "
            "Use 'heuristic-v1' to enable, or 'off' to disable."
        ),
    )
    sp.add_argument("--archive-dir", help="Directory to move processed files (default: delete)")
    sp.add_argument("--embed", action="store_true", default=True, help="Run embedding after ingest (default: True)")
    sp.add_argument("--no-embed", dest="embed", action="store_false", help="Skip embedding")
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--update-index", action="store_true", default=True, help="Update Route A index file after ingest (default: True)")
    sp.add_argument("--no-update-index", dest="update_index", action="store_false", help="Skip index update")
    sp.add_argument("--index-to", default=None, help=f"Index output path (default: {DEFAULT_INDEX_PATH})")
    sp.add_argument("--index-limit", type=int, default=5000, help="Index: max observations to include")
    sp.set_defaults(func=cmd_harvest)

    sp = sub.add_parser("writeback-lancedb", help="Write graded metadata back into LanceDB rows")
    add_common(sp)
    sp.add_argument("--lancedb", required=True, help="LanceDB directory path")
    sp.add_argument("--table", required=True, help="LanceDB table name")
    sp.add_argument("--limit", type=int, default=50, help="Max SQLite rows to inspect (default: 50)")
    sp.add_argument(
        "--batch",
        type=int,
        default=25,
        help="Batch size for node writeback calls (default: 25)",
    )
    sp.add_argument(
        "--force",
        "--overwrite",
        dest="force",
        action="store_true",
        default=False,
        help="Overwrite existing metadata fields when incoming values are available",
    )
    sp.add_argument(
        "--force-fields",
        dest="force_fields",
        default=None,
        help=(
            "Comma-separated list of fields allowed to be overwritten when --force is set "
            "(importance, importance_label, scope, category, trust_tier)."
        ),
    )
    sp.add_argument("--dry-run", action="store_true", help="Dry-run mode: show receipts without writing")
    sp.set_defaults(func=cmd_writeback_lancedb)

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
