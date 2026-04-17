import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser, cmd_optimize_challenger_review


class TestOptimizeChallengerReview(unittest.TestCase):
    def test_optimize_parser_parses_challenger_review_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "challenger-review",
                "--from-file",
                "/tmp/evolution.json",
                "--policy-mode",
                "strict_v1",
                "--max-disagreement-clusters",
                "4",
                "--top",
                "7",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "challenger-review")
        self.assertEqual(args.from_file, "/tmp/evolution.json")
        self.assertEqual(args.policy_mode, "strict_v1")
        self.assertEqual(args.max_disagreement_clusters, 4)
        self.assertEqual(args.top, 7)

    def test_challenger_review_emits_disagreement_for_higher_value_importance_candidate(self):
        conn = _connect(":memory:")
        packet = {
            "kind": "openclaw-mem.optimize.evolution-review.v0",
            "items": [
                {
                    "candidate_id": "importance-downshift-12",
                    "action": "adjust_importance_score",
                    "risk_level": "low",
                    "patch": {"importance": {"score": 0.65, "label": "nice_to_have", "delta": -0.10}},
                    "evidence": {"current_score": 0.75, "recent_use_count": 0},
                    "target": {"observationId": 12},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "evolution.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {"from_file": str(path), "policy_mode": "strict_v1", "max_disagreement_clusters": 10, "top": 10, "json": True},
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_challenger_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.challenger-review.v0")
        self.assertEqual(out["counts"]["disagreements"], 1)
        self.assertEqual(out["counts"]["disagreementClusters"], 1)
        self.assertEqual(out["items"][0]["challenger_risk_level"], "medium")
        self.assertEqual(out["items"][0]["action_family"], "importance")
        self.assertEqual(out["items"][0]["disagreement_kind"], "risk_upgrade")
        self.assertTrue(out["items"][0]["quarantine_recommended"])
        self.assertIn("higher_value_memory_requires_review", out["items"][0]["challenger_reasons"])
        self.assertFalse(out["summary"]["agreement_pass"])
        self.assertTrue(out["summary"]["quarantine_recommended"])
        self.assertEqual(out["disagreement_clusters"][0]["action_family"], "importance")
        conn.close()


if __name__ == "__main__":
    unittest.main()
