"""Output-free ContextPack construction for programmatic and transport surfaces."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openclaw_mem import defaults
from openclaw_mem import context_pack_v1
from openclaw_mem.core.embeddings import OpenAIEmbeddingsClient, get_api_key
from openclaw_mem.core.search import hybrid_search, lexical_search, vector_search
from openclaw_mem.core.vector_index import create_vector_index


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def _metadata(conn: sqlite3.Connection, ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT id, detail_json FROM observations WHERE id IN ({','.join(['?'] * len(ids))})",
        ids,
    ).fetchall()
    result: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        try:
            value = json.loads(row["detail_json"] or "{}")
        except Exception:
            value = {}
        result[int(row["id"])] = value if isinstance(value, dict) else {}
    return result


def build_pack(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 8,
    budget_tokens: int = 1200,
    scope: Optional[str] = None,
    query_en: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    vector_backend: str = "auto",
) -> Dict[str, Any]:
    query_text = str(query or "").strip()
    if not query_text:
        raise ValueError("empty query")
    bounded_limit = max(1, int(limit))
    bounded_budget = max(1, int(budget_tokens))
    candidate_limit = max(bounded_limit * 3, bounded_limit + 8)
    candidates = lexical_search(
        conn,
        query_text,
        limit=candidate_limit,
        scope=scope,
    )
    model_name = str(model or defaults.embed_model())
    vector_ids: List[int] = []
    vector_en_ids: List[int] = []
    actual_vector_backend = create_vector_index(vector_backend).name
    has_vectors = conn.execute(
        "SELECT 1 FROM observation_embeddings WHERE model = ? LIMIT 1", (model_name,)
    ).fetchone() is not None
    api_key = get_api_key()
    if has_vectors and api_key:
        try:
            inputs = [query_text] + ([query_en] if query_en else [])
            vectors = OpenAIEmbeddingsClient(api_key, base_url).embed(inputs, model=model_name)
            vector_ids = [
                int(item["id"])
                for item in vector_search(
                    conn,
                    vectors[0],
                    model=model_name,
                    limit=candidate_limit,
                    vector_backend=actual_vector_backend,
                )
            ]
            if query_en and len(vectors) > 1:
                english_rows = vector_search(
                    conn,
                    vectors[1],
                    model=model_name,
                    limit=candidate_limit,
                    table="observation_embeddings_en",
                    vector_backend=actual_vector_backend,
                )
                if not english_rows:
                    english_rows = vector_search(
                        conn,
                        vectors[1],
                        model=model_name,
                        limit=candidate_limit,
                        vector_backend=actual_vector_backend,
                    )
                vector_en_ids = [int(item["id"]) for item in english_rows]
            candidates = hybrid_search(
                conn,
                query_text,
                limit=candidate_limit,
                vector_ids=vector_ids,
                vector_en_ids=vector_en_ids,
            )
        except Exception:
            # Embedding/network failures are fail-open to the lexical lane.
            vector_ids = []
            vector_en_ids = []
    detail_map = _metadata(conn, [int(item["id"]) for item in candidates])
    importance_rank = {"must_remember": 0, "nice_to_have": 1, "ignore": 2, "unknown": 3}
    trust_rank = {"trusted": 0, "verified": 0, "unknown": 1, "untrusted": 2, "quarantined": 3}

    def candidate_text(item: Dict[str, Any], detail: Dict[str, Any]) -> str:
        if str(detail.get("schema") or "") == "openclaw-mem.artifact.compaction-receipt.v1":
            compact = detail.get("compact") if isinstance(detail.get("compact"), dict) else {}
            compact_text = str(compact.get("text") or "").replace("\n", " ").strip()
            if compact_text:
                return compact_text
        return str(item.get("summary_en") or item.get("summary") or "").replace("\n", " ").strip()

    def importance_label(detail: Dict[str, Any]) -> str:
        importance = detail.get("importance")
        if isinstance(importance, dict):
            label = str(importance.get("label") or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
        else:
            label = str(detail.get("importance_label") or importance or "unknown").strip().lower()
        return {"high": "must_remember", "medium": "nice_to_have", "low": "ignore"}.get(label, label)

    candidates.sort(
        key=lambda item: (
            0 if item.get("tool_name") == "graph.synth-compile" else 1,
            trust_rank.get(str(detail_map.get(int(item["id"]), {}).get("trust") or "unknown"), 99),
            importance_rank.get(importance_label(detail_map.get(int(item["id"]), {})), 99),
            -float(item.get("rrf_score") or 0.0),
            -int(item.get("id") or 0),
        )
    )
    selected_items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    context_items: List[context_pack_v1.ContextPackV1Item] = []
    used_tokens = 0
    for candidate in candidates:
        if len(selected_items) >= bounded_limit:
            break
        row_id = int(candidate["id"])
        detail = detail_map.get(row_id, {})
        text = candidate_text(candidate, detail)
        if not text:
            continue
        token_estimate = _estimate_tokens(text)
        if used_tokens + token_estimate > bounded_budget:
            continue
        record_ref = f"obs:{row_id}"
        trust = str(detail.get("trust") or detail.get("trust_tier") or "unknown")
        if bool(detail.get("quarantined") or detail.get("quarantine")):
            continue
        importance = importance_label(detail)
        used_tokens += token_estimate
        selected_items.append(
            {
                "recordRef": record_ref,
                "layer": "L1",
                "id": row_id,
                "summary": text,
                "kind": candidate.get("kind"),
                "lang": candidate.get("lang"),
            }
        )
        citations.append({"recordRef": record_ref, "url": None})
        context_items.append(
            context_pack_v1.ContextPackV1Item(
                recordRef=record_ref,
                layer="L1",
                type="memory",
                importance=importance,
                trust=trust,
                text=text,
                citations=context_pack_v1.ContextPackV1ItemCitations(url=None, recordRef=record_ref),
            )
        )
    bundle_text = "\n".join(f"- [{item['recordRef']}] {item['summary']}" for item in selected_items)
    context_pack = context_pack_v1.ContextPackV1(
        schema=context_pack_v1.CONTEXT_PACK_V1_SCHEMA,
        meta=context_pack_v1.ContextPackV1Meta(
            ts=_utcnow_iso(),
            query=query_text,
            scope=scope,
            budgetTokens=bounded_budget,
            maxItems=bounded_limit,
        ),
        bundle_text=bundle_text,
        items=context_items,
        notes=context_pack_v1.ContextPackV1Notes(
            how_to_use=[
                "Prefer bundle_text for direct injection.",
                "Use items[].recordRef as the citation key.",
                "If you need detail, retrieve L2 by recordRef in a bounded follow-up.",
            ]
        ),
    )
    return {
        "bundle_text": bundle_text,
        "items": selected_items,
        "citations": citations,
        "context_pack": context_pack_v1.to_dict(context_pack),
        "budget": {
            "budgetTokens": bounded_budget,
            "estimatedTokens": used_tokens,
            "maxItems": bounded_limit,
            "includedItems": len(selected_items),
        },
        "vector_backend": actual_vector_backend,
    }
