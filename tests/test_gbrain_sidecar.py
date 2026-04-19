from __future__ import annotations

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from openclaw_mem import gbrain_sidecar
from openclaw_mem.cli import _connect, build_parser


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


class TestGBrainSidecarCLI(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
