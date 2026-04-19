from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openclaw_mem import gbrain_sidecar
from openclaw_mem.cli import _connect, _insert_observation, _pack_gbrain_bundle_text, build_parser


class TestGBrainSidecarModule(unittest.TestCase):
    def test_consult_normalizes_results(self):
        completed = subprocess.CompletedProcess(
            args=["gbrain"],
            returncode=0,
            stdout=json.dumps([
                {"slug": "people/alice", "score": 0.93, "chunk_text": "Alice knows the rollout state."},
                {"slug": "projects/beta", "score": 0.52, "chunk_text": "Beta project timeline."},
            ]),
            stderr="",
        )
        with patch("openclaw_mem.gbrain_sidecar.subprocess.run", return_value=completed):
            out = gbrain_sidecar.consult("rollout state", limit=2, gbrain_bin="gbrain")

        self.assertTrue(out["ok"])
        self.assertFalse(out["fail_open"])
        self.assertEqual(out["result_count"], 2)
        self.assertEqual(out["items"][0]["recordRef"], "gbrain:people/alice")
        self.assertIn("[gbrain:people/alice]", out["bundle_text"])

    def test_consult_fail_open_when_binary_missing(self):
        with patch("openclaw_mem.gbrain_sidecar.subprocess.run", side_effect=FileNotFoundError()):
            out = gbrain_sidecar.consult("rollout state", gbrain_bin="missing-gbrain")

        self.assertFalse(out["ok"])
        self.assertTrue(out["fail_open"])
        self.assertIn("missing-gbrain", out["error"])

    def test_submit_job_is_bounded_to_embed_lane(self):
        with self.assertRaises(ValueError):
            gbrain_sidecar.submit_job(name="sync")

    def test_list_jobs_is_bounded_to_embed_lane(self):
        with self.assertRaises(ValueError):
            gbrain_sidecar.list_jobs(name="sync")

    def test_retry_job_prechecks_family(self):
        with patch(
            "openclaw_mem.gbrain_sidecar._run_gbrain_call",
            side_effect=[
                gbrain_sidecar.GBrainCallResult(
                    ok=True,
                    command=["gbrain", "call", "get_job", "{}"],
                    returncode=0,
                    stdout="{}",
                    stderr="",
                    duration_ms=5,
                    payload={"id": 7, "name": "sync"},
                )
            ],
        ):
            with self.assertRaises(ValueError):
                gbrain_sidecar.retry_job(7)

    def test_build_refresh_recommendation_uses_consult_refs(self):
        payload = gbrain_sidecar.build_refresh_recommendation(
            record_ref="obs:123",
            consult_payload={
                "schema": gbrain_sidecar.CONSULT_SCHEMA,
                "ok": True,
                "query": {"text": "alpha"},
                "result_count": 1,
                "items": [{"recordRef": "gbrain:people/alice"}],
            },
        )
        self.assertEqual(payload["kind"], "openclaw-mem.graph.synth.recommend.v0")
        self.assertEqual(payload["items"][0]["action"], "refresh_card")
        self.assertEqual(payload["items"][0]["target"]["recordRef"], "obs:123")
        self.assertIn("gbrain:people/alice", payload["items"][0]["evidence_refs"])


