"""Output-free episodic record query primitives.

This module owns episodic validation and read payload construction.  CLI
adapters are responsible only for rendering errors/results and choosing exit
codes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from openclaw_mem import __version__
from openclaw_mem import defaults
from openclaw_mem.scope import normalize_scope_token
from openclaw_mem.vector import l2_norm, pack_f32, rank_cosine, rank_rrf


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
EPISODIC_REDACT_PLACEHOLDER = "[REDACTED]"
EPISODIC_DEFAULT_RETENTION_DAYS: Dict[str, Optional[int]] = {
    "conversation.user": 60,
    "conversation.assistant": 90,
    "tool.call": 30,
    "tool.result": 30,
    "ops.decision": None,
    "ops.alert": 90,
}

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


class MissingApiKeyError(ValueError):
    """Raised when an embedding mutation is requested without credentials."""


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


def _search_match_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    query: str,
    search_limit: int,
    broad_fallback_max_tokens: Optional[int] = None,
) -> List[sqlite3.Row]:
    sql = (
        "SELECT e.id, e.event_id, e.ts_ms, e.scope, e.session_id, e.agent_id, e.type, e.summary, "
        "e.payload_json, e.refs_json, e.redacted, e.schema_version, e.created_at, "
        "snippet(episodic_events_fts, 1, '[', ']', '…', 16) AS snippet, "
        "bm25(episodic_events_fts) AS score "
        "FROM episodic_events_fts "
        "JOIN episodic_events e ON e.id = episodic_events_fts.rowid "
        "WHERE episodic_events_fts MATCH ? AND e.scope = ? "
        "ORDER BY bm25(episodic_events_fts) ASC, e.ts_ms DESC, e.id DESC "
        "LIMIT ?"
    )
    rows: List[sqlite3.Row] = []
    try:
        rows = conn.execute(sql, (query, scope, int(search_limit))).fetchall()
    except sqlite3.OperationalError:
        sanitized = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
        sanitized = " ".join(sanitized.split())
        retry_query = sanitized if sanitized else query
        if retry_query != query:
            try:
                rows = conn.execute(sql, (retry_query, scope, int(search_limit))).fetchall()
            except sqlite3.OperationalError:
                rows = []
    if rows:
        return rows
    tokens = [token for token in re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE).split() if token]
    if broad_fallback_max_tokens is not None and len(tokens) > max(0, int(broad_fallback_max_tokens)):
        return []
    if len(tokens) > 1:
        try:
            return conn.execute(sql, (" OR ".join(tokens), scope, int(search_limit))).fetchall()
        except sqlite3.OperationalError:
            return []
    return []


def _search_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _vector_rankings(
    conn: sqlite3.Connection,
    *,
    scope: str,
    query: str,
    query_en: Optional[str],
    model: str,
    candidate_limit: int,
    base_url: Optional[str],
    api_key_provider: Callable[[], Optional[str]],
    client_factory: Callable[[str, Optional[str]], Any],
) -> Dict[str, Any]:
    has_rows = conn.execute(
        """
        SELECT 1
        FROM episodic_event_embeddings emb
        JOIN episodic_events e ON e.id = emb.event_row_id
        WHERE emb.model = ? AND e.scope = ?
        LIMIT 1
        """,
        (model, scope),
    ).fetchone() is not None
    empty = {"vec_ids": [], "vec_scores": {}, "vec_en_ids": [], "vec_en_scores": {}}
    if not has_rows:
        return {"vector_status": "missing_embeddings", **empty}
    api_key = api_key_provider()
    if not api_key:
        return {"vector_status": "missing_api_key", **empty}
    try:
        client = client_factory(api_key, base_url)
        embed_inputs = [query] + ([query_en] if query_en else [])
        embed_vecs = client.embed(embed_inputs, model=model)
        query_vec = embed_vecs[0]
        query_en_vec = embed_vecs[1] if query_en and len(embed_vecs) > 1 else None
    except Exception as exc:
        return {"vector_status": str(exc), **empty}

    query_dim = len(query_vec)
    rows = conn.execute(
        """
        SELECT emb.event_row_id, emb.vector, emb.norm
        FROM episodic_event_embeddings emb
        JOIN episodic_events e ON e.id = emb.event_row_id
        WHERE emb.model = ? AND emb.dim = ? AND e.scope = ?
        ORDER BY emb.event_row_id ASC
        """,
        (model, query_dim, scope),
    ).fetchall()
    vec_ranked = rank_cosine(
        query_vec=query_vec,
        items=((int(row[0]), row[1], float(row[2])) for row in rows),
        limit=max(1, int(candidate_limit)),
    )
    vec_ids = [row_id for row_id, _ in vec_ranked]
    vec_scores = {int(row_id): float(score) for row_id, score in vec_ranked}

    vec_en_ranked: List[Tuple[int, float]] = []
    if query_en_vec is not None:
        query_en_dim = len(query_en_vec)
        vec_en_rows = rows
        if query_en_dim != query_dim:
            vec_en_rows = conn.execute(
                """
                SELECT emb.event_row_id, emb.vector, emb.norm
                FROM episodic_event_embeddings emb
                JOIN episodic_events e ON e.id = emb.event_row_id
                WHERE emb.model = ? AND emb.dim = ? AND e.scope = ?
                ORDER BY emb.event_row_id ASC
                """,
                (model, query_en_dim, scope),
            ).fetchall()
        vec_en_ranked = rank_cosine(
            query_vec=query_en_vec,
            items=((int(row[0]), row[1], float(row[2])) for row in vec_en_rows),
            limit=max(1, int(candidate_limit)),
        )
    return {
        "vector_status": "ok",
        "vec_ids": vec_ids,
        "vec_scores": vec_scores,
        "vec_en_ids": [row_id for row_id, _ in vec_en_ranked],
        "vec_en_scores": {int(row_id): float(score) for row_id, score in vec_en_ranked},
    }


def _fetch_rows_by_ids(conn: sqlite3.Connection, *, ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not ids:
        return {}
    query_sql = (
        "SELECT id, event_id, ts_ms, scope, session_id, agent_id, type, summary, "
        "payload_json, refs_json, redacted, schema_version, created_at "
        f"FROM episodic_events WHERE id IN ({','.join(['?'] * len(ids))})"
    )
    return {int(row["id"]): dict(row) for row in conn.execute(query_sql, ids).fetchall()}


def search_events(
    conn: sqlite3.Connection,
    *,
    raw_scope: Optional[str],
    global_scope: bool,
    query: Any,
    limit: int = 5,
    per_session_limit: int = 3,
    search_limit: int = 40,
    include_payload: bool = False,
    mode: str = "lexical",
    query_en: Optional[str] = None,
    trace: bool = False,
    model: Optional[str] = None,
    k: int = 60,
    base_url: Optional[str] = None,
    broad_fallback_max_tokens: Optional[int] = None,
    api_key_provider: Optional[Callable[[], Optional[str]]] = None,
    client_factory: Optional[Callable[[str, Optional[str]], Any]] = None,
) -> Dict[str, Any]:
    scope = resolve_query_scope(raw_scope, global_scope)
    query_text = str(query or "").strip()
    if not query_text:
        raise ValueError("query is required")
    bounded_limit = max(1, min(EPISODIC_MAX_QUERY_LIMIT, int(limit or 5)))
    bounded_per_session = max(1, min(20, int(per_session_limit or 3)))
    bounded_search = max(1, min(500, int(search_limit or 40)))
    retrieval_mode = str(mode or "lexical").strip().lower() or "lexical"
    if retrieval_mode not in {"lexical", "hybrid", "vector"}:
        raise ValueError("mode must be one of: lexical, hybrid, vector")
    normalized_query_en = str(query_en or "").strip() or None
    model_name = str(model or defaults.embed_model())

    fts_rows: List[sqlite3.Row] = []
    if retrieval_mode in {"lexical", "hybrid"}:
        fts_rows = _search_match_rows(
            conn,
            scope=scope,
            query=query_text,
            search_limit=bounded_search,
            broad_fallback_max_tokens=broad_fallback_max_tokens,
        )
    fts_ids = [int(row["id"]) for row in fts_rows]
    fts_score_map = {int(row["id"]): float(row["score"]) for row in fts_rows if row["score"] is not None}
    snippet_map = {
        int(row["id"]): re.sub(r"\s+", " ", str(row["snippet"] or "")).strip()
        for row in fts_rows
    }

    vec_state: Dict[str, Any] = {
        "vector_status": None,
        "vec_ids": [],
        "vec_scores": {},
        "vec_en_ids": [],
        "vec_en_scores": {},
    }
    if retrieval_mode in {"hybrid", "vector"}:
        vec_state = _vector_rankings(
            conn,
            scope=scope,
            query=query_text,
            query_en=normalized_query_en,
            model=model_name,
            candidate_limit=bounded_search,
            base_url=base_url,
            api_key_provider=api_key_provider or (lambda: None),
            client_factory=client_factory or (lambda _api_key, _base_url: None),
        )
    vec_ids = list(vec_state.get("vec_ids") or [])
    vec_scores = dict(vec_state.get("vec_scores") or {})
    vec_en_ids = list(vec_state.get("vec_en_ids") or [])
    vec_en_scores = dict(vec_state.get("vec_en_scores") or {})
    vector_status = vec_state.get("vector_status")

    ranked_lists: List[List[int]] = []
    if retrieval_mode in {"lexical", "hybrid"} and fts_ids:
        ranked_lists.append(fts_ids)
    if retrieval_mode in {"hybrid", "vector"} and vec_ids:
        ranked_lists.append(vec_ids)
    if retrieval_mode in {"hybrid", "vector"} and vec_en_ids:
        ranked_lists.append(vec_en_ids)
    if retrieval_mode == "vector" and not ranked_lists:
        ordered: List[Tuple[int, float]] = []
    elif retrieval_mode in {"lexical", "hybrid"} and (retrieval_mode == "lexical" or not ranked_lists):
        ordered = [(row_id, 1.0 / (k + index + 1)) for index, row_id in enumerate(fts_ids)]
    else:
        ordered = rank_rrf(ranked_lists, k=max(1, int(k)), limit=bounded_search)

    ordered_ids = [int(row_id) for row_id, _ in ordered]
    rrf_scores = {int(row_id): float(score) for row_id, score in ordered}
    row_map = _fetch_rows_by_ids(conn, ids=ordered_ids)
    fts_id_set, vec_id_set, vec_en_id_set = set(fts_ids), set(vec_ids), set(vec_en_ids)
    grouped: Dict[str, Dict[str, Any]] = {}
    for rank_index, row_id in enumerate(ordered_ids, 1):
        row = row_map.get(row_id)
        if row is None:
            continue
        session_id = str(row["session_id"] or "")
        entry = grouped.setdefault(
            session_id,
            {
                "session_id": session_id,
                "hit_count": 0,
                "best_match_score": None,
                "best_match_rank": None,
                "best_rrf_score": None,
                "latest_ts_ms": int(row["ts_ms"] or 0),
                "agent_ids": set(),
                "type_counts": {},
                "matched_items": [],
            },
        )
        entry["hit_count"] += 1
        entry["latest_ts_ms"] = max(int(entry["latest_ts_ms"]), int(row["ts_ms"] or 0))
        entry["agent_ids"].add(str(row["agent_id"] or ""))
        event_type = str(row["type"] or "unknown")
        entry["type_counts"][event_type] = int(entry["type_counts"].get(event_type, 0)) + 1
        if entry["best_match_rank"] is None or rank_index < entry["best_match_rank"]:
            entry["best_match_rank"] = rank_index
        rrf_score = float(rrf_scores.get(row_id, 0.0))
        if entry["best_rrf_score"] is None or rrf_score > entry["best_rrf_score"]:
            entry["best_rrf_score"] = rrf_score
        if retrieval_mode == "lexical":
            fts_score = fts_score_map.get(row_id)
            if fts_score is not None and (entry["best_match_score"] is None or fts_score < entry["best_match_score"]):
                entry["best_match_score"] = fts_score
        item = row_to_item(row, include_payload=include_payload)
        lanes = []
        if row_id in fts_id_set:
            lanes.append("fts")
        if row_id in vec_id_set:
            lanes.append("vector")
        if row_id in vec_en_id_set:
            lanes.append("vector_query_en")
        item["match"] = {
            "lanes": lanes,
            "rank": rank_index,
            "rrf_score": rrf_score,
            "snippet": snippet_map.get(row_id) or item.get("summary"),
        }
        if row_id in fts_score_map:
            item["match"]["fts_score"] = float(fts_score_map[row_id])
        if row_id in vec_scores:
            item["match"]["vector_score"] = float(vec_scores[row_id])
        if row_id in vec_en_scores:
            item["match"]["vector_query_en_score"] = float(vec_en_scores[row_id])
        entry["matched_items"].append(item)

    ranked_sessions = sorted(
        grouped.values(),
        key=lambda item: (
            -int(item["hit_count"]),
            int(item["best_match_rank"]) if item["best_match_rank"] is not None else 10**9,
            -int(item["latest_ts_ms"]),
            str(item["session_id"]),
        ),
    )[:bounded_limit]
    sessions: List[Dict[str, Any]] = []
    for rank, entry in enumerate(ranked_sessions, 1):
        matched_items = list(entry["matched_items"])[:bounded_per_session]
        summary_parts: List[str] = []
        seen_summary = set()
        for item in matched_items:
            item_summary = str(item.get("summary") or "").strip()
            if item_summary and item_summary not in seen_summary:
                seen_summary.add(item_summary)
                summary_parts.append(item_summary)
        sessions.append(
            {
                "rank": rank,
                "session_id": entry["session_id"],
                "hit_count": int(entry["hit_count"]),
                "best_match_rank": entry["best_match_rank"],
                "best_match_score": entry["best_match_score"],
                "best_rrf_score": entry["best_rrf_score"],
                "latest_ts_ms": int(entry["latest_ts_ms"]),
                "agent_ids": sorted(value for value in entry["agent_ids"] if value),
                "type_counts": [
                    {"type": key, "count": int(value)}
                    for key, value in sorted(entry["type_counts"].items(), key=lambda pair: (-int(pair[1]), str(pair[0])))
                ],
                "summary": " | ".join(summary_parts)[:280],
                "replay_hint": {
                    "scope": scope,
                    "session_id": entry["session_id"],
                    "command": f"openclaw-mem episodes replay {shlex.quote(entry['session_id'])} --scope {shlex.quote(scope)} --json",
                },
                "matched_items": matched_items,
            }
        )

    payload: Dict[str, Any] = {
        "kind": "openclaw-mem.episodes.search.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "scope": scope,
        "query": {"text": query_text, "text_en": normalized_query_en},
        "result": {
            "count": len(sessions),
            "session_limit": bounded_limit,
            "per_session_limit": bounded_per_session,
            "search_limit": bounded_search,
            "include_payload": bool(include_payload),
            "mode": retrieval_mode,
            "sessions": sessions,
        },
    }
    if vector_status and retrieval_mode in {"hybrid", "vector"}:
        payload["vector_status"] = vector_status
    if trace:
        payload["trace"] = {
            "mode": retrieval_mode,
            "model": model_name,
            "query": {"text": query_text, "text_en": normalized_query_en},
            "fts_top_k": [
                {
                    "id": int(row["id"]),
                    "event_id": str(row["event_id"] or ""),
                    "session_id": str(row["session_id"] or ""),
                    "score": float(row["score"] or 0.0),
                    "snippet": snippet_map.get(int(row["id"])) or "",
                }
                for row in fts_rows[:bounded_search]
            ],
            "vec_top_k": [
                {"id": int(row_id), "score": float(vec_scores.get(int(row_id), 0.0)), "session_id": str((row_map.get(int(row_id)) or {}).get("session_id") or "")}
                for row_id in vec_ids[:bounded_search]
            ],
            "vec_query_en_top_k": [
                {"id": int(row_id), "score": float(vec_en_scores.get(int(row_id), 0.0)), "session_id": str((row_map.get(int(row_id)) or {}).get("session_id") or "")}
                for row_id in vec_en_ids[:bounded_search]
            ],
            "fused_ranking": [
                {
                    "id": int(row_id),
                    "event_id": str((row_map.get(int(row_id)) or {}).get("event_id") or ""),
                    "session_id": str((row_map.get(int(row_id)) or {}).get("session_id") or ""),
                    "rrf_score": float(rrf_scores.get(int(row_id), 0.0)),
                    "lanes": [
                        lane
                        for lane, present in (
                            ("fts", int(row_id) in fts_id_set),
                            ("vector", int(row_id) in vec_id_set),
                            ("vector_query_en", int(row_id) in vec_en_id_set),
                        )
                        if present
                    ],
                }
                for row_id in ordered_ids[:bounded_search]
            ],
        }
    return payload


def embed_events(
    conn: sqlite3.Connection,
    *,
    api_key: Optional[str],
    client_factory: Callable[[str, Optional[str]], Any],
    model: Optional[str] = None,
    limit: int = 200,
    batch: int = 32,
    base_url: Optional[str] = None,
    raw_scope: Optional[str] = None,
    global_scope: bool = False,
) -> Dict[str, Any]:
    if not api_key:
        raise MissingApiKeyError("OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json")
    model_name = str(model or defaults.embed_model())
    bounded_limit = max(1, int(limit or 200))
    bounded_batch = max(1, int(batch or 32))
    scope_text = str(raw_scope or "").strip()
    if global_scope and scope_text:
        raise ValueError("--global cannot be combined with --scope")
    filters: List[str] = []
    params: List[Any] = []
    if global_scope:
        filters.append("e.scope = ?")
        params.append("global")
    elif scope_text:
        filters.append("e.scope = ?")
        params.append(normalize_scope(scope_text))
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = conn.execute(
        f"""
        SELECT e.id, e.scope, e.search_text, emb.search_text_hash
        FROM episodic_events e
        LEFT JOIN episodic_event_embeddings emb
          ON emb.event_row_id = e.id AND emb.model = ?
        {where_sql}
        ORDER BY e.id ASC
        """,
        [model_name, *params],
    ).fetchall()
    todo: List[Dict[str, Any]] = []
    for row in rows:
        text_value = str(row["search_text"] or "").strip()
        if not text_value:
            continue
        text_hash = _search_text_hash(text_value)
        if str(row["search_text_hash"] or "") == text_hash:
            continue
        todo.append({"id": int(row["id"]), "scope": str(row["scope"] or ""), "text": text_value, "search_text_hash": text_hash})
        if len(todo) >= bounded_limit:
            break

    client = client_factory(api_key, base_url)
    created_at = utcnow_iso()
    embedded_ids: List[int] = []
    per_scope: Dict[str, int] = {}
    for index in range(0, len(todo), bounded_batch):
        chunk = todo[index : index + bounded_batch]
        vectors = client.embed([str(item["text"]) for item in chunk], model=model_name)
        for item, vector in zip(chunk, vectors):
            conn.execute(
                """
                INSERT OR REPLACE INTO episodic_event_embeddings
                (event_row_id, model, dim, vector, norm, search_text_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (int(item["id"]), model_name, len(vector), pack_f32(vector), l2_norm(vector), str(item["search_text_hash"]), created_at),
            )
            embedded_ids.append(int(item["id"]))
            scope_key = str(item["scope"] or "")
            per_scope[scope_key] = int(per_scope.get(scope_key, 0)) + 1
        conn.commit()
    return {
        "kind": "openclaw-mem.episodes.embed.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "model": model_name,
        "scope_filter": "global" if global_scope else (scope_text or None),
        "limit": bounded_limit,
        "batch": bounded_batch,
        "embedded": len(embedded_ids),
        "ids": embedded_ids[:50],
        "per_scope": [{"scope": key, "count": int(value)} for key, value in sorted(per_scope.items())],
    }


