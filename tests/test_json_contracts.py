import json
import os
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

    def _run_cli(self, *args, input_data: str | None = None, env: dict | None = None):
        uv = shutil.which("uv")
        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)

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
            input=input_data,
            env=env_vars,
        )

    def _run_json_ok(self, *args, **kwargs):
        result = self._run_cli(*args, **kwargs)
        if result.returncode != 0:
            self.fail(
                f"CLI failed: rc={result.returncode}\\nstderr=\\n{result.stderr}\\nstdout=\\n{result.stdout}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON output:\\n{result.stdout}")

    def test_pack_context_pack_json_contract_v1(self):
        self._write_source_observation(
            {
                "kind": "fact",
                "summary": "context pack contract sample",
                "summary_en": "context pack contract sample",
                "tool_name": "test",
                "detail": {"note": "contract baseline"},
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
            "context pack",
            "--json",
            "--trace",
            "--limit",
            "4",
            "--budget-tokens",
            "220",
        )
        self._assert_exact_keys(
            out,
            {"bundle_text", "items", "citations", "trace", "context_pack"},
            "pack",
        )

        context_pack = out["context_pack"]
        self._assert_exact_keys(
            context_pack,
            {"schema", "meta", "bundle_text", "items", "notes"},
            "pack.context_pack",
        )
        self.assertEqual(context_pack["schema"], "openclaw-mem.context-pack.v1")
        self.assertEqual(context_pack["bundle_text"], out["bundle_text"])
        self.assertIsInstance(context_pack["items"], list)
        self.assertIsInstance(context_pack["notes"], dict)
        self._assert_exact_keys(context_pack["notes"], {"how_to_use"}, "pack.context_pack.notes")
        if context_pack["items"]:
            item = context_pack["items"][0]
            self._assert_exact_keys(
                item,
                {"recordRef", "layer", "type", "importance", "trust", "text", "citations"},
                "pack.context_pack.items[0]",
            )
            self._assert_exact_keys(item["citations"], {"url", "recordRef"}, "pack.context_pack.items[0].citations")
            self.assertIsInstance(item["recordRef"], str)

        self._assert_exact_keys(context_pack["meta"], {"ts", "query", "scope", "budgetTokens", "maxItems"}, "pack.context_pack.meta")

    def test_artifact_cli_json_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            env = {"OPENCLAW_STATE_DIR": td}
            payload = Path(td) / "tool-output.txt"
            payload.write_text("A" * 250 + "\n" + "B" * 250, encoding="utf-8")

            stash = self._run_json_ok(
                "artifact",
                "stash",
                "--from",
                str(payload),
                "--meta-json",
                '{"source":"json-contract-test"}',
                env=env,
            )
            self._assert_exact_keys(
                stash,
                {"schema", "handle", "sha256", "bytes", "createdAt", "kind", "meta"},
                "artifact.stash",
            )
            self.assertEqual(stash["schema"], "openclaw-mem.artifact.stash.v1")

            fetch = self._run_json_ok(
                "artifact",
                "fetch",
                stash["handle"],
                "--mode",
                "headtail",
                "--max-chars",
                "20",
                env=env,
            )
            self._assert_exact_keys(
                fetch,
                {"schema", "handle", "selector", "text"},
                "artifact.fetch",
            )
            self.assertEqual(fetch["schema"], "openclaw-mem.artifact.fetch.v1")
            self.assertEqual(fetch["selector"], {"mode": "headtail", "maxChars": 20})

            peek = self._run_json_ok(
                "artifact",
                "peek",
                stash["handle"],
                "--preview-chars",
                "18",
                env=env,
            )
            self._assert_exact_keys(
                peek,
                {"schema", "handle", "sha256", "bytes", "createdAt", "kind", "compression", "meta", "preview", "previewChars"},
                "artifact.peek",
            )
            self.assertEqual(peek["schema"], "openclaw-mem.artifact.peek.v1")
            self.assertEqual(len(peek["preview"]), 18)

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
        self._assert_exact_keys(out, {"bundle_text", "items", "citations", "context_pack", "trace"}, "pack")

        context_pack = out["context_pack"]
        self.assertEqual(context_pack["schema"], "openclaw-mem.context-pack.v1")
        self._assert_exact_keys(context_pack, {"schema", "meta", "bundle_text", "items", "notes"}, "pack.context_pack")
        self._assert_exact_keys(
            context_pack["meta"],
            {"ts", "query", "scope", "budgetTokens", "maxItems"},
            "pack.context_pack.meta",
        )
        self._assert_exact_keys(context_pack["notes"], {"how_to_use"}, "pack.context_pack.notes")
        self.assertIsInstance(context_pack["items"], list)
        self.assertEqual(context_pack["bundle_text"], out["bundle_text"])
        if context_pack["items"]:
            item = context_pack["items"][0]
            self._assert_exact_keys(
                item,
                {"recordRef", "layer", "type", "importance", "trust", "text", "citations"},
                "pack.context_pack.items[0]",
            )
            self._assert_exact_keys(
                item["citations"],
                {"url", "recordRef"},
                "pack.context_pack.items[0].citations",
            )

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

        lifecycle = trace["extensions"].get("lifecycle_shadow")
        self.assertIsInstance(lifecycle, dict)
        self._assert_exact_keys(
            lifecycle,
            {"kind", "mode", "ts", "query", "selection", "counts", "reasons", "policies", "mutation", "storage"},
            "pack.trace.extensions.lifecycle_shadow",
        )
        self._assert_exact_keys(lifecycle["query"], {"hash", "chars"}, "pack.trace.extensions.lifecycle_shadow.query")
        self._assert_exact_keys(
            lifecycle["selection"],
            {"pack_selected_refs", "citation_record_refs", "trace_refreshed_record_refs", "selection_signature"},
            "pack.trace.extensions.lifecycle_shadow.selection",
        )
        self._assert_exact_keys(
            lifecycle["counts"],
            {
                "selected_total",
                "citation_total",
                "candidate_total",
                "excluded_total",
                "selected_by_trust",
                "selected_by_importance",
            },
            "pack.trace.extensions.lifecycle_shadow.counts",
        )
        self._assert_exact_keys(
            lifecycle["mutation"],
            {
                "memory_mutation",
                "auto_archive_applied",
                "auto_mutation_applied",
                "writes_observations",
                "writes_embeddings",
                "writes_lifecycle_state",
                "writes_shadow_log",
            },
            "pack.trace.extensions.lifecycle_shadow.mutation",
        )
        self.assertEqual(lifecycle["mutation"]["memory_mutation"], "none")

    def test_pack_trust_policy_contract_v1(self):
        rows = [
            {
                "kind": "test.observation",
                "summary": "trusted trust policy row",
                "tool_name": "test",
                "detail": {"trust_tier": "trusted"},
            },
            {
                "kind": "test.observation",
                "summary": "quarantine trust policy row",
                "tool_name": "test",
                "detail": {"trust_tier": "quarantine"},
            },
            {
                "kind": "test.observation",
                "summary": "unknown trust policy row",
                "tool_name": "test",
                "detail": {},
            },
        ]
        self.source.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        harvest_out = self._run_json_ok(
            "harvest",
            "--source",
            str(self.source),
            "--no-embed",
            "--no-update-index",
        )
        self.assertEqual(harvest_out["ingested"], 3)

        out = self._run_json_ok(
            "pack",
            "--query",
            "trust policy",
            "--trace",
            "--limit",
            "3",
            "--budget-tokens",
            "400",
            "--pack-trust-policy",
            "exclude_quarantined_fail_open",
        )

        self._assert_exact_keys(
            out,
            {"bundle_text", "items", "citations", "context_pack", "trace", "trust_policy", "policy_surface"},
            "pack.trust_policy",
        )

        policy = out["trust_policy"]
        self._assert_exact_keys(
            policy,
            {
                "kind",
                "mode",
                "checked_count",
                "included_count",
                "excluded_count",
                "fail_open_count",
                "decision_reason_counts",
                "decisions",
                "selected_refs",
            },
            "pack.trust_policy",
        )
        self.assertEqual(policy["kind"], "openclaw-mem.pack.trust-policy.v1")
        self.assertEqual(policy["mode"], "exclude_quarantined_fail_open")
        self.assertEqual(policy["checked_count"], 3)
        self.assertEqual(policy["included_count"], 2)
        self.assertEqual(policy["excluded_count"], 1)
        self.assertEqual(policy["fail_open_count"], 1)
        self.assertEqual(
            policy["decision_reason_counts"],
            {
                "trust_allowed": 1,
                "trust_quarantined_excluded": 1,
                "trust_unknown_fail_open": 1,
            },
        )
        self.assertEqual(policy["selected_refs"], ["obs:1", "obs:3"])

        selected_refs = [item["recordRef"] for item in out["items"]]
        citation_refs = [item["recordRef"] for item in out["citations"]]
        self.assertEqual(selected_refs, ["obs:1", "obs:3"])
        self.assertEqual(citation_refs, ["obs:1", "obs:3"])

        policy_surface = out["policy_surface"]
        self._assert_exact_keys(
            policy_surface,
            {"kind", "selection", "counts", "reasons", "policies", "consistency"},
            "pack.policy_surface",
        )
        self._assert_exact_keys(
            policy_surface["selection"],
            {
                "pack_selected_refs",
                "citation_record_refs",
                "trust_selected_refs",
                "graph_selected_refs",
                "shared_pack_and_graph_refs",
            },
            "pack.policy_surface.selection",
        )
        self._assert_exact_keys(
            policy_surface["counts"],
            {"pack_selected_count", "citation_count", "candidate_count", "pack_excluded_count"},
            "pack.policy_surface.counts",
        )
        self._assert_exact_keys(
            policy_surface["reasons"],
            {
                "pack_included_reason_counts",
                "pack_excluded_reason_counts",
                "trust_policy_reason_counts",
                "graph_provenance_reason_counts",
            },
            "pack.policy_surface.reasons",
        )
        self._assert_exact_keys(
            policy_surface["policies"],
            {"trust_policy", "graph_provenance_policy"},
            "pack.policy_surface.policies",
        )
        self._assert_exact_keys(
            policy_surface["consistency"],
            {
                "pack_items_match_citations",
                "pack_items_subset_of_trust_selected_refs",
                "pack_items_missing_from_trust_selected_refs",
            },
            "pack.policy_surface.consistency",
        )

        self.assertEqual(policy_surface["kind"], "openclaw-mem.pack.policy-surface.v1")
        self.assertEqual(policy_surface["selection"]["pack_selected_refs"], selected_refs)
        self.assertEqual(policy_surface["selection"]["citation_record_refs"], citation_refs)
        self.assertEqual(policy_surface["selection"]["trust_selected_refs"], policy["selected_refs"])
        self.assertIsNone(policy_surface["selection"]["graph_selected_refs"])
        self.assertIsNone(policy_surface["selection"]["shared_pack_and_graph_refs"])
        self.assertEqual(policy_surface["reasons"]["trust_policy_reason_counts"], policy["decision_reason_counts"])
        self.assertEqual(policy_surface["reasons"]["graph_provenance_reason_counts"], {})
        self.assertEqual(policy_surface["policies"]["trust_policy"]["selected_refs"], policy["selected_refs"])
        self.assertIsNone(policy_surface["policies"]["graph_provenance_policy"])
        self.assertTrue(policy_surface["consistency"]["pack_items_match_citations"])
        self.assertTrue(policy_surface["consistency"]["pack_items_subset_of_trust_selected_refs"])
        self.assertEqual(policy_surface["consistency"]["pack_items_missing_from_trust_selected_refs"], [])

        self.assertEqual(out["trace"]["extensions"].get("trust_policy"), policy)
        self.assertEqual(out["trace"]["extensions"].get("policy_surface"), policy_surface)

        lifecycle = out["trace"]["extensions"].get("lifecycle_shadow")
        self.assertIsInstance(lifecycle, dict)
        self.assertEqual(lifecycle["kind"], "openclaw-mem.pack.lifecycle-shadow.v1")
        self.assertEqual(lifecycle["selection"]["pack_selected_refs"], selected_refs)
        self.assertEqual(lifecycle["selection"]["citation_record_refs"], citation_refs)
        self.assertEqual(lifecycle["selection"]["trace_refreshed_record_refs"], selected_refs)
        self.assertEqual(lifecycle["counts"]["selected_total"], len(selected_refs))
        self.assertEqual(lifecycle["counts"]["citation_total"], len(citation_refs))
        self.assertEqual(lifecycle["counts"]["candidate_total"], 3)
        self.assertEqual(lifecycle["counts"]["excluded_total"], 1)
        self.assertEqual(lifecycle["mutation"]["memory_mutation"], "none")
        self.assertEqual(lifecycle["mutation"]["auto_archive_applied"], 0)
        self.assertEqual(lifecycle["mutation"]["auto_mutation_applied"], 0)


if __name__ == "__main__":
    unittest.main()
