"""Output-free ContextPack construction for programmatic and transport surfaces."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openclaw_mem import context_pack_v1
from openclaw_mem.core.search import lexical_search


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
) -> Dict[str, Any]:
    query_text = str(query or "").strip()
    if not query_text:
        raise ValueError("empty query")
    bounded_limit = max(1, int(limit))
    bounded_budget = max(1, int(budget_tokens))
    candidates = lexical_search(
        conn,
        query_text,
        limit=max(bounded_limit * 3, bounded_limit + 8),
        scope=scope,
    )
    detail_map = _metadata(conn, [int(item["id"]) for item in candidates])
    selected_items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    context_items: List[context_pack_v1.ContextPackV1Item] = []
    used_tokens = 0
    for candidate in candidates:
        if len(selected_items) >= bounded_limit:
            break
        text = str(candidate.get("summary") or "").strip()
        if not text:
            continue
        token_estimate = _estimate_tokens(text)
        if used_tokens + token_estimate > bounded_budget:
            continue
        row_id = int(candidate["id"])
        record_ref = f"obs:{row_id}"
        detail = detail_map.get(row_id, {})
        trust = str(detail.get("trust") or detail.get("trust_tier") or "unknown")
        if bool(detail.get("quarantined") or detail.get("quarantine")):
            continue
        importance = str(detail.get("importance_label") or detail.get("importance") or "unknown")
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
    }