class TestGBrainSidecarCLI(unittest.TestCase):
    def test_pack_gbrain_bundle_prefers_graph_bundle_when_present(self):
        payload = {"bundle_text_with_graph": "graph bundle\n"}
        _pack_gbrain_bundle_text(
            payload,
            bundle_text="plain bundle\n",
            gbrain_consult={"bundle_text": "gbrain bundle"},
        )
        self.assertEqual(payload.get("bundle_text_with_gbrain"), "graph bundle\ngbrain bundle\n")

    def test_pack_adds_gbrain_payload_and_trace_extension(self):
        conn = _connect(":memory:")
        args = build_parser().parse_args(
            [
                "pack",
                "--query",
                "rollout state",
                "--trace",
                "--use-gbrain",
                "on",
            ]
        )
        pack_state = {
            "fts_ids": set(),
            "vec_ids": set(),
            "vec_en_ids": set(),
            "rrf_scores": {1: 0.8},
            "obs_map": {1: {"id": 1, "kind": "fact", "summary": "local memory row", "lang": "en"}},
            "ordered_ids": [1],
            "candidate_limit": 12,
        }
        consult_payload = {
            "schema": gbrain_sidecar.CONSULT_SCHEMA,
            "source": "gbrain",
            "query": {"text": "rollout state"},
            "config": {"gbrain_bin": "gbrain", "limit": 4, "timeout_ms": 1500, "expand": False},
            "ok": True,
            "fail_open": False,
            "timing": {"duration_ms": 12},
            "command": ["gbrain", "call", "query", "{}"],
            "items": [
                {
                    "rank": 1,
                    "recordRef": "gbrain:people/alice",
                    "slug": "people/alice",
                    "title": None,
                    "score": 0.91,
                    "text": "Alice knows the rollout state.",
                    "stale": False,
                    "citations": {"recordRef": "gbrain:people/alice", "slug": "people/alice"},
                }
            ],
            "result_count": 1,
            "error": None,
            "bundle_text": "- [gbrain:people/alice] Alice knows the rollout state.",
        }

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                with patch("openclaw_mem.cli._hybrid_retrieve", return_value=pack_state), patch(
                    "openclaw_mem.cli._hybrid_prefer_synthesis_cards",
                    return_value=([1], {"preferredCardRefs": [], "coveredRawRefs": [], "coverageMap": {}}),
                ), patch("openclaw_mem.cli._pack_gbrain_consult_optional", return_value=consult_payload):
                    args.func(conn, args)
            out = json.loads(buf.getvalue())
        finally:
            conn.close()

        self.assertIn("gbrain", out)
        self.assertIn("bundle_text_with_gbrain", out)
        trace_gbrain = (((out.get("trace") or {}).get("extensions") or {}).get("gbrain") or {})
        self.assertEqual(trace_gbrain.get("result_count"), 1)
        self.assertEqual(trace_gbrain.get("record_refs"), ["gbrain:people/alice"])

    def test_jobs_submit_normalizes_result(self):
        conn = _connect(":memory:")
        args = build_parser().parse_args(
            [
                "gbrain-sidecar",
                "jobs-submit",
                "--name",
                "embed",
                "--params-json",
                '{"slug":"people/alice"}',
            ]
        )
        with patch(
            "openclaw_mem.gbrain_sidecar._run_gbrain_call",
            return_value=gbrain_sidecar.GBrainCallResult(
                ok=True,
                command=["gbrain", "call", "submit_job", "{}"],
                returncode=0,
                stdout="{}",
                stderr="",
                duration_ms=15,
                payload={"id": 7, "name": "embed", "status": "waiting"},
            ),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        conn.close()

        self.assertTrue(out["ok"])
        self.assertEqual(out["phase2_allowed_job"], "embed")
        self.assertEqual((out.get("result") or {}).get("id"), 7)

    def test_jobs_submit_rejects_non_object_params(self):
        conn = _connect(":memory:")
        args = build_parser().parse_args(
            [
                "gbrain-sidecar",
                "jobs-submit",
                "--name",
                "embed",
                "--params-json",
                "[1,2]",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as exc:
            args.func(conn, args)
        out = json.loads(buf.getvalue())
        conn.close()

        self.assertEqual(exc.exception.code, 2)
        self.assertEqual(out["error"], "params must be a JSON object")

    def test_recommend_refresh_emits_graph_recommend_packet(self):
        conn = _connect(":memory:")
        with tempfile.TemporaryDirectory() as td:
            consult_path = Path(td) / "consult.json"
            consult_path.write_text(
                json.dumps(
                    {
                        "schema": gbrain_sidecar.CONSULT_SCHEMA,
                        "ok": True,
                        "query": {"text": "alpha"},
                        "result_count": 1,
                        "items": [{"recordRef": "gbrain:people/alice"}],
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                [
                    "gbrain-sidecar",
                    "recommend-refresh",
                    "--record-ref",
                    "obs:123",
                    "--consult-file",
                    str(consult_path),
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        conn.close()

        self.assertEqual(out["kind"], "openclaw-mem.graph.synth.recommend.v0")
        self.assertEqual(out["items"][0]["target"]["recordRef"], "obs:123")
        self.assertIn("gbrain:people/alice", out["items"][0]["evidence_refs"])

    def test_refresh_canary_apply_runs_bounded_refresh(self):
        conn = _connect(":memory:")
        _insert_observation(conn, {"kind": "note", "summary": "alpha source", "tool_name": "memory_store", "detail": {}})
        compile_args = build_parser().parse_args(
            [
                "graph",
                "--json",
                "synth",
                "compile",
                "--query",
                "alpha",
                "--title",
                "Alpha synthesis",
                "--summary",
                "Alpha synthesis",
            ]
        )
        compile_buf = io.StringIO()
        with redirect_stdout(compile_buf):
            compile_args.func(conn, compile_args)
        card_ref = json.loads(compile_buf.getvalue())["cardRef"]
        _insert_observation(conn, {"kind": "note", "summary": "alpha newer source", "tool_name": "memory_store", "detail": {}})

        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td) / "governor.json"
            packet_path.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.governor-review.v0",
                        "items": [
                            {
                                "candidate_id": "gbrain-refresh:obs:2",
                                "recommended_action": "refresh_card",
                                "decision": "approved_for_apply",
                                "apply_lane": "graph.synth.refresh",
                                "target": {"recordRef": card_ref},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                [
                    "gbrain-sidecar",
                    "refresh-canary",
                    "--from-file",
                    str(packet_path),
                    "--apply",
                    "--run-dir",
                    td,
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(conn, args)
            out = json.loads(buf.getvalue())
        old_id = int(card_ref.split(":", 1)[1])
        old_row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (old_id,)).fetchone()
        old_detail = json.loads(old_row["detail_json"] or "{}")
        conn.close()

        self.assertEqual(out["result"], "applied")
        self.assertEqual(out["applied_count"], 1)
        self.assertEqual(old_detail["graph_synthesis"]["status"], "superseded")

    def test_refresh_canary_dry_run_does_not_burn_retry_budget(self):
        conn = _connect(":memory:")
        _insert_observation(conn, {"kind": "note", "summary": "alpha source", "tool_name": "memory_store", "detail": {}})
        compile_args = build_parser().parse_args(
            [
                "graph",
                "--json",
                "synth",
                "compile",
                "--query",
                "alpha",
                "--title",
                "Alpha synthesis",
                "--summary",
                "Alpha synthesis",
            ]
        )
        compile_buf = io.StringIO()
        with redirect_stdout(compile_buf):
            compile_args.func(conn, compile_args)
        card_ref = json.loads(compile_buf.getvalue())["cardRef"]

        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td) / "governor.json"
            packet_path.write_text(
                json.dumps(
                    {
                        "kind": "openclaw-mem.optimize.governor-review.v0",
                        "items": [
                            {
                                "candidate_id": "gbrain-refresh:obs:2",
                                "recommended_action": "refresh_card",
                                "decision": "approved_for_apply",
                                "apply_lane": "graph.synth.refresh",
                                "target": {"recordRef": card_ref},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dry_args = build_parser().parse_args(
                [
                    "gbrain-sidecar",
                    "refresh-canary",
                    "--from-file",
                    str(packet_path),
                    "--run-dir",
                    td,
                ]
            )
            apply_args = build_parser().parse_args(
                [
                    "gbrain-sidecar",
                    "refresh-canary",
                    "--from-file",
                    str(packet_path),
                    "--apply",
                    "--run-dir",
                    td,
                ]
            )
            dry_buf = io.StringIO()
            with redirect_stdout(dry_buf):
                dry_args.func(conn, dry_args)
            dry_out = json.loads(dry_buf.getvalue())

            apply_buf = io.StringIO()
            with redirect_stdout(apply_buf):
                apply_args.func(conn, apply_args)
            apply_out = json.loads(apply_buf.getvalue())
        conn.close()

        self.assertEqual(dry_out["result"], "dry_run")
        self.assertEqual(apply_out["result"], "applied")
        self.assertEqual(apply_out["applied_count"], 1)


if __name__ == "__main__":
    unittest.main()
