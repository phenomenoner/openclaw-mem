import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser, cmd_optimize_governor_review


class TestOptimizeGovernorReview(unittest.TestCase):
    def test_optimize_parser_parses_governor_review_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "governor-review",
                "--from-file",
                "/tmp/recommend.json",
                "--governor",
                "lyria",
                "--approve-refresh",
                "--approve-stale",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "governor-review")
        self.assertEqual(args.from_file, "/tmp/recommend.json")
        self.assertEqual(args.governor, "lyria")
        self.assertTrue(args.approve_refresh)
        self.assertTrue(args.approve_stale)

    def test_governor_review_defaults_refresh_to_proposal_only(self):
        conn = _connect(":memory:")
        packet = {
            "kind": "openclaw-mem.graph.synth.recommend.v0",
            "items": [
                {
                    "action": "refresh_card",
                    "reasons": ["stale_card"],
                    "target": {"recordRef": "obs:123"},
                    "suggestion": {"command": "openclaw-mem graph synth refresh obs:123", "args": ["obs:123"]},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "recommend.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {"from_file": str(path), "governor": "lyria", "approve_refresh": False, "json": True},
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_governor_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.governor-review.v0")
        self.assertEqual(out["policy"]["memory_mutation"], "none")
        self.assertEqual(out["policy"]["writes_performed"], 0)
        self.assertEqual(out["counts"]["proposalOnly"], 1)
        self.assertEqual(out["items"][0]["decision"], "proposal_only")
        self.assertEqual(out["items"][0]["judged_by"], "lyria")
        conn.close()

    def test_governor_review_can_approve_refresh(self):
        conn = _connect(":memory:")
        packet = {
            "kind": "openclaw-mem.graph.synth.recommend.v0",
            "items": [
                {
                    "action": "refresh_card",
                    "reasons": ["review_signal_present"],
                    "target": {"recordRef": "obs:77"},
                    "suggestion": {"command": "openclaw-mem graph synth refresh obs:77", "args": ["obs:77"]},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "recommend.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {"from_file": str(path), "governor": "lyria", "approve_refresh": True, "json": True},
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_governor_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["counts"]["approvedForApply"], 1)
        self.assertEqual(out["items"][0]["decision"], "approved_for_apply")
        self.assertEqual(out["items"][0]["apply_lane"], "graph.synth.refresh")
        conn.close()

    def test_governor_review_rejects_malformed_packet(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text(json.dumps({"kind": "wrong.kind", "items": []}), encoding="utf-8")
            args = type(
                "Args",
                (),
                {"from_file": str(path), "governor": "lyria", "approve_refresh": False, "json": True},
            )()
            buf = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                with redirect_stdout(buf):
                    cmd_optimize_governor_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("unsupported packet kind", out["error"])
        conn.close()

    def test_governor_review_can_approve_stale_candidate(self):
        conn = _connect(":memory:")
        packet = {
            "kind": "openclaw-mem.optimize.evolution-review.v0",
            "items": [
                {
                    "candidate_id": "stale-candidate-12",
                    "action": "set_stale_candidate",
                    "risk_level": "low",
                    "target": {"observationId": 12, "recordRef": "obs:12"},
                    "patch": {"lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
                    "evidence_refs": ["obs:12"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "evolution.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "governor": "lyria",
                    "approve_refresh": False,
                    "approve_stale": True,
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_governor_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["counts"]["approvedForApply"], 1)
        self.assertEqual(out["items"][0]["decision"], "approved_for_apply")
        self.assertEqual(out["items"][0]["apply_lane"], "observations.assist")
        self.assertEqual(out["items"][0]["recommended_action"], "set_stale_candidate")
        conn.close()


if __name__ == "__main__":
    unittest.main()
