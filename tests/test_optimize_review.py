import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_review
from openclaw_mem.optimization import _extract_recall_result_count


def _iso_days_ago(days: int) -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        - timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")


def _insert_lifecycle_row(conn, *, selected_refs: list[str]) -> None:
    receipt = {
        "kind": "openclaw-mem.pack.lifecycle-shadow.v1",
        "ts": _iso_days_ago(0),
        "selection": {
            "pack_selected_refs": list(selected_refs),
            "citation_record_refs": list(selected_refs),
            "trace_refreshed_record_refs": list(selected_refs),
            "selection_signature": "sha256:test",
        },
        "mutation": {
            "memory_mutation": "none",
            "auto_archive_applied": 0,
            "auto_mutation_applied": 0,
        },
    }
    conn.execute(
        """
        INSERT INTO pack_lifecycle_shadow_log (
            ts, query_hash, selection_signature, selected_count, citation_count, candidate_count, receipt_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _iso_days_ago(0),
            "sha256:q",
            "sha256:test",
            len(selected_refs),
            len(selected_refs),
            len(selected_refs),
            json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()


class TestOptimizeReview(unittest.TestCase):
    def test_optimize_parser_parses_review_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "review",
                "--limit",
                "200",
                "--stale-days",
                "45",
                "--duplicate-min-count",
                "3",
                "--bloat-summary-chars",
                "320",
                "--bloat-detail-bytes",
                "9000",
                "--orphan-min-tokens",
                "4",
                "--miss-min-count",
                "5",
                "--lifecycle-limit",
                "44",
                "--scope",
                "finlife/mvp",
                "--top",
                "7",
            ]
        )

        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "review")
        self.assertEqual(args.limit, 200)
        self.assertEqual(args.stale_days, 45)
        self.assertEqual(args.duplicate_min_count, 3)
        self.assertEqual(args.bloat_summary_chars, 320)
        self.assertEqual(args.bloat_detail_bytes, 9000)
        self.assertEqual(args.orphan_min_tokens, 4)
        self.assertEqual(args.miss_min_count, 5)
        self.assertEqual(args.lifecycle_limit, 44)
        self.assertEqual(args.scope, "finlife/mvp")
        self.assertEqual(args.top, 7)

    def test_optimize_review_json_reports_signals_and_keeps_store_read_only(self):
        conn = _connect(":memory:")

        # stale candidate (old + non-critical)
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(120),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "legacy rollout detail that is likely stale",
                "detail": {"importance": {"score": 0.55, "label": "nice_to_have"}},
            },
        )

        # duplicate cluster
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(2),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO finalize weekly benchmark checklist",
                "detail": {"importance": {"score": 0.6}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO finalize weekly benchmark checklist",
                "detail": {"importance": {"score": 0.61}},
            },
        )

        # bloat candidate
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "tool",
                "tool_name": "exec",
                "summary": "x" * 320,
                "detail": {"payload": "y" * 6000},
            },
        )

        # weakly connected candidate (rare lexical island)
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(3),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "quasarflux nebula drift anomaly snapshot",
                "detail": {"importance": {"score": 0.4, "label": "ignore"}},
            },
        )
        conn.commit()

        before_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.review.v0")

        self.assertGreaterEqual(out["signals"]["staleness"]["count"], 1)
        self.assertGreaterEqual(out["signals"]["duplication"]["groups"], 1)
        self.assertGreaterEqual(out["signals"]["bloat"]["count"], 1)
        self.assertGreaterEqual(out["signals"]["weakly_connected"]["count"], 1)
        self.assertEqual(out["source"]["total_rows"], before_count)
        self.assertEqual(out["source"]["coverage_pct"], 100.0)
        self.assertEqual(out["source"]["sample_order"], "id_desc_recent_window")
        self.assertEqual(out["signals"]["staleness"]["excluded_must_remember"], 0)
        self.assertEqual(out["signals"]["duplication"]["fingerprint_algo"], "normalize_v1")
        self.assertEqual(out["policy"]["query_only_enforced"], True)
        self.assertEqual(out["warnings"], [])

        rec_types = {r["type"] for r in out.get("recommendations", [])}
        self.assertIn("mark_stale_candidate", rec_types)
        self.assertIn("merge_candidates", rec_types)
        self.assertIn("summarize_bloat_candidates", rec_types)
        self.assertIn("strengthen_edge_candidates", rec_types)

        self.assertEqual(out["policy"]["writes_performed"], 0)
        self.assertEqual(out["policy"]["memory_mutation"], "none")

        after_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        self.assertEqual(before_count, after_count)
        self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 0)

        conn.close()

    def test_optimize_review_reports_repeated_memory_recall_misses(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "memory recall miss 1",
                "detail": {"scope": "alpha", "query": "Cache Invalidation Policy", "results": []},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "memory recall miss 2",
                "detail": {"scope": "alpha", "query": "cache invalidation policy", "results": 0},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "memory recall successful",
                "detail": {"scope": "alpha", "query": "cache invalidation policy", "results": [{"id": "x"}]},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "memory recall miss beta",
                "detail": {"scope": "beta", "query": "cache invalidation policy", "results": 0},
            },
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "miss_min_count": 2,
                "scope": None,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        misses = out["signals"]["repeated_misses"]
        self.assertEqual(misses["groups"], 1)
        self.assertEqual(misses["miss_events"], 2)
        self.assertEqual(misses["min_count"], 2)
        self.assertEqual(misses["items"][0]["scope"], "alpha")
        self.assertEqual(misses["items"][0]["query"], "cache invalidation policy")
        self.assertEqual(misses["items"][0]["count"], 2)

        rec_types = {r["type"] for r in out.get("recommendations", [])}
        self.assertIn("widen_scope_candidate", rec_types)
        self.assertEqual(out["policy"]["writes_performed"], 0)

        conn.close()

    def test_optimize_review_protects_stale_rows_with_recent_use(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(120),
                "kind": "fact",
                "tool_name": "memory_store",
                "summary": "Long-lived memory that still gets selected in pack",
                "detail": {"importance": {"score": 0.55, "label": "nice_to_have"}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(120),
                "kind": "fact",
                "tool_name": "memory_store",
                "summary": "Long-lived memory with no recent use evidence",
                "detail": {"importance": {"score": 0.55, "label": "nice_to_have"}},
            },
        )
        _insert_lifecycle_row(conn, selected_refs=["obs:1"])

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "miss_min_count": 2,
                "lifecycle_limit": 50,
                "scope": None,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        stale = out["signals"]["staleness"]
        recent_use = out["signals"]["recent_use"]

        self.assertEqual(stale["count"], 1)
        self.assertEqual(stale["protected_recent_use"], 1)
        self.assertEqual(stale["items"][0]["id"], 2)
        self.assertEqual(recent_use["rows_with_recent_use"], 1)
        self.assertEqual(recent_use["selection_events"], 1)
        self.assertEqual(recent_use["items"][0]["id"], 1)
        self.assertEqual(recent_use["items"][0]["recent_use_count"], 1)

        rec = next(r for r in out.get("recommendations", []) if r["type"] == "mark_stale_candidate")
        self.assertEqual(rec["evidence"]["protected_recent_use"], 1)
        conn.close()

    def test_extract_recall_result_count_supports_common_schema_variants(self):
        cases = [
            ({"result_count": 3}, 3),
            ({"results_count": "4"}, 4),
            ({"results": [{"id": "a"}, {"id": "b"}]}, 2),
            ({"results": 0}, 0),
            ({"details": {"results": [{"id": "x"}]}}, 1),
            ({"details": {"results": "5"}}, 5),
            ({"receipt": {"lifecycle": {"selected_total": 6}}}, 6),
            ({"receipt": {"lifecycle": {"selectedTotal": "7"}}}, 7),
            ({"receipt": {"lifecycle": {"selected_counts": {"must": 2, "nice": 1}}}}, 3),
            ({"receipt": {"lifecycle": {"selectedCounts": {"must": "2", "nice": 3}}}}, 5),
            ({"results": True}, None),
            ({"details": {"results": -1}}, None),
            ({"receipt": {"lifecycle": {"selected_counts": {"must": "x"}}}}, None),
        ]

        for detail_obj, expected in cases:
            with self.subTest(detail_obj=detail_obj):
                self.assertEqual(_extract_recall_result_count(detail_obj), expected)

    def test_optimize_review_reports_sampling_warning_when_limit_is_partial(self):
        conn = _connect(":memory:")
        for i in range(5):
            _insert_observation(
                conn,
                {
                    "ts": _iso_days_ago(90 - i),
                    "kind": "note",
                    "tool_name": "memory_store",
                    "summary": f"legacy note {i}",
                    "detail": {"importance": {"score": 0.4, "label": "ignore"}},
                },
            )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 2,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "miss_min_count": 2,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["source"]["rows_scanned"], 2)
        self.assertEqual(out["source"]["total_rows"], 5)
        self.assertEqual(out["source"]["coverage_pct"], 40.0)
        self.assertEqual(out["warnings"][0]["code"], "sample_is_recent_window")
        self.assertEqual(out["policy"]["writes_performed"], 0)
        self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 0)

        conn.close()


    def test_optimize_review_respects_miss_min_count_threshold(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "memory recall miss 1",
                "detail": {"scope": "alpha", "query": "cache invalidation policy", "results": []},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "memory recall miss 2",
                "detail": {"scope": "alpha", "query": "cache invalidation policy", "results": 0},
            },
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "miss_min_count": 3,
                "scope": None,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["signals"]["repeated_misses"]["groups"], 0)
        self.assertEqual(out["signals"]["repeated_misses"]["miss_events"], 0)
        rec_types = {r["type"] for r in out.get("recommendations", [])}
        self.assertNotIn("widen_scope_candidate", rec_types)

        conn.close()


    def test_optimize_review_scope_filter_limits_dataset(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(5),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO stabilize cache invalidation policy",
                "detail": {"scope": "alpha", "importance": {"score": 0.5}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(4),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO stabilize cache invalidation policy",
                "detail": {"scope": "alpha", "importance": {"score": 0.52}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(3),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO stabilize cache invalidation policy",
                "detail": {"scope": "beta", "importance": {"score": 0.54}},
            },
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 100,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "scope": "alpha",
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["source"]["scope"], "alpha")
        self.assertEqual(out["source"]["rows_scanned"], 2)
        self.assertEqual(out["source"]["total_rows"], 2)
        self.assertEqual(out["source"]["coverage_pct"], 100.0)
        self.assertEqual(out["signals"]["duplication"]["groups"], 1)
        self.assertEqual(out["signals"]["duplication"]["duplicate_rows"], 1)

        conn.close()


    def test_optimize_review_scope_filter_normalizes_scope_tokens(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(5),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO stabilize normalization policy",
                "detail": {"scope": "Alpha Team", "importance": {"score": 0.5}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(4),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO stabilize normalization policy",
                "detail": {"scope": "alpha-team", "importance": {"score": 0.52}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(3),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO stabilize normalization policy",
                "detail": {"scope": "alpha_team_two", "importance": {"score": 0.54}},
            },
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 100,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "scope": "ALPHA team",
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["source"]["scope"], "alpha-team")
        self.assertEqual(out["source"]["rows_scanned"], 2)
        self.assertEqual(out["source"]["total_rows"], 2)
        self.assertEqual(out["signals"]["duplication"]["groups"], 1)
        self.assertEqual(out["signals"]["duplication"]["duplicate_rows"], 1)

        conn.close()


    def test_optimize_review_duplicate_signal_is_scope_isolated(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(2),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO confirm rollout checklist",
                "detail": {"scope": "alpha", "importance": {"score": 0.55}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "task",
                "tool_name": "memory_store",
                "summary": "TODO confirm rollout checklist",
                "detail": {"scope": "beta", "importance": {"score": 0.56}},
            },
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 100,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "scope": None,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["signals"]["duplication"]["groups"], 0)
        self.assertEqual(out["signals"]["duplication"]["duplicate_rows"], 0)
        self.assertEqual(out["signals"]["duplication"]["scope_isolated"], True)

        conn.close()

    def test_optimize_review_importance_drift_signal_is_bounded_and_read_only(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Operator decision index refresh checkpoint",
                "detail": {"importance": {"score": 0.95, "label": "ignore"}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Legacy sync reminder",
                "detail": {"importance": {"score": 0.2, "label": "must_remember"}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "No importance metadata yet",
                "detail": {},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Malformed importance payload",
                "detail": {"importance": {"score": "oops", "label": "??"}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Rotate API key for production deploy",
                "detail": {"importance": {"score": 0.1, "label": "ignore"}},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Store private key escrow location",
                "detail": {"importance": {"score": 0.2, "label": "ignore"}},
            },
        )
        conn.commit()

        before_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "miss_min_count": 2,
                "lifecycle_limit": 20,
                "scope": None,
                "top": 1,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        drift = out["signals"]["importance_drift"]
        policy_card = drift["policy_card"]

        self.assertEqual(
            set(drift["normalized_label_distribution"].keys()),
            {"must_remember", "nice_to_have", "ignore", "unknown"},
        )
        self.assertEqual(sum(drift["normalized_label_distribution"].values()), out["source"]["rows_scanned"])
        self.assertEqual(drift["normalized_label_distribution"]["must_remember"], 1)
        self.assertEqual(drift["normalized_label_distribution"]["ignore"], 3)
        self.assertEqual(drift["normalized_label_distribution"]["unknown"], 2)

        self.assertEqual(drift["score_label_mismatch_count"], 2)
        self.assertEqual(drift["missing_or_unparseable_count"], 2)
        self.assertEqual(drift["high_risk_content_mismatch_count"], 2)

        self.assertEqual(policy_card["kind"], "openclaw-mem.optimize.importance-drift-policy-card.v0")
        self.assertEqual(policy_card["mode"], "proposal_only_read_only")
        self.assertTrue(policy_card["query_only_enforced"])
        self.assertEqual(policy_card["writes_performed"], 0)
        self.assertEqual(policy_card["memory_mutation"], "none")
        self.assertEqual(policy_card["status"], "hold")
        self.assertFalse(policy_card["acceptable_for_promotion_apply"])
        self.assertIn("high_risk_underlabel_count_exceeded", policy_card["reasons"])
        self.assertGreater(policy_card["metrics"]["high_risk_underlabel_rate_pct"], 0.0)

        self.assertEqual(len(drift["score_label_mismatch_items"]), 1)
        self.assertEqual(len(drift["missing_or_unparseable_items"]), 1)
        self.assertEqual(len(drift["high_risk_content_mismatch_items"]), 1)

        mismatch = drift["score_label_mismatch_items"][0]
        self.assertNotEqual(mismatch["stored_label"], mismatch["normalized_label"])

        high_risk = drift["high_risk_content_mismatch_items"][0]
        self.assertEqual(high_risk["severity"], "high")
        self.assertGreaterEqual(len(high_risk["keyword_hits"]), 1)

        self.assertEqual(out["policy"]["writes_performed"], 0)
        self.assertEqual(out["policy"]["memory_mutation"], "none")
        self.assertEqual(out["policy"]["query_only_enforced"], True)

        after_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        self.assertEqual(before_count, after_count)
        self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 0)

        conn.close()

    def test_optimize_review_text_mentions_importance_drift_signal(self):
        conn = _connect(":memory:")
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Text renderer probe",
                "detail": {"importance": {"score": 0.5, "label": "nice_to_have"}},
            },
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "miss_min_count": 2,
                "lifecycle_limit": 20,
                "scope": None,
                "top": 10,
                "json": False,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        text = buf.getvalue()
        self.assertIn("importance_drift=label_mismatch:", text)
        self.assertIn("missing_or_unparseable:", text)
        self.assertIn("high_risk_content:", text)
        self.assertIn("importance_drift_gate=", text)
        conn.close()

    def test_optimize_review_importance_drift_policy_card_passes_on_clean_sample(self):
        conn = _connect(":memory:")
        _insert_observation(
            conn,
            {
                "ts": _iso_days_ago(1),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Operator approved runbook index",
                "detail": {"importance": {"score": 0.81, "label": "must_remember"}},
            },
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 1000,
                "stale_days": 60,
                "duplicate_min_count": 2,
                "bloat_summary_chars": 240,
                "bloat_detail_bytes": 4096,
                "orphan_min_tokens": 2,
                "miss_min_count": 2,
                "lifecycle_limit": 20,
                "scope": None,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_review(conn, args)

        out = json.loads(buf.getvalue())
        policy_card = out["signals"]["importance_drift"]["policy_card"]
        self.assertEqual(policy_card["status"], "accept")
        self.assertTrue(policy_card["acceptable_for_promotion_apply"])
        self.assertEqual(policy_card["reasons"], [])
        self.assertEqual(policy_card["metrics"]["rows_scanned"], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
