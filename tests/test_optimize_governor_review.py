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
                "--approve-importance",
                "--approve-stale",
                "--approve-soft-archive",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "governor-review")
        self.assertEqual(args.from_file, "/tmp/recommend.json")
        self.assertEqual(args.governor, "lyria")
        self.assertTrue(args.approve_refresh)
        self.assertTrue(args.approve_importance)
        self.assertTrue(args.approve_stale)
        self.assertTrue(args.approve_soft_archive)

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

    def test_governor_review_can_approve_importance_adjustment(self):
        conn = _connect(":memory:")
        packet = {
            "kind": "openclaw-mem.optimize.evolution-review.v0",
            "items": [
                {
                    "candidate_id": "importance-downshift-12",
                    "action": "adjust_importance_score",
                    "risk_level": "low",
                    "target": {"observationId": 12, "recordRef": "obs:12"},
                    "patch": {"importance": {"score": 0.3, "label": "ignore", "delta": -0.1, "reason_code": "stale_pressure"}},
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
                    "approve_importance": True,
                    "approve_stale": False,
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
        self.assertEqual(out["items"][0]["recommended_action"], "adjust_importance_score")
        self.assertTrue(out["items"][0]["auto_apply_eligible"])
        self.assertEqual(out["items"][0]["risk_reasons"], [])
        conn.close()

    def test_governor_review_keeps_medium_risk_importance_as_proposal_only(self):
        conn = _connect(":memory:")
        packet = {
            "kind": "openclaw-mem.optimize.evolution-review.v0",
            "items": [
                {
                    "candidate_id": "importance-downshift-12",
                    "action": "adjust_importance_score",
                    "risk_level": "medium",
                    "risk_reasons": ["higher_value_memory_requires_review"],
                    "auto_apply_eligible": False,
                    "target": {"observationId": 12, "recordRef": "obs:12"},
                    "patch": {"importance": {"score": 0.65, "label": "nice_to_have", "delta": -0.1, "reason_code": "stale_pressure"}},
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
                    "approve_importance": True,
                    "approve_stale": False,
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_governor_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["counts"]["approvedForApply"], 0)
        self.assertEqual(out["counts"]["proposalOnly"], 1)
        self.assertEqual(out["items"][0]["decision"], "proposal_only")
        self.assertIn("classifier_requires_review", out["items"][0]["reasons"])
        self.assertEqual(out["items"][0]["risk_reasons"], ["higher_value_memory_requires_review"])
        conn.close()

    def test_governor_review_soft_archive_requires_explicit_approval_flag(self):
        conn = _connect(":memory:")
        packet = {
            "kind": "openclaw-mem.optimize.evolution-review.v0",
            "items": [
                {
                    "candidate_id": "soft-archive-candidate-12",
                    "action": "set_soft_archive_candidate",
                    "risk_level": "low",
                    "auto_apply_eligible": False,
                    "target": {"observationId": 12, "recordRef": "obs:12"},
                    "patch": {"lifecycle": {"soft_archive_candidate": True, "set_archived_at": True, "archive_reason_code": "stale_low_importance"}},
                    "evidence_refs": ["obs:12"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "evolution.json"
            path.write_text(json.dumps(packet), encoding="utf-8")

            args_default = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "governor": "lyria",
                    "approve_refresh": False,
                    "approve_importance": False,
                    "approve_stale": False,
                    "approve_soft_archive": False,
                    "json": True,
                },
            )()
            default_buf = io.StringIO()
            with redirect_stdout(default_buf):
                cmd_optimize_governor_review(conn, args_default)
            out_default = json.loads(default_buf.getvalue())
            self.assertEqual(out_default["counts"]["approvedForApply"], 0)
            self.assertEqual(out_default["counts"]["proposalOnly"], 1)
            self.assertIn("awaiting_governor_soft_archive_approval", out_default["items"][0]["reasons"])

            args_approved = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "governor": "lyria",
                    "approve_refresh": False,
                    "approve_importance": False,
                    "approve_stale": False,
                    "approve_soft_archive": True,
                    "json": True,
                },
            )()
            approved_buf = io.StringIO()
            with redirect_stdout(approved_buf):
                cmd_optimize_governor_review(conn, args_approved)
            out_approved = json.loads(approved_buf.getvalue())
            self.assertEqual(out_approved["counts"]["approvedForApply"], 1)
            self.assertEqual(out_approved["items"][0]["decision"], "approved_for_apply")
            self.assertEqual(out_approved["items"][0]["recommended_action"], "set_soft_archive_candidate")
            self.assertIn("approve_soft_archive_enabled", out_approved["items"][0]["reasons"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