def redact_events(
    conn: sqlite3.Connection,
    *,
    event_id: Any = None,
    session_id: Any = None,
    raw_scope: Optional[str] = None,
    global_scope: bool = False,
    replacement: str = "placeholder",
) -> Dict[str, Any]:
    normalized_event_id = str(event_id or "").strip() or None
    normalized_session_id = str(session_id or "").strip() or None
    if bool(normalized_event_id) == bool(normalized_session_id):
        raise ValueError("provide exactly one of --event-id or --session-id")
    normalized_replacement = str(replacement or "placeholder").strip().lower()
    if normalized_replacement not in {"null", "placeholder"}:
        raise ValueError("replacement must be 'null' or 'placeholder'")
    if normalized_replacement == "null":
        payload_value = refs_value = None
    else:
        payload_value = refs_value = _json_compact_dumps(EPISODIC_REDACT_PLACEHOLDER)

    scope: Optional[str]
    if normalized_event_id:
        cursor = conn.execute(
            "UPDATE episodic_events SET payload_json = ?, refs_json = ?, redacted = 1, search_text = summary WHERE event_id = ?",
            (payload_value, refs_value, normalized_event_id),
        )
        scope = None
    else:
        scope = resolve_query_scope(raw_scope, global_scope)
        cursor = conn.execute(
            "UPDATE episodic_events SET payload_json = ?, refs_json = ?, redacted = 1, search_text = summary WHERE session_id = ? AND scope = ?",
            (payload_value, refs_value, normalized_session_id, scope),
        )
    conn.commit()
    return {
        "kind": "openclaw-mem.episodes.redact.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "target": {"event_id": normalized_event_id, "session_id": normalized_session_id, "scope": scope},
        "replacement": normalized_replacement,
        "redacted_count": int(cursor.rowcount),
    }


