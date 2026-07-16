"""Output-free retrieval primitives for supported programmatic surfaces."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from openclaw_mem.scope import normalize_scope_token
from openclaw_mem.core.vector_index import create_vector_index
from openclaw_mem.vector import rank_rrf


def _parse_detail(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _supersede_ref_to_id(raw: Any) -> Optional[int]:
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw if raw > 0 else None
    if not isinstance(raw, str):
        return None
    match = re.fullmatch(r"(?:obs:)?(\d+)", raw.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    value = int(match.group(1))
    return value if value > 0 else None


def _superseded_ids(detail_map: Dict[int, Dict[str, Any]]) -> set[int]:
    result: set[int] = set()
    for detail in detail_map.values():
        provenance = detail.get("provenance")
        if not isinstance(provenance, dict):
            continue
        raw_refs = provenance.get("supersedes")
        if isinstance(raw_refs, (str, int)) and not isinstance(raw_refs, bool):
            values = [raw_refs]
        elif isinstance(raw_refs, list):
            values = raw_refs
        else:
            continue
        for raw in values:
            row_id = _supersede_ref_to_id(raw)
            if row_id is not None:
                result.add(row_id)
    return result


def _cjk_terms(query: str, max_terms: int = 16) -> List[str]:
    terms: List[str] = []
    for run in re.findall(r"[\u3400-\u9fff]+", query or ""):
        if len(run) < 2:
            continue
        terms.append(run)
        if len(run) > 2:
            terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    result: List[str] = []
    seen = set()
    for term in terms:
        if term not in seen:
            seen.add(term)
            result.append(term)
        if len(result) >= max_terms:
            break
    return result


def _cjk_fallback(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    scope: Optional[str] = None,
) -> List[sqlite3.Row]:
    terms = _cjk_terms(query)
    if not terms:
        return []
    values = [f"%{term}%" for term in terms]
    score_expr = " + ".join("CASE WHEN o.summary LIKE ? THEN 1 ELSE 0 END" for _ in values)
    where_expr = " OR ".join("o.summary LIKE ?" for _ in values)
    rows = conn.execute(
        f"""
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               o.summary AS snippet, o.summary_en AS snippet_en,
               -1.0 * ({score_expr}) AS score, o.detail_json
        FROM observations o
        WHERE ({where_expr})
        ORDER BY score ASC, o.id DESC
        LIMIT ?
        """,
        [*values, *values, int(limit)],
    ).fetchall()
    normalized_scope = normalize_scope_token(scope)
    if not normalized_scope:
        return rows
    result = []
    for row in rows:
        if normalize_scope_token(_parse_detail(row["detail_json"]).get("scope")) == normalized_scope:
            result.append(row)
    return result[: int(limit)]


def lexical_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    scope: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query_text = str(query or "").strip()
    if not query_text:
        raise ValueError("empty query")
    bounded_limit = max(1, int(limit))
    sql = """
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               snippet(observations_fts, 0, '[', ']', '…', 12) AS snippet,
               snippet(observations_fts, 1, '[', ']', '…', 12) AS snippet_en,
               bm25(observations_fts) AS score, o.detail_json
        FROM observations_fts
        JOIN observations o ON o.id = observations_fts.rowid
        WHERE observations_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
    """

    def run_fts(value: str) -> List[sqlite3.Row]:
        return conn.execute(sql, (value, bounded_limit)).fetchall()

    try:
        rows = run_fts(query_text)
    except sqlite3.OperationalError:
        sanitized = " ".join(re.sub(r"[^\w\s]", " ", query_text, flags=re.UNICODE).split())
        try:
            rows = run_fts(sanitized) if sanitized and sanitized != query_text else []
        except sqlite3.OperationalError:
            rows = []
    if not rows:
        tokens = [token for token in re.sub(r"[^\w\s]", " ", query_text, flags=re.UNICODE).split() if token]
        if len(tokens) > 1:
            try:
                rows = run_fts(" OR ".join(tokens))
            except sqlite3.OperationalError:
                rows = []
    if not rows and _cjk_terms(query_text):
        rows = _cjk_fallback(conn, query_text, bounded_limit, scope=scope)

    normalized_scope = normalize_scope_token(scope)
    detail_map = {int(row["id"]): _parse_detail(row["detail_json"]) for row in rows}
    superseded = _superseded_ids(detail_map)
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        detail = detail_map.get(int(item["id"]), {})
        item.pop("detail_json", None)
        if normalized_scope and normalize_scope_token(detail.get("scope")) != normalized_scope:
            continue
        if int(item["id"]) in superseded or detail.get("superseded_by") or detail.get("supersededBy"):
            continue
        result.append(item)
        if len(result) >= bounded_limit:
            break
    return result


def vector_search(
    conn: sqlite3.Connection,
    query_vector: List[float],
    *,
    model: str,
    limit: int = 20,
    table: str = "observation_embeddings",
    vector_backend: str = "auto",
) -> List[Dict[str, Any]]:
    if table not in {"observation_embeddings", "observation_embeddings_en"}:
        raise ValueError("unsupported embeddings table")
    index = create_vector_index(vector_backend)
    ranked = index.search(
        conn,
        query_vector,
        model=model,
        limit=max(1, int(limit)),
        table=table,
    )
    if not ranked:
        return []
    ids = [row_id for row_id, _ in ranked]
    observations = conn.execute(
        f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?'] * len(ids))})",
        ids,
    ).fetchall()
    observation_map = {int(row["id"]): dict(row) for row in observations}
    result = []
    for row_id, score in ranked:
        item = observation_map.get(row_id)
        if item:
            item["score"] = float(score)
            item["vector_backend"] = index.name
            result.append(item)
    return result


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    vector_ids: Optional[List[int]] = None,
    vector_en_ids: Optional[List[int]] = None,
    k: int = 60,
) -> List[Dict[str, Any]]:
    lexical = lexical_search(conn, query, limit=max(1, int(limit)) * 2)
    fts_ids = [int(item["id"]) for item in lexical]
    ranked = rank_rrf([fts_ids, vector_ids or [], vector_en_ids or []], k=max(1, int(k)), limit=max(1, int(limit)))
    if not ranked:
        return []
    lexical_map = {int(item["id"]): dict(item) for item in lexical}
    missing = [row_id for row_id, _ in ranked if row_id not in lexical_map]
    if missing:
        for row in conn.execute(
            f"SELECT id, ts, kind, tool_name, summary, summary_en, lang FROM observations WHERE id IN ({','.join(['?'] * len(missing))})",
            missing,
        ).fetchall():
            lexical_map[int(row["id"])] = dict(row)
    result = []
    for row_id, score in ranked:
        item = lexical_map.get(row_id)
        if not item:
            continue
        item["rrf_score"] = float(score)
        item["match"] = [
            lane
            for lane, present in (
                ("text", row_id in fts_ids),
                ("vector", row_id in set(vector_ids or [])),
                ("vector_en", row_id in set(vector_en_ids or [])),
            )
            if present
        ]
        result.append(item)
    return result
