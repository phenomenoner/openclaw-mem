import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from openclaw_mem.cli import (
    _connect,
    _insert_observation,
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



    def test_apply_run_with_witness_refreshes_and_rollback_marks_new_card(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "mem.sqlite"
            conn = _connect(str(db_path))
            _insert_observation(conn, {"kind": "note", "summary": "alpha source", "tool_name": "memory_store", "detail": {}})
            compile_args = build_parser().parse_args([
                "--db", str(db_path), "graph", "--json", "synth", "compile",
                "--query", "alpha", "--title", "Alpha synthesis", "--summary", "Alpha synthesis",
            ])
            buf = io.StringIO()
            with redirect_stdout(buf):
                compile_args.func(conn, compile_args)
            card_ref = json.loads(buf.getvalue())["cardRef"]
            _insert_observation(conn, {"kind": "note", "summary": "alpha newer source", "tool_name": "memory_store", "detail": {}})
            plan = root / "plan.json"
            witness = root / "witness.json"
            run_dir = root / "runs"
            now = datetime.now(timezone.utc).isoformat()
            plan.write_text(json.dumps({
                "kind": "openclaw-mem.dream-lite.apply.v0",
                "run_id": "plan-1",
                "ts": now,
                "mode": "dry_run",
                "result": "planned",
                "blocked_reason": None,
                "candidate_id": "c1",
                "recommended_action": "refresh_card",
                "governor_decision": "approved_for_apply",
                "apply_lane": "graph.synth.refresh",
                "target": {"recordRef": card_ref, "before_hash": None},
                "snapshot_ref": None,
                "rollback_ref": None,
                "sidecar_witness_ref": None,
                "writes_performed": 0,
                "policy": {"read_only": True, "memory_mutation": "none", "authority_mutation": "none"},
            }), encoding="utf-8")
            witness.write_text(json.dumps({
                "kind": "openclaw-mem.self-reflection.dream-witness.v0",
                "witness_id": "w1",
                "apply_run_id": "plan-1",
                "ts": now,
                "verdict": "ok",
                "coherence_risk": "low",
                "reasons": [],
            }), encoding="utf-8")
            run_args = build_parser().parse_args([
                "--db", str(db_path), "dream-lite", "apply", "run",
                "--plan", str(plan), "--witness", str(witness), "--run-dir", str(run_dir),
                "--run-id", "apply-1", "--json",
            ])
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_args.func(conn, run_args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["result"], "applied")
            self.assertEqual(out["writes_performed"], 2)
            rollback_ref = out["rollback_ref"]
            new_ref = out["refresh_payload"]["result"]["recordRef"]

            rollback_args = build_parser().parse_args([
                "--db", str(db_path), "dream-lite", "apply", "rollback",
                "--rollback", rollback_ref, "--run-dir", str(run_dir), "--json",
            ])
            rb_buf = io.StringIO()
            with redirect_stdout(rb_buf):
                rollback_args.func(conn, rollback_args)
            rb = json.loads(rb_buf.getvalue())
            self.assertEqual(rb["result"], "rolled_back")
            self.assertTrue(Path(rb["receipt_ref"]).exists())
            verify_args = build_parser().parse_args(["dream-lite", "apply", "verify", "--since", "24h", "--run-dir", str(run_dir), "--json"])
            verify_buf = io.StringIO()
            with redirect_stdout(verify_buf):
                verify_args.func(conn, verify_args)
            verify_out = json.loads(verify_buf.getvalue())
            self.assertEqual(verify_out["status"], "pass")
            new_row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (int(new_ref.split(":", 1)[1]),)).fetchone()
            new_detail = json.loads(new_row["detail_json"] or "{}")
            self.assertEqual(new_detail["graph_synthesis"]["status"], "rolled_back")
            conn.close()

    def test_apply_run_blocks_missing_or_flagged_witness(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan = root / "plan.json"
            plan.write_text(json.dumps({
                "kind": "openclaw-mem.dream-lite.apply.v0",
                "run_id": "plan-1",
                "ts": datetime.now(timezone.utc).isoformat(),
                "mode": "dry_run",
                "result": "planned",
                "recommended_action": "refresh_card",
                "governor_decision": "approved_for_apply",
                "apply_lane": "graph.synth.refresh",
                "target": {"recordRef": "obs:999", "before_hash": None},
                "snapshot_ref": None,
                "rollback_ref": None,
                "sidecar_witness_ref": None,
                "writes_performed": 0,
                "policy": {"read_only": True, "memory_mutation": "none", "authority_mutation": "none"},
            }), encoding="utf-8")
            args = build_parser().parse_args(["dream-lite", "apply", "run", "--plan", str(plan), "--run-dir", str(root / "runs"), "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["result"], "aborted")
            self.assertIn("missing_witness", out["blocked_reasons"])
        conn.close()

    def test_director_apply_rehearsal_requires_flag_and_checks_hash(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staged = root / "staged.json"
            checkpoint = root / "checkpoint.json"
            staged_payload = {
                "kind": "openclaw-mem.dream-director.staged-patch.v0",
                "stage_id": "s1",
                "ts": NOW,
                "source_candidate_ref": None,
                "candidate_count": 1,
                "patches": [{"path": "AGENTS.md", "op": "note", "text": "x"}],
                "risk_classes": ["authority_surface"],
                "checkpoint_required": True,
                "blocked_reasons": [],
                "writes_performed": 0,
                "policy": {"read_only": True},
            }
            staged.write_text(json.dumps(staged_payload, sort_keys=True), encoding="utf-8")
            checkpoint.write_text(json.dumps({
                "kind": "openclaw-mem.dream-director.checkpoint.v0",
                "checkpoint_id": "ck1",
                "ts": NOW,
                "staged_patch_ref": str(staged),
                "staged_patch_sha256": "bad",
                "checkpoint_required": True,
                "blocked_reasons": [],
                "live_mutation": False,
                "writes_performed": 0,
                "policy": {"read_only": True},
            }), encoding="utf-8")
            args = build_parser().parse_args(["dream-lite", "director", "apply", "--checkpoint", str(checkpoint), "--rehearsal-dir", str(root / "rehearsal"), "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
            self.assertIn("staged_patch_hash_mismatch", out["blocked_reasons"])
            self.assertIn("authority_rehearsal_requires_explicit_flag", out["blocked_reasons"])
            self.assertFalse(out["live_mutation"])
            self.assertEqual(out["writes_performed"], 0)
        conn.close()



    def test_apply_verify_since_rejects_fake_applied_receipt_with_missing_refs(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            fake = run_dir / "fake.after.json"
            fake.write_text(json.dumps({
                "kind": "openclaw-mem.dream-lite.apply.after.v0",
                "run_id": "fake",
                "ts": datetime.now(timezone.utc).isoformat(),
                "result": "applied",
                "before_ref": str(run_dir / "missing.before.json"),
                "rollback_ref": str(run_dir / "missing.rollback.json"),
                "witness_ref": str(run_dir / "witness.json"),
                "witness": {"verdict": "ok"},
                "writes_performed": 2,
            }), encoding="utf-8")
            args = build_parser().parse_args(["dream-lite", "apply", "verify", "--since", "24h", "--run-dir", str(run_dir), "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "fail")
        self.assertTrue(any("before_ref_not_found" in r for r in out["reasons"]))
        self.assertTrue(any("rollback_ref_not_found" in r for r in out["reasons"]))
        conn.close()

    def test_apply_run_rejects_unbound_witness(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan = root / "plan.json"
            witness = root / "witness.json"
            plan.write_text(json.dumps({
                "kind": "openclaw-mem.dream-lite.apply.v0",
                "run_id": "plan-1",
                "ts": datetime.now(timezone.utc).isoformat(),
                "mode": "dry_run",
                "result": "planned",
                "recommended_action": "refresh_card",
                "governor_decision": "approved_for_apply",
                "apply_lane": "graph.synth.refresh",
                "target": {"recordRef": "obs:999", "before_hash": None},
                "snapshot_ref": None,
                "rollback_ref": None,
                "sidecar_witness_ref": None,
                "writes_performed": 0,
                "policy": {"read_only": True, "memory_mutation": "none", "authority_mutation": "none"},
            }), encoding="utf-8")
            witness.write_text(json.dumps({
                "kind": "openclaw-mem.self-reflection.dream-witness.v0",
                "plan_run_id": "other-plan",
                "verdict": "ok",
                "coherence_risk": "low",
                "reasons": [],
            }), encoding="utf-8")
            args = build_parser().parse_args(["dream-lite", "apply", "run", "--plan", str(plan), "--witness", str(witness), "--run-dir", str(root / "runs"), "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        self.assertEqual(out["result"], "aborted")
        self.assertIn("witness_plan_binding_mismatch", out["blocked_reasons"])
        conn.close()



    def test_apply_verify_since_rejects_before_hash_mismatch(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            before = run_dir / "x.before.json"
            rollback = run_dir / "x.rollback.json"
            before.write_text(json.dumps({
                "kind": "openclaw-mem.dream-lite.apply.before.v0",
                "run_id": "x",
                "ts": datetime.now(timezone.utc).isoformat(),
                "before_snapshot": {"detail_sha256": "real-hash"},
                "writes_performed": 0,
            }), encoding="utf-8")
            rollback.write_text(json.dumps({
                "kind": "openclaw-mem.dream-lite.apply.rollback.v0",
                "apply_run_id": "x",
                "ts": datetime.now(timezone.utc).isoformat(),
                "before_snapshot": {"detail_sha256": "real-hash"},
                "writes_performed": 0,
            }), encoding="utf-8")
            after = run_dir / "x.after.json"
            after.write_text(json.dumps({
                "kind": "openclaw-mem.dream-lite.apply.after.v0",
                "run_id": "x",
                "ts": datetime.now(timezone.utc).isoformat(),
                "result": "applied",
                "before_ref": str(before),
                "rollback_ref": str(rollback),
                "witness_ref": str(run_dir / "witness.json"),
                "witness": {"verdict": "ok"},
                "before_hash": "tampered-hash",
                "writes_performed": 2,
            }), encoding="utf-8")
            args = build_parser().parse_args(["dream-lite", "apply", "verify", "--since", "24h", "--run-dir", str(run_dir), "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "fail")
        self.assertTrue(any("before_hash_mismatch" in r for r in out["reasons"]))
        conn.close()



    def test_apply_verify_since_empty_window_is_inconclusive(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            args = build_parser().parse_args(["dream-lite", "apply", "verify", "--since", "24h", "--run-dir", td, "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "inconclusive")
        conn.close()

    def test_apply_verify_since_rejects_rollback_continuity_mismatch(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            ts = datetime.now(timezone.utc).isoformat()
            before = run_dir / "x.before.json"
            rollback = run_dir / "x.rollback.json"
            after = run_dir / "x.after.json"
            before.write_text(json.dumps({"kind":"openclaw-mem.dream-lite.apply.before.v0","ts":ts,"before_snapshot":{"detail_sha256":"h1"}}), encoding="utf-8")
            rollback.write_text(json.dumps({"kind":"openclaw-mem.dream-lite.apply.rollback.v0","apply_run_id":"other","ts":ts,"before_snapshot":{"detail_sha256":"h2"}}), encoding="utf-8")
            after.write_text(json.dumps({"kind":"openclaw-mem.dream-lite.apply.after.v0","run_id":"x","ts":ts,"result":"applied","before_ref":str(before),"rollback_ref":str(rollback),"witness_ref":"w","witness":{"verdict":"ok"},"before_hash":"h1","writes_performed":2}), encoding="utf-8")
            args = build_parser().parse_args(["dream-lite", "apply", "verify", "--since", "24h", "--run-dir", str(run_dir), "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "fail")
        self.assertTrue(any("rollback_apply_run_id_mismatch" in r for r in out["reasons"]))
        self.assertTrue(any("rollback_before_hash_mismatch" in r for r in out["reasons"]))
        conn.close()

    def test_director_apply_rescans_authority_paths_even_when_checkpoint_false(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staged = root / "staged.json"
            checkpoint = root / "checkpoint.json"
            staged_payload = {"kind":"openclaw-mem.dream-director.staged-patch.v0","stage_id":"s","ts":NOW,"source_candidate_ref":None,"candidate_count":1,"patches":[{"path":"AGENTS.md","op":"note","text":"x"}],"risk_classes":["journal_only"],"checkpoint_required":False,"blocked_reasons":[],"writes_performed":0,"policy":{"read_only":True}}
            staged.write_text(json.dumps(staged_payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            import hashlib
            sha = hashlib.sha256(json.dumps(staged_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            checkpoint.write_text(json.dumps({"kind":"openclaw-mem.dream-director.checkpoint.v0","checkpoint_id":"c","ts":NOW,"staged_patch_ref":str(staged),"staged_patch_sha256":sha,"checkpoint_required":False,"blocked_reasons":[],"live_mutation":False,"writes_performed":0,"policy":{"read_only":True}}), encoding="utf-8")
            args = build_parser().parse_args(["dream-lite", "director", "apply", "--checkpoint", str(checkpoint), "--rehearsal-dir", str(root / "r"), "--json"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        self.assertTrue(out["checkpoint_required"])
        self.assertIn("authority_rehearsal_requires_explicit_flag", out["blocked_reasons"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
