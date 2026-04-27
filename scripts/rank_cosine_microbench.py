#!/usr/bin/env python3
"""Synthetic rank_cosine microbench receipt helper.

Usage:
  uv run --python 3.13 -- python scripts/rank_cosine_microbench.py
  uv run --python 3.13 -- python scripts/rank_cosine_microbench.py --sizes 1000 10000

Prints JSON with elapsed time for bounded top-k ranking. This is intentionally
not part of the test suite so the 100k receipt does not slow normal CI runs.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openclaw_mem.vector import l2_norm, pack_f32, rank_cosine  # noqa: E402


def _git_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:
        return None


def _items(count: int, dim: int):
    for idx in range(count):
        vec = [float(((idx + 1) * (j + 3)) % 29) / 29.0 for j in range(dim)]
        yield (idx, pack_f32(vec), l2_norm(vec))


def main() -> int:
    parser = argparse.ArgumentParser(description="rank_cosine synthetic bounded-top-k microbench")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 10_000, 100_000])
    parser.add_argument("--dim", type=int, default=16)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    query_vec = [float((j * 7) % 31) / 31.0 for j in range(args.dim)]
    runs = []
    for size in args.sizes:
        start = time.perf_counter()
        ranked = rank_cosine(query_vec=query_vec, items=_items(size, args.dim), limit=args.limit)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        runs.append(
            {
                "candidates": size,
                "dim": args.dim,
                "limit": args.limit,
                "elapsed_ms": round(elapsed_ms, 3),
                "result_count": len(ranked),
                "top_ids": [rid for rid, _ in ranked[:5]],
                "top_score": ranked[0][1] if ranked else None,
            }
        )

    print(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "git_sha": _git_sha(),
                "python": platform.python_version(),
                "runs": runs,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
