from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_mem.cli import _connect, build_parser
from openclaw_mem.graph import facts


FIXTURE_DIR = Path(__file__).resolve().parent / "data" / "temporal_fact_view"


class TestTemporalFactCore(unittest.TestCase):
    def test_fixture_rebuild_preserves_stable_ids_and_lints_clean(self) -> None:
        records = facts.load_jsonl(FIXTURE_DIR / "TEMPORAL_FACT_VIEW_FIXTURES.v0.jsonl")
        conn = _connect(":memory:")
        try:
            first = facts.rebuild_from_records(conn, records, source_root=FIXTURE_DIR)
            second = facts.rebuild_from_records(conn, records, source_root=FIXTURE_DIR)

            self.assertEqual(first["fact_ids"], second["fact_ids"])
            self.assertEqual(first["count"], 2)

            current = facts.current_facts(conn, subject_ref="entity:openclaw-mem", source_root=FIXTURE_DIR)
            self.assertEqual(current["count"], 2)

            lint = facts.lint_facts(conn, source_root=FIXTURE_DIR)
            self.assertTrue(lint["ok"], lint)
            self.assertEqual(lint["counts"]["staleFacts"], 0)
        finally:
            conn.close()

    def test_dangling_source_rejected_and_unknown_predicate_lints_if_injected(self) -> None:
        conn = _connect(":memory:")
        try:
            with self.assertRaises(facts.FactValidationError) as ctx:
                facts.assert_fact(
                    conn,
                    subject_ref="entity:openclaw-mem",
                    subject_label="openclaw-mem",
                    predicate="status",
                    object_type="literal",
                    object_value="ready",
                    valid_from="2026-06-03T00:00:00Z",
                    source_refs=["doc:missing.md"],
                    assertion_ref="receipt:test",
                    source_root=FIXTURE_DIR,
                )
            self.assertEqual(ctx.exception.issues[0]["code"], "dangling_source_ref")

            receipt = facts.assert_fact(
                conn,
                subject_ref="entity:openclaw-mem",
                subject_label="openclaw-mem",
                predicate="uses",
                object_type="literal",
                object_value="ContextPack",
                valid_from="2026-06-03T00:00:00Z",
                source_refs=["doc:source.md"],
                assertion_ref="receipt:test-valid",
                source_root=FIXTURE_DIR,
            )
            fact_id = receipt["fact"]["id"]
            conn.execute("UPDATE graph_facts SET predicate = ? WHERE id = ?", ("freeform", fact_id))
            conn.commit()

            lint = facts.lint_facts(conn, source_root=FIXTURE_DIR)
            self.assertFalse(lint["ok"])
            self.assertIn("unknown_predicate", {item["code"] for item in lint["issues"]})
        finally:
            conn.close()

    def test_confidence_cap_dedupes_sources_and_assert_rejects_single_value_overlap(self) -> None:
        conn = _connect(":memory:")
        try:
            with self.assertRaises(facts.FactValidationError) as duplicate_ctx:
                facts.assert_fact(
                    conn,
                    subject_ref="entity:openclaw-mem",
                    subject_label="openclaw-mem",
                    predicate="uses",
                    object_type="literal",
                    object_value="ContextPack",
                    valid_from="2026-06-03T00:00:00Z",
                    confidence_tier="corroborated",
                    source_refs=["doc:source.md", "doc:source.md"],
                    assertion_ref="receipt:duplicate-source",
                    source_root=FIXTURE_DIR,
                )
            self.assertEqual(duplicate_ctx.exception.issues[0]["code"], "confidence_exceeds_source_cap")

            first = facts.assert_fact(
                conn,
                subject_ref="entity:openclaw-mem",
                subject_label="openclaw-mem",
                predicate="status",
                object_type="literal",
                object_value="planned",
                valid_from="2026-06-03T00:00:00Z",
                source_refs=["doc:source.md"],
                assertion_ref="receipt:status-planned",
                source_root=FIXTURE_DIR,
            )
            with self.assertRaises(facts.FactValidationError) as conflict_ctx:
                facts.assert_fact(
                    conn,
                    subject_ref="entity:openclaw-mem",
                    subject_label="openclaw-mem",
                    predicate="status",
                    object_type="literal",
                    object_value="implemented",
                    valid_from="2026-06-04T00:00:00Z",
                    source_refs=["doc:source.md"],
                    assertion_ref="receipt:status-implemented-conflict",
                    source_root=FIXTURE_DIR,
                )
            self.assertEqual(conflict_ctx.exception.issues[0]["code"], "single_value_interval_conflict")

            second = facts.assert_fact(
                conn,
                subject_ref="entity:openclaw-mem",
                subject_label="openclaw-mem",
                predicate="status",
                object_type="literal",
                object_value="implemented",
                valid_from="2026-06-04T00:00:00Z",
                source_refs=["doc:source.md"],
                assertion_ref="receipt:status-implemented-ok",
                supersedes=[first["fact"]["id"]],
                source_root=FIXTURE_DIR,
            )
            self.assertEqual(second["fact"]["object"]["value"], "implemented")
        finally:
            conn.close()

    def test_supersede_and_invalidate_remove_prior_current_truth(self) -> None:
        conn = _connect(":memory:")
        try:
            first = facts.assert_fact(
                conn,
                subject_ref="entity:openclaw-mem",
                subject_label="openclaw-mem",
                predicate="status",
                object_type="literal",
                object_value="planned",
                valid_from="2026-06-03T00:00:00Z",
                source_refs=["doc:source.md"],
                assertion_ref="receipt:status-planned",
                source_root=FIXTURE_DIR,
            )
            second = facts.assert_fact(
                conn,
                subject_ref="entity:openclaw-mem",
                subject_label="openclaw-mem",
                predicate="status",
                object_type="literal",
                object_value="implemented",
                valid_from="2026-06-04T00:00:00Z",
                source_refs=["doc:source.md"],
                assertion_ref="receipt:status-implemented",
                supersedes=[first["fact"]["id"]],
                source_root=FIXTURE_DIR,
            )

            current = facts.current_facts(
                conn,
                subject_ref="entity:openclaw-mem",
                as_of="2026-06-05T00:00:00Z",
                source_root=FIXTURE_DIR,
            )
            self.assertEqual(current["count"], 1)
            self.assertEqual(current["facts"][0]["object"]["value"], "implemented")

            timeline = facts.timeline(conn, subject_ref="entity:openclaw-mem", predicate="status", source_root=FIXTURE_DIR)
            statuses = {item["id"]: item["status"] for item in timeline["events"]}
            self.assertEqual(statuses[first["fact"]["id"]], "superseded")

            facts.invalidate_fact(
                conn,
                fact_id=second["fact"]["id"],
                invalidated_at="2026-06-06T00:00:00Z",
                source_refs=["doc:source.md"],
                assertion_ref="receipt:status-invalidated",
                source_root=FIXTURE_DIR,
            )
            after = facts.current_facts(
                conn,
                subject_ref="entity:openclaw-mem",
                as_of="2026-06-07T00:00:00Z",
                source_root=FIXTURE_DIR,
            )
            self.assertEqual(after["count"], 0)
        finally:
            conn.close()

    def test_source_hash_drift_marks_stale_and_excludes_current_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.md"
            source.write_text("initial evidence\n", encoding="utf-8")
            conn = _connect(":memory:")
            try:
                facts.assert_fact(
                    conn,
                    subject_ref="entity:openclaw-mem",
                    subject_label="openclaw-mem",
                    predicate="source_of_truth",
                    object_type="literal",
                    object_value="Store records",
                    valid_from="2026-06-03T00:00:00Z",
                    source_refs=["doc:source.md"],
                    assertion_ref="receipt:initial",
                    source_root=root,
                )
                source.write_text("changed evidence\n", encoding="utf-8")

                stale = facts.stale_facts(conn, source_root=root)
                self.assertEqual(stale["count"], 1)

                current = facts.current_facts(conn, subject_ref="entity:openclaw-mem", source_root=root)
                self.assertEqual(current["count"], 0)
                self.assertEqual(current["excluded"][0]["reason"], "stale_excluded")

                included = facts.current_facts(
                    conn,
                    subject_ref="entity:openclaw-mem",
                    include_stale=True,
                    source_root=root,
                )
                self.assertEqual(included["count"], 1)
                self.assertEqual(included["facts"][0]["status"], "stale")

                applied = facts.stale_facts(conn, apply=True, source_root=root)
                self.assertTrue(applied["writes_performed"])
            finally:
                conn.close()

    def test_pack_trace_route_and_extraction_measure_are_reviewable(self) -> None:
        records = facts.load_jsonl(FIXTURE_DIR / "TEMPORAL_FACT_VIEW_FIXTURES.v0.jsonl")
        conn = _connect(":memory:")
        try:
            facts.rebuild_from_records(conn, records, source_root=FIXTURE_DIR)
            pack = facts.fact_pack(
                conn,
                subject_ref="entity:openclaw-mem",
                max_items=1,
                budget_tokens=1200,
                source_root=FIXTURE_DIR,
            )
            self.assertEqual(pack["kind"], facts.FACT_PACK_KIND)
            self.assertEqual(len(pack["items"]), 1)
            self.assertTrue(pack["trace"]["allIncludedHaveSources"])
            self.assertIn("max_items", {item["reason"] for item in pack["trace"]["excluded"]})
            self.assertEqual(pack["context_pack"]["schema"], "openclaw-mem.context-pack.v1")
            self.assertEqual(pack["context_pack"]["items"][0]["evidenceSourceRefs"][0]["ref"], "source.md")

            route = facts.route_fact_query(
                conn,
                query="current truth for entity:openclaw-mem",
                source_root=FIXTURE_DIR,
            )
            self.assertTrue(route["fact_view_used"])
            self.assertTrue(route["receipt"]["visible_context_pack_receipt"])

            proposal = facts.propose_extractions(
                text="entity:openclaw-mem source_of_truth Store records",
                source_refs=["doc:source.md"],
            )
            self.assertFalse(proposal["writes_performed"])
            self.assertEqual(proposal["proposal_count"], 1)

            measure = facts.measure_extraction_precision(
                corpus_rows=[
                    {
                        "text": "entity:openclaw-mem source_of_truth Store records",
                        "source_refs": ["doc:source.md"],
                    }
                ],
                golden_rows=[
                    {
                        "subject": "entity:openclaw-mem",
                        "predicate": "source_of_truth",
                        "object": "Store records",
                    }
                ],
            )
            self.assertEqual(measure["precision"], 1.0)
            self.assertEqual(measure["recall"], 1.0)
            self.assertFalse(measure["apply_allowed"])
        finally:
            conn.close()


