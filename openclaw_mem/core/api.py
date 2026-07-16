"""Supported programmatic entrypoints independent of the CLI parser."""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
from contextlib import redirect_stdout
from typing import Any, Mapping

from openclaw_mem.core.db import _connect
from openclaw_mem.core.records import _insert_observation


def connect(db_path: str) -> sqlite3.Connection:
    return _connect(db_path)


def store_observation(conn: sqlite3.Connection, obs: Mapping[str, Any]) -> int:
    return _insert_observation(conn, dict(obs))


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 20,
    scope: str | None = None,
) -> Any:
    # T10 moves the implementation; keep this compatibility wrapper lazy so
    # importing the stable storage API does not import the CLI monolith.
    from openclaw_mem.cli import cmd_search

    args = argparse.Namespace(query=query, limit=limit, graph=False, graph_path=None, scope=scope, json=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_search(conn, args)
    return json.loads(buf.getvalue())


def pack(conn: sqlite3.Connection, query: str, **kwargs: Any) -> Any:
    # T10 replaces this lazy bridge with the extracted core pack pipeline.
    from openclaw_mem.cli import cmd_pack

    values = {
        "query": query,
        "query_en": None,
        "limit": 8,
        "budget_tokens": 1200,
        "trace": False,
        "json": True,
        "use_graph": "off",
    }
    values.update(kwargs)
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_pack(conn, argparse.Namespace(**values))
    return json.loads(buf.getvalue())
