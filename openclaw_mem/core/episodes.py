"""Output-free episodic record query primitives.

This module owns episodic validation and read payload construction.  CLI
adapters are responsible only for rendering errors/results and choosing exit
codes.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openclaw_mem import __version__
from openclaw_mem.scope import normalize_scope_token


EPISODIC_ALLOWED_TYPES = {
    "conversation.user",
    "conversation.assistant",
    "tool.call",
    "tool.result",
    "ops.decision",
    "ops.alert",
    "ops.observation",
}
EPISODIC_MAX_QUERY_LIMIT = 500


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_scope(raw: Any) -> str:
    normalized = normalize_scope_token(raw)
    if not normalized:
        raise ValueError("invalid scope")
    return normalized


def resolve_query_scope(raw_scope: Optional[str], allow_global: bool) -> str:
    if raw_scope is None or not str(raw_scope).strip():
        if allow_global:
            return "global"
        raise ValueError("scope is required (or pass --global)")

    normalized = normalize_scope(raw_scope)
    if allow_global and normalized != "global":
        raise ValueError("--global cannot be combined with non-global --scope")
    return normalized


def normalize_type(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value not in EPISODIC_ALLOWED_TYPES:
        allowed = ", ".join(sorted(EPISODIC_ALLOWED_TYPES))
        raise ValueError(f"invalid type: {value or '<empty>'}; allowed: {allowed}")
    return value


def normalize_types_filter(raw_types: Optional[List[str]]) -> Optional[List[str]]:
    if not raw_types:
        return None

    out: List[str] = []
    seen = set()
    for raw in raw_types:
        for part in (part.strip() for part in str(raw).split(",")):
            if not part:
                continue
            event_type = normalize_type(part)
            if event_type not in seen:
                seen.add(event_type)
                out.append(event_type)
    return out or None


def parse_ts_ms(raw: Any) -> int:
    if raw is None:
        return int(time.time() * 1000)
    try:
        value = int(raw)
    except Exception as exc:
        raise ValueError(f"invalid ts_ms: {raw}") from exc
    if value <= 0:
        raise ValueError("ts_ms must be > 0")
    return value


def row_to_item(row: sqlite3.Row, *, include_payload: bool) -> Dict[str, Any]:
    refs_obj: Any = None
    if row["refs_json"] is not None:
        try:
            refs_obj = json.loads(row["refs_json"])
        except Exception:
            pass

    item: Dict[str, Any] = {
        "id": int(row["id"]),
        "event_id": row["event_id"],
        "ts_ms": int(row["ts_ms"]),
        "scope": row["scope"],
        "session_id": row["session_id"],
        "agent_id": row["agent_id"],
        "type": row["type"],
        "summary": row["summary"],
        "refs": refs_obj,
        "redacted": bool(row["redacted"]),
        "schema_version": row["schema_version"],
        "created_at": row["created_at"],
    }
    if include_payload:
        payload_obj: Any = None
        if row["payload_json"] is not None:
            try:
                payload_obj = json.loads(row["payload_json"])
            except Exception:
                pass
        item["payload"] = payload_obj
    return item


def query_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    session_id: Optional[str],
    from_ts_ms: Optional[int],
    to_ts_ms: Optional[int],
    types_filter: Optional[List[str]],
    limit: int,
) -> List[sqlite3.Row]:
    clauses = ["scope = ?"]
    params: List[Any] = [scope]
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if from_ts_ms is not None:
        clauses.append("ts_ms >= ?")
        params.append(int(from_ts_ms))
    if to_ts_ms is not None:
        clauses.append("ts_ms <= ?")
        params.append(int(to_ts_ms))
    if types_filter:
        clauses.append(f"type IN ({','.join(['?'] * len(types_filter))})")
        params.extend(types_filter)
    sql = (
        "SELECT id, event_id, ts_ms, scope, session_id, agent_id, type, summary, "
        "payload_json, refs_json, redacted, schema_version, created_at "
        f"FROM episodic_events WHERE {' AND '.join(clauses)} "
        "ORDER BY ts_ms ASC, id ASC LIMIT ?"
    )
    params.append(int(limit))
    return conn.execute(sql, params).fetchall()


def query(
    conn: sqlite3.Connection,
    *,
    raw_scope: Optional[str],
    global_scope: bool,
    session_id: Optional[str] = None,
    from_ts_ms: Any = None,
    to_ts_ms: Any = None,
    raw_types: Optional[List[str]] = None,
    limit: int = 50,
    include_payload: bool = False,
) -> Dict[str, Any]:
    scope = resolve_query_scope(raw_scope, global_scope)
    session_id = str(session_id or "").strip() or None
    parsed_from = parse_ts_ms(from_ts_ms) if from_ts_ms is not None else None
    parsed_to = parse_ts_ms(to_ts_ms) if to_ts_ms is not None else None
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise ValueError("from_ts_ms cannot be greater than to_ts_ms")
    types_filter = normalize_types_filter(raw_types)
    bounded_limit = max(1, min(EPISODIC_MAX_QUERY_LIMIT, int(limit)))
    rows = query_rows(
        conn,
        scope=scope,
        session_id=session_id,
        from_ts_ms=parsed_from,
        to_ts_ms=parsed_to,
        types_filter=types_filter,
        limit=bounded_limit,
    )
    items = [row_to_item(row, include_payload=include_payload) for row in rows]
    return {
        "kind": "openclaw-mem.episodes.query.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "scope": scope,
        "filters": {
            "session_id": session_id,
            "from_ts_ms": parsed_from,
            "to_ts_ms": parsed_to,
            "types": types_filter or [],
            "limit": bounded_limit,
            "include_payload": bool(include_payload),
        },
        "count": len(items),
        "items": items,
    }


def replay(
    conn: sqlite3.Connection,
    *,
    raw_scope: Optional[str],
    global_scope: bool,
    session_id: str,
    limit: int = 200,
    include_payload: bool = False,
) -> Dict[str, Any]:
    scope = resolve_query_scope(raw_scope, global_scope)
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise ValueError("session_id is required")
    bounded_limit = max(1, min(EPISODIC_MAX_QUERY_LIMIT, int(limit)))
    rows = query_rows(
        conn,
        scope=scope,
        session_id=normalized_session_id,
        from_ts_ms=None,
        to_ts_ms=None,
        types_filter=None,
        limit=bounded_limit,
    )
    items = [row_to_item(row, include_payload=include_payload) for row in rows]
    return {
        "kind": "openclaw-mem.episodes.replay.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "scope": scope,
        "session_id": normalized_session_id,
        "count": len(items),
        "limit": bounded_limit,
        "include_payload": bool(include_payload),
        "items": items,
    }
