#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def fail(code: str, message: str, **extra: object) -> int:
    print(json.dumps({"ok": False, "errorCode": code, "error": message, **extra}, ensure_ascii=False, separators=(",", ":")))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild an OpenClaw mem-engine Qdrant Edge shard from JSONL rows on stdin.")
    ap.add_argument("--shard-root", required=True)
    ap.add_argument("--vector-name", default="text")
    ap.add_argument("--vector-dim", type=int, default=1536)
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    if args.vector_dim <= 0:
        return fail("invalid_vector_dim", "vector dimension must be > 0")

    try:
        import qdrant_edge as q  # type: ignore
    except Exception as exc:
        return fail("dependency_unavailable", f"qdrant-edge dependency unavailable: {type(exc).__name__}: {exc}")

    shard_root = Path(args.shard_root).expanduser()
    if args.replace and shard_root.exists():
        shutil.rmtree(shard_root)
    shard_root.mkdir(parents=True, exist_ok=True)

    rows = []
    skipped = 0
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            skipped += 1
            continue
        vector = item.get("vector")
        if not isinstance(vector, list) or len(vector) != args.vector_dim:
            skipped += 1
            continue
        rows.append(item)

    cfg = q.EdgeConfig(vectors={args.vector_name: q.EdgeVectorParams(size=args.vector_dim, distance=q.Distance.Cosine)})
    shard = q.EdgeShard.create(str(shard_root), cfg)
    points = []
    try:
        for field in ("id", "scope", "importance_label", "category", "trust_tier"):
            try:
                shard.update(q.UpdateOperation.create_field_index(field, q.PayloadSchemaType.Keyword))
            except Exception:
                pass

        for idx, item in enumerate(rows, start=1):
            payload = {
                "id": str(item.get("id") or ""),
                "text": str(item.get("text") or ""),
                "createdAt": int(item.get("createdAt") or 0),
                "category": str(item.get("category") or "other"),
                "importance": item.get("importance"),
                "importance_label": str(item.get("importance_label") or ""),
                "scope": str(item.get("scope") or ""),
                "trust_tier": str(item.get("trust_tier") or ""),
            }
            if not payload["id"] or payload["id"] == "__schema__":
                skipped += 1
                continue
            points.append(q.Point(id=idx, vector={args.vector_name: [float(x) for x in item["vector"]]}, payload=payload))

        if points:
            shard.update(q.UpdateOperation.upsert_points(points))
            try:
                shard.flush()
            except Exception:
                pass
        info = shard.info()
        points_count = getattr(info, "points_count", len(points))
    finally:
        try:
            shard.close()
        except Exception:
            pass

    print(json.dumps({
        "ok": True,
        "backend": "qdrant-edge",
        "shardRoot": str(shard_root),
        "vectorName": args.vector_name,
        "vectorDim": args.vector_dim,
        "inputRows": len(rows),
        "stored": len(points),
        "skipped": skipped,
        "pointsCount": points_count,
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
