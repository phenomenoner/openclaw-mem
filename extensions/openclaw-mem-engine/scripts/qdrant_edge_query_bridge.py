#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def fail(code: str, message: str, **extra: object) -> int:
    return emit({"ok": False, "errorCode": code, "error": message, **extra})


def main() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except Exception as exc:
        return fail("invalid_request_json", f"invalid request JSON: {type(exc).__name__}")

    shard_root = Path(str(req.get("shardRoot") or "")).expanduser()
    vector_name = str(req.get("vectorName") or "text")
    vector = req.get("vector")
    limit = int(req.get("limit") or 10)
    scope = req.get("scope")
    labels = req.get("labels") if isinstance(req.get("labels"), list) else []

    if not shard_root.exists():
        return fail("missing_shard", "qdrant-edge shard root does not exist", shardRoot=str(shard_root))
    if not isinstance(vector, list) or not vector:
        return fail("missing_vector", "qdrant-edge bridge requires vector search input")

    try:
        import qdrant_edge as q  # type: ignore
    except Exception as exc:
        return fail("dependency_unavailable", f"qdrant-edge dependency unavailable: {type(exc).__name__}: {exc}")

    try:
        shard = q.EdgeShard.load(str(shard_root))
    except Exception as exc:
        return fail("shard_load_failed", f"failed to load qdrant-edge shard: {type(exc).__name__}: {exc}")

    must = []
    if scope:
        must.append(q.FieldCondition(key="scope", match=q.MatchValue(value=str(scope))))
    if labels:
        # Qdrant payload may store importance_label as a keyword. For multiple labels,
        # query without label filter and post-filter below to avoid depending on optional
        # `should` API differences between qdrant-edge-py versions.
        pass

    try:
        req_obj = q.QueryRequest(
            query=q.Query.Nearest([float(x) for x in vector], using=vector_name),
            filter=q.Filter(must=must) if must else None,
            limit=max(1, min(100, limit * 4 if labels else limit)),
            with_vector=False,
            with_payload=True,
        )
        rows = shard.query(req_obj)
    except Exception as exc:
        return fail("query_failed", f"qdrant-edge query failed: {type(exc).__name__}: {exc}")
    finally:
        try:
            shard.close()
        except Exception:
            pass

    label_set = {str(x) for x in labels}
    hits = []
    for row in rows:
        payload = dict(getattr(row, "payload", {}) or {})
        if label_set and str(payload.get("importance_label") or "") not in label_set:
            continue
        hits.append({
            "id": str(payload.get("id") or getattr(row, "id", "")),
            "score": float(getattr(row, "score", 0.0) or 0.0),
            "distance": 0,
            "row": {
                "id": str(payload.get("id") or getattr(row, "id", "")),
                "text": str(payload.get("text") or ""),
                "createdAt": int(payload.get("createdAt") or 0),
                "category": str(payload.get("category") or "other"),
                "importance": payload.get("importance"),
                "importance_label": str(payload.get("importance_label") or ""),
                "scope": str(payload.get("scope") or ""),
                "trust_tier": str(payload.get("trust_tier") or ""),
            },
        })
        if len(hits) >= limit:
            break

    return emit({"ok": True, "hits": hits, "receipt": {"backend": "qdrant-edge", "shardRoot": str(shard_root), "returned": len(hits)}})


if __name__ == "__main__":
    raise SystemExit(main())
