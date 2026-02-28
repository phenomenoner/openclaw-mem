#!/usr/bin/env python3
"""Simple Hit@K benchmark harness for openclaw-mem docs search.

Input JSONL format (one query per line):
  {"query": "hybrid retrieval", "expects": ["doc:repo:path#chunk"], "k": 5}

- `expects` accepts either recordRef values or path fragments (substring match).
- Optional `k` overrides default --k-per-query for this row.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def _run_search(db: str, query: str, top_k: int) -> List[Dict[str, Any]]:
    cmd = [
        "openclaw-mem",
        "--db",
        db,
        "docs",
        "search",
        query,
        "--limit",
        str(top_k),
        "--json",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "docs search failed").strip())
    payload = json.loads(p.stdout or "{}")
    return list(payload.get("results") or [])


def _matches(expect: str, results: List[Dict[str, Any]]) -> bool:
    expect = (expect or "").strip()
    if not expect:
        return False

    for row in results:
        ref = str(row.get("recordRef") or "")
        path = str(row.get("path") or "")
        if expect == ref:
            return True
        if expect in ref or expect in path:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute Hit@K for docs search on a JSONL query set")
    ap.add_argument("--db", required=True, help="SQLite DB path")
    ap.add_argument("--queries", required=True, help="JSONL file path")
    ap.add_argument("--k-per-query", type=int, default=5, help="Top-K used when row has no explicit k (default: 5)")
    args = ap.parse_args()

    qpath = Path(args.queries)
    if not qpath.exists():
        print(json.dumps({"error": "queries file not found", "path": str(qpath)}, ensure_ascii=False), file=sys.stderr)
        return 2

    rows = []
    with qpath.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            s = raw.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception as e:
                print(json.dumps({"error": "invalid jsonl", "line": line_no, "detail": str(e)}, ensure_ascii=False), file=sys.stderr)
                return 2
            rows.append(obj)

    if not rows:
        print(json.dumps({"error": "empty query set"}, ensure_ascii=False), file=sys.stderr)
        return 2

    total = 0
    hit = 0
    details = []

    for i, row in enumerate(rows, start=1):
        q = str(row.get("query") or "").strip()
        expects = row.get("expects") or []
        if isinstance(expects, str):
            expects = [expects]
        expects = [str(x) for x in expects if str(x).strip()]
        if not q or not expects:
            continue

        top_k = int(row.get("k") or args.k_per_query)
        top_k = max(1, top_k)

        results = _run_search(args.db, q, top_k)
        ok = any(_matches(exp, results) for exp in expects)

        total += 1
        if ok:
            hit += 1

        details.append(
            {
                "idx": i,
                "query": q,
                "expects": expects,
                "hit": ok,
                "top": [str(r.get("recordRef") or "") for r in results[:top_k]],
            }
        )

    payload = {
        "kind": "openclaw-mem.docs.benchmark.hitk.v0",
        "db": args.db,
        "queries": str(qpath),
        "total": total,
        "hit": hit,
        "hit_at_k": (float(hit) / float(total)) if total else 0.0,
        "details": details,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