class TestTemporalFactCli(unittest.TestCase):
    def _run(self, args: list[str]) -> dict:
        code, payload = self._run_allow_exit(args)
        if code:
            raise SystemExit(code)
        return payload

    def _run_allow_exit(self, args: list[str]) -> tuple[int, dict]:
        parser = build_parser()
        ns = parser.parse_args(args)
        ns.db = getattr(ns, "db", None) or getattr(ns, "db_global", None) or ":memory:"
        ns.json = bool(getattr(ns, "json", False) or getattr(ns, "json_global", False))
        conn = _connect(ns.db or ":memory:")
        try:
            buf = io.StringIO()
            code = 0
            with redirect_stdout(buf):
                try:
                    ns.func(conn, ns)
                except SystemExit as exc:
                    code = int(exc.code or 0)
            return code, json.loads(buf.getvalue())
        finally:
            conn.close()

    def test_cli_assert_current_lint_pack_propose_and_measure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "mem.sqlite"
            source = root / "source.md"
            source.write_text("entity:openclaw-mem source_of_truth Store records\n", encoding="utf-8")

            asserted = self._run(
                [
                    "--db",
                    str(db),
                    "graph",
                    "fact",
                    "assert",
                    "--subject",
                    "entity:openclaw-mem",
                    "--predicate",
                    "source_of_truth",
                    "--object",
                    "Store records",
                    "--valid-from",
                    "2026-06-03T00:00:00Z",
                    "--source-ref",
                    "doc:source.md",
                    "--assertion-ref",
                    "receipt:cli-test",
                    "--source-root",
                    str(root),
                ]
            )
            self.assertEqual(asserted["fact"]["predicate"], "source_of_truth")

            current = self._run(
                [
                    "--db",
                    str(db),
                    "graph",
                    "fact",
                    "current",
                    "--subject",
                    "entity:openclaw-mem",
                    "--source-root",
                    str(root),
                ]
            )
            self.assertEqual(current["count"], 1)

            lint = self._run(["--db", str(db), "graph", "fact", "lint", "--source-root", str(root)])
            self.assertTrue(lint["ok"])

            pack = self._run(
                [
                    "--db",
                    str(db),
                    "graph",
                    "fact",
                    "pack",
                    "--subject",
                    "entity:openclaw-mem",
                    "--source-root",
                    str(root),
                ]
            )
            self.assertEqual(pack["context_pack"]["items"][0]["recordRef"], asserted["fact"]["id"])

            proposed = self._run(
                [
                    "--db",
                    str(db),
                    "graph",
                    "fact",
                    "propose",
                    "--file",
                    str(source),
                    "--source-ref",
                    "doc:source.md",
                ]
            )
            self.assertEqual(proposed["proposal_count"], 1)
            self.assertFalse(proposed["writes_performed"])

            empty_code, empty_propose = self._run_allow_exit(
                [
                    "--db",
                    str(db),
                    "graph",
                    "fact",
                    "propose",
                    "--source-ref",
                    "doc:source.md",
                ]
            )
            self.assertEqual(empty_code, 2)
            self.assertEqual(empty_propose["issues"][0]["code"], "missing_proposal_input")

            corpus = root / "corpus.jsonl"
            corpus.write_text(
                json.dumps({"text": source.read_text(encoding="utf-8"), "source_refs": ["doc:source.md"]}) + "\n",
                encoding="utf-8",
            )
            golden = root / "golden.jsonl"
            golden.write_text(
                json.dumps(
                    {
                        "subject": "entity:openclaw-mem",
                        "predicate": "source_of_truth",
                        "object": "Store records",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            measured = self._run(
                [
                    "--db",
                    str(db),
                    "graph",
                    "fact",
                    "measure-extraction",
                    "--corpus",
                    str(corpus),
                    "--golden",
                    str(golden),
                ]
            )
            self.assertEqual(measured["precision"], 1.0)
            self.assertFalse(measured["apply_allowed"])


if __name__ == "__main__":
    unittest.main()
