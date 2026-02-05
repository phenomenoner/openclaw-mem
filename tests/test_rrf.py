from __future__ import annotations
import unittest
from openclaw_mem.vector import rank_rrf

class TestRRF(unittest.TestCase):
    def test_rrf_basic(self):
        # Item 1 is rank 0 in list A, rank 1 in list B
        # Item 2 is rank 1 in list A, not in B
        # Item 3 is not in A, rank 0 in B
        
        list_a = [1, 2]
        list_b = [3, 1]
        
        # k=1 for simple math
        # Score(1) = 1/(1+0+1) + 1/(1+1+1) = 1/2 + 1/3 = 0.5 + 0.333 = 0.833
        # Score(3) = 1/(1+0+1) = 0.5
        # Score(2) = 1/(1+1+1) = 0.333
        
        ranking = rank_rrf(ranked_lists=[list_a, list_b], k=1)
        
        ids = [r[0] for r in ranking]
        self.assertEqual(ids, [1, 3, 2])
        self.assertAlmostEqual(ranking[0][1], 0.8333333, places=5)

    def test_rrf_empty(self):
        ranking = rank_rrf(ranked_lists=[], k=60)
        self.assertEqual(ranking, [])
        
        ranking = rank_rrf(ranked_lists=[[], []], k=60)
        self.assertEqual(ranking, [])

    def test_rrf_limit(self):
        list_a = [1, 2, 3, 4]
        ranking = rank_rrf(ranked_lists=[list_a], k=60, limit=2)
        self.assertEqual(len(ranking), 2)
        self.assertEqual(ranking[0][0], 1)
        self.assertEqual(ranking[1][0], 2)

if __name__ == "__main__":
    unittest.main()
