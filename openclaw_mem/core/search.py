"""Output-free retrieval primitives for supported programmatic surfaces."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from openclaw_mem.scope import normalize_scope_token
from openclaw_mem.core.records import detect_lang
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


def _ascii_terms(query: str, max_terms: int = 16) -> List[str]:
    result: List[str] = []
    seen = set()
    for term in re.findall(r"[A-Za-z0-9_]+", query or ""):
        normalized = term.casefold()
        if normalized not in seen:
            seen.add(normalized)
            result.append(term)
        if len(result) >= max_terms:
            break
    return result


def _like_fallback(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    scope: Optional[str] = None,
) -> List[sqlite3.Row]:
    cjk_terms = _cjk_terms(query)
    ascii_terms = _ascii_terms(query)
    if not cjk_terms and not ascii_terms:
        return []
    predicates: List[tuple[str, str]] = []
    cjk_where: List[str] = []
    cjk_values: List[str] = []
    for term in cjk_terms:
        value = f"%{term}%"
        predicates.append(("o.summary LIKE ?", value))
        cjk_where.append("o.summary LIKE ?")
        cjk_values.append(value)
    ascii_where: List[str] = []
    ascii_values: List[str] = []
    for term in ascii_terms:
        value = f"%{term}%"
        predicates.append(("o.summary LIKE ?", value))
        predicates.append(("COALESCE(o.summary_en, '') LIKE ?", value))
        ascii_where.append(
            "(o.summary LIKE ? OR COALESCE(o.summary_en, '') LIKE ?)"
        )
        ascii_values.extend((value, value))
    score_expr = " + ".join(f"CASE WHEN {expr} THEN 1 ELSE 0 END" for expr, _ in predicates)
    score_values = [value for _, value in predicates]
    where_parts: List[str] = []
    where_values: List[str] = []
    if cjk_where:
        where_parts.append("(" + " OR ".join(cjk_where) + ")")
        where_values.extend(cjk_values)
    if ascii_where:
        # Avoid widening an English multi-token query to rows matching only a
        # common token. Mixed queries may still recover translated rows via
        # their complete ASCII subquery.
        where_parts.append("(" + " AND ".join(ascii_where) + ")")
        where_values.extend(ascii_values)
    where_expr = " OR ".join(where_parts)
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
        [*score_values, *where_values, int(limit)],
    ).fetchall()
    normalized_scope = normalize_scope_token(scope)
    if not normalized_scope:
        return rows
    result = []
    for row in rows:
        if normalize_scope_token(_parse_detail(row["detail_json"]).get("scope")) == normalized_scope:
            result.append(row)
    return result[: int(limit)]


# Compatibility name retained for callers that exercised the former private helper.
_cjk_fallback = _like_fallback


def _trigram_rows(
    conn: sqlite3.Connection, query: str, limit: int
) -> List[sqlite3.Row]:
    phrase = '"' + str(query).replace('"', '""') + '"'
    return conn.execute(
        """
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               snippet(observations_fts_tri, 0, '[', ']', '…', 12) AS snippet,
               snippet(observations_fts_tri, 1, '[', ']', '…', 12) AS snippet_en,
               bm25(observations_fts_tri) AS score, o.detail_json
        FROM observations_fts_tri
        JOIN observations o ON o.id = observations_fts_tri.rowid
        WHERE observations_fts_tri MATCH ?
        ORDER BY score ASC, o.id DESC
        LIMIT ?
        """,
        (phrase, int(limit)),
    ).fetchall()


def _fallback_threshold() -> float:
    raw = os.environ.get("OPENCLAW_MEM_FTS_FALLBACK_BM25_THRESHOLD", "0.25")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.25


def _should_run_fallback(rows: List[sqlite3.Row], limit: int) -> bool:
    if len(rows) >= limit:
        return False
    if not rows:
        return True
    try:
        top_score = abs(float(rows[0]["score"]))
    except (KeyError, TypeError, ValueError):
        return True
    return top_score < _fallback_threshold()


def _fuse_rows(
    lane_rows: Dict[str, List[Mapping[str, Any]]], limit: int
) -> List[Mapping[str, Any]]:
    populated = [(name, rows) for name, rows in lane_rows.items() if rows]
    if not populated:
        return []
    if len(populated) == 1:
        return populated[0][1][:limit]
    row_maps = [{int(row["id"]): row for row in rows} for _, rows in populated]
    fused = rank_rrf([list(row_map) for row_map in row_maps], limit=limit)
    return [
        next(row_map[row_id] for row_map in row_maps if row_id in row_map)
        for row_id, _score in fused
    ]


def _mixed_fts_query(query: str, ascii_terms: List[str]) -> str:
    phrase = '"' + query.replace('"', '""') + '"'
    if not ascii_terms:
        return phrase
    return f"({phrase}) OR (" + " OR ".join(ascii_terms) + ")"


def _lexical_search_impl(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    scope: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    query_text = str(query or "").strip()
    if not query_text:
        raise ValueError("empty query")
    bounded_limit = max(1, int(limit))
    def run_fts(value: str) -> List[Mapping[str, Any]]:
        candidate_cap = max(512, bounded_limit * 32)
        candidates = conn.execute(
            "SELECT rowid AS id, rank AS score FROM observations_fts "
            "WHERE observations_fts MATCH ? LIMIT ?",
            (value, candidate_cap),
        ).fetchall()
        ranked = sorted(
            candidates,
            key=lambda row: (float(row["score"]), int(row["id"])),
        )[:bounded_limit]
        if not ranked:
            return []
        ranked_ids = [int(row["id"]) for row in ranked]
        placeholders = ",".join("?" for _ in ranked_ids)
        content_rows = conn.execute(
            "SELECT id, ts, kind, tool_name, summary, summary_en, lang, detail_json "
            f"FROM observations WHERE id IN ({placeholders})",
            ranked_ids,
        ).fetchall()
        content = {int(row["id"]): dict(row) for row in content_rows}
        results: List[Mapping[str, Any]] = []
        for ranked_row in ranked:
            row_id = int(ranked_row["id"])
            item = dict(content[row_id])
            item["snippet"] = item.get("summary")
            item["snippet_en"] = item.get("summary_en")
            item["score"] = float(ranked_row["score"])
            results.append(item)
        return results

    cjk_runs = re.findall(r"[\u3400-\u9fff]+", query_text)
    has_cjk = bool(cjk_runs)
    has_ascii = bool(re.search(r"[A-Za-z0-9]", query_text))
    trigram_exists = bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'observations_fts_tri'"
        ).fetchone()
    )
    lane_rows: Dict[str, List[Mapping[str, Any]]] = {}
    attempted_lanes: List[str] = []
    fallback_triggered = False
    ascii_terms = _ascii_terms(query_text)

    if has_cjk and len(query_text) < 3:
        attempted_lanes.append("cjk_like")
        lane_rows["cjk_like"] = _like_fallback(
            conn, query_text, bounded_limit, scope=scope
        )
        fallback_triggered = True
    elif has_cjk and trigram_exists:
        attempted_lanes.append("trigram")
        try:
            trigram_rows = _trigram_rows(conn, query_text, bounded_limit)
        except sqlite3.OperationalError:
            trigram_rows = []
        lane_rows["trigram"] = trigram_rows
        if has_ascii:
            attempted_lanes.append("fts_original")
            try:
                unicode_rows = run_fts(_mixed_fts_query(query_text, ascii_terms))
            except sqlite3.OperationalError:
                try:
                    unicode_rows = run_fts(" OR ".join(ascii_terms)) if ascii_terms else []
                except sqlite3.OperationalError:
                    unicode_rows = []
            lane_rows["fts_original"] = unicode_rows
    else:
        attempted_lanes.append("fts_original")
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
        lane_rows["fts_original"] = rows

    rows = _fuse_rows(lane_rows, bounded_limit)
    if "cjk_like" not in attempted_lanes and _should_run_fallback(rows, bounded_limit):
        fallback_triggered = True
        attempted_lanes.append("cjk_like")
        lane_rows["cjk_like"] = _like_fallback(
            conn, query_text, bounded_limit, scope=scope
        )
        rows = _fuse_rows(lane_rows, bounded_limit)

    normalized_scope = normalize_scope_token(scope)
    detail_map = {int(row["id"]): _parse_detail(row["detail_json"]) for row in rows}
    superseded = _superseded_ids(detail_map)
    result: List[Dict[str, Any]] = []
    legacy_lane_names = {
        "fts_original": "unicode61",
        "trigram": "trigram",
        "cjk_like": "like",
    }
    lanes_used = [legacy_lane_names[name] for name in attempted_lanes]
    for row in rows:
        item = dict(row)
        item["lanes_used"] = list(lanes_used)
        detail = detail_map.get(int(item["id"]), {})
        item.pop("detail_json", None)
        if normalized_scope and normalize_scope_token(detail.get("scope")) != normalized_scope:
            continue
        if int(item["id"]) in superseded or detail.get("superseded_by") or detail.get("supersededBy"):
            continue
        result.append(item)
        if len(result) >= bounded_limit:
            break

    result_ids = {int(item["id"]) for item in result}
    lane_hits = {
        "fts_original": len(
            result_ids.intersection(int(row["id"]) for row in lane_rows.get("fts_original", []))
        ),
        "fts_en": 0,
        "cjk_like": len(
            result_ids.intersection(int(row["id"]) for row in lane_rows.get("cjk_like", []))
        ),
        "trigram": len(
            result_ids.intersection(int(row["id"]) for row in lane_rows.get("trigram", []))
        ),
        "vector": 0,
        "vector_en": 0,
    }
    fts_ids = {int(row["id"]) for row in lane_rows.get("fts_original", [])}
    cross_lang_recovered = 0
    for item in result:
        summary = str(item.get("summary") or "").casefold()
        summary_en = str(item.get("summary_en") or "").casefold()
        en_hit = bool(ascii_terms) and any(term.casefold() in summary_en for term in ascii_terms)
        original_hit = any(term.casefold() in summary for term in ascii_terms)
        if int(item["id"]) in fts_ids and en_hit:
            lane_hits["fts_en"] += 1
        if detect_lang(query_text) in {"zh", "mixed"} and en_hit and not original_hit:
            cross_lang_recovered += 1
    receipt = {
        "kind": "openclaw-mem.search.receipt.v1",
        "query_lang": detect_lang(query_text),
        "lane_hits": lane_hits,
        "fallback_triggered": fallback_triggered,
        "cross_lang_recovered": cross_lang_recovered,
        "result_count": len(result),
    }
    return result, receipt


def lexical_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    scope: Optional[str] = None,
) -> List[Dict[str, Any]]:
    results, _receipt = _lexical_search_impl(conn, query, limit=limit, scope=scope)
    return results


def lexical_search_with_receipt(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    results, receipt = _lexical_search_impl(conn, query, limit=limit, scope=scope)
    return {**receipt, "results": results}


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


def _hybrid_search_impl(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    vector_ids: Optional[List[int]] = None,
    vector_en_ids: Optional[List[int]] = None,
    k: int = 60,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lexical_receipt = lexical_search_with_receipt(
        conn, query, limit=max(1, int(limit)) * 2
    )
    lexical = list(lexical_receipt.pop("results"))
    fts_ids = [int(item["id"]) for item in lexical]
    ranked = rank_rrf([fts_ids, vector_ids or [], vector_en_ids or []], k=max(1, int(k)), limit=max(1, int(limit)))
    if not ranked:
        return [], lexical_receipt
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
    selected_ids = {int(item["id"]) for item in result}
    lane_hits = dict(lexical_receipt.get("lane_hits") or {})
    lane_hits["vector"] = len(selected_ids.intersection(vector_ids or []))
    lane_hits["vector_en"] = len(selected_ids.intersection(vector_en_ids or []))
    receipt = {**lexical_receipt, "lane_hits": lane_hits, "result_count": len(result)}
    for item in result:
        item.update(
            {
                key: receipt[key]
                for key in (
                    "query_lang",
                    "lane_hits",
                    "fallback_triggered",
                    "cross_lang_recovered",
                )
            }
        )
    return result, receipt


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    vector_ids: Optional[List[int]] = None,
    vector_en_ids: Optional[List[int]] = None,
    k: int = 60,
) -> List[Dict[str, Any]]:
    results, _receipt = _hybrid_search_impl(
        conn,
        query,
        limit=limit,
        vector_ids=vector_ids,
        vector_en_ids=vector_en_ids,
        k=k,
    )
    return results


def hybrid_search_with_receipt(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    vector_ids: Optional[List[int]] = None,
    vector_en_ids: Optional[List[int]] = None,
    k: int = 60,
) -> Dict[str, Any]:
    results, receipt = _hybrid_search_impl(
        conn,
        query,
        limit=limit,
        vector_ids=vector_ids,
        vector_en_ids=vector_en_ids,
        k=k,
    )
    return {**receipt, "results": results}
