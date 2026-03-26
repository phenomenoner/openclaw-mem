import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from openclaw_mem.cli import _connect, build_parser, cmd_optimize_consolidation_review


def _insert_lifecycle_row(conn, *, selected_refs: list[str]) -> None:
    receipt = {
        "kind": "openclaw-mem.pack.lifecycle-shadow.v1",
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
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
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "sha256:q",
            "sha256:test",
            len(selected_refs),
            len(selected_refs),
            len(selected_refs),
            json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()


class TestOptimizeConsolidationReview(unittest.TestCase):
    def _run(self, conn, argv, *, expect_exit=None):
        args = build_parser().parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            if expect_exit is None:
                args.func(conn, args)
            else:
                with self.assertRaises(SystemExit) as cm:
                    args.func(conn, args)
                self.assertEqual(cm.exception.code, expect_exit)
        text = buf.getvalue().strip()
        return json.loads(text) if text else None

    @staticmethod
    def _ts_days_ago(days: int) -> int:
        dt = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=days)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _insert_episode(
        conn,
        *,
        event_id: str,
        ts_ms: int,
        scope: str,
        session_id: str,
        event_type: str,
        summary: str,
        payload=None,
        refs=None,
        redacted: int = 0,
    ):
        conn.execute(
            """
            INSERT INTO episodic_events (
                event_id, ts_ms, scope, session_id, agent_id, type, summary,
                payload_json, refs_json, redacted, schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                ts_ms,
                scope,
                session_id,
                "tester",
                event_type,
                summary,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                json.dumps(refs, ensure_ascii=False) if refs is not None else None,
                redacted,
                "v0",
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def test_optimize_parser_parses_consolidation_review_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "consolidation-review",
                "--limit",
                "250",
                "--scope",
                "alpha/team",
                "--session-id",
                "s-42",
                "--summary-min-group-size",
                "3",
                "--summary-min-shared-tokens",
                "2",
                "--archive-lookahead-days",
                "9",
                "--archive-min-signal-reasons",
                "3",
                "--link-min-shared-tokens",
                "4",
                "--lifecycle-limit",
                "33",
                "--top",
                "6",
            ]
        )

        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "consolidation-review")
        self.assertEqual(args.limit, 250)
        self.assertEqual(args.scope, "alpha/team")
        self.assertEqual(args.session_id, "s-42")
        self.assertEqual(args.summary_min_group_size, 3)
        self.assertEqual(args.summary_min_shared_tokens, 2)
        self.assertEqual(args.archive_lookahead_days, 9)
        self.assertEqual(args.archive_min_signal_reasons, 3)
        self.assertEqual(args.link_min_shared_tokens, 4)
        self.assertEqual(args.lifecycle_limit, 33)
        self.assertEqual(args.top, 6)

    def test_consolidation_review_reports_summary_archive_and_link_candidates(self):
        conn = _connect(":memory:")

        # Summary cluster within one session.
        self._insert_episode(
            conn,
            event_id="ev-1",
            ts_ms=self._ts_days_ago(3),
            scope="alpha",
            session_id="s-1",
            event_type="conversation.user",
            summary="Investigate latency spike in memory recall lane",
            payload={"kind": "msg"},
            refs={"recordRef": "obs:1"},
        )
        self._insert_episode(
            conn,
            event_id="ev-2",
            ts_ms=self._ts_days_ago(2),
            scope="alpha",
            session_id="s-1",
            event_type="conversation.assistant",
            summary="Memory recall latency spike still affects the debug lane",
            payload={"kind": "msg"},
            refs={"recordRef": "obs:2"},
        )
        self._insert_episode(
            conn,
            event_id="ev-3",
            ts_ms=self._ts_days_ago(1),
            scope="alpha",
            session_id="s-1",
            event_type="tool.result",
            summary="Recall lane latency metrics confirm spike in debug memory path",
            payload={"kind": "tool"},
            refs={"recordRef": "obs:3"},
        )

        # Cross-session lexical link candidate.
        self._insert_episode(
            conn,
            event_id="ev-4",
            ts_ms=self._ts_days_ago(1),
            scope="alpha",
            session_id="s-2",
            event_type="conversation.user",
            summary="Need a rollback plan for memory recall latency",
            payload={"kind": "msg"},
            refs={"recordRef": "obs:4"},
        )

        # Archive candidate: nearing TTL with low-signal traits.
        self._insert_episode(
            conn,
            event_id="ev-5",
            ts_ms=self._ts_days_ago(28),
            scope="alpha",
            session_id="s-old",
            event_type="tool.result",
            summary="ok temp note",
            payload=None,
            refs=None,
            redacted=1,
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 500,
                "scope": None,
                "session_id": None,
                "summary_min_group_size": 2,
                "summary_min_shared_tokens": 2,
                "archive_lookahead_days": 7,
                "archive_min_signal_reasons": 2,
                "link_min_shared_tokens": 2,
                "lifecycle_limit": 200,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_consolidation_review(conn, args)
        out = json.loads(buf.getvalue())

        self.assertEqual(out["kind"], "openclaw-mem.optimize.consolidation-review.v0")
        self.assertEqual(out["policy"]["writes_performed"], 0)
        self.assertEqual(out["policy"]["memory_mutation"], "none")
        self.assertEqual(out["policy"]["canonical_rewrite"], "forbidden")

        self.assertGreaterEqual(out["candidates"]["summary"]["groups"], 1)
        self.assertGreaterEqual(out["candidates"]["archive"]["count"], 1)
        self.assertGreaterEqual(out["candidates"]["links"]["pairs"], 1)

        summary_item = out["candidates"]["summary"]["items"][0]
        self.assertIn("draft_summary", summary_item)
        self.assertGreaterEqual(len(summary_item["source_event_refs"]), 2)
        self.assertIn("memory", summary_item["shared_tokens"])

        archive_item = out["candidates"]["archive"]["items"][0]
        self.assertEqual(archive_item["event_id"], "ev-5")
        self.assertIn("redacted", archive_item["low_signal_reasons"])

        link_item = out["candidates"]["links"]["items"][0]
        self.assertEqual(link_item["left"]["scope"], "alpha")
        self.assertNotEqual(link_item["left"]["session_id"], link_item["right"]["session_id"])

        rec_types = {r["type"] for r in out.get("recommendations", [])}
        self.assertIn("review_summary_candidates", rec_types)
        self.assertIn("stage_archive_candidates", rec_types)
        self.assertIn("review_link_candidates", rec_types)
        conn.close()

    def test_consolidation_review_protects_archive_candidates_with_recent_use_refs(self):
        conn = _connect(":memory:")
        self._insert_episode(
            conn,
            event_id="ev-protected",
            ts_ms=self._ts_days_ago(28),
            scope="alpha",
            session_id="s-old",
            event_type="tool.result",
            summary="temp low signal note",
            payload=None,
            refs={"recordRef": "obs:1"},
            redacted=1,
        )
        self._insert_episode(
            conn,
            event_id="ev-plain",
            ts_ms=self._ts_days_ago(28),
            scope="alpha",
            session_id="s-old",
            event_type="tool.result",
            summary="plain low signal note",
            payload=None,
            refs=None,
            redacted=1,
        )
        _insert_lifecycle_row(conn, selected_refs=["obs:1"])

        args = type(
            "Args",
            (),
            {
                "limit": 500,
                "scope": None,
                "session_id": None,
                "summary_min_group_size": 2,
                "summary_min_shared_tokens": 2,
                "archive_lookahead_days": 7,
                "archive_min_signal_reasons": 2,
                "link_min_shared_tokens": 2,
                "lifecycle_limit": 50,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_consolidation_review(conn, args)
        out = json.loads(buf.getvalue())

        archive = out["candidates"]["archive"]
        recent_use = out["signals"]["recent_use"]
        self.assertEqual(archive["count"], 1)
        self.assertEqual(archive["protected_by_recent_use"], 1)
        self.assertEqual(archive["items"][0]["event_id"], "ev-plain")
        self.assertEqual(recent_use["protected_archive_candidates"], 1)
        self.assertEqual(recent_use["linked_observation_rows"], 1)
        self.assertEqual(recent_use["items"][0]["id"], 1)
        conn.close()

    def test_consolidation_review_scope_and_session_filters(self):
        conn = _connect(":memory:")
        self._insert_episode(
            conn,
            event_id="alpha-1",
            ts_ms=self._ts_days_ago(1),
            scope="alpha-team",
            session_id="s-focus",
            event_type="conversation.user",
            summary="Cluster alpha memory drift issue",
            payload={"kind": "msg"},
            refs={"recordRef": "obs:10"},
        )
        self._insert_episode(
            conn,
            event_id="alpha-2",
            ts_ms=self._ts_days_ago(1),
            scope="alpha-team",
            session_id="s-focus",
            event_type="conversation.assistant",
            summary="Alpha memory drift issue needs triage",
            payload={"kind": "msg"},
            refs={"recordRef": "obs:11"},
        )
        self._insert_episode(
            conn,
            event_id="beta-1",
            ts_ms=self._ts_days_ago(1),
            scope="beta-team",
            session_id="s-other",
            event_type="conversation.user",
            summary="Unrelated beta scope event",
            payload={"kind": "msg"},
            refs={"recordRef": "obs:12"},
        )
        conn.commit()

        args = type(
            "Args",
            (),
            {
                "limit": 500,
                "scope": "alpha team",
                "session_id": "s-focus",
                "summary_min_group_size": 2,
                "summary_min_shared_tokens": 2,
                "archive_lookahead_days": 7,
                "archive_min_signal_reasons": 2,
                "link_min_shared_tokens": 2,
                "lifecycle_limit": 200,
                "top": 10,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_consolidation_review(conn, args)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["source"]["scope"], "alpha-team")
        self.assertEqual(out["source"]["session_id"], "s-focus")
        self.assertEqual(out["source"]["rows_scanned"], 2)
        self.assertEqual(out["candidates"]["summary"]["groups"], 1)
        conn.close()
