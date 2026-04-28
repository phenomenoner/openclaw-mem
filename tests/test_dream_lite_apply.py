import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from openclaw_mem.cli import (
    _connect,
    build_parser,
    cmd_dream_lite_apply_plan,
    cmd_dream_lite_apply_verify,
    cmd_dream_lite_director_checkpoint,
    cmd_dream_lite_director_observe,
    cmd_dream_lite_director_stage,
)


NOW = "2026-04-28T11:11:11Z"
RUN_ID = "fixed-run"


def governor_packet(items):
    return {
        "kind": "openclaw-mem.optimize.governor-review.v0",
        "ts": NOW,
        "source": {"kind": "openclaw-mem.graph.synth.recommend.v0", "fromFile": "recommend.json"},
        "policy": {"writes_performed": 0, "memory_mutation": "none"},
        "items": items,
    }


def refresh_item(candidate_id="c1", decision="approved_for_apply", record_ref="synth:one"):
    return {
        "candidate_id": candidate_id,
        "recommended_action": "refresh_card",
        "decision": decision,
        "apply_lane": "graph.synth.refresh",
        "target": {"recordRef": record_ref},
    }


class TestDreamLiteApplyPhase1(unittest.TestCase):
    def test_parser_parses_dream_lite_apply_plan(self):
        args = build_parser().parse_args(
            [
                "dream-lite",
                "apply",
                "plan",
                "--governor-packet",
                "/tmp/governor.json",
                "--out",
                "/tmp/plan.json",
                "--run-id",
                RUN_ID,
                "--now",
                NOW,
                "--json",
            ]
        )
        self.assertEqual(args.cmd, "dream-lite")
        self.assertEqual(args.dream_lite_cmd, "apply")
        self.assertEqual(args.dream_lite_apply_cmd, "plan")
        self.assertEqual(args.governor_packet, "/tmp/governor.json")
        self.assertTrue(args.json)

    def test_apply_plan_emits_planned_receipt_for_one_eligible_refresh(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td) / "governor.json"
            packet_path.write_text(json.dumps(governor_packet([refresh_item()])), encoding="utf-8")
            args = SimpleNamespace(
                governor_packet=str(packet_path),
                from_file=None,
                out=None,
                run_id=RUN_ID,
                now=NOW,
                json=True,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_dream_lite_apply_plan(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.dream-lite.apply.v0")
        self.assertEqual(out["run_id"], RUN_ID)
        self.assertEqual(out["ts"], NOW)
        self.assertEqual(out["result"], "planned")
        self.assertEqual(out["recommended_action"], "refresh_card")
        self.assertEqual(out["target"]["recordRef"], "synth:one")
        self.assertIsNone(out["target"]["before_hash"])
        self.assertEqual(out["writes_performed"], 0)
        conn.close()

    def test_apply_plan_aborts_compile_new_card_even_if_approved(self):
        conn = _connect(":memory:")
        item = {
            "candidate_id": "c2",
            "recommended_action": "compile_new_card",
            "decision": "approved_for_apply",
            "apply_lane": "graph.synth.compile",
            "target": {"recordRefs": ["obs:1"]},
        }
        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td) / "governor.json"
            packet_path.write_text(json.dumps(governor_packet([item])), encoding="utf-8")
            args = SimpleNamespace(governor_packet=str(packet_path), from_file=None, out=None, run_id=RUN_ID, now=NOW, json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_dream_lite_apply_plan(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["result"], "aborted")
        self.assertEqual(out["blocked_reason"], "compile_new_card_not_apply_eligible_in_v0")
        self.assertEqual(out["writes_performed"], 0)
        conn.close()

    def test_apply_plan_aborts_when_more_than_one_candidate(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td) / "governor.json"
            packet_path.write_text(json.dumps(governor_packet([refresh_item("c1"), refresh_item("c2", record_ref="synth:two")])) , encoding="utf-8")
            args = SimpleNamespace(governor_packet=str(packet_path), from_file=None, out=None, run_id=RUN_ID, now=NOW, json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_dream_lite_apply_plan(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["result"], "aborted")
        self.assertEqual(out["blocked_reason"], "max_candidates_per_run_exceeded")
        conn.close()

    def test_apply_verify_rejects_tampered_action_or_writes(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.dream-lite.apply.v0",
                        "run_id": RUN_ID,
                        "result": "planned",
                        "recommended_action": "compile_new_card",
                        "governor_decision": "approved_for_apply",
                        "target": {"recordRef": "synth:one"},
                        "writes_performed": 1,
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(receipt=str(receipt), from_file=None, now=NOW, json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_dream_lite_apply_verify(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "fail")
        self.assertIn("writes_performed_must_be_zero_in_phase1", out["reasons"])
        self.assertIn("unsupported_recommended_action", out["reasons"])
        conn.close()


    def test_apply_verify_rejects_non_phase1_or_mutating_policy(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.dream-lite.apply.v0",
                        "run_id": RUN_ID,
                        "mode": "wet_run",
                        "result": "planned",
                        "recommended_action": "refresh_card",
                        "governor_decision": "approved_for_apply",
                        "apply_lane": "graph.synth.refresh",
                        "target": {"recordRef": "synth:one"},
                        "snapshot_ref": None,
                        "rollback_ref": None,
                        "sidecar_witness_ref": None,
                        "writes_performed": 0,
                        "policy": {"read_only": False, "memory_mutation": "write", "authority_mutation": "none"},
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(receipt=str(receipt), from_file=None, now=NOW, json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_dream_lite_apply_verify(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "fail")
        self.assertIn("mode_must_be_dry_run_in_phase1", out["reasons"])
        self.assertIn("policy_read_only_required", out["reasons"])
        self.assertIn("memory_mutation_must_be_none", out["reasons"])
        conn.close()

    def test_director_stage_rescans_patch_paths_for_authority_surfaces(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidates = root / "candidates.json"
            staged = root / "staged.json"
            candidates.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.dream-director.instruction-candidate.v0",
                        "candidate_id": "manual-bypass",
                        "ts": NOW,
                        "observation_window": "24h",
                        "writes_performed": 0,
                        "policy": {"read_only": True},
                        "candidates": [
                            {
                                "candidate_id": "p1",
                                "risk_class": "journal_only",
                                "checkpoint_required": False,
                                "candidate_patches": [{"path": "AGENTS.md", "op": "note", "text": "x"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(candidates=str(candidates), from_file=None, max_patch_bytes=40000, out=str(staged), run_id="stage-1", now=NOW, json=True)
            with redirect_stdout(io.StringIO()):
                cmd_dream_lite_director_stage(conn, args)
            out = json.loads(staged.read_text(encoding="utf-8"))
        self.assertTrue(out["checkpoint_required"])
        self.assertIn("authority_surface", out["risk_classes"])
        self.assertEqual(out["blocked_reasons"], [])
        self.assertEqual(out["writes_performed"], 0)
        conn.close()


    def test_apply_verify_requires_writes_performed_and_rejects_authority_target(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.dream-lite.apply.v0",
                        "run_id": RUN_ID,
                        "mode": "dry_run",
                        "result": "planned",
                        "recommended_action": "refresh_card",
                        "governor_decision": "approved_for_apply",
                        "apply_lane": "graph.synth.refresh",
                        "target": {"recordRef": "SOUL.md"},
                        "snapshot_ref": None,
                        "rollback_ref": None,
                        "sidecar_witness_ref": None,
                        "policy": {"read_only": True, "memory_mutation": "none", "authority_mutation": "none"},
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(receipt=str(receipt), from_file=None, now=NOW, json=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_dream_lite_apply_verify(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "fail")
        self.assertIn("missing_writes_performed", out["reasons"])
        self.assertIn("planned_receipt_target_must_not_be_authority_surface", out["reasons"])
        conn.close()

    def test_director_stage_rejects_unsupported_apply_lane(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidates = root / "candidates.json"
            staged = root / "staged.json"
            candidates.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.dream-director.instruction-candidate.v0",
                        "candidate_id": "bad-lane",
                        "ts": NOW,
                        "observation_window": "24h",
                        "writes_performed": 0,
                        "policy": {"read_only": True},
                        "candidates": [
                            {
                                "candidate_id": "p1",
                                "risk_class": "journal_only",
                                "apply_lane": "direct_apply",
                                "checkpoint_required": False,
                                "candidate_patches": [{"path": "notes.md", "op": "note", "text": "x"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(candidates=str(candidates), from_file=None, max_patch_bytes=40000, out=str(staged), run_id="stage-1", now=NOW, json=True)
            with redirect_stdout(io.StringIO()):
                cmd_dream_lite_director_stage(conn, args)
            out = json.loads(staged.read_text(encoding="utf-8"))
        self.assertIn("unsupported_apply_lane", out["blocked_reasons"])
        self.assertEqual(out["patches"], [])
        self.assertEqual(out["writes_performed"], 0)
        conn.close()

    def test_director_observe_stage_checkpoint_round_trip(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            daily = root / "daily.json"
            candidates = root / "candidates.json"
            staged = root / "staged.json"
            checkpoint = root / "checkpoint.json"
            daily.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.dream-director.observation-input.v0",
                        "observation_window": "24h",
                        "source_refs": ["receipt:1"],
                        "proposals": [
                            {
                                "candidate_id": "p1",
                                "risk_class": "authority_surface",
                                "candidate_patches": [{"path": "SOUL.md", "op": "note", "text": "reinforce warmth"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(input=str(daily), from_file=None, since=None, max_candidates=20, out=str(candidates), run_id=RUN_ID, now=NOW, json=True)
            with redirect_stdout(io.StringIO()):
                cmd_dream_lite_director_observe(conn, args)
            cand = json.loads(candidates.read_text(encoding="utf-8"))
            self.assertTrue(cand["checkpoint_required"])
            self.assertEqual(cand["writes_performed"], 0)

            args = SimpleNamespace(candidates=str(candidates), from_file=None, max_patch_bytes=40000, out=str(staged), run_id="stage-1", now=NOW, json=True)
            with redirect_stdout(io.StringIO()):
                cmd_dream_lite_director_stage(conn, args)
            stage_payload = json.loads(staged.read_text(encoding="utf-8"))
            self.assertEqual(stage_payload["kind"], "openclaw-mem.dream-director.staged-patch.v0")
            self.assertTrue(stage_payload["checkpoint_required"])
            self.assertEqual(stage_payload["blocked_reasons"], [])

            args = SimpleNamespace(staged=str(staged), patch=None, from_file=None, out=str(checkpoint), run_id="checkpoint-1", now=NOW, json=True)
            with redirect_stdout(io.StringIO()):
                cmd_dream_lite_director_checkpoint(conn, args)
            ckpt = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(ckpt["kind"], "openclaw-mem.dream-director.checkpoint.v0")
            self.assertTrue(ckpt["checkpoint_required"])
            self.assertFalse(ckpt["live_mutation"])
            self.assertEqual(ckpt["writes_performed"], 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
