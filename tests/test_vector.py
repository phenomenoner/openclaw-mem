import unittest

from openclaw_mem.vector import pack_f32, unpack_f32, l2_norm, cosine_similarity, rank_cosine


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


if __name__ == "__main__":
    unittest.main()
