from __future__ import annotations

import re
import unittest

from openclaw_mem.importance import label_from_score, make_importance, parse_importance_score


class TestImportance(unittest.TestCase):
    def test_label_thresholds(self):
        self.assertEqual(label_from_score(0.80), "must_remember")
        self.assertEqual(label_from_score(0.7999999), "nice_to_have")
        self.assertEqual(label_from_score(0.50), "nice_to_have")
        self.assertEqual(label_from_score(0.4999999), "ignore")

    def test_parse_importance_score_clamps_numeric_inputs(self):
        self.assertEqual(parse_importance_score(1.4), 1.0)
        self.assertEqual(parse_importance_score(-0.2), 0.0)
        self.assertEqual(parse_importance_score(0), 0.0)
        self.assertEqual(parse_importance_score(0.42), 0.42)

    def test_parse_importance_score_supports_label_fallback(self):
        self.assertEqual(parse_importance_score({"label": " must_remember "}), 0.8)
        self.assertEqual(parse_importance_score({"label": "nice_to_have"}), 0.5)
        self.assertEqual(parse_importance_score({"label": "ignore"}), 0.0)

    def test_parse_importance_score_supports_label_aliases(self):
        self.assertEqual(parse_importance_score({"label": "must remember"}), 0.8)
        self.assertEqual(parse_importance_score({"label": "nice-to-have"}), 0.5)
        self.assertEqual(parse_importance_score({"label": "medium"}), 0.5)
        self.assertEqual(parse_importance_score({"label": "high"}), 0.8)

    def test_parse_importance_score_invalid_returns_zero(self):
        self.assertEqual(parse_importance_score(None), 0.0)
        self.assertEqual(parse_importance_score({"score": "high"}), 0.0)
        self.assertEqual(parse_importance_score({"label": "UNKNOWN"}), 0.0)

    def test_make_importance_normalizes_label_and_adds_timestamp(self):
        obj = make_importance(
            score=0.95,
            method="heuristic-v1",
            rationale="stable policy decision",
            version=2,
            label=" Must_Remember ",
        )
        self.assertEqual(obj["label"], "must_remember")
        self.assertEqual(obj["score"], 0.95)
        self.assertEqual(obj["method"], "heuristic-v1")
        self.assertEqual(obj["version"], 2)
        self.assertIsInstance(obj["graded_at"], str)
        self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", obj["graded_at"]))


if __name__ == "__main__":
    unittest.main()
