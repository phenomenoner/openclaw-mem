import unittest

from openclaw_mem.vector import pack_f32, unpack_f32, l2_norm, cosine_similarity, rank_cosine, rank_rrf


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
