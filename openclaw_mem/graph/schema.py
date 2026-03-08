from __future__ import annotations

import sqlite3

GRAPH_SCHEMA_VERSION = 1


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
"""


def ensure_graph_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    conn.execute(
        "INSERT INTO graph_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("schema_version", str(GRAPH_SCHEMA_VERSION)),
    )
