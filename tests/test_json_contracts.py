import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestJsonContracts(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(__file__).resolve().parents[1]
        self.db_path = Path(self.tmpdir.name) / "test.sqlite"
        self.source = Path(self.tmpdir.name) / "openclaw-mem-observations.jsonl"
        self.state_path = Path(self.tmpdir.name) / "triage-state.json"
        self.cron_jobs_path = Path(self.tmpdir.name) / "jobs.json"
        self.cron_jobs_path.write_text('{"jobs": []}', encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_cli(self, *args):
        uv = shutil.which("uv")
        if uv:
            cmd = [
                uv,
                "run",
                "--python",
                "3.13",
                "--",
                "python",
                "-m",
                "openclaw_mem",
                "--db",
                str(self.db_path),
                "--json",
                *args,
            ]
        else:
            cmd = [
                sys.executable,
                "-m",
                "openclaw_mem",
                "--db",
                str(self.db_path),
                "--json",
                *args,
            ]

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )

    def _run_json_ok(self, *args):
        result = self._run_cli(*args)
        if result.returncode != 0:
            self.fail(
                f"CLI failed: rc={result.returncode}\\nstderr=\\n{result.stderr}\\nstdout=\\n{result.stdout}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON output:\\n{result.stdout}")

    def _assert_exact_keys(self, payload, expected, label):
        actual_keys = set(payload.keys())
        expected_keys = set(expected)
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        if missing or extra:
            self.fail(f"{label} keys drifted: missing={missing} extra={extra}")

    def _assert_version_v0(self, payload):
        self.assertIsInstance(payload["version"], dict)
        self.assertEqual(payload["version"].get("schema"), "v0")
        self.assertIn("openclaw_mem", payload["version"])
        self._assert_exact_keys(payload["version"], {"openclaw_mem", "schema"}, "version")

    def _write_source_observation(self, obs):
        line = json.dumps(obs, ensure_ascii=False)
        self.source.write_text(line + "\n", encoding="utf-8")

    def test_harvest_json_contract_v0_empty_source(self):
        out = self._run_json_ok(
            "harvest",
            "--source",
            str(self.source),
            "--no-embed",
            "--no-update-index",
        )

        self.assertEqual(out["kind"], "openclaw-mem.harvest.v0")
        self.assertIsInstance(out["ts"], str)
        self._assert_version_v0(out)
        self._assert_exact_keys(
            out,
            {
                "kind",
                "ts",
                "version",
                "ok",
                "processed_files",
                "ingested",
                "reason",
                "total_seen",
                "graded_filled",
                "skipped_existing",
                "skipped_disabled",
                "scorer_errors",
                "label_counts",
            },
            "harvest(empty)",
        )
        self.assertEqual(
            out["label_counts"],
            {"must_remember": 0, "nice_to_have": 0, "ignore": 0, "unknown": 0},
        )

    def test_harvest_json_contract_v0_ingested(self):
        self._write_source_observation(
            {
                "kind": "test.observation",
                "summary": "contract payload sample",
                "tool_name": "test",
                "detail": {"note": "no explicit importance"},
            }
        )

        out = self._run_json_ok(
            "harvest",
            "--source",
            str(self.source),
            "--no-embed",
            "--no-update-index",
        )

        self.assertEqual(out["kind"], "openclaw-mem.harvest.v0")
        self.assertIsInstance(out["ts"], str)
        self._assert_version_v0(out)
        self._assert_exact_keys(
            out,
            {
                "kind",
                "ts",
                "version",
                "ok",
                "ingested",
                "processed_files",
                "files",
                "recovered",
                "rotated",
                "source",
                "archive",
                "total_seen",
                "graded_filled",
                "skipped_existing",
                "skipped_disabled",
                "scorer_errors",
                "label_counts",
                "embedded",
            },
            "harvest(ingested)",
        )
        self.assertEqual(out["ingested"], 1)
        self.assertEqual(out["processed_files"], 1)
        self.assertEqual(out["embedded"], 0)
        self.assertEqual(out["archive"], "deleted")
        self.assertEqual(out["source"], str(self.source))
        self.assertFalse(out["recovered"])
        self.assertTrue(out["rotated"])
        self.assertEqual(len(out["files"]), 1)
        self.assertNotIn("embed_error", out)

    def test_triage_json_contract_v0(self):
        # triage uses exit codes for automation:
        # - 0: no new issues
        # - 10: attention needed
        result = self._run_cli(
            "triage",
            "--mode",
            "heartbeat",
            "--state-path",
            str(self.state_path),
            "--cron-jobs-path",
            str(self.cron_jobs_path),
        )
        if result.returncode not in (0, 10):
            self.fail(
                f"CLI failed: rc={result.returncode}\\nstderr=\\n{result.stderr}\\nstdout=\\n{result.stdout}"
            )
        try:
            out = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON output:\\n{result.stdout}")

        self.assertEqual(out["kind"], "openclaw-mem.triage.v0")
        self.assertIsInstance(out["ts"], str)
        self._assert_version_v0(out)
        self._assert_exact_keys(
            out,
            {
                "kind",
                "ts",
                "version",
                "ok",
                "mode",
                "dedupe",
                "since_minutes",
                "since_utc",
                "keywords",
                "cron_jobs_path",
                "tasks_since_minutes",
                "tasks_since_utc",
                "importance_min",
                "state_path",
                "needs_attention",
                "observations",
                "cron",
                "tasks",
            },
            "triage",
        )
        self._assert_exact_keys(out["observations"], {"found_total", "found_new", "matches"}, "triage.observations")
        self._assert_exact_keys(out["cron"], {"found_total", "found_new", "matches"}, "triage.cron")
        self._assert_exact_keys(out["tasks"], {"found_total", "found_new", "matches"}, "triage.tasks")

    def test_profile_json_contract_v0(self):
        out = self._run_json_ok("profile")

        self.assertEqual(out["kind"], "openclaw-mem.profile.v0")
        self.assertIsInstance(out["ts"], str)
        self._assert_version_v0(out)
        self._assert_exact_keys(
            out,
            {
                "kind",
                "ts",
                "version",
                "db",
                "observations",
                "importance",
                "embeddings",
                "recent",
            },
            "profile",
        )
        self._assert_exact_keys(
            out["observations"],
            {"count", "min_ts", "max_ts", "kinds", "tools"},
            "profile.observations",
        )
        self._assert_exact_keys(
            out["importance"],
            {"present", "missing", "label_counts", "avg_score"},
            "profile.importance",
        )
        self._assert_exact_keys(out["embeddings"], {"original", "english"}, "profile.embeddings")
        self._assert_exact_keys(out["embeddings"]["original"], {"count", "models"}, "profile.embeddings.original")
        self._assert_exact_keys(out["embeddings"]["english"], {"count", "models"}, "profile.embeddings.english")

    def test_pack_trace_json_contract_v1(self):
        self._write_source_observation(
            {
                "kind": "test.observation",
                "summary": "pack trace contract sample",
                "tool_name": "test",
                "detail": {"note": "trace coverage"},
            }
        )
        harvest_out = self._run_json_ok(
            "harvest",
            "--source",
            str(self.source),
            "--no-embed",
            "--no-update-index",
        )
        self.assertEqual(harvest_out["ingested"], 1)

        out = self._run_json_ok(
            "pack",
            "--query",
            "pack trace contract",
            "--trace",
            "--limit",
            "3",
            "--budget-tokens",
            "200",
        )
        self._assert_exact_keys(out, {"bundle_text", "items", "citations", "trace"}, "pack")

        trace = out["trace"]
        self.assertEqual(trace["kind"], "openclaw-mem.pack.trace.v1")
        self._assert_exact_keys(
            trace,
            {
                "kind",
                "ts",
                "version",
                "query",
                "budgets",
                "lanes",
                "candidates",
                "output",
                "timing",
                "extensions",
            },
            "pack.trace",
        )
        self.assertEqual(trace["version"].get("schema"), "v1")
        self._assert_exact_keys(trace["version"], {"openclaw_mem", "schema"}, "pack.trace.version")
        self._assert_exact_keys(trace["query"], {"text", "scope", "intent"}, "pack.trace.query")
        self._assert_exact_keys(
            trace["budgets"],
            {"budgetTokens", "maxItems", "maxL2Items", "niceCap"},
            "pack.trace.budgets",
        )
        self.assertIsInstance(trace["lanes"], list)
        self.assertGreaterEqual(len(trace["lanes"]), 1)
        lane = trace["lanes"][0]
        self._assert_exact_keys(lane, {"name", "source", "searched", "retrievers"}, "pack.trace.lanes[0]")
        if lane["retrievers"]:
            self._assert_exact_keys(
                lane["retrievers"][0],
                {"kind", "topK", "k"},
                "pack.trace.lanes[0].retrievers[0]",
            )

        self.assertIsInstance(trace["candidates"], list)
        if trace["candidates"]:
            candidate = trace["candidates"][0]
            self._assert_exact_keys(
                candidate,
                {"id", "layer", "importance", "trust", "scores", "decision", "citations"},
                "pack.trace.candidates[0]",
            )
            self._assert_exact_keys(
                candidate["scores"],
                {"rrf", "fts", "semantic"},
                "pack.trace.candidates[0].scores",
            )
            self._assert_exact_keys(
                candidate["decision"],
                {"included", "reason", "rationale", "caps"},
                "pack.trace.candidates[0].decision",
            )
            self._assert_exact_keys(
                candidate["decision"]["caps"],
                {"niceCapHit", "l2CapHit"},
                "pack.trace.candidates[0].decision.caps",
            )
            self._assert_exact_keys(
                candidate["citations"],
                {"url", "recordRef"},
                "pack.trace.candidates[0].citations",
            )

        self._assert_exact_keys(
            trace["output"],
            {
                "includedCount",
                "excludedCount",
                "l2IncludedCount",
                "citationsCount",
                "refreshedRecordRefs",
                "coverage",
            },
            "pack.trace.output",
        )
        self._assert_exact_keys(
            trace["output"]["coverage"],
            {
                "rationaleMissingCount",
                "citationMissingCount",
                "allIncludedHaveRationale",
                "allIncludedHaveCitations",
            },
            "pack.trace.output.coverage",
        )
        self._assert_exact_keys(trace["timing"], {"durationMs"}, "pack.trace.timing")
        self.assertIsInstance(trace["extensions"], dict)


if __name__ == "__main__":
    unittest.main()
