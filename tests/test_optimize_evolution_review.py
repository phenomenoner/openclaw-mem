import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_evolution_review


class TestOptimizeEvolutionReview(unittest.TestCase):
    def test_optimize_parser_parses_evolution_review_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "evolution-review",
                "--limit",
                "500",
                "--stale-days",
                "45",
                "--lifecycle-limit",
                "90",
                "--scope",
                "team/alpha",
                "--top",
                "7",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "evolution-review")
        self.assertEqual(args.limit, 500)
        self.assertEqual(args.stale_days, 45)
        self.assertEqual(args.lifecycle_limit, 90)
        self.assertEqual(args.scope, "team/alpha")
        self.assertEqual(args.top, 7)

    def test_evolution_review_emits_low_risk_stale_candidate_packet(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Old scoped memory that no longer shows recent use",
                "detail": {
                    "scope": "team/alpha",
                    "importance": {"score": 0.41},
                },
            },
        )

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "lifecycle_limit": 50,
                "scope": "team/alpha",
                "top": 5,
                "json": True,
            },
        )()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_evolution_review(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.evolution-review.v0")
        self.assertEqual(out["policy"]["memory_mutation"], "none")
        self.assertEqual(out["counts"]["items"], 2)
        self.assertEqual(out["items"][0]["action"], "set_stale_candidate")
        self.assertEqual(out["items"][0]["risk_level"], "low")
        self.assertEqual(out["items"][0]["risk_reasons"][:2], ["bounded_lifecycle_patch", "age_threshold_signal_present"])
        self.assertTrue(out["items"][0]["auto_apply_eligible"])
        self.assertTrue(out["items"][0]["safe_for_auto_apply"])
        self.assertEqual(out["items"][0]["target"]["observationId"], obs_id)
        self.assertEqual(out["items"][0]["patch"]["lifecycle"]["stale_reason_code"], "age_threshold")
        self.assertEqual(out["items"][1]["action"], "adjust_importance_score")
        self.assertEqual(out["items"][1]["risk_level"], "low")
        self.assertIn("bounded_importance_delta", out["items"][1]["risk_reasons"])
        self.assertTrue(out["items"][1]["auto_apply_eligible"])
        self.assertEqual(out["items"][1]["target"]["observationId"], obs_id)
        self.assertEqual(out["items"][1]["patch"]["importance"]["score"], 0.31)
        self.assertEqual(out["items"][1]["patch"]["importance"]["label"], "ignore")
        conn.close()

    def test_evolution_review_marks_higher_value_importance_downshift_as_medium_risk(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Old but still somewhat valuable scoped memory",
                "detail": {
                    "scope": "team/alpha",
                    "importance": {"score": 0.75},
                },
            },
        )

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "lifecycle_limit": 50,
                "scope": "team/alpha",
                "top": 5,
                "json": True,
            },
        )()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_evolution_review(conn, args)

        out = json.loads(buf.getvalue())
        importance_items = [item for item in out["items"] if item["action"] == "adjust_importance_score"]
        self.assertEqual(len(importance_items), 1)
        self.assertEqual(importance_items[0]["risk_level"], "medium")
        self.assertIn("higher_value_memory_requires_review", importance_items[0]["risk_reasons"])
        self.assertFalse(importance_items[0]["auto_apply_eligible"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
