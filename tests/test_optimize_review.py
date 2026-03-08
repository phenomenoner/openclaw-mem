import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_review


def _iso_days_ago(days: int) -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        - timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")


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


if __name__ == "__main__":
    unittest.main()
