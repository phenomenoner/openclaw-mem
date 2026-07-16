"""Output-free episodic record query primitives.

This module owns episodic validation and read payload construction.  CLI
adapters are responsible only for rendering errors/results and choosing exit
codes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
EPISODIC_SCHEMA_VERSION = "openclaw-mem.episodic.v0"
EPISODIC_DEFAULT_PAYLOAD_CAP_BYTES = 8 * 1024
EPISODIC_DEFAULT_REFS_CAP_BYTES = 4 * 1024
EPISODIC_SEARCH_TEXT_MAX_CHARS = 2400

EPISODIC_SECRET_LIKE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|pwd|secret)\b\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9\-_]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\baws[_-]?secret[_-]?access[_-]?key\b\s*[:=]\s*[A-Za-z0-9/+=]{20,}\b", re.IGNORECASE),
    re.compile(r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9\-_.=]{16,}\b", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-_.=]{24,}\b", re.IGNORECASE),
)
EPISODIC_PII_LITE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?\d[\d\-\s()]{7,}\d)(?!\d)"), "[REDACTED_PHONE]"),
)
EPISODIC_TOOL_OUTPUT_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^```(?:json|bash|sh|shell|log|output|yaml)?", re.IGNORECASE),
    re.compile(r"\b(?:stdout|stderr|exit\s*code|traceback|stack\s*trace)\b", re.IGNORECASE),
    re.compile(r"\b(?:tool[_\s-]?call|tool[_\s-]?result|command output)\b", re.IGNORECASE),
)


class DuplicateEventError(ValueError):
    """Raised when an episodic event id already exists."""

    def __init__(self, detail: str) -> None:
        super().__init__("event_id already exists")
        self.detail = detail


def _sanitize_str_surrogates(value: str) -> str:
    if not value:
        return value
    return "".join("\ufffd" if 0xD800 <= ord(ch) <= 0xDFFF else ch for ch in value)


def _sanitize_jsonable_surrogates(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_str_surrogates(value)
    if isinstance(value, dict):
        return {
            _sanitize_str_surrogates(key) if isinstance(key, str) else key: _sanitize_jsonable_surrogates(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_jsonable_surrogates(item) for item in value]
    return value


def _json_compact_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_optional_json_arg(
    raw_json: Optional[str], raw_file: Optional[str], label: str
) -> Tuple[Any, Optional[str], int]:
    if raw_json and raw_file:
        raise ValueError(f"provide only one of --{label}-json or --{label}-file")
    if raw_json:
        source = raw_json
    elif raw_file:
        path = Path(str(raw_file)).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"{label} file not found: {path}")
        source = path.read_text(encoding="utf-8")
    else:
        return None, None, 0
    try:
        parsed = json.loads(source)
    except Exception as exc:
        raise ValueError(f"invalid {label} JSON") from exc
    parsed = _sanitize_jsonable_surrogates(parsed)
    serialized = _json_compact_dumps(parsed)
    return parsed, serialized, len(serialized.encode("utf-8"))


def _looks_like_secret(text: str) -> bool:
    compact = str(text or "").strip()
    return bool(compact) and any(pattern.search(compact) for pattern in EPISODIC_SECRET_LIKE_PATTERNS)


def _contains_pii_lite(text: str) -> bool:
    compact = str(text or "").strip()
    return bool(compact) and any(pattern.search(compact) for pattern, _ in EPISODIC_PII_LITE_PATTERNS)


def _looks_like_tool_output(text: str) -> bool:
    compact = str(text or "").strip()
    if not compact or "<relevant-memories>" in compact:
        return True
    if re.search(r"^\{[\s\S]*\}$", compact) and re.search(r'"(?:stdout|stderr|exitCode|command|tool)"', compact):
        return True
    return any(pattern.search(compact) for pattern in EPISODIC_TOOL_OUTPUT_PATTERNS)


def _guard_text_fragments(
    summary: str,
    payload_serialized: Optional[str],
    refs_serialized: Optional[str],
    allow_tool_output: bool,
) -> None:
    if allow_tool_output:
        return
    if _looks_like_secret(summary):
        raise ValueError("summary appears to contain secret-like content; pass --allow-tool-output to override")
    if _contains_pii_lite(summary):
        raise ValueError("summary appears to contain pii-like content; pass --allow-tool-output to override")
    for fragment in (payload_serialized, refs_serialized):
        if fragment is None:
            continue
        if _looks_like_secret(fragment):
            raise ValueError("payload appears to contain secret-like content; pass --allow-tool-output to override")
        if _contains_pii_lite(fragment):
            raise ValueError("payload appears to contain pii-like content; pass --allow-tool-output to override")
        if _looks_like_tool_output(fragment):
            raise ValueError("payload appears to contain tool-output-like content; pass --allow-tool-output to override")


def _collect_search_fragments(value: Any, out: List[str], *, max_fragments: int = 48) -> None:
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
            _collect_search_fragments(value.get(key), out, max_fragments=max_fragments)
            if len(out) >= max_fragments:
                break
        return
    if isinstance(value, list):
        for item in value:
            _collect_search_fragments(item, out, max_fragments=max_fragments)
            if len(out) >= max_fragments:
                break


def _text_fragments_from_json(raw: Any) -> List[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        value = json.loads(raw)
    except Exception:
        text = re.sub(r"\s+", " ", _sanitize_str_surrogates(raw)).strip()
        return [text[:400]] if text else []
    out: List[str] = []
    _collect_search_fragments(value, out)
    return out


def build_search_text(*, summary: str, payload_json: Any, refs_json: Any) -> str:
    parts: List[str] = []
    seen = set()
    candidates = [summary, *_text_fragments_from_json(payload_json), *_text_fragments_from_json(refs_json)]
    for candidate in candidates:
        text = re.sub(r"\s+", " ", _sanitize_str_surrogates(str(candidate or ""))).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    result = "\n".join(parts).strip()
    if len(result) > EPISODIC_SEARCH_TEXT_MAX_CHARS:
        result = result[:EPISODIC_SEARCH_TEXT_MAX_CHARS].rstrip()
    return result


def append_event(
    conn: sqlite3.Connection,
    *,
    event_type: Any,
    raw_scope: Any,
    session_id: Any,
    agent_id: Any,
    summary: Any,
    event_id: Any = None,
    ts_ms: Any = None,
    payload_json: Optional[str] = None,
    payload_file: Optional[str] = None,
    refs_json: Optional[str] = None,
    refs_file: Optional[str] = None,
    payload_cap_bytes: int = EPISODIC_DEFAULT_PAYLOAD_CAP_BYTES,
    refs_cap_bytes: int = EPISODIC_DEFAULT_REFS_CAP_BYTES,
    allow_tool_output: bool = False,
) -> Dict[str, Any]:
    normalized_type = normalize_type(event_type)
    scope = normalize_scope(raw_scope)
    parsed_ts_ms = parse_ts_ms(ts_ms)
    normalized_session_id = str(session_id or "").strip()
    normalized_agent_id = str(agent_id or "").strip()
    normalized_summary = _sanitize_str_surrogates(str(summary or "").strip())
    if not normalized_session_id:
        raise ValueError("session_id is required")
    if not normalized_agent_id:
        raise ValueError("agent_id is required")
    if not normalized_summary:
        raise ValueError("summary is required")
    payload_cap = int(payload_cap_bytes)
    refs_cap = int(refs_cap_bytes)
    if payload_cap <= 0 or refs_cap <= 0:
        raise ValueError("payload/refs caps must be > 0")

    payload_obj, payload_serialized, payload_size = _parse_optional_json_arg(payload_json, payload_file, "payload")
    refs_obj, refs_serialized, refs_size = _parse_optional_json_arg(refs_json, refs_file, "refs")
    if payload_size > payload_cap:
        raise ValueError(f"payload exceeds cap ({payload_size} > {payload_cap} bytes)")
    if refs_size > refs_cap:
        raise ValueError(f"refs exceeds cap ({refs_size} > {refs_cap} bytes)")
    _guard_text_fragments(normalized_summary, payload_serialized, refs_serialized, allow_tool_output)

    normalized_event_id = str(event_id or "").strip() or str(uuid.uuid4())
    created_at = utcnow_iso()
    try:
        conn.execute(
            """
            INSERT INTO episodic_events (
                event_id, ts_ms, scope, session_id, agent_id, type, summary,
                payload_json, refs_json, redacted, schema_version, created_at, search_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                normalized_event_id,
                parsed_ts_ms,
                scope,
                normalized_session_id,
                normalized_agent_id,
                normalized_type,
                normalized_summary,
                payload_serialized,
                refs_serialized,
                EPISODIC_SCHEMA_VERSION,
                created_at,
                build_search_text(summary=normalized_summary, payload_json=payload_serialized, refs_json=refs_serialized),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise DuplicateEventError(str(exc)) from exc

    return {
        "kind": "openclaw-mem.episodes.append.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "event": {
            "event_id": normalized_event_id,
            "ts_ms": parsed_ts_ms,
            "scope": scope,
            "session_id": normalized_session_id,
            "agent_id": normalized_agent_id,
            "type": normalized_type,
            "summary": normalized_summary,
            "payload_bytes": payload_size,
            "refs_bytes": refs_size,
            "schema_version": EPISODIC_SCHEMA_VERSION,
            "redacted": False,
            "payload_present": payload_obj is not None,
            "refs_present": refs_obj is not None,
        },
        "caps": {"payload_cap_bytes": payload_cap, "refs_cap_bytes": refs_cap},
    }


