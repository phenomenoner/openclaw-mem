"""Vector utilities for openclaw-mem (Phase 3).

Design goals:
- No third-party deps
- Store vectors compactly (float32 BLOB)
- Provide cosine similarity ranking

Note: This is a minimal implementation intended for M0+/Phase 3.
"""

from __future__ import annotations

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
    """
    q = list(query_vec)
    qn = l2_norm(q)
    if qn == 0.0:
        return []

    scored: List[Tuple[int, float]] = []
    for obs_id, blob, norm in items:
        if not blob or not norm:
            continue
        if norm == 0.0:
            continue
        v = unpack_f32(blob)
        s = dot(q, v) / (qn * norm)
        scored.append((obs_id, float(s)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def rank_rrf(
    *,
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

    # Sort by score descending
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_items[:limit]
