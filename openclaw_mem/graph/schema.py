from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

GRAPH_SCHEMA_VERSION = 1


_REQUIRED_GRAPH_TABLES = (
    "graph_nodes",
    "graph_edges",
    "graph_meta",
    "graph_refresh_receipts",
)


def connect_graph_db_for_query(
    db_path: str | Path,
    *,
    required_tables: Iterable[str] = _REQUIRED_GRAPH_TABLES,
) -> sqlite3.Connection:
    db_file = Path(str(db_path or "")).resolve()
    if not str(db_path or "").strip():
        raise ValueError("db_path is required")
    if not db_file.is_file():
        raise ValueError(f"graph db not found: {db_file}")

    try:
        conn = sqlite3.connect(str(db_file))
    except sqlite3.Error as exc:
        raise ValueError(f"failed to open graph db: {db_file}: {exc}") from exc

    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", ("table",)).fetchall()
    except sqlite3.Error as exc:
        conn.close()
        raise ValueError(f"failed to inspect graph db schema: {db_file}: {exc}") from exc

    existing_tables = {str(row[0]) for row in rows}
    missing_tables = [name for name in required_tables if name not in existing_tables]
    if missing_tables:
        conn.close()
        raise ValueError(
            "graph schema missing required tables: " + ", ".join(missing_tables)
        )

    return conn


_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS graph_nodes (
  node_id TEXT PRIMARY KEY,
  node_type TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
  src_id TEXT NOT NULL,
  dst_id TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  provenance TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  PRIMARY KEY (src_id, dst_id, edge_type, provenance)
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(src_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_dst ON graph_edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(edge_type);

CREATE TABLE IF NOT EXISTS graph_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_refresh_receipts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  refreshed_at TEXT NOT NULL,
  source_path TEXT NOT NULL,
  topology_digest TEXT NOT NULL,
  node_count INTEGER NOT NULL,
  edge_count INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_graph_refresh_receipts_refreshed_at
ON graph_refresh_receipts(refreshed_at DESC);
"""


def ensure_graph_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    conn.execute(
        "INSERT INTO graph_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("schema_version", str(GRAPH_SCHEMA_VERSION)),
    )
