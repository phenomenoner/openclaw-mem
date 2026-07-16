"""Unified, fail-open recall routing over existing retrieval lanes."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from openclaw_mem import defaults
from openclaw_mem.core.embeddings import (
    EmbeddingProvider,
    create_embedding_provider,
    embedding_provider_name,
    get_api_key,
)
from openclaw_mem.core.search import hybrid_search_with_receipt, lexical_search_with_receipt, vector_search
from openclaw_mem.graph.search_adapter import blend_lexical_graph, graph_search_candidates
from openclaw_mem.scope import normalize_scope_token


RECALL_KIND = "openclaw-mem.recall.v1"
RECALL_MODES = frozenset({"auto", "lexical", "vector", "hybrid", "graph"})


def _stored_embedding_models(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [
        (str(row[0]), int(row[1]))
        for row in conn.execute(
            "SELECT model, COUNT(*) FROM observation_embeddings "
            "GROUP BY model ORDER BY COUNT(*) DESC, model ASC"
        ).fetchall()
    ]


def _result_lanes(results: list[Dict[str, Any]], receipt: Dict[str, Any]) -> list[str]:
    lanes: list[str] = []
    for item in results:
        for lane in item.get("lanes_used") or item.get("match") or []:
            value = "lexical" if lane == "text" else str(lane)
            if value not in lanes:
                lanes.append(value)
    for lane, count in (receipt.get("lane_hits") or {}).items():
        if int(count or 0) <= 0:
            continue
        value = {"fts_original": "lexical", "fts_en": "lexical_en", "cjk_like": "like"}.get(
            str(lane), str(lane)
        )
        if value not in lanes:
            lanes.append(value)
    return lanes


def _scope_filter(
    conn: sqlite3.Connection,
    results: list[Dict[str, Any]],
    scope: Optional[str],
) -> list[Dict[str, Any]]:
    normalized = normalize_scope_token(scope)
    ids = [int(item["id"]) for item in results if item.get("id") is not None]
    if not normalized or not ids:
        return results
    rows = conn.execute(
        f"SELECT id, json_extract(detail_json, '$.scope') FROM observations "
        f"WHERE id IN ({','.join('?' for _ in ids)})",
        ids,
    ).fetchall()
    allowed = {int(row[0]) for row in rows if normalize_scope_token(row[1]) == normalized}
    return [item for item in results if int(item.get("id", -1)) in allowed]


def _lexical(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int,
    scope: Optional[str],
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    receipt = lexical_search_with_receipt(conn, query, limit=limit, scope=scope)
    results = list(receipt.pop("results"))
    return results, receipt


def recall(
    conn: sqlite3.Connection,
    query: str,
    *,
    mode: str = "auto",
    limit: int = 20,
    scope: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    vector_backend: str = "auto",
    graph_path: Optional[str | Path] = None,
    graph_readiness_state: Optional[str | Path] = None,
    graph_stale_after_days: int = 30,
    provider_factory: Optional[Callable[..., EmbeddingProvider]] = None,
) -> Dict[str, Any]:
    """Route recall without throwing for an unavailable optional lane."""

    query_text = str(query or "").strip()
    requested = str(mode or "auto").strip().lower()
    if not query_text:
        raise ValueError("empty query")
    if requested not in RECALL_MODES:
        raise ValueError(f"unsupported recall mode: {requested}")
    bounded_limit = max(1, int(limit))
    models = _stored_embedding_models(conn)
    has_vectors = bool(models)
    provider_hint = embedding_provider_name()
    provider_configured = provider_hint == "local" or bool(get_api_key())
    selected = (
        "hybrid"
        if requested == "auto" and (has_vectors or provider_configured)
        else "lexical"
        if requested == "auto"
        else requested
    )
    routing_reason = (
        "stored_embeddings_detected"
        if requested == "auto" and has_vectors
        else "embedding_provider_configured"
        if requested == "auto" and provider_configured
        else "no_stored_embeddings"
        if requested == "auto"
        else "explicit_mode"
    )

    if selected == "graph":
        lexical_results, lexical_receipt = _lexical(
            conn, query_text, limit=bounded_limit, scope=scope
        )
        graph_receipt = (
            graph_search_candidates(
                query=query_text,
                graph_path=graph_path,
                limit=bounded_limit,
                stale_after_days=max(0, int(graph_stale_after_days)),
                readiness_state_path=graph_readiness_state,
            )
            if graph_path
            else {"ok": True, "candidates": [], "fallback_reason": "graph_path_not_provided"}
        )
        graph_results = list(graph_receipt.get("candidates") or [])
        blended_results = blend_lexical_graph(lexical_results, graph_results)
        if graph_results:
            return {
                "kind": RECALL_KIND,
                "query": query_text,
                "mode_requested": requested,
                "mode_effective": "graph",
                "lanes_used": ["graph", "lexical"],
                "results": blended_results,
                "routing_reason": "graph_candidates_available",
                "graph": graph_receipt,
                "retrieval": lexical_receipt,
            }
        return {
            "kind": RECALL_KIND,
            "query": query_text,
            "mode_requested": requested,
            "mode_effective": "lexical",
            "degraded_from": "graph",
            "lanes_used": _result_lanes(lexical_results, lexical_receipt),
            "results": blended_results,
            "routing_reason": str(graph_receipt.get("fallback_reason") or "no_graph_candidates"),
            "graph": graph_receipt,
            "retrieval": lexical_receipt,
        }

    if selected == "lexical":
        results, lexical_receipt = _lexical(conn, query_text, limit=bounded_limit, scope=scope)
        return {
            "kind": RECALL_KIND,
            "query": query_text,
            "mode_requested": requested,
            "mode_effective": "lexical",
            "lanes_used": _result_lanes(results, lexical_receipt),
            "results": results,
            "routing_reason": routing_reason,
            "retrieval": lexical_receipt,
        }

    if selected == "hybrid" and not has_vectors and requested == "auto":
        hybrid_receipt = hybrid_search_with_receipt(
            conn, query_text, limit=bounded_limit, vector_ids=[]
        )
        results = _scope_filter(conn, list(hybrid_receipt.pop("results")), scope)
        return {
            "kind": RECALL_KIND,
            "query": query_text,
            "mode_requested": requested,
            "mode_effective": "hybrid",
            "lanes_used": _result_lanes(results, hybrid_receipt),
            "results": results,
            "routing_reason": "embedding_provider_configured_no_stored_vectors",
            "retrieval": hybrid_receipt,
        }

    failure = "" if has_vectors else "no_stored_embeddings"
    provider: Optional[EmbeddingProvider] = None
    query_vector: Optional[list[float]] = None
    selected_model = str(model or (models[0][0] if models else defaults.embed_model()))
    if not failure:
        try:
            factory = provider_factory or create_embedding_provider
            provider = factory(api_key=get_api_key(), base_url=base_url, model=selected_model)
            selected_model = str(provider.model_id or selected_model)
            if not any(name == selected_model for name, _count in models):
                failure = f"no_stored_embeddings_for_model:{selected_model}"
            else:
                vectors = provider.embed([query_text], model=selected_model)
                if not vectors:
                    failure = "embedding_provider_returned_no_vector"
                else:
                    query_vector = list(vectors[0])
        except Exception as exc:
            failure = f"embedding_unavailable:{type(exc).__name__}"

    if failure or query_vector is None:
        results, lexical_receipt = _lexical(conn, query_text, limit=bounded_limit, scope=scope)
        return {
            "kind": RECALL_KIND,
            "query": query_text,
            "mode_requested": requested,
            "mode_effective": "lexical",
            "degraded_from": selected,
            "lanes_used": _result_lanes(results, lexical_receipt),
            "results": results,
            "routing_reason": failure or "vector_lane_unavailable",
            "retrieval": lexical_receipt,
        }

    try:
        vector_results = vector_search(
            conn,
            query_vector,
            model=selected_model,
            limit=max(bounded_limit * 4, bounded_limit),
            vector_backend=vector_backend,
        )
    except Exception as exc:
        vector_results = []
        failure = f"vector_index_unavailable:{type(exc).__name__}"
    vector_results = _scope_filter(conn, vector_results, scope)[:bounded_limit]
    if not vector_results and not scope:
        results, lexical_receipt = _lexical(conn, query_text, limit=bounded_limit, scope=scope)
        return {
            "kind": RECALL_KIND,
            "query": query_text,
            "mode_requested": requested,
            "mode_effective": "lexical",
            "degraded_from": selected,
            "lanes_used": _result_lanes(results, lexical_receipt),
            "results": results,
            "routing_reason": failure or "vector_index_no_compatible_rows",
            "retrieval": lexical_receipt,
        }
    if selected == "vector":
        return {
            "kind": RECALL_KIND,
            "query": query_text,
            "mode_requested": requested,
            "mode_effective": "vector",
            "lanes_used": ["vector"] if vector_results else [],
            "results": vector_results,
            "routing_reason": f"embedding_provider:{provider.provider_name}",
            "embedding_model": selected_model,
        }

    try:
        hybrid_receipt = hybrid_search_with_receipt(
            conn,
            query_text,
            limit=bounded_limit,
            vector_ids=[int(item["id"]) for item in vector_results],
        )
    except Exception as exc:
        results, lexical_receipt = _lexical(conn, query_text, limit=bounded_limit, scope=scope)
        return {
            "kind": RECALL_KIND,
            "query": query_text,
            "mode_requested": requested,
            "mode_effective": "lexical",
            "degraded_from": "hybrid",
            "lanes_used": _result_lanes(results, lexical_receipt),
            "results": results,
            "routing_reason": f"hybrid_unavailable:{type(exc).__name__}",
            "retrieval": lexical_receipt,
        }
    results = _scope_filter(conn, list(hybrid_receipt.pop("results")), scope)
    return {
        "kind": RECALL_KIND,
        "query": query_text,
        "mode_requested": requested,
        "mode_effective": "hybrid",
        "lanes_used": _result_lanes(results, hybrid_receipt),
        "results": results,
        "routing_reason": f"embedding_provider:{provider.provider_name}",
        "embedding_model": selected_model,
        "retrieval": hybrid_receipt,
    }
