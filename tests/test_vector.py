import math
import time
import unittest

from openclaw_mem.vector import dot, pack_f32, unpack_f32, l2_norm, cosine_similarity, rank_cosine, rank_rrf


def _rank_cosine_full_sort_baseline(*, query_vec, items, limit=20):
    """Previous rank_cosine implementation for finite-score golden tests."""
    q = list(query_vec)
    qn = l2_norm(q)
    if qn == 0.0:
        return []

    scored = []
    q_dim = len(q)
    for obs_id, blob, norm in items:
        if not blob or not norm:
            continue
        if norm == 0.0:
            continue

        try:
            v = unpack_f32(blob)
        except Exception:
            continue

        if len(v) != q_dim:
            continue

        scored.append((obs_id, float(dot(q, v) / (qn * norm))))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


class TestVectorUtils(unittest.TestCase):
    def test_pack_unpack_roundtrip(self):
        vec = [0.1, 0.2, -0.3, 4.0]
        blob = pack_f32(vec)
        out = unpack_f32(blob)
        self.assertEqual(len(out), len(vec))
        # float32 precision
        for a, b in zip(vec, out):
            self.assertAlmostEqual(a, b, places=5)

    def test_norm(self):
        self.assertAlmostEqual(l2_norm([3.0, 4.0]), 5.0)
        self.assertEqual(l2_norm([0.0, 0.0]), 0.0)

    def test_cosine_similarity(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [-1, 0]), -1.0)

    def test_rank_cosine(self):
        q = [1.0, 0.0]
        items = [
            (1, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0])),
            (2, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0])),
            (3, pack_f32([-1.0, 0.0]), l2_norm([-1.0, 0.0])),
        ]
        ranked = rank_cosine(query_vec=q, items=items, limit=3)
        self.assertEqual([rid for rid, _ in ranked], [1, 2, 3])
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_rank_cosine_skips_empty_vectors(self):
        q = [1.0, 0.0]
        items = [
            (1, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0])),
            (2, b"", l2_norm([1.0, 0.0])),
            (3, pack_f32([0.0, 0.0]), l2_norm([0.0, 0.0])),
            (4, pack_f32([0.5, 0.5]), l2_norm([0.5, 0.5])),
        ]
        ranked = rank_cosine(query_vec=q, items=items, limit=10)
        self.assertEqual([rid for rid, _ in ranked], [1, 4])

    def test_rank_cosine_skips_dimension_mismatch(self):
        q = [1.0, 0.0, 0.0]
        items = [
            (1, pack_f32([1.0, 0.0, 0.0]), l2_norm([1.0, 0.0, 0.0])),
            (2, pack_f32([1.0, 0.0]), l2_norm([1.0, 0.0])),
            (3, pack_f32([0.0, 1.0, 0.0]), l2_norm([0.0, 1.0, 0.0])),
        ]
        ranked = rank_cosine(query_vec=q, items=items, limit=10)
        self.assertEqual([rid for rid, _ in ranked], [1, 3])

    def test_rank_cosine_matches_full_sort_baseline_for_edge_cases(self):
        malformed_blob = b"not-a-float32-size"
        cases = [
            (
                "normal_and_malformed",
                [1.0, 0.0],
                [
                    (1, pack_f32([0.2, 0.0]), l2_norm([0.2, 0.0])),
                    (2, malformed_blob, 1.0),
                    (3, pack_f32([0.0, 1.0]), l2_norm([0.0, 1.0])),
                    (4, pack_f32([-1.0, 0.0]), l2_norm([-1.0, 0.0])),
                ],
                [1, 2, 10],
            ),
            (
                "zero_norm_and_all_zero",
                [1.0, 0.0],
                [
                    (1, pack_f32([1.0, 0.0]), 1.0),
                    (2, pack_f32([0.0, 0.0]), 0.0),
                    (3, pack_f32([0.5, 0.5]), l2_norm([0.5, 0.5])),
                ],
                [0, 1, 10],
            ),
            (
                "zero_query",
                [0.0, 0.0],
                [(1, pack_f32([1.0, 0.0]), 1.0)],
                [1, 10],
            ),
            (
                "dimension_mismatch",
                [1.0, 0.0, 0.0],
                [
                    (1, pack_f32([1.0, 0.0, 0.0]), 1.0),
                    (2, pack_f32([1.0, 0.0]), 1.0),
                    (3, pack_f32([0.0, 1.0, 0.0]), 1.0),
                ],
                [1, 2, 10],
            ),
            (
                "ties_preserve_input_order",
                [1.0, 0.0],
                [
                    (10, pack_f32([1.0, 0.0]), 1.0),
                    (5, pack_f32([1.0, 0.0]), 1.0),
                    (7, pack_f32([0.5, 0.0]), 0.5),
                    (9, pack_f32([0.0, 1.0]), 1.0),
                ],
                [1, 2, 3, 10],
            ),
        ]

        for name, query_vec, items, limits in cases:
            for limit in limits:
                with self.subTest(name=name, limit=limit):
                    expected = _rank_cosine_full_sort_baseline(query_vec=query_vec, items=items, limit=limit)
                    actual = rank_cosine(query_vec=query_vec, items=iter(items), limit=limit)
                    self.assertEqual(actual, expected)

    def test_rank_cosine_skips_nonfinite_scores_and_queries(self):
        q = [1.0, 0.0]
        items = [
            (1, pack_f32([1.0, 0.0]), 1.0),
            (2, pack_f32([math.nan, 0.0]), math.nan),
            (3, pack_f32([math.inf, 0.0]), math.inf),
            (4, pack_f32([0.0, 1.0]), 1.0),
        ]

        self.assertEqual(rank_cosine(query_vec=q, items=items, limit=10), [(1, 1.0), (4, 0.0)])
        self.assertEqual(rank_cosine(query_vec=[math.nan, 0.0], items=items, limit=10), [])

    def test_rank_cosine_bounded_selection_matches_baseline_past_limit(self):
        q = [1.0, 0.0]
        items = []
        for idx in range(100):
            score = ((idx * 37) % 100) / 100.0
            vec = [score, 1.0 - score]
            items.append((idx, pack_f32(vec), l2_norm(vec)))
        # Duplicate top scores across the cutoff to verify stable input-order tie handling.
        items.extend(
            [
                (1000, pack_f32([1.0, 0.0]), 1.0),
                (1001, pack_f32([1.0, 0.0]), 1.0),
                (1002, pack_f32([1.0, 0.0]), 1.0),
            ]
        )

        for limit in [1, 5, 20, 200]:
            with self.subTest(limit=limit):
                self.assertEqual(
                    rank_cosine(query_vec=q, items=iter(items), limit=limit),
                    _rank_cosine_full_sort_baseline(query_vec=q, items=items, limit=limit),
                )

    def test_rank_cosine_preserves_ties_straddling_heap_cutoff(self):
        q = [1.0, 0.0]
        items = [
            (1, pack_f32([0.9, 0.1]), l2_norm([0.9, 0.1])),
            (2, pack_f32([0.8, 0.2]), l2_norm([0.8, 0.2])),
            (10, pack_f32([0.7, 0.0]), 0.7),
            (11, pack_f32([0.7, 0.0]), 0.7),
            (12, pack_f32([0.7, 0.0]), 0.7),
            (13, pack_f32([0.7, 0.0]), 0.7),
            (3, pack_f32([0.6, 0.4]), l2_norm([0.6, 0.4])),
        ]

        self.assertEqual(
            rank_cosine(query_vec=q, items=iter(items), limit=4),
            _rank_cosine_full_sort_baseline(query_vec=q, items=items, limit=4),
        )

    def test_rank_cosine_synthetic_microbench_receipt(self):
        q = [1.0, 0.0, 0.5]
        items = [
            (idx, pack_f32([float(idx % 17), float((idx * 3) % 19), 1.0]), l2_norm([float(idx % 17), float((idx * 3) % 19), 1.0]))
            for idx in range(1000)
        ]
        start = time.perf_counter()
        ranked = rank_cosine(query_vec=q, items=items, limit=10)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        self.assertEqual(ranked, _rank_cosine_full_sort_baseline(query_vec=q, items=items, limit=10))
        self.assertLess(elapsed_ms, 500.0)

    def test_rank_rrf(self):
        # List 1: [1, 2, 3] (Rank 0, 1, 2)
        # List 2: [3, 1, 4] (Rank 0, 1, 2)
        # k=1 for easy math
        # 1: 1/(1+0+1) + 1/(1+1+1) = 1/2 + 1/3 = 0.5 + 0.333 = 0.833
        # 2: 1/(1+1+1) + 0         = 1/3 = 0.333
        # 3: 1/(1+2+1) + 1/(1+0+1) = 1/4 + 1/2 = 0.25 + 0.5 = 0.75
        # 4: 0         + 1/(1+2+1) = 1/4 = 0.25
        # Expected order: 1, 3, 2, 4
        
        lists = [
            [1, 2, 3],
            [3, 1, 4]
        ]
        ranked = rank_rrf(lists, k=1, limit=10)
        ids = [r[0] for r in ranked]
        self.assertEqual(ids, [1, 3, 2, 4])
        self.assertAlmostEqual(ranked[0][1], 0.8333333, places=5)


if __name__ == "__main__":
    unittest.main()
