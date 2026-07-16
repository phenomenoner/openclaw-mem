"""Stable SQLite storage primitives shared by CLI and integrations."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from openclaw_mem import __version__

CURRENT_DB_VERSION = 3
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
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if not skip_init:
        if user_version > CURRENT_DB_VERSION:
            conn.close()
            raise RuntimeError(
                "db_version_unsupported: database user_version "
                f"{user_version} is newer than supported version {CURRENT_DB_VERSION}; "
                "upgrade openclaw-mem or inspect it with a compatible read-only tool"
            )
        if readonly_db:
            conn.execute("PRAGMA busy_timeout=5000;")
            return conn
        if user_version == 0:
            had_user_schema = conn.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone() is not None
            _init_db(conn)
            if not had_user_schema:
                for migration in MIGRATIONS:
                    if migration.id > 1:
                        migration.apply(conn)
                conn.execute(f"PRAGMA user_version = {CURRENT_DB_VERSION}")
                conn.commit()
            user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    # Opening a database with a pending expensive migration is deliberately a
    # zero-write compatibility lane. Even switching journal mode would mutate
    # the file, so WAL is enabled only once the database is current.
    if user_version >= CURRENT_DB_VERSION:
        _enable_wal_best_effort(conn)
    else:
        conn.execute("PRAGMA busy_timeout=5000;")
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


def _apply_fts_search_text_migration(conn: sqlite3.Connection) -> None:
    """Rebuild derived FTS generations and backfill episodic search text."""

    episodic_cols = {row[1] for row in conn.execute("PRAGMA table_info(episodic_events)")}
    if "search_text" not in episodic_cols:
        conn.execute(
            "ALTER TABLE episodic_events ADD COLUMN search_text TEXT NOT NULL DEFAULT ''"
        )

    for row in conn.execute(
        "SELECT id, summary, payload_json, refs_json FROM episodic_events "
        "WHERE COALESCE(search_text, '') = '' ORDER BY id"
    ).fetchall():
        conn.execute(
            "UPDATE episodic_events SET search_text = ? WHERE id = ?",
            (
                _episodic_build_search_text(
                    summary=str(row[1] or ""), payload_json=row[2], refs_json=row[3]
                ),
                int(row[0]),
            ),
        )

    conn.execute("DROP TABLE IF EXISTS observations_fts")
    conn.execute(
        "CREATE VIRTUAL TABLE observations_fts USING fts5("
        "summary, summary_en, tool_name, detail_json, "
        "content='observations', content_rowid='id')"
    )
    conn.execute("INSERT INTO observations_fts(observations_fts) VALUES('rebuild')")
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'observations_fts_tri'"
    ).fetchone():
        conn.execute("INSERT INTO observations_fts_tri(observations_fts_tri) VALUES('rebuild')")

    for trigger in ("episodic_events_ai", "episodic_events_ad", "episodic_events_au"):
        conn.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
    conn.execute("DROP TABLE IF EXISTS episodic_events_fts")
    conn.execute(
        "CREATE VIRTUAL TABLE episodic_events_fts USING fts5("
        "summary, search_text, type, session_id, agent_id, "
        "content='episodic_events', content_rowid='id')"
    )
    conn.execute("INSERT INTO episodic_events_fts(episodic_events_fts) VALUES('rebuild')")
    trigger_statements = (
        """CREATE TRIGGER episodic_events_ai AFTER INSERT ON episodic_events BEGIN
          INSERT INTO episodic_events_fts(rowid, summary, search_text, type, session_id, agent_id)
          VALUES (new.id, new.summary, new.search_text, new.type, new.session_id, new.agent_id);
        END""",
        """CREATE TRIGGER episodic_events_ad AFTER DELETE ON episodic_events BEGIN
          INSERT INTO episodic_events_fts(episodic_events_fts, rowid, summary, search_text, type, session_id, agent_id)
          VALUES ('delete', old.id, old.summary, old.search_text, old.type, old.session_id, old.agent_id);
        END""",
        """CREATE TRIGGER episodic_events_au AFTER UPDATE ON episodic_events BEGIN
          INSERT INTO episodic_events_fts(episodic_events_fts, rowid, summary, search_text, type, session_id, agent_id)
          VALUES ('delete', old.id, old.summary, old.search_text, old.type, old.session_id, old.agent_id);
          INSERT INTO episodic_events_fts(rowid, summary, search_text, type, session_id, agent_id)
          VALUES (new.id, new.summary, new.search_text, new.type, new.session_id, new.agent_id);
        END""",
    )
    for statement in trigger_statements:
        conn.execute(statement)


def _apply_trigram_migration(conn: sqlite3.Connection) -> None:
    """Create and fully populate the derived CJK trigram FTS lane."""

    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts_tri USING fts5("
        "summary, summary_en, content='observations', content_rowid='id', tokenize='trigram')"
    )
    conn.execute("INSERT INTO observations_fts_tri(observations_fts_tri) VALUES('rebuild')")


MIGRATIONS: Tuple[Migration, ...] = (
    Migration(id=1, description="baseline schema", apply=_init_db, cost="cheap"),
    Migration(
        id=2,
        description="rebuild bilingual and episodic FTS indexes",
        apply=_apply_fts_search_text_migration,
        cost="expensive",
    ),
    Migration(
        id=3,
        description="build CJK trigram FTS index",
        apply=_apply_trigram_migration,
        cost="expensive",
    ),
)


def migration_state(conn: sqlite3.Connection) -> Dict[str, Any]:
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    pending = [migration.id for migration in MIGRATIONS if migration.id > version]
    expensive = [
        migration.id
        for migration in MIGRATIONS
        if migration.id > version and migration.cost == "expensive"
    ]
    return {
        "current_version": version,
        "target_version": CURRENT_DB_VERSION,
        "compat_mode": bool(expensive),
        "pending": pending,
        "pending_expensive": expensive,
        "hint": "run `openclaw-mem db migrate`" if expensive else None,
    }


def _database_row_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table in ("observations", "episodic_events", "docs_chunks"):
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone():
            counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    return counts


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate_database(
    db_path: str | Path,
    *,
    dry_run: bool = False,
    receipt_path: str | Path | None = None,
) -> Dict[str, Any]:
    path = Path(db_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"database not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        from_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if from_version > CURRENT_DB_VERSION:
            raise RuntimeError(
                f"database version {from_version} is newer than supported {CURRENT_DB_VERSION}"
            )
        steps = [migration for migration in MIGRATIONS if migration.id > from_version]
        backup = Path(f"{path}.pre-v{CURRENT_DB_VERSION}.backup.sqlite")
        plan: Dict[str, Any] = {
            "kind": "openclaw-mem.db.migration.plan.v1",
            "db_path": str(path),
            "from_version": from_version,
            "to_version": CURRENT_DB_VERSION,
            "steps": [
                {"id": item.id, "description": item.description, "cost": item.cost}
                for item in steps
            ],
            "backup_path": str(backup),
            "dry_run": True,
        }
        if dry_run or not steps:
            return plan
        if backup.exists():
            raise FileExistsError(f"migration backup already exists: {backup}")

        started = time.perf_counter()
        conn.execute("VACUUM INTO ?", (str(backup),))
        backup_sha256 = _file_sha256(backup)
        before = _database_row_counts(conn)
        applied: List[Dict[str, Any]] = []
        try:
            for migration in steps:
                migration.apply(conn)
                conn.execute(f"PRAGMA user_version = {migration.id}")
                applied.append(
                    {
                        "id": migration.id,
                        "description": migration.description,
                        "cost": migration.cost,
                    }
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        after = _database_row_counts(conn)
        if before != after:
            raise RuntimeError(
                f"migration row-count invariant failed: before={before!r}, after={after!r}"
            )
        receipt = {
            "kind": "openclaw-mem.db.migration.receipt.v1",
            "db_path": str(path),
            "from_version": from_version,
            "to_version": CURRENT_DB_VERSION,
            "steps": applied,
            "row_counts_before": before,
            "row_counts_after": after,
            "backup_path": str(backup),
            "backup_sha256": backup_sha256,
            "migrated_sha256": _file_sha256(path),
            "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
        }
    finally:
        conn.close()

    output = (
        Path(receipt_path).expanduser().resolve()
        if receipt_path is not None
        else Path(f"{path}.migration-v{CURRENT_DB_VERSION}.receipt.json")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt["receipt_path"] = str(output)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def rollback_database(
    db_path: str | Path, receipt_path: str | Path
) -> Dict[str, Any]:
    path = Path(db_path).expanduser().resolve()
    receipt_file = Path(receipt_path).expanduser().resolve()
    payload = json.loads(receipt_file.read_text(encoding="utf-8"))
    if payload.get("kind") != "openclaw-mem.db.migration.receipt.v1":
        raise ValueError("invalid migration receipt kind")
    if Path(str(payload.get("db_path") or "")).expanduser().resolve() != path:
        raise ValueError("migration receipt database path does not match --db")
    backup = Path(str(payload.get("backup_path") or "")).expanduser().resolve()
    expected_backup = Path(
        f"{path}.pre-v{int(payload.get('to_version') or 0)}.backup.sqlite"
    ).resolve()
    if backup != expected_backup:
        raise ValueError("migration receipt backup path is not the governed database backup")
    if not backup.exists() or not backup.is_file():
        raise FileNotFoundError(f"migration backup not found: {backup}")
    expected_hash = str(payload.get("backup_sha256") or "")
    actual_hash = _file_sha256(backup)
    if not expected_hash or actual_hash != expected_hash:
        raise RuntimeError("migration backup hash mismatch; rollback denied")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"database not found: {path}")

    rolled_back = Path(f"{path}.rolledback")
    if rolled_back.exists():
        raise FileExistsError(f"rolled-back database copy already exists: {rolled_back}")
    os.replace(path, rolled_back)
    try:
        os.replace(backup, path)
    except Exception:
        os.replace(rolled_back, path)
        raise
    return {
        "kind": "openclaw-mem.db.rollback.receipt.v1",
        "db_path": str(path),
        "restored_version": int(payload["from_version"]),
        "rolled_back_path": str(rolled_back),
        "restored_sha256": _file_sha256(path),
        "source_receipt": str(receipt_file),
    }