def parse_retention_policy(raw: Optional[List[str]]) -> Dict[str, Optional[int]]:
    policy = dict(EPISODIC_DEFAULT_RETENTION_DAYS)
    if not raw:
        return policy
    for entry in raw:
        text = str(entry or "").strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError(f"invalid --policy entry: {text}")
        type_raw, days_raw = text.split("=", 1)
        event_type = normalize_type(type_raw)
        days_token = days_raw.strip().lower()
        if days_token in {"forever", "inf", "infinite", "none"}:
            policy[event_type] = None
            continue
        try:
            days = int(days_token)
        except Exception as exc:
            raise ValueError(f"invalid retention days for {event_type}: {days_raw}") from exc
        if days < 0:
            raise ValueError(f"retention days must be >= 0 for {event_type}")
        policy[event_type] = days
    return policy


def gc_events(
    conn: sqlite3.Connection,
    *,
    raw_scope: Optional[str],
    global_scope: bool,
    now_ts_ms: Any = None,
    raw_policy: Optional[List[str]] = None,
) -> Dict[str, Any]:
    scope = resolve_query_scope(raw_scope, global_scope)
    parsed_now_ts_ms = parse_ts_ms(now_ts_ms)
    policy = parse_retention_policy(raw_policy)
    deleted_by_type: Dict[str, int] = {}
    deleted_total = 0
    for event_type in sorted(EPISODIC_ALLOWED_TYPES):
        days = policy.get(event_type)
        if days is None:
            deleted_by_type[event_type] = 0
            continue
        cutoff = parsed_now_ts_ms - (int(days) * 24 * 60 * 60 * 1000)
        cursor = conn.execute(
            "DELETE FROM episodic_events WHERE scope = ? AND type = ? AND ts_ms < ?",
            (scope, event_type, int(cutoff)),
        )
        deleted = int(cursor.rowcount)
        deleted_by_type[event_type] = deleted
        deleted_total += deleted
    conn.commit()
    return {
        "kind": "openclaw-mem.episodes.gc.v0",
        "ts": utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "scope": scope,
        "now_ts_ms": parsed_now_ts_ms,
        "deleted_total": deleted_total,
        "deleted_by_type": deleted_by_type,
        "policy_days": {key: policy.get(key) for key in sorted(EPISODIC_ALLOWED_TYPES)},
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
