import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_policy_loop


_UUID_A = "11111111-1111-1111-1111-111111111111"
_UUID_B = "22222222-2222-2222-2222-222222222222"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _insert_lifecycle_row(conn, *, selected: int, citation: int, candidate: int, memory_mutation: str = "none") -> None:
    receipt = {
        "kind": "openclaw-mem.pack.lifecycle-shadow.v1",
        "ts": _now_iso(),
        "policies": {
            "trust_policy_mode": "exclude_quarantined_fail_open",
            "graph_provenance_policy_mode": "structured_only_fail_open",
        },
        "mutation": {
            "memory_mutation": memory_mutation,
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
            _now_iso(),
            "sha256:abc",
            "sha256:sig",
            selected,
            citation,
            candidate,
            json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()


class TestOptimizePolicyLoop(unittest.TestCase):
    def test_optimize_parser_parses_policy_loop_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "policy-loop",
                "--review-limit",
                "800",
                "--writeback-limit",
                "320",
                "--lifecycle-limit",
                "64",
                "--miss-min-count",
                "3",
                "--scope",
                "team/alpha",
                "--top",
                "9",
                "--sunrise-state",
                "/tmp/sunrise.json",
                "--min-live-green-streak",
                "20",
                "--min-lifecycle-runs-stage-b",
                "5",
                "--min-lifecycle-runs-stage-c",
                "10",
                "--min-writeback-eligible-ratio",
                "0.7",
                "--max-repeated-miss-groups-stage-c",
                "2",
            ]
        )

        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "policy-loop")
        self.assertEqual(args.review_limit, 800)
        self.assertEqual(args.writeback_limit, 320)
        self.assertEqual(args.lifecycle_limit, 64)
        self.assertEqual(args.miss_min_count, 3)
        self.assertEqual(args.scope, "team/alpha")
        self.assertEqual(args.top, 9)
        self.assertEqual(args.sunrise_state, "/tmp/sunrise.json")
        self.assertEqual(args.min_live_green_streak, 20)
        self.assertEqual(args.min_lifecycle_runs_stage_b, 5)
        self.assertEqual(args.min_lifecycle_runs_stage_c, 10)
        self.assertEqual(args.min_writeback_eligible_ratio, 0.7)
        self.assertEqual(args.max_repeated_miss_groups_stage_c, 2)

    def test_optimize_policy_loop_reports_ready_stage_gates_when_evidence_is_green(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _now_iso(),
                "kind": "fact",
                "tool_name": "memory_store",
                "summary": "Remember Alpha memory",
                "detail": {"memory_id": _UUID_A, "importance": {"score": 0.91}, "scope": "team/alpha", "category": "fact"},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _now_iso(),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Remember Beta memory",
                "detail": {"memory": {"lancedb_id": _UUID_B}, "importance": {"score": 0.62}, "scope": "team/alpha", "category": "note"},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _now_iso(),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "No lancedb id yet",
                "detail": {"scope": "team/alpha"},
            },
        )

        _insert_lifecycle_row(conn, selected=2, citation=2, candidate=3)
        _insert_lifecycle_row(conn, selected=1, citation=1, candidate=2)

        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "sunrise_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "stage": "A-live",
                        "readyForStageB": True,
                        "liveGreenStreak": 20,
                        "lastHealthy": True,
                        "lastRunAt": _now_iso(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            args = type(
                "Args",
                (),
                {
                    "review_limit": 1000,
                    "writeback_limit": 500,
                    "lifecycle_limit": 200,
                    "miss_min_count": 2,
                    "scope": None,
                    "top": 10,
                    "sunrise_state": str(state_path),
                    "min_live_green_streak": 18,
                    "min_lifecycle_runs_stage_b": 2,
                    "min_lifecycle_runs_stage_c": 2,
                    "min_writeback_eligible_ratio": 0.6,
                    "max_repeated_miss_groups_stage_c": 1,
                    "json": True,
                },
            )()

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_policy_loop(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["kind"], "openclaw-mem.optimize.policy-loop.v0")
        self.assertEqual(out["policy"]["memory_mutation"], "none")
        self.assertEqual(out["policy"]["writes_performed"], 0)
        self.assertEqual(out["sunrise"]["stage_b"]["status"], "ready")
        self.assertEqual(out["sunrise"]["stage_c"]["status"], "ready")
        self.assertEqual(out["signals"]["writeback"]["eligible"], 2)
        self.assertEqual(out["signals"]["writeback"]["scanned"], 3)
        self.assertEqual(out["signals"]["writeback"]["eligible_ratio"], 0.6667)

        recommendation_types = {r["type"] for r in out.get("recommendations", [])}
        self.assertIn("stage_b_canary_review_packet", recommendation_types)

        conn.close()

    def test_optimize_policy_loop_holds_when_state_missing_and_mutation_drift_detected(self):
        conn = _connect(":memory:")

        _insert_observation(
            conn,
            {
                "ts": _now_iso(),
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "No lancedb id",
                "detail": {"scope": "team/beta"},
            },
        )

        _insert_observation(
            conn,
            {
                "ts": _now_iso(),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "recall miss 1",
                "detail": {"scope": "team/beta", "query": "rollout gate", "results": []},
            },
        )
        _insert_observation(
            conn,
            {
                "ts": _now_iso(),
                "kind": "tool",
                "tool_name": "memory_recall",
                "summary": "recall miss 2",
                "detail": {"scope": "team/beta", "query": "rollout gate", "results": 0},
            },
        )

        _insert_lifecycle_row(conn, selected=0, citation=0, candidate=2, memory_mutation="archive_candidates")

        args = type(
            "Args",
            (),
            {
                "review_limit": 1000,
                "writeback_limit": 500,
                "lifecycle_limit": 200,
                "miss_min_count": 2,
                "scope": None,
                "top": 10,
                "sunrise_state": None,
                "min_live_green_streak": 18,
                "min_lifecycle_runs_stage_b": 1,
                "min_lifecycle_runs_stage_c": 1,
                "min_writeback_eligible_ratio": 0.5,
                "max_repeated_miss_groups_stage_c": 0,
                "json": True,
            },
        )()

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_optimize_policy_loop(conn, args)

        out = json.loads(buf.getvalue())
        self.assertEqual(out["sunrise"]["stage_b"]["status"], "hold")
        self.assertIn("sunrise_state_missing", out["sunrise"]["stage_b"]["reasons"])
        self.assertIn("writeback_eligible_ratio_below_threshold", out["sunrise"]["stage_b"]["reasons"])
        self.assertIn("lifecycle_mutation_not_shadow", out["sunrise"]["stage_b"]["reasons"])

        self.assertEqual(out["sunrise"]["stage_c"]["status"], "hold")
        self.assertIn("stage_b_not_ready", out["sunrise"]["stage_c"]["reasons"])
        self.assertIn("repeated_miss_pressure_high", out["sunrise"]["stage_c"]["reasons"])

        recommendation_types = {r["type"] for r in out.get("recommendations", [])}
        self.assertIn("improve_writeback_linkage", recommendation_types)
        self.assertIn("target_recall_gap_review", recommendation_types)

        conn.close()
