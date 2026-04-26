import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation, build_parser, cmd_optimize_assist_apply


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


class TestOptimizeAssistApply(unittest.TestCase):
    def test_optimize_parser_parses_assist_apply_flags(self):
        args = build_parser().parse_args(
            [
                "optimize",
                "assist-apply",
                "--from-file",
                "/tmp/governor.json",
                "--operator",
                "lyria",
                "--lane",
                "observations.assist",
                "--run-dir",
                "/tmp/assist-runs",
                "--max-rows-per-run",
                "3",
                "--max-rows-per-24h",
                "9",
                "--max-importance-adjustments-per-run",
                "2",
                "--max-importance-adjustments-per-24h",
                "7",
                "--dry-run",
            ]
        )
        self.assertEqual(args.cmd, "optimize")
        self.assertEqual(args.optimize_cmd, "assist-apply")
        self.assertEqual(args.from_file, "/tmp/governor.json")
        self.assertEqual(args.operator, "lyria")
        self.assertEqual(args.lane, "observations.assist")
        self.assertEqual(args.run_dir, "/tmp/assist-runs")
        self.assertEqual(args.max_rows_per_run, 3)
        self.assertEqual(args.max_rows_per_24h, 9)
        self.assertEqual(args.max_importance_adjustments_per_run, 2)
        self.assertEqual(args.max_importance_adjustments_per_24h, 7)
        self.assertTrue(args.dry_run)

    def test_assist_apply_updates_importance_score_and_label(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.52, "label": "nice_to_have"}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"importance-downshift-{obs_id}",
                    "recommended_action": "adjust_importance_score",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"importance": {"score": 0.42, "label": "ignore", "delta": -0.1, "reason_code": "stale_pressure"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["result"], "applied")
            self.assertEqual(out["applied_rows"], 1)
            self.assertEqual(out["applied_action_counts"]["adjust_importance_score"], 1)
            self.assertTrue(any(x["path"] == "/importance/score" for x in out["diff_summary"]))
            self.assertTrue(any(x["path"] == "/importance/label" for x in out["diff_summary"]))
            self.assertTrue(Path(out["artifacts"]["effect_ref"]).exists())
            effect = json.loads(Path(out["artifacts"]["effect_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(effect["kind"], "openclaw-mem.optimize.assist.effect-batch.v0")
            self.assertEqual(effect["items"][0]["effect_summary"], "insufficient_data")

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail = json.loads(row["detail_json"])
        self.assertEqual(detail["importance"]["score"], 0.42)
        self.assertEqual(detail["importance"]["label"], "ignore")
        self.assertEqual(detail["importance"]["method"], "optimize_assist")
        self.assertEqual(detail["optimization"]["assist"]["effect"]["effect_summary"], "insufficient_data")
        conn.close()

    def test_assist_apply_dry_run_emits_receipts_and_skips_write(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.32}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"stale-candidate-{obs_id}",
                    "recommended_action": "set_stale_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": True,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["kind"], "openclaw-mem.optimize.assist.after.v1")
            self.assertEqual(out["result"], "dry_run")
            self.assertEqual(out["applied_rows"], 0)
            self.assertEqual(out["skipped_rows"], 1)
            self.assertTrue(Path(out["artifacts"]["before_ref"]).exists())
            self.assertTrue(Path(out["artifacts"]["after_ref"]).exists())
            self.assertTrue(Path(out["artifacts"]["rollback_ref"]).exists())
            self.assertTrue(Path(out["artifacts"]["effect_ref"]).exists())

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail = json.loads(row["detail_json"])
        self.assertNotIn("lifecycle", detail)
        conn.close()

    def test_assist_apply_updates_observation_detail_json(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.32}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"stale-candidate-{obs_id}",
                    "recommended_action": "set_stale_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["result"], "applied")
            self.assertEqual(out["applied_rows"], 1)
            self.assertEqual(len(out["diff_summary"]), 2)

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail = json.loads(row["detail_json"])
        self.assertTrue(detail["lifecycle"]["stale_candidate"])
        self.assertEqual(detail["lifecycle"]["stale_reason_code"], "age_threshold")
        self.assertEqual(detail["optimization"]["assist"]["proposal_id"], f"stale-candidate-{obs_id}")
        conn.close()

    def test_assist_apply_blocks_second_attempt_for_same_packet(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.32}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"stale-candidate-{obs_id}",
                    "recommended_action": "set_stale_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"lifecycle": {"stale_candidate": True, "stale_reason_code": "age_threshold"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": True,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                cmd_optimize_assist_apply(conn, args)
            second_buf = io.StringIO()
            with redirect_stdout(second_buf):
                cmd_optimize_assist_apply(conn, args)

            first = json.loads(first_buf.getvalue())
            second = json.loads(second_buf.getvalue())

        self.assertEqual(first["result"], "dry_run")
        self.assertEqual(second["result"], "aborted")
        self.assertIn("max_retries_per_packet_exceeded", second["blocked_by_caps"])
        conn.close()

    def test_assist_apply_blocks_when_importance_family_cap_is_exceeded(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_ids = [
            _insert_observation(
                conn,
                {
                    "ts": stale_ts,
                    "kind": "note",
                    "tool_name": "memory_store",
                    "summary": f"Candidate memory {i}",
                    "detail": {"scope": "team/alpha", "importance": {"score": 0.42, "label": "ignore"}},
                },
            )
            for i in range(4)
        ]
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"importance-downshift-{obs_id}",
                    "recommended_action": "adjust_importance_score",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"importance": {"score": 0.32, "label": "ignore", "delta": -0.1, "reason_code": "stale_pressure"}},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
                for obs_id in obs_ids
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "max_importance_adjustments_per_run": 3,
                    "max_importance_adjustments_per_24h": 10,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())

        self.assertEqual(out["result"], "aborted")
        self.assertIn("max_importance_adjustments_per_run_exceeded", out["blocked_by_caps"])
        self.assertEqual(out["applied_action_counts"]["adjust_importance_score"], 0)
        conn.close()

    def test_assist_apply_soft_archive_dry_run_then_real_apply_with_receipts(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        obs_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Archive candidate memory",
                "detail": {"scope": "team/alpha", "importance": {"score": 0.18, "label": "ignore"}},
            },
        )
        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"soft-archive-candidate-{obs_id}",
                    "recommended_action": "set_soft_archive_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": obs_id, "recordRef": f"obs:{obs_id}"},
                    "patch": {"lifecycle": {"soft_archive_candidate": True, "set_archived_at": True, "archive_reason_code": "stale_low_importance"}},
                    "evidence": {"recent_use_count": 0, "importance": "ignore"},
                    "evidence_refs": [f"obs:{obs_id}"],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td_dry:
            dry_path = Path(td_dry) / "governor.json"
            dry_path.write_text(json.dumps(packet), encoding="utf-8")
            dry_args = type(
                "Args",
                (),
                {
                    "from_file": str(dry_path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td_dry,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": True,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            dry_buf = io.StringIO()
            with redirect_stdout(dry_buf):
                cmd_optimize_assist_apply(conn, dry_args)
            dry_out = json.loads(dry_buf.getvalue())
            self.assertEqual(dry_out["result"], "dry_run")
            self.assertEqual(dry_out["applied_rows"], 0)
            self.assertEqual(dry_out["skipped_rows"], 1)

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail_after_dry = json.loads(row["detail_json"])
        self.assertFalse(isinstance(detail_after_dry.get("lifecycle"), dict) and bool(detail_after_dry["lifecycle"].get("archived_at")))

        with tempfile.TemporaryDirectory() as td_apply:
            apply_path = Path(td_apply) / "governor.json"
            apply_path.write_text(json.dumps(packet), encoding="utf-8")
            apply_args = type(
                "Args",
                (),
                {
                    "from_file": str(apply_path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td_apply,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            apply_buf = io.StringIO()
            with redirect_stdout(apply_buf):
                cmd_optimize_assist_apply(conn, apply_args)
            apply_out = json.loads(apply_buf.getvalue())
            self.assertEqual(apply_out["result"], "applied")
            self.assertEqual(apply_out["applied_rows"], 1)
            self.assertEqual(apply_out["applied_action_counts"]["set_soft_archive_candidate"], 1)
            self.assertTrue(any(x["path"] == "/lifecycle/archived_at" for x in apply_out["diff_summary"]))
            self.assertTrue(any(x["path"] == "/lifecycle/archive_reason_code" for x in apply_out["diff_summary"]))
            rollback = json.loads(Path(apply_out["artifacts"]["rollback_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(rollback["kind"], "openclaw-mem.optimize.assist.rollback.v1")
            self.assertTrue(rollback["mutations"][0].get("after_detail_json"))

        row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
        detail_after_apply = json.loads(row["detail_json"])
        self.assertTrue(detail_after_apply["lifecycle"]["soft_archive_candidate"])
        self.assertEqual(detail_after_apply["lifecycle"]["archive_reason_code"], "stale_low_importance")
        self.assertTrue(isinstance(detail_after_apply["lifecycle"].get("archived_at"), str) and detail_after_apply["lifecycle"]["archived_at"])
        conn.close()

    def test_assist_apply_soft_archive_rechecks_and_skips_protected_rows(self):
        conn = _connect(":memory:")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=150)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        must_remember_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "decision",
                "tool_name": "memory_store",
                "summary": "Critical decision should never archive",
                "detail": {"importance": {"score": 0.92, "label": "must_remember"}},
            },
        )
        recent_use_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Old low-value note but recently reused",
                "detail": {"importance": {"score": 0.2, "label": "ignore"}},
            },
        )
        already_archived_id = _insert_observation(
            conn,
            {
                "ts": stale_ts,
                "kind": "note",
                "tool_name": "memory_store",
                "summary": "Already archived note",
                "detail": {
                    "importance": {"score": 0.2, "label": "ignore"},
                    "lifecycle": {"archived_at": _iso_days_ago(10), "archive_reason_code": "stale_low_importance"},
                },
            },
        )
        _insert_lifecycle_row(conn, selected_refs=[f"obs:{recent_use_id}"])

        packet = {
            "kind": "openclaw-mem.optimize.governor-review.v0",
            "items": [
                {
                    "candidate_id": f"soft-archive-candidate-{must_remember_id}",
                    "recommended_action": "set_soft_archive_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": must_remember_id, "recordRef": f"obs:{must_remember_id}"},
                    "patch": {"lifecycle": {"soft_archive_candidate": True, "set_archived_at": True, "archive_reason_code": "stale_low_importance"}},
                    "evidence": {"recent_use_count": 0, "importance": "must_remember"},
                    "evidence_refs": [f"obs:{must_remember_id}"],
                },
                {
                    "candidate_id": f"soft-archive-candidate-{recent_use_id}",
                    "recommended_action": "set_soft_archive_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": recent_use_id, "recordRef": f"obs:{recent_use_id}"},
                    "patch": {"lifecycle": {"soft_archive_candidate": True, "set_archived_at": True, "archive_reason_code": "stale_low_importance"}},
                    "evidence": {"recent_use_count": 0, "importance": "ignore"},
                    "evidence_refs": [f"obs:{recent_use_id}"],
                },
                {
                    "candidate_id": f"soft-archive-candidate-{already_archived_id}",
                    "recommended_action": "set_soft_archive_candidate",
                    "decision": "approved_for_apply",
                    "apply_lane": "observations.assist",
                    "target": {"observationId": already_archived_id, "recordRef": f"obs:{already_archived_id}"},
                    "patch": {"lifecycle": {"soft_archive_candidate": True, "set_archived_at": True, "archive_reason_code": "stale_low_importance"}},
                    "evidence": {"recent_use_count": 0, "importance": "ignore"},
                    "evidence_refs": [f"obs:{already_archived_id}"],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "governor.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "from_file": str(path),
                    "operator": "lyria",
                    "lane": "observations.assist",
                    "run_dir": td,
                    "max_rows_per_run": 5,
                    "max_rows_per_24h": 20,
                    "dry_run": False,
                    "db": ":memory:",
                    "json": True,
                },
            )()
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_optimize_assist_apply(conn, args)
            out = json.loads(buf.getvalue())

        self.assertEqual(out["result"], "applied")
        self.assertEqual(out["applied_rows"], 0)
        self.assertEqual(out["skipped_rows"], 3)
        self.assertEqual(out["applied_action_counts"]["set_soft_archive_candidate"], 0)
        skip_reasons = {entry["reason"] for entry in out["skipped_by_protection"]}
        self.assertIn("must_remember_protected", skip_reasons)
        self.assertIn("recent_use_conflict_protected", skip_reasons)
        self.assertIn("already_archived_idempotent_skip", skip_reasons)

        must_detail = json.loads(conn.execute("SELECT detail_json FROM observations WHERE id = ?", (must_remember_id,)).fetchone()["detail_json"])
        self.assertFalse(isinstance(must_detail.get("lifecycle"), dict) and bool(must_detail["lifecycle"].get("archived_at")))

        recent_detail = json.loads(conn.execute("SELECT detail_json FROM observations WHERE id = ?", (recent_use_id,)).fetchone()["detail_json"])
        self.assertFalse(isinstance(recent_detail.get("lifecycle"), dict) and bool(recent_detail["lifecycle"].get("archived_at")))

        archived_detail = json.loads(conn.execute("SELECT detail_json FROM observations WHERE id = ?", (already_archived_id,)).fetchone()["detail_json"])
        self.assertEqual(archived_detail["lifecycle"]["archive_reason_code"], "stale_low_importance")
        self.assertTrue(archived_detail["lifecycle"]["archived_at"])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 3)
        conn.close()


if __name__ == "__main__":
    unittest.main()
