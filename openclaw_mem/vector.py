"""Vector utilities for openclaw-mem (Phase 3).

Design goals:
- No third-party deps
- Store vectors compactly (float32 BLOB)
- Provide cosine similarity ranking

Note: This is a minimal implementation intended for M0+/Phase 3.
"""

from __future__ import annotations

import heapq
import math
from array import array
from typing import Iterable, List, Sequence, Tuple, Dict


def pack_f32(vec: Sequence[float]) -> bytes:
    """Pack float vector into float32 bytes."""
    arr = array("f", vec)
    return arr.tobytes()


def unpack_f32(blob: bytes) -> List[float]:
    """Unpack float32 bytes into Python floats."""
    arr = array("f")
    arr.frombytes(blob)
    return list(arr)


def l2_norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum((x * x) for x in vec))


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x * y) for x, y in zip(a, b))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    na = l2_norm(a)
    nb = l2_norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot(a, b) / (na * nb)


def rank_cosine(
    *,
    query_vec: Sequence[float],
    items: Iterable[Tuple[int, bytes, float]],
    limit: int = 20,
) -> List[Tuple[int, float]]:
    """Rank (observation_id, score) by cosine similarity.

    items: iterable of (observation_id, vector_blob, vector_norm)

    Results preserve the previous full-sort ordering: score descending, with
    equal scores retaining input order. Internally this keeps only the best
    ``limit`` rows while scanning, avoiding a full scored list/full sort for
    bounded retrieval. Non-finite query norms, vector norms, or scores are
    skipped, and non-positive limits return an empty result.
    """
    q = list(query_vec)
    qn = l2_norm(q)
    if qn == 0.0 or not math.isfinite(qn) or limit <= 0:
        return []

    top: List[Tuple[float, int, int]] = []
    q_dim = len(q)
    for seq, (obs_id, blob, norm) in enumerate(items):
        if not blob or not norm:
            continue
        if norm == 0.0 or not math.isfinite(norm):
            continue

        try:
            v = unpack_f32(blob)
        except Exception:
            # Skip malformed blobs instead of failing vector retrieval.
            continue

        if len(v) != q_dim:
            # Skip stale/mismatched embeddings to prevent invalid comparisons.
            continue

        s = dot(q, v) / (qn * norm)
        score = float(s)
        if not math.isfinite(score):
            # Non-finite scores cannot be ordered safely in the bounded heap.
            continue

        entry = (score, -seq, int(obs_id))
        if len(top) < limit:
            heapq.heappush(top, entry)
        elif entry > top[0]:
            heapq.heapreplace(top, entry)

    top.sort(key=lambda x: (-x[0], -x[1]))
    return [(obs_id, score) for score, _, obs_id in top]


def rank_rrf(
    ranked_lists: Sequence[Sequence[int]],
    k: int = 60,
    limit: int = 20,
) -> List[Tuple[int, float]]:
    """Rank IDs using Reciprocal Rank Fusion (RRF).

    ranked_lists: list of lists of IDs (e.g. [fts_ids, vec_ids])
    Returns list of (id, rrf_score).
    """
    scores: Dict[int, float] = {}

    for ranking in ranked_lists:
        for rank, item_id in enumerate(ranking):
            # RRF score = 1 / (k + rank)
            # rank is 0-indexed here
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)

    # Sort deterministically: score desc, then id asc for stable ties.
    sorted_items = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return sorted_items[:limit]
