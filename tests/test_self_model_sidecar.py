import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from openclaw_mem import self_model_sidecar
from openclaw_mem.cli import _connect, build_parser
from openclaw_mem.continuity_soak import SoakConfig, compute_drift_summary, ensure_baseline, evaluate_soak


class TestSelfModelSidecarCli(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _connect(":memory:")
        self.conn.execute(
            "INSERT INTO observations (ts, kind, summary, summary_en, lang, tool_name, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-04-18T08:00:00Z",
                "conversation.user",
                "Ship the additive side-car, keep topology unchanged, and avoid anthropomorphism.",
                "",
                "en",
                "message",
                json.dumps({"scope": "proj-a", "session_id": "s1", "role": "engineer operator"}),
            ),
        )
        self.conn.execute(
            "INSERT INTO episodic_events (event_id, ts_ms, scope, session_id, agent_id, type, summary, payload_json, refs_json, redacted, schema_version, created_at, search_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "evt-1",
                1713427200000,
                "proj-a",
                "s1",
                "lyria",
                "conversation.assistant",
                "Use receipts, verifier checks, and release controls.",
                json.dumps({"goal": "ship_mvp", "style": "direct warm concise", "stance": "Nuwa is prior only"}),
                "[]",
                0,
                "v0",
                "2026-04-18T08:05:00Z",
                "Use receipts, verifier checks, and release controls.",
            ),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _run(self, argv):
        args = build_parser().parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            args.func(self.conn, args)
        return json.loads(buf.getvalue())

    def _run_text(self, argv):
        args = build_parser().parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            args.func(self.conn, args)
        return buf.getvalue()

    def _observation_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0])

    def _event_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM episodic_events").fetchone()[0])

    def test_parser_continuity_current(self):
        args = build_parser().parse_args(["continuity", "current", "--json"])
        self.assertEqual(args.cmd, "continuity")
        self.assertEqual(args.self_cmd, "current")

        adjudication = build_parser().parse_args(["continuity", "adjudication", "--json"])
        self.assertEqual(adjudication.self_cmd, "adjudication")

        alias = build_parser().parse_args(["self", "current", "--json"])
        self.assertEqual(alias.cmd, "self")
        self.assertEqual(alias.self_cmd, "current")

    def test_readonly_guard_blocks_core_writes(self):
        with self.assertRaisesRegex(Exception, "attempt to write a readonly database"):
            with self_model_sidecar.db_readonly_guard(self.conn):
                self.conn.execute(
                    "INSERT INTO observations (ts, kind, summary, summary_en, lang, tool_name, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("2026-04-18T08:10:00Z", "conversation.user", "blocked write", "", "en", "message", "{}"),
                )

    def test_current_persist_and_attachment_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs_before = self._observation_count()
            events_before = self._event_count()
            persona_path = Path(tmp) / "persona.json"
            persona_path.write_text(
                json.dumps(
                    {
                        "roles": {"engineer": 1.0, "operator": 0.8},
                        "goals": {"ship_mvp": 1.0},
                        "stances": {"sidecar_only": 1.0},
                        "style_commitments": {"evidence_first": 1.0},
                    }
                ),
                encoding="utf-8",
            )
            current = self._run(
                [
                    "continuity",
                    "current",
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--persona-file",
                    str(persona_path),
                    "--run-dir",
                    tmp,
                    "--persist",
                    "--json",
                ]
            )
            self.assertEqual(current["schema"], "openclaw-mem.self-model.snapshot.v0")
            self.assertIn("role:engineer", current["roles"])
            self.assertIn("goal:ship_mvp", current["goals"])
            self.assertTrue(current["evidence_summary"]["derived"])
            self.assertTrue(current["evidence_summary"]["non_authoritative"])
            self.assertEqual(current["evidence_summary"]["operator_surface"], "continuity")
            self.assertTrue(current["provenance"]["query_only_enforced"])
            snapshot_path = current["persisted"]["snapshot_path"]
            amap = self._run(["continuity", "attachment-map", "--snapshot", snapshot_path, "--json"])
            self.assertEqual(amap["schema"], "openclaw-mem.self-model.attachment-map.v0")
            self.assertGreaterEqual(amap["counts"]["goal"], 1)
            top = amap["top_attachments"][0]
            self.assertIn(top["band"], {"low", "medium", "high"})
            self.assertIn(top["fragility"], {"fragile", "watch", "supported", "contested"})
            self.assertIn(top["adjudication_state"], {"accepted", "tentative", "fragile", "contested", "retired", "rejected"})
            self.assertTrue(top["provenance"]["derived"])

            adjudication = self._run(["continuity", "adjudication", "--snapshot", snapshot_path, "--json"])
            self.assertEqual(adjudication["schema"], "openclaw-mem.self-model.adjudication.v0")
            self.assertEqual(adjudication["policy_version"], self_model_sidecar.ADJUDICATION_POLICY_VERSION)

            public_summary = self._run(["continuity", "public-summary", "--snapshot", snapshot_path, "--json"])
            self.assertEqual(public_summary["schema"], "openclaw-mem.self-model.public-summary.v0")
            self.assertTrue(public_summary["provenance"]["public_safe"])

            explain = self._run(["continuity", "explain", "--snapshot", snapshot_path, "--stance", "goal:ship_mvp", "--run-dir", tmp, "--json"])
            self.assertEqual(explain["schema"], "openclaw-mem.self-model.explain.v0")
            self.assertTrue(explain["found"])
            self.assertEqual(explain["attachment"]["id"], "goal:ship_mvp")

            sensitivity = self._run(["continuity", "sensitivity", "--snapshot", snapshot_path, "--stance", "goal:ship_mvp", "--json"])
            self.assertEqual(sensitivity["schema"], "openclaw-mem.self-model.sensitivity.v0")
            self.assertEqual(sensitivity["target_scope"], "goal:ship_mvp")
            self.assertEqual(len(sensitivity["analyses"]), 1)

            ledger = self._run(["continuity", "ledger", "--snapshot", snapshot_path, "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            self.assertEqual(ledger["schema"], "openclaw-mem.self-model.claim-ledger.v0")
            self.assertGreaterEqual(ledger["node_count"], 1)
            self.assertTrue(ledger["nodes"][0]["provenance"]["derived"])

            mirror = self._run(["continuity", "mirror", "--snapshot", snapshot_path, "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            self.assertEqual(mirror["schema"], "openclaw-mem.self-model.mirror.v0")
            self.assertIn("current_continuity", mirror)
            self.assertIn("suggested_governance_actions", mirror)
            self.assertIn("governance_action_summary", mirror)
            self.assertLessEqual(len(mirror["suggested_governance_actions"]), 8)
            mirror_md = self._run_text(["continuity", "mirror", "--snapshot", snapshot_path, "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--markdown"])
            self.assertIn("# Continuity Mirror", mirror_md)
            self.assertIn("Derived, editable, non-authoritative", mirror_md)
            self.assertIn("Showing", mirror_md)

            rule_table = self._run(["continuity", "rule-table", "--json"])
            self.assertEqual(rule_table["schema"], "openclaw-mem.self-model.adjudication-rule-table.v0")
            self.assertIn("prior_only_claims_never_accepted", rule_table["hard_guards"])

            golden = self._run(["continuity", "golden-eval", "--snapshot", snapshot_path, "--json"])
            self.assertEqual(golden["schema"], "openclaw-mem.self-model.golden-eval.v0")
            self.assertGreaterEqual(golden["case_count"], 1)
            self.assertIn("identity_consistency", golden["metrics"])
            by_id = {item["id"]: item for item in golden["results"]}
            self.assertTrue(by_id["no_consciousness_claim"]["passed"])
            self.assertTrue(by_id["no_soul_claim"]["passed"])

            governance = self._run(["continuity", "governance", "--snapshot", snapshot_path, "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            self.assertEqual(governance["schema"], "openclaw-mem.self-model.governance-review.v0")
            self.assertEqual(governance["operator_contract"], "Review suggestions only; apply requires explicit continuity release command with receipts.")

            wording = self._run(["continuity", "wording-lint", "--snapshot", snapshot_path, "--json"])
            self.assertEqual(wording["schema"], "openclaw-mem.self-model.wording-lint.v0")
            self.assertTrue(wording["ok"])
            self.assertEqual(obs_before, self._observation_count())
            self.assertEqual(events_before, self._event_count())

    def test_release_diff_and_compare_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs_before = self._observation_count()
            events_before = self._event_count()
            baseline = Path(tmp) / "baseline.json"
            baseline.write_text(json.dumps({"style_commitments": {"warm": 1.0}}), encoding="utf-8")
            candidate = Path(tmp) / "candidate.json"
            candidate.write_text(json.dumps({"style_commitments": {"concise": 1.0}, "goals": {"verify": 1.0}}), encoding="utf-8")

            before = self._run(["continuity", "current", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--persist", "--json"])
            release = self._run(
                [
                    "continuity",
                    "release",
                    "--run-dir",
                    tmp,
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--stance",
                    "goal:ship_mvp",
                    "--reason",
                    "testing weakening flow",
                    "--mode",
                    "weaken",
                    "--factor",
                    "0.2",
                    "--json",
                ]
            )
            self.assertEqual(release["schema"], "openclaw-mem.self-model.release-receipt.v0")
            self.assertEqual(release["scope"], "proj-a")
            self.assertEqual(release["session_id"], "s1")
            self.assertEqual(release["before_release_state"], "active")
            self.assertEqual(release["after_release_state"], "weakening")
            after = self._run(["continuity", "current", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--persist", "--json"])
            diff = self._run(["continuity", "diff", "--from", before["persisted"]["snapshot_path"], "--to", after["persisted"]["snapshot_path"], "--json"])
            self.assertEqual(diff["schema"], "openclaw-mem.self-model.diff.v0")
            changed_ids = {item["id"] for item in diff["changed"]}
            self.assertIn("goal:ship_mvp", changed_ids)
            self.assertIn(diff["drift_class"], {"no_op", "organic", "suspicious"})
            self.assertEqual(diff["provenance"]["arbiter_policy"], "openclaw-mem-memory-of-record-wins")

            rebind = self._run(
                [
                    "continuity",
                    "release",
                    "--run-dir",
                    tmp,
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--stance",
                    "goal:ship_mvp",
                    "--reason",
                    "testing rebind flow",
                    "--mode",
                    "rebind",
                    "--json",
                ]
            )
            self.assertEqual(rebind["before_release_state"], "weakening")
            self.assertEqual(rebind["after_release_state"], "active")
            rebound = self._run(["continuity", "current", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--persist", "--json"])
            rebound_goal = next(item for item in rebound["attachments"] if item["id"] == "goal:ship_mvp")
            self.assertEqual(rebound_goal["release_state"], "active")

            retire = self._run(
                [
                    "continuity",
                    "release",
                    "--run-dir",
                    tmp,
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--stance",
                    "goal:ship_mvp",
                    "--reason",
                    "testing retirement flow",
                    "--mode",
                    "retire",
                    "--json",
                ]
            )
            self.assertEqual(retire["before_release_state"], "active")
            self.assertEqual(retire["after_release_state"], "retired")
            retired = self._run(["continuity", "current", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--persist", "--json"])
            self.assertNotIn("goal:ship_mvp", {item["id"] for item in retired["attachments"]})

            history = self._run(["continuity", "release-history", "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--stance", "goal:ship_mvp", "--json"])
            self.assertEqual(history["schema"], "openclaw-mem.self-model.release-history.v0")
            self.assertEqual(history["receipt_count"], 3)
            self.assertEqual(history["current_state_by_stance"]["goal:ship_mvp"], "retired")

            patterns = self._run(["continuity", "patterns", "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            self.assertEqual(patterns["schema"], "openclaw-mem.self-model.pattern-report.v0")
            self.assertGreaterEqual(patterns["snapshot_count"], 3)
            self.assertTrue(Path(patterns["path"]).exists())

            triggers = self._run(["continuity", "triggers", "--snapshot", after["persisted"]["snapshot_path"], "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            self.assertEqual(triggers["schema"], "openclaw-mem.self-model.trigger-report.v0")

            interventions = self._run(["continuity", "interventions", "--snapshot", after["persisted"]["snapshot_path"], "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            self.assertEqual(interventions["schema"], "openclaw-mem.self-model.intervention-report.v0")

            compare = self._run(
                [
                    "continuity",
                    "compare-migration",
                    "--scope",
                    "proj-a",
                    "--session-id",
                    "s1",
                    "--run-dir",
                    tmp,
                    "--baseline-persona-file",
                    str(baseline),
                    "--candidate-persona-file",
                    str(candidate),
                    "--persist",
                    "--json",
                ]
            )
            self.assertEqual(compare["schema"], "openclaw-mem.self-model.compare-migration.v0")
            self.assertNotIn("latest_path", compare["baseline_paths"])
            self.assertNotIn("latest_path", compare["candidate_paths"])
            self.assertGreaterEqual(compare["diff"]["summary"]["changed"] + compare["diff"]["summary"]["added"], 1)
            self.assertTrue(compare["provenance"]["query_only_enforced"])

            compare_sessions = self._run(
                [
                    "continuity",
                    "compare-sessions",
                    "--left-scope",
                    "proj-a",
                    "--left-session-id",
                    "s1",
                    "--right-scope",
                    "proj-a",
                    "--right-session-id",
                    "missing",
                    "--run-dir",
                    tmp,
                    "--persist",
                    "--json",
                ]
            )
            self.assertEqual(compare_sessions["schema"], "openclaw-mem.self-model.compare-sessions.v0")
            self.assertIn("left_paths", compare_sessions)
            self.assertIn("right_paths", compare_sessions)
            self.assertTrue(Path(compare_sessions["left_paths"]["snapshot_path"]).exists())
            self.assertTrue(Path(compare_sessions["right_paths"]["snapshot_path"]).exists())
            self.assertEqual(json.loads(Path(compare_sessions["left_paths"]["snapshot_path"]).read_text(encoding="utf-8"))["schema"], "openclaw-mem.self-model.snapshot.v0")
            self.assertEqual(json.loads(Path(compare_sessions["right_paths"]["snapshot_path"]).read_text(encoding="utf-8"))["schema"], "openclaw-mem.self-model.snapshot.v0")

            pattern_count_before = len(list((Path(tmp) / "patterns").glob("pattern-report-*.json"))) if (Path(tmp) / "patterns").exists() else 0
            self._run(["continuity", "triggers", "--snapshot", after["persisted"]["snapshot_path"], "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            pattern_count_after_trigger = len(list((Path(tmp) / "patterns").glob("pattern-report-*.json"))) if (Path(tmp) / "patterns").exists() else 0
            self.assertEqual(pattern_count_before, pattern_count_after_trigger)

            self._run(["continuity", "interventions", "--snapshot", after["persisted"]["snapshot_path"], "--run-dir", tmp, "--scope", "proj-a", "--session-id", "s1", "--json"])
            pattern_count_after_intervention = len(list((Path(tmp) / "patterns").glob("pattern-report-*.json"))) if (Path(tmp) / "patterns").exists() else 0
            self.assertEqual(pattern_count_before, pattern_count_after_intervention)

            threat = self._run(["continuity", "threat-feed", "--snapshot", after["persisted"]["snapshot_path"], "--json"])
            self.assertEqual(threat["schema"], "openclaw-mem.self-model.threat-feed.v0")
            self.assertIn("provenance", threat)

            enabled = self._run(["continuity", "enable", "--run-dir", tmp, "--cadence-seconds", "60", "--json"])
            self.assertTrue(enabled["enabled"])
            self.assertIn("receipt_path", enabled)
            status = self._run(["continuity", "status", "--run-dir", tmp, "--json"])
            self.assertTrue(status["control"]["enabled"])
            self.assertTrue(status["residue"]["latest_pointer_present"])
            autorun = self._run(["continuity", "auto-run", "--scope", "proj-a", "--session-id", "s1", "--run-dir", tmp, "--cycles", "1", "--json"])
            self.assertTrue(autorun["ok"])
            self.assertEqual(len(autorun["runs"]), 1)
            disabled = self._run(["continuity", "disable", "--run-dir", tmp, "--json"])
            self.assertFalse(disabled["enabled"])
            self.assertTrue(disabled["cleared_latest_pointer"])
            self.assertEqual(disabled["cleared_snapshot_id"], retired["snapshot_id"])
            disabled_status = self._run(["continuity", "status", "--run-dir", tmp, "--json"])
            self.assertIsNone(disabled_status["latest_snapshot_id"])
            self.assertFalse(disabled_status["residue"]["latest_pointer_present"])
            self.assertEqual(obs_before, self._observation_count())
            self.assertEqual(events_before, self._event_count())

    def test_diff_marks_suspicious_large_delta(self):
        before = {
            "snapshot_id": "before",
            "source_digest": "same-source",
            "attachments": [{"id": "goal:verify", "attachment_score": 0.2, "confidence": 0.3, "fragility": "supported"}],
        }
        after = {
            "snapshot_id": "after",
            "source_digest": "different-source",
            "attachments": [{"id": "goal:verify", "attachment_score": 0.7, "confidence": 0.8, "fragility": "fragile"}],
        }
        diff = self_model_sidecar.compare_snapshots(before, after)
        self.assertEqual(diff["drift_class"], "suspicious")
        self.assertIn("large_delta:goal:verify", diff["risk_flags"])
        self.assertIn("fragile_claim:goal:verify", diff["risk_flags"])

    def test_adjudication_negative_fixtures(self):
        attachments = self_model_sidecar._with_attachment_provenance(
            [
                {
                    "id": "goal:prior_only",
                    "category": "goal",
                    "label": "prior only",
                    "attachment_score": 0.6,
                    "evidence_count": 0,
                    "evidence_ids": [],
                    "source_classes": [],
                    "prior_weight": 1.0,
                    "contradiction_hits": 0,
                    "matched_keywords": [],
                    "release_state": "active",
                },
                {
                    "id": "goal:thin_and_coherent",
                    "category": "goal",
                    "label": "thin and coherent",
                    "attachment_score": 0.8,
                    "evidence_count": 1,
                    "evidence_ids": ["obs:1"],
                    "source_classes": ["observation"],
                    "prior_weight": 0.2,
                    "contradiction_hits": 0,
                    "matched_keywords": ["ship"],
                    "release_state": "active",
                },
                {
                    "id": "goal:contested",
                    "category": "goal",
                    "label": "contested",
                    "attachment_score": 0.7,
                    "evidence_count": 1,
                    "evidence_ids": ["obs:2"],
                    "source_classes": ["observation"],
                    "prior_weight": 0.0,
                    "contradiction_hits": 2,
                    "matched_keywords": ["ship"],
                    "release_state": "active",
                },
                {
                    "id": "goal:revalidation_needed",
                    "category": "goal",
                    "label": "revalidation needed",
                    "attachment_score": 0.9,
                    "evidence_count": 2,
                    "evidence_ids": ["obs:3", "evt:3"],
                    "source_classes": ["observation", "episodic_event"],
                    "prior_weight": 0.0,
                    "contradiction_hits": 0,
                    "matched_keywords": ["verify"],
                    "release_state": "weakening",
                },
                {
                    "id": "goal:unsupported",
                    "category": "goal",
                    "label": "unsupported",
                    "attachment_score": 0.0,
                    "evidence_count": 0,
                    "evidence_ids": [],
                    "source_classes": [],
                    "prior_weight": 0.0,
                    "contradiction_hits": 0,
                    "matched_keywords": [],
                    "release_state": "active",
                },
            ]
        )
        by_id = {item["id"]: item for item in attachments}
        self.assertEqual(by_id["goal:prior_only"]["adjudication_state"], "tentative")
        self.assertFalse(by_id["goal:prior_only"]["publication"]["public_visible"])
        self.assertEqual(by_id["goal:thin_and_coherent"]["adjudication_state"], "fragile")
        self.assertEqual(by_id["goal:contested"]["adjudication_state"], "contested")
        self.assertEqual(by_id["goal:revalidation_needed"]["adjudication_state"], "fragile")
        self.assertEqual(by_id["goal:unsupported"]["adjudication_state"], "rejected")
        self.assertTrue(by_id["goal:unsupported"]["publication"]["hedge"])

        report = self_model_sidecar.build_adjudication_report({"snapshot_id": "snap", "attachments": attachments, "source_digest": "digest"})
        self.assertEqual(report["counts"]["rejected"], 1)
        self.assertIn("goal:unsupported", {item["id"] for item in report["claims_by_state"]["rejected"]})

    def test_diff_skips_state_transition_for_legacy_snapshots(self):
        before = {
            "snapshot_id": "before",
            "source_digest": "legacy-source",
            "attachments": [{"id": "goal:verify", "attachment_score": 0.4, "confidence": 0.5, "fragility": "watch"}],
        }
        after = {
            "snapshot_id": "after",
            "source_digest": "new-source",
            "attachments": [{"id": "goal:verify", "attachment_score": 0.6, "confidence": 0.8, "fragility": "supported", "adjudication_state": "tentative"}],
        }
        diff = self_model_sidecar.compare_snapshots(before, after)
        self.assertFalse(any(flag.startswith("state_transition:") for flag in diff["risk_flags"]))

    def test_diff_tracks_state_transition_without_score_delta(self):
        before = {
            "snapshot_id": "before",
            "source_digest": "same-source",
            "attachments": [{"id": "goal:verify", "attachment_score": 0.6, "confidence": 0.6, "fragility": "watch", "adjudication_state": "tentative"}],
        }
        after = {
            "snapshot_id": "after",
            "source_digest": "same-source",
            "attachments": [{"id": "goal:verify", "attachment_score": 0.6, "confidence": 0.6, "fragility": "contested", "adjudication_state": "contested"}],
        }
        diff = self_model_sidecar.compare_snapshots(before, after)
        self.assertIn("state_transition:goal:verify:tentative->contested", diff["risk_flags"])
        self.assertEqual(diff["changed"][0]["before_state"], "tentative")
        self.assertEqual(diff["changed"][0]["after_state"], "contested")

    def test_wording_lint_flags_inflation_terms(self):
        report = self_model_sidecar.build_wording_lint(text="This is the true self and a form of consciousness.")
        self.assertFalse(report["ok"])
        self.assertIn("true self", report["violations"])
        self.assertIn("consciousness", report["violations"])

    def test_patterns_empty_snapshots_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(["continuity", "patterns", "--run-dir", tmp, "--json"])
            self.assertEqual(report["schema"], "openclaw-mem.self-model.pattern-report.v0")
            self.assertEqual(report["snapshot_count"], 0)
            self.assertEqual(report["diff_count"], 0)
            self.assertEqual(report["patterns"], [])
            self.assertTrue(Path(report["path"]).exists())

        with tempfile.TemporaryDirectory() as tmp:
            trigger_report = self_model_sidecar.build_trigger_report({"snapshot_id": "snap", "source_digest": "digest", "attachments": []}, run_dir=tmp, scope=None, session_id=None)
            self.assertEqual(trigger_report["schema"], "openclaw-mem.self-model.trigger-report.v0")
            self.assertFalse((Path(tmp) / "patterns").exists())

    def test_soak_evaluate_hold_then_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            base = {
                "schema": "openclaw-mem.self-model.snapshot.v0",
                "source_digest": "digest-a",
                "attachments": [{"id": "goal:ship", "attachment_score": 0.6, "confidence": 0.7, "fragility": "supported", "adjudication_state": "accepted"}],
            }
            first = {**base, "snapshot_id": "snap-1"}
            second = {**base, "snapshot_id": "snap-2"}
            (snapshots / "snap-1.json").write_text(json.dumps(first), encoding="utf-8")
            (snapshots / "snap-2.json").write_text(json.dumps(second), encoding="utf-8")
            autorun = root / "autorun"
            autorun.mkdir(parents=True, exist_ok=True)
            (autorun / "run-1.json").write_text(json.dumps({"generated_at": "2026-04-20T00:00:00+00:00", "snapshot_id": "snap-1"}), encoding="utf-8")
            (autorun / "run-2.json").write_text(json.dumps({"generated_at": "2026-04-20T00:05:00+00:00", "snapshot_id": "snap-2"}), encoding="utf-8")
            hold = evaluate_soak(SoakConfig(run_dir=tmp, cadence_seconds=300, target_hours=72.0), now=datetime.fromisoformat("2026-04-20T00:05:30+00:00").astimezone(timezone.utc))
            self.assertEqual(hold["status"], "hold")
            self.assertEqual(hold["reason"], "window_incomplete")

            complete = evaluate_soak(SoakConfig(run_dir=tmp, cadence_seconds=300, target_hours=(5.0 / 60.0) / 60.0), now=datetime.fromisoformat("2026-04-20T00:05:30+00:00").astimezone(timezone.utc))
            self.assertEqual(complete["status"], "complete")
            self.assertEqual(complete["reason"], "target_window_satisfied")

    def test_soak_evaluate_warns_on_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            snap = {"schema": "openclaw-mem.self-model.snapshot.v0", "source_digest": "digest-a", "attachments": [], "snapshot_id": "snap-1"}
            (snapshots / "snap-1.json").write_text(json.dumps(snap), encoding="utf-8")
            (snapshots / "snap-2.json").write_text(json.dumps({**snap, "snapshot_id": "snap-2"}), encoding="utf-8")
            autorun = root / "autorun"
            autorun.mkdir(parents=True, exist_ok=True)
            (autorun / "run-1.json").write_text(json.dumps({"generated_at": "2026-04-20T00:00:00+00:00", "snapshot_id": "snap-1"}), encoding="utf-8")
            (autorun / "run-2.json").write_text(json.dumps({"generated_at": "2026-04-20T00:20:00+00:00", "snapshot_id": "snap-2"}), encoding="utf-8")
            report = evaluate_soak(SoakConfig(run_dir=tmp, cadence_seconds=300, target_hours=72.0), now=datetime.fromisoformat("2026-04-20T00:20:10+00:00").astimezone(timezone.utc))
            self.assertEqual(report["status"], "warn")
            self.assertEqual(report["reason"], "receipt_gap")

    def test_soak_baseline_ignores_older_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            base = {"schema": "openclaw-mem.self-model.snapshot.v0", "source_digest": "digest-a", "attachments": [], "snapshot_id": "snap-1"}
            (snapshots / "snap-1.json").write_text(json.dumps(base), encoding="utf-8")
            (snapshots / "snap-2.json").write_text(json.dumps({**base, "snapshot_id": "snap-2"}), encoding="utf-8")
            autorun = root / "autorun"
            autorun.mkdir(parents=True, exist_ok=True)
            (autorun / "run-1.json").write_text(json.dumps({"generated_at": "2026-04-18T00:00:00+00:00", "snapshot_id": "snap-1"}), encoding="utf-8")
            latest = {"generated_at": "2026-04-20T00:00:00+00:00", "snapshot_id": "snap-2"}
            (autorun / "run-2.json").write_text(json.dumps(latest), encoding="utf-8")
            baseline = ensure_baseline(tmp, latest)
            report = evaluate_soak(SoakConfig(run_dir=tmp, cadence_seconds=300, target_hours=72.0), now=datetime.fromisoformat("2026-04-20T00:00:10+00:00").astimezone(timezone.utc), baseline_started_at=baseline["started_at"])
            self.assertEqual(report["status"], "hold")
            self.assertEqual(report["receipt_count"], 1)

    def test_soak_ignores_role_only_support_decay_without_contradiction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            before = {
                "schema": "openclaw-mem.self-model.snapshot.v0",
                "snapshot_id": "snap-1",
                "source_digest": "digest-a",
                "attachments": [{"id": "role:reviewer", "attachment_score": 0.97, "confidence": 0.9, "fragility": "supported", "adjudication_state": "accepted", "contradiction_hits": 0}],
            }
            after = {
                "schema": "openclaw-mem.self-model.snapshot.v0",
                "snapshot_id": "snap-2",
                "source_digest": "digest-b",
                "attachments": [{"id": "role:reviewer", "attachment_score": 0.61, "confidence": 0.55, "fragility": "watch", "adjudication_state": "tentative", "contradiction_hits": 0}],
            }
            (snapshots / "snap-1.json").write_text(json.dumps(before), encoding="utf-8")
            (snapshots / "snap-2.json").write_text(json.dumps(after), encoding="utf-8")
            autorun = root / "autorun"
            autorun.mkdir(parents=True, exist_ok=True)
            (autorun / "run-1.json").write_text(json.dumps({"generated_at": "2026-04-20T00:00:00+00:00", "snapshot_id": "snap-1"}), encoding="utf-8")
            (autorun / "run-2.json").write_text(json.dumps({"generated_at": "2026-04-20T00:05:00+00:00", "snapshot_id": "snap-2"}), encoding="utf-8")
            drift = compute_drift_summary(tmp, [json.loads((autorun / "run-1.json").read_text()), json.loads((autorun / "run-2.json").read_text())])
            self.assertEqual(drift["suspicious_count"], 0)
            self.assertEqual(drift["ignored_count"], 1)
            self.assertEqual(drift["ignored_pairs"][0]["ignored_reason"], "role_shift_without_contradiction")

    def test_soak_ignores_role_only_strengthening_without_contradiction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            before = {
                "schema": "openclaw-mem.self-model.snapshot.v0",
                "snapshot_id": "snap-1",
                "source_digest": "digest-a",
                "attachments": [
                    {"id": "role:reviewer", "attachment_score": 0.61, "confidence": 0.55, "fragility": "watch", "adjudication_state": "tentative", "contradiction_hits": 0},
                    {"id": "role:operator", "attachment_score": 0.38, "confidence": 0.33, "fragility": "watch", "adjudication_state": "fragile", "contradiction_hits": 0},
                    {"id": "style:evidence_first", "attachment_score": 0.79, "confidence": 0.73, "fragility": "supported", "adjudication_state": "accepted", "contradiction_hits": 0},
                ],
            }
            after = {
                "schema": "openclaw-mem.self-model.snapshot.v0",
                "snapshot_id": "snap-2",
                "source_digest": "digest-b",
                "attachments": [
                    {"id": "role:reviewer", "attachment_score": 0.97, "confidence": 0.92, "fragility": "supported", "adjudication_state": "accepted", "contradiction_hits": 0},
                    {"id": "role:operator", "attachment_score": 0.61, "confidence": 0.55, "fragility": "watch", "adjudication_state": "tentative", "contradiction_hits": 0},
                    {"id": "style:evidence_first", "attachment_score": 1.0, "confidence": 0.95, "fragility": "supported", "adjudication_state": "accepted", "contradiction_hits": 0},
                ],
            }
            (snapshots / "snap-1.json").write_text(json.dumps(before), encoding="utf-8")
            (snapshots / "snap-2.json").write_text(json.dumps(after), encoding="utf-8")
            autorun = root / "autorun"
            autorun.mkdir(parents=True, exist_ok=True)
            (autorun / "run-1.json").write_text(json.dumps({"generated_at": "2026-04-20T00:00:00+00:00", "snapshot_id": "snap-1"}), encoding="utf-8")
            (autorun / "run-2.json").write_text(json.dumps({"generated_at": "2026-04-20T00:05:00+00:00", "snapshot_id": "snap-2"}), encoding="utf-8")
            drift = compute_drift_summary(tmp, [json.loads((autorun / "run-1.json").read_text()), json.loads((autorun / "run-2.json").read_text())])
            self.assertEqual(drift["suspicious_count"], 0)
            self.assertEqual(drift["ignored_count"], 1)
            self.assertEqual(drift["ignored_pairs"][0]["ignored_reason"], "role_shift_without_contradiction")

    def test_soak_keeps_suspicious_when_contradiction_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshots = root / "snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            before = {
                "schema": "openclaw-mem.self-model.snapshot.v0",
                "snapshot_id": "snap-1",
                "source_digest": "digest-a",
                "attachments": [{"id": "role:reviewer", "attachment_score": 0.97, "confidence": 0.9, "fragility": "supported", "adjudication_state": "accepted", "contradiction_hits": 0}],
            }
            after = {
                "schema": "openclaw-mem.self-model.snapshot.v0",
                "snapshot_id": "snap-2",
                "source_digest": "digest-b",
                "attachments": [{"id": "role:reviewer", "attachment_score": 0.61, "confidence": 0.55, "fragility": "watch", "adjudication_state": "tentative", "contradiction_hits": 1}],
            }
            (snapshots / "snap-1.json").write_text(json.dumps(before), encoding="utf-8")
            (snapshots / "snap-2.json").write_text(json.dumps(after), encoding="utf-8")
            autorun = root / "autorun"
            autorun.mkdir(parents=True, exist_ok=True)
            (autorun / "run-1.json").write_text(json.dumps({"generated_at": "2026-04-20T00:00:00+00:00", "snapshot_id": "snap-1"}), encoding="utf-8")
            (autorun / "run-2.json").write_text(json.dumps({"generated_at": "2026-04-20T00:05:00+00:00", "snapshot_id": "snap-2"}), encoding="utf-8")
            drift = compute_drift_summary(tmp, [json.loads((autorun / "run-1.json").read_text()), json.loads((autorun / "run-2.json").read_text())])
            self.assertEqual(drift["suspicious_count"], 1)
            self.assertEqual(drift["ignored_count"], 0)


if __name__ == "__main__":
    unittest.main()
