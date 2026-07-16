"""Stable SQLite storage primitives shared by CLI and integrations."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from openclaw_mem import __version__

CURRENT_DB_VERSION = 1
_PACK_LIFECYCLE_SHADOW_TABLE = "pack_lifecycle_shadow_log"
_SURROGATE_MIN = 0xD800
_SURROGATE_MAX = 0xDFFF
EPISODIC_SEARCH_TEXT_MAX_CHARS = 2400


def _resolve_state_dir() -> str:
    override = (os.getenv("OPENCLAW_STATE_DIR") or os.getenv("CLAWDBOT_STATE_DIR") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = (os.getenv("OPENCLAW_HOME") or "").strip() or os.path.expanduser("~")
    return os.path.join(os.path.abspath(os.path.expanduser(home)), ".openclaw")


DEFAULT_DB = os.path.join(_resolve_state_dir(), "memory", "openclaw-mem.sqlite")

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _enable_wal_best_effort(conn: sqlite3.Connection) -> None:
    """Enable SQLite WAL when possible without breaking read-only lanes.

    WAL is preferred for the normal writable store because it improves reader /
    writer concurrency. Some sidecar deployments intentionally run read-mostly
    endpoints against a database file or volume that cannot switch journal mode
    at request time. In that case, read commands must not fail before they can
    perform a SELECT, so journal-mode setup is best-effort while busy_timeout is
    still attempted independently.
    """

    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        tolerated = (
            "readonly" in msg
            or "read-only" in msg
            or "attempt to write a readonly database" in msg
            or "permission denied" in msg
        )
        if not tolerated:
            raise
    conn.execute("PRAGMA busy_timeout=5000;")


@dataclass(frozen=True)
class Migration:
    id: int
    description: str
    apply: Callable[[sqlite3.Connection], None]
    cost: str


def _connect(db_path: str) -> sqlite3.Connection:
    # Allow in-memory DB and relative paths without a directory component.
    # (Useful for unit tests and quick experiments.)
    dir_ = os.path.dirname(db_path)
    if db_path not in (":memory:", "") and dir_:
        os.makedirs(dir_, exist_ok=True)

    # Concurrency hardening for the live sidecar DB:
    # - WAL for concurrent readers/writers when the DB can switch journal mode
    # - non-zero connect timeout / busy_timeout so parallel cron/tool lanes
    #   wait briefly instead of failing immediately under transient contention
    # WAL setup is intentionally best-effort so read endpoints can still query
    # read-only/read-mostly sidecar databases.
    skip_init = str(os.environ.get("OPENCLAW_MEM_SKIP_INIT_DB") or "").strip().lower() in {"1", "true", "yes", "on"}
    readonly_db = str(os.environ.get("OPENCLAW_MEM_READONLY_DB") or "").strip().lower() in {"1", "true", "yes", "on"}
    if readonly_db and db_path not in (":memory:", ""):
        uri_path = Path(db_path).expanduser().resolve().as_posix()
        conn = sqlite3.connect(f"file:{uri_path}?mode=ro&immutable=1", timeout=10.0, uri=True)
    else:
        conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    _enable_wal_best_effort(conn)
    if not skip_init:
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if user_version > CURRENT_DB_VERSION:
            conn.close()
            raise RuntimeError(
                "db_version_unsupported: database user_version "
                f"{user_version} is newer than supported version {CURRENT_DB_VERSION}; "
                "upgrade openclaw-mem or inspect it with a compatible read-only tool"
            )
        if user_version == 0:
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

    conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_tool_ts ON observations(tool_name, ts);")

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

    # Docs memory sidecar (hybrid retrieval over operator-authored markdown).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS docs_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            repo TEXT NOT NULL,
            path TEXT NOT NULL,
            doc_kind TEXT NOT NULL,
            heading_path TEXT,
            title TEXT,
            text TEXT NOT NULL,
            source_kind TEXT NOT NULL DEFAULT 'operator',
            source_ref TEXT NOT NULL,
            ts_hint TEXT,
            content_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(doc_id, chunk_id)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunks_doc_id ON docs_chunks(doc_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunks_kind ON docs_chunks(doc_kind);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunks_repo_path ON docs_chunks(repo, path);")

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_chunks_fts
        USING fts5(text, title, heading_path, path, repo, doc_kind, content='docs_chunks', content_rowid='id');
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS docs_embeddings (
            chunk_rowid INTEGER NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(chunk_rowid, model)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_embeddings_model ON docs_embeddings(model);")

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS docs_chunks_ai
        AFTER INSERT ON docs_chunks
        BEGIN
            INSERT INTO docs_chunks_fts(rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES (new.id, new.text, new.title, new.heading_path, new.path, new.repo, new.doc_kind);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS docs_chunks_ad
        AFTER DELETE ON docs_chunks
        BEGIN
            INSERT INTO docs_chunks_fts(docs_chunks_fts, rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES ('delete', old.id, old.text, old.title, old.heading_path, old.path, old.repo, old.doc_kind);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS docs_chunks_au
        AFTER UPDATE ON docs_chunks
        BEGIN
            INSERT INTO docs_chunks_fts(docs_chunks_fts, rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES ('delete', old.id, old.text, old.title, old.heading_path, old.path, old.repo, old.doc_kind);
            INSERT INTO docs_chunks_fts(rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES (new.id, new.text, new.title, new.heading_path, new.path, new.repo, new.doc_kind);
        END;
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS episodic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            ts_ms INTEGER NOT NULL,
            scope TEXT NOT NULL,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            type TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_json TEXT,
            refs_json TEXT,
            redacted INTEGER NOT NULL DEFAULT 0,
            schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_episodic_event_id ON episodic_events(event_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_scope_ts ON episodic_events(scope, ts_ms);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_session_ts ON episodic_events(session_id, ts_ms);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_scope_type_ts ON episodic_events(scope, type, ts_ms);")

    episodic_cols = {r[1] for r in conn.execute("PRAGMA table_info(episodic_events)").fetchall()}
    if "search_text" not in episodic_cols:
        conn.execute("ALTER TABLE episodic_events ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS episodic_events_fts
        USING fts5(summary, search_text, type, session_id, agent_id, content='episodic_events', content_rowid='id');
        """
    )

    episodic_fts_cols = [r[1] for r in conn.execute("PRAGMA table_info(episodic_events_fts)").fetchall()]
    if "search_text" not in episodic_fts_cols:
        conn.execute("DROP TABLE IF EXISTS episodic_events_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE episodic_events_fts
            USING fts5(summary, search_text, type, session_id, agent_id, content='episodic_events', content_rowid='id');
            """
        )
        conn.execute(
            """
            INSERT INTO episodic_events_fts(rowid, summary, search_text, type, session_id, agent_id)
            SELECT id, summary, search_text, type, session_id, agent_id
            FROM episodic_events;
            """
        )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS episodic_events_ai
        AFTER INSERT ON episodic_events
        BEGIN
            INSERT INTO episodic_events_fts(rowid, summary, search_text, type, session_id, agent_id)
            VALUES (new.id, new.summary, new.search_text, new.type, new.session_id, new.agent_id);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS episodic_events_ad
        AFTER DELETE ON episodic_events
        BEGIN
            INSERT INTO episodic_events_fts(episodic_events_fts, rowid, summary, search_text, type, session_id, agent_id)
            VALUES ('delete', old.id, old.summary, old.search_text, old.type, old.session_id, old.agent_id);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS episodic_events_au
        AFTER UPDATE ON episodic_events
        BEGIN
            INSERT INTO episodic_events_fts(episodic_events_fts, rowid, summary, search_text, type, session_id, agent_id)
            VALUES ('delete', old.id, old.summary, old.search_text, old.type, old.session_id, old.agent_id);
            INSERT INTO episodic_events_fts(rowid, summary, search_text, type, session_id, agent_id)
            VALUES (new.id, new.summary, new.search_text, new.type, new.session_id, new.agent_id);
        END;
        """
    )

    for row in conn.execute(
        "SELECT id, summary, payload_json, refs_json FROM episodic_events WHERE COALESCE(search_text, '') = ''"
    ).fetchall():
        conn.execute(
            "UPDATE episodic_events SET search_text = ? WHERE id = ?",
            (
                _episodic_build_search_text(
                    summary=str(row[1] or ""),
                    payload_json=row[2],
                    refs_json=row[3],
                ),
                int(row[0]),
            ),
        )

    try:
        fts_any = conn.execute("SELECT rowid FROM episodic_events_fts LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        fts_any = True  # fail-open

    if not fts_any:
        total_row = conn.execute("SELECT COUNT(*) FROM episodic_events").fetchone()
        total = int(total_row[0] or 0) if total_row else 0
        if total > 0:
            conn.execute("INSERT INTO episodic_events_fts(episodic_events_fts) VALUES('rebuild')")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS episodic_event_embeddings (
            event_row_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            search_text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(event_row_id) REFERENCES episodic_events(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_episodic_event_embeddings_model ON episodic_event_embeddings(model);"
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_PACK_LIFECYCLE_SHADOW_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            query_hash TEXT,
            selection_signature TEXT NOT NULL,
            selected_count INTEGER NOT NULL,
            citation_count INTEGER NOT NULL,
            candidate_count INTEGER NOT NULL,
            receipt_json TEXT NOT NULL
        );
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{_PACK_LIFECYCLE_SHADOW_TABLE}_ts ON {_PACK_LIFECYCLE_SHADOW_TABLE}(ts DESC);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{_PACK_LIFECYCLE_SHADOW_TABLE}_signature ON {_PACK_LIFECYCLE_SHADOW_TABLE}(selection_signature);"
    )

    readonly_db = str(os.environ.get("OPENCLAW_MEM_READONLY_DB") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not readonly_db:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        stamp = {
            "min_reader_version": "1",
            "last_writer_version": __version__,
            "last_writer_ts": _utcnow_iso(),
        }
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            stamp.items(),
        )
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if user_version == 0:
            conn.execute("PRAGMA user_version = 1")

    conn.commit()


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


def _episodic_collect_search_fragments(value: Any, out: List[str], *, max_fragments: int = 48) -> None:
    if len(out) >= max_fragments or value is None:
        return

    if isinstance(value, str):
        text = re.sub(r"\s+", " ", _sanitize_str_surrogates(value)).strip()
        if text:
            out.append(text[:400])
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        out.append(str(value))
        return

    if isinstance(value, dict):
        for key in sorted(value.keys()):
            _episodic_collect_search_fragments(value.get(key), out, max_fragments=max_fragments)
            if len(out) >= max_fragments:
                break
        return

    if isinstance(value, list):
        for item in value:
            _episodic_collect_search_fragments(item, out, max_fragments=max_fragments)
            if len(out) >= max_fragments:
                break


def _episodic_text_fragments_from_json(raw: Any) -> List[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        obj = json.loads(raw)
    except Exception:
        text = re.sub(r"\s+", " ", _sanitize_str_surrogates(raw)).strip()
        return [text[:400]] if text else []

    out: List[str] = []
    _episodic_collect_search_fragments(obj, out)
    return out


def _episodic_build_search_text(*, summary: str, payload_json: Any, refs_json: Any) -> str:
    parts: List[str] = []
    seen: set[str] = set()

    for candidate in [summary, *_episodic_text_fragments_from_json(payload_json), *_episodic_text_fragments_from_json(refs_json)]:
        text = re.sub(r"\s+", " ", _sanitize_str_surrogates(str(candidate or ""))).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)

    out = "\n".join(parts).strip()
    if len(out) > EPISODIC_SEARCH_TEXT_MAX_CHARS:
        out = out[:EPISODIC_SEARCH_TEXT_MAX_CHARS].rstrip()
    return out


MIGRATIONS: Tuple[Migration, ...] = (
    Migration(id=1, description="baseline schema", apply=_init_db, cost="cheap"),
)
