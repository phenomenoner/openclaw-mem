from __future__ import annotations

import io
import json
import sqlite3
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from openclaw_mem.cli import build_parser
from openclaw_mem.core.api import connect, store_observation
from openclaw_mem.core.curation import rollback_optimize_assist
from openclaw_mem.core.pack import build_pack
from openclaw_mem.core.search import lexical_search
from openclaw_mem.core.use_decay import decay_candidates, priority_for, refresh_selected_records


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _iso_days_ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _detail(conn: sqlite3.Connection, obs_id: int) -> dict:
    row = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (obs_id,)).fetchone()
    return json.loads(row["detail_json"])


def _run(conn: sqlite3.Connection, argv: list[str]) -> dict:
    args = build_parser().parse_args([*argv, "--json"])
    output = io.StringIO()
    with redirect_stdout(output):
        args.func(conn, args)
    return json.loads(output.getvalue())


@pytest.mark.parametrize(
    ("kind", "detail", "expected"),
    [
        ("preference", {}, "P1"),
        ("decision", {}, "P1"),
        ("fact", {}, "P1"),
        ("learning", {}, "P1"),
        ("plan", {}, "P1"),
        ("event", {}, "P2"),
        ("note", {}, "P2"),
        ("tool", {}, "P2"),
        ("event", {"lifecycle": {"priority": "P0"}}, "P0"),
        ("note", {"lifecycle": {"priority": "p1"}}, "P1"),
    ],
)
def test_priority_resolution_explicit_then_kind(kind: str, detail: dict, expected: str) -> None:
    assert priority_for(kind, detail) == expected


def test_timeline_and_get_do_not_track_use_but_final_pack_citation_does() -> None:
    conn = connect(":memory:")
    try:
        obs_id = store_observation(
            conn,
            {"kind": "fact", "summary": "citation tracking needle", "detail": {}},
        )
        conn.commit()

        _run(conn, ["get", str(obs_id)])
        _run(conn, ["timeline", str(obs_id), "--window", "1"])
        assert "last_used_at" not in _detail(conn, obs_id).get("lifecycle", {})

        payload = build_pack(
            conn,
            "citation tracking needle",
            limit=2,
            budget_tokens=200,
            quota_enabled=False,
            use_tracking=True,
        )
        lifecycle = _detail(conn, obs_id)["lifecycle"]

        assert payload["items"][0]["recordRef"] == f"obs:{obs_id}"
        assert payload["lifecycle_write"]["selection"]["refreshed_record_refs"] == [f"obs:{obs_id}"]
        assert lifecycle["used_count"] == 1
        assert lifecycle["last_used_at"] == payload["lifecycle_write"]["ts"]
    finally:
        conn.close()


def test_use_tracking_env_zero_and_readonly_connections_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "readonly.sqlite"
    writable = connect(str(path))
    obs_id = store_observation(writable, {"kind": "fact", "summary": "readonly tracking", "detail": {}})
    writable.commit()

    monkeypatch.setenv("OPENCLAW_MEM_USE_TRACKING", "0")
    disabled = refresh_selected_records(
        writable,
        selected_refs=[f"obs:{obs_id}"],
        ts="2026-07-17T00:00:00Z",
    )
    assert disabled["status"] == "disabled"
    assert "last_used_at" not in _detail(writable, obs_id).get("lifecycle", {})
    writable.close()

    monkeypatch.setenv("OPENCLAW_MEM_USE_TRACKING", "1")
    readonly = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    readonly.row_factory = sqlite3.Row
    try:
        receipt = refresh_selected_records(
            readonly,
            selected_refs=[f"obs:{obs_id}"],
            ts="2026-07-17T00:00:00Z",
        )
        assert receipt["status"] == "readonly"
        assert receipt["mutation"]["writes_observations"] == 0
    finally:
        readonly.close()


def test_decay_candidate_threshold_table_and_p0_protection() -> None:
    conn = connect(":memory:")
    try:
        fixtures = [
            ("fact", 89, {"lifecycle": {"state": "active"}}),
            ("fact", 90, {"lifecycle": {"state": "active"}}),
            ("event", 29, {"lifecycle": {"state": "active"}}),
            ("event", 30, {"lifecycle": {"state": "active"}}),
            ("event", 365, {"lifecycle": {"state": "active", "priority": "P0"}}),
            ("event", 91, {"lifecycle": {"state": "active", "priority": "P1"}}),
        ]
        for index, (kind, days, detail) in enumerate(fixtures):
            store_observation(
                conn,
                {"ts": _iso_days_ago(days), "kind": kind, "summary": f"decay fixture {index}", "detail": detail},
            )
        conn.commit()

        receipt = decay_candidates(conn, p1_unused_days=90, p2_unused_days=30, now=NOW)
        by_id = {item["id"]: item for item in receipt["items"]}

        assert set(by_id) == {2, 4, 6}
        assert by_id[2]["priority"] == "P1"
        assert by_id[4]["priority"] == "P2"
        assert by_id[6]["threshold_days"] == 90
        assert receipt["protected_p0"] == 1
    finally:
        conn.close()


def test_decay_e2e_governed_archive_exclusion_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_DECAY_P2_UNUSED_DAYS", "30")
    conn = connect(":memory:")
    try:
        obs_id = store_observation(
            conn,
            {
                "ts": _iso_days_ago(31),
                "kind": "note",
                "summary": "reversible decay archive needle",
                "detail": {
                    "importance": {"score": 0.2, "label": "ignore"},
                    "lifecycle": {"state": "active", "priority": "P2"},
                },
            },
        )
        conn.commit()

        scan = _run(conn, ["curate", "scan", "--target", "memory", "--top", "20"])
        evolution = scan["inner"][1]["receipt"]
        decay_items = [item for item in evolution["items"] if item.get("candidate_id") == f"use-decay-p2-{obs_id}"]
        assert len(decay_items) == 1
        assert evolution["use_decay"]["thresholds"]["P2"] == 30
        recommendation_path = tmp_path / "decay.json"
        recommendation_path.write_text(
            json.dumps({**evolution, "items": decay_items}), encoding="utf-8"
        )

        reviewed = _run(
            conn,
            [
                "curate",
                "review",
                "--target",
                "memory",
                "--from-file",
                str(recommendation_path),
                "--approve-soft-archive",
            ],
        )
        governor_path = tmp_path / "governor.json"
        governor_path.write_text(json.dumps(reviewed["inner"]), encoding="utf-8")
        applied = _run(
            conn,
            [
                "curate",
                "apply",
                "--target",
                "memory",
                "--from-file",
                str(governor_path),
                "--run-dir",
                str(tmp_path / "assist"),
            ],
        )

        assert _detail(conn, obs_id)["lifecycle"]["state"] == "soft-archived"
        assert applied["inner"]["archived_counts"] == {
            "total": 1,
            "by_priority": {"P2": 1},
            "by_kind": {"note": 1},
            "by_trust": {"unknown": 1},
        }
        assert [receipt["to"] for receipt in applied["inner"]["lifecycle_transition_receipts"]] == [
            "stale",
            "soft-archived",
        ]
        assert lexical_search(conn, "reversible decay archive needle") == []

        rollback_ref = applied["inner"]["artifacts"]["rollback_ref"]
        rolled_back = rollback_optimize_assist(conn, rollback_ref, actor="test")
        assert rolled_back["ok"] is True
        assert _detail(conn, obs_id)["lifecycle"]["state"] == "active"
        assert lexical_search(conn, "reversible decay archive needle")[0]["id"] == obs_id
    finally:
        conn.close()
