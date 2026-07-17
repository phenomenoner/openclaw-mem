"""Supported programmatic entrypoints independent of the CLI parser."""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from openclaw_mem.core.db import _connect
from openclaw_mem.core.pack import build_pack
from openclaw_mem.core.records import _insert_observation
from openclaw_mem.core.search import lexical_search


def connect(db_path: str) -> sqlite3.Connection:
    return _connect(db_path)


def store_observation(conn: sqlite3.Connection, obs: Mapping[str, Any]) -> int:
    return _insert_observation(conn, dict(obs))


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 20,
    scope: str | None = None,
    include_archived: bool = False,
) -> Any:
    return lexical_search(
        conn,
        query,
        limit=limit,
        scope=scope,
        include_archived=include_archived,
    )


def pack(conn: sqlite3.Connection, query: str, **kwargs: Any) -> Any:
    return build_pack(conn, query, **kwargs)