def _session_store_basename(raw_path: Any) -> str:
    normalized = str(raw_path or "").strip().replace("\\", "/")
    return normalized.rsplit("/", 1)[-1].strip() or "sessions.json"


def append_session_store_receipt(
    conn: sqlite3.Connection,
    *,
    raw_scope: Any = "global",
    ts_ms: Any = None,
    agent_id: Any = "openclaw",
    event_name: Any = "session_store_rotated",
    store_path: Any = None,
    size_bytes: Any = None,
    backup_count: Any = None,
    event_id: Any = None,
) -> Dict[str, Any]:
    scope = normalize_scope(raw_scope or "global")
    parsed_ts_ms = parse_ts_ms(ts_ms)
    normalized_agent_id = str(agent_id or "openclaw").strip() or "openclaw"
    normalized_event_name = str(event_name or "session_store_rotated").strip()
    if normalized_event_name not in {"session_store_rotated", "session_store_cleanup"}:
        raise ValueError("--event must be session_store_rotated or session_store_cleanup")

    store_basename = _session_store_basename(store_path)
    parsed_size_bytes = int(size_bytes) if size_bytes is not None else None
    parsed_backup_count = int(backup_count) if backup_count is not None else None
    if parsed_size_bytes is not None and parsed_size_bytes < 0:
        raise ValueError("--size-bytes must be >= 0")
    if parsed_backup_count is not None and parsed_backup_count < 0:
        raise ValueError("--backup-count must be >= 0")

    payload_obj: Dict[str, Any] = {
        "event": normalized_event_name,
        "store_basename": store_basename,
    }
    if parsed_size_bytes is not None:
        payload_obj["size_bytes"] = parsed_size_bytes
    if parsed_backup_count is not None:
        payload_obj["backup_count"] = parsed_backup_count
    refs_obj = {"source": "openclaw_session_store_maintenance", "store_basename": store_basename}
    payload_serialized = _json_compact_dumps(payload_obj)
    refs_serialized = _json_compact_dumps(refs_obj)
    payload_bytes = len(payload_serialized.encode("utf-8"))
    refs_bytes = len(refs_serialized.encode("utf-8"))

    summary_parts = [normalized_event_name, f"store={store_basename}"]
    if parsed_size_bytes is not None:
        summary_parts.append(f"size_bytes={parsed_size_bytes}")
    if parsed_backup_count is not None:
        summary_parts.append(f"backup_count={parsed_backup_count}")
    summary = " ".join(summary_parts)

    normalized_event_id = str(event_id or "").strip()
    if not normalized_event_id:
        seed = (
            f"{scope}:{normalized_agent_id}:{normalized_event_name}:{store_basename}:"
            f"{parsed_ts_ms}:{parsed_size_bytes}:{parsed_backup_count}"
        )
        normalized_event_id = f"session-store-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"
    try:
        conn.execute(
            """
            INSERT INTO episodic_events (
                event_id, ts_ms, scope, session_id, agent_id, type, summary,
                payload_json, refs_json, redacted, schema_version, created_at, search_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                normalized_event_id,
                parsed_ts_ms,
                scope,
                "openclaw-session-store",
                normalized_agent_id,
                "ops.observation",
                summary,
                payload_serialized,
                refs_serialized,
                EPISODIC_SCHEMA_VERSION,
                utcnow_iso(),
                build_search_text(summary=summary, payload_json=payload_serialized, refs_json=refs_serialized),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise DuplicateEventError(str(exc)) from exc

    return {
        "kind": "openclaw-mem.episodes.append-session-store-receipt.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "event": {
            "event_id": normalized_event_id,
            "ts_ms": parsed_ts_ms,
            "scope": scope,
            "session_id": "openclaw-session-store",
            "agent_id": normalized_agent_id,
            "type": "ops.observation",
            "summary": summary,
            "payload_bytes": payload_bytes,
            "refs_bytes": refs_bytes,
            "schema_version": EPISODIC_SCHEMA_VERSION,
            "redacted": False,
        },
    }


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
