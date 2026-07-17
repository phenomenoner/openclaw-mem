from __future__ import annotations

import json
from argparse import Namespace

import pytest

from openclaw_mem.cli import build_parser, cmd_db_info, cmd_db_lifecycle_set, cmd_profile
from openclaw_mem.core.db import _connect
from openclaw_mem.core.lifecycle import (
    ACTIVE,
    CAPTURED,
    CATEGORIZED,
    CONSOLIDATED,
    HISTORY_LIMIT,
    LEGAL_TRANSITIONS,
    SOFT_ARCHIVED,
    STALE,
    LifecycleTransitionError,
    state_from_detail,
    transition,
)
from openclaw_mem.core.pack import build_pack
from openclaw_mem.core.recall import recall
from openclaw_mem.core.records import _insert_observation
from openclaw_mem.core.search import hybrid_search, lexical_search


def _row(conn, *, detail=None, summary="lifecycle fixture") -> int:
    row_id = _insert_observation(
        conn,
        {"summary": summary, "kind": "note", "detail": detail or {}},
    )
    conn.commit()
    return row_id


def test_missing_lifecycle_is_active_and_quarantine_is_orthogonal() -> None:
    assert state_from_detail({}) == ACTIVE
    assert state_from_detail({"trust": "quarantined"}) == ACTIVE
    assert state_from_detail({"lifecycle": {"archived_at": "2026-01-01T00:00:00Z"}}) == SOFT_ARCHIVED


def test_legal_transition_matrix_and_receipt() -> None:
    for from_state, targets in LEGAL_TRANSITIONS.items():
        for target in targets:
            conn = _connect(":memory:")
            try:
                row_id = _row(conn, detail={"lifecycle": {"state": from_state}})
                receipt = transition(conn, row_id, target, "matrix_test", "pytest")
                assert receipt["kind"] == "openclaw-mem.lifecycle.transition.v1"
                assert (receipt["from"], receipt["to"]) == (from_state, target)
                assert receipt["evidence_refs"] == [f"obs:{row_id}"]
            finally:
                conn.close()


def test_illegal_transition_has_actionable_hint_and_does_not_write() -> None:
    conn = _connect(":memory:")
    try:
        row_id = _row(conn, detail={"lifecycle": {"state": CAPTURED}})
        before = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (row_id,)).fetchone()[0]
        with pytest.raises(LifecycleTransitionError) as caught:
            transition(conn, row_id, SOFT_ARCHIVED, "invalid", "pytest")
        assert "allowed next states" in caught.value.hint
        after = conn.execute("SELECT detail_json FROM observations WHERE id = ?", (row_id,)).fetchone()[0]
        assert after == before
    finally:
        conn.close()


def test_history_is_bounded_and_same_state_is_idempotent() -> None:
    conn = _connect(":memory:")
    try:
        row_id = _row(conn)
        states = [CONSOLIDATED, ACTIVE] * 13
        for index, state in enumerate(states):
            transition(conn, row_id, state, f"cycle_{index}", "pytest")
        receipt = transition(conn, row_id, ACTIVE, "idempotent", "pytest")
        assert receipt["changed"] is False
        detail = json.loads(
            conn.execute("SELECT detail_json FROM observations WHERE id = ?", (row_id,)).fetchone()[0]
        )
        assert len(detail["lifecycle"]["history"]) == HISTORY_LIMIT
        assert detail["lifecycle"]["history"][-1]["changed"] is False
        assert detail["lifecycle"]["state"] == ACTIVE
        assert detail["lifecycle"]["last_reason"] == "idempotent"
        assert detail["lifecycle"]["updated_at"]
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [(CAPTURED, ACTIVE), (CATEGORIZED, STALE), (ACTIVE, SOFT_ARCHIVED), (SOFT_ARCHIVED, STALE)],
)
def test_representative_illegal_transitions(from_state: str, to_state: str) -> None:
    conn = _connect(":memory:")
    try:
        row_id = _row(conn, detail={"lifecycle": {"state": from_state}})
        with pytest.raises(LifecycleTransitionError):
            transition(conn, row_id, to_state, "invalid", "pytest")
    finally:
        conn.close()


def test_search_recall_and_hybrid_exclude_soft_archived_by_default() -> None:
    conn = _connect(":memory:")
    try:
        active_id = _row(conn, summary="lifecycle retrieval beacon active")
        archived_id = _row(
            conn,
            summary="lifecycle retrieval beacon archived",
            detail={"lifecycle": {"state": SOFT_ARCHIVED}},
        )

        default_lexical = lexical_search(conn, "lifecycle retrieval beacon", limit=10)
        archived_lexical = lexical_search(
            conn, "lifecycle retrieval beacon", limit=10, include_archived=True
        )
        assert {item["id"] for item in default_lexical} == {active_id}
        assert {item["id"] for item in archived_lexical} == {active_id, archived_id}

        default_hybrid = hybrid_search(
            conn,
            "lifecycle retrieval beacon",
            limit=10,
            vector_ids=[archived_id, active_id],
        )
        archived_hybrid = hybrid_search(
            conn,
            "lifecycle retrieval beacon",
            limit=10,
            vector_ids=[archived_id, active_id],
            include_archived=True,
        )
        assert {item["id"] for item in default_hybrid} == {active_id}
        assert {item["id"] for item in archived_hybrid} == {active_id, archived_id}

        default_recall = recall(conn, "lifecycle retrieval beacon", mode="lexical", limit=10)
        archived_recall = recall(
            conn,
            "lifecycle retrieval beacon",
            mode="lexical",
            limit=10,
            include_archived=True,
        )
        assert {item["id"] for item in default_recall["results"]} == {active_id}
        assert {item["id"] for item in archived_recall["results"]} == {active_id, archived_id}
    finally:
        conn.close()


def test_programmatic_pack_excludes_soft_archived_unless_requested() -> None:
    conn = _connect(":memory:")
    try:
        active_id = _row(conn, summary="pack lifecycle beacon active")
        archived_id = _row(
            conn,
            summary="pack lifecycle beacon archived",
            detail={"lifecycle": {"state": SOFT_ARCHIVED}},
        )
        default_pack = build_pack(conn, "pack lifecycle beacon", limit=10)
        archived_pack = build_pack(
            conn, "pack lifecycle beacon", limit=10, include_archived=True
        )
        assert {item["id"] for item in default_pack["items"]} == {active_id}
        assert {item["id"] for item in archived_pack["items"]} == {active_id, archived_id}
    finally:
        conn.close()


def test_cli_lifecycle_set_and_distribution_surfaces(capsys: pytest.CaptureFixture[str]) -> None:
    conn = _connect(":memory:")
    try:
        row_id = _row(conn)
        cmd_db_lifecycle_set(
            conn,
            Namespace(
                observation_id=row_id,
                state=STALE,
                reason="operator_review",
                actor="pytest",
                json=True,
            ),
        )
        receipt = json.loads(capsys.readouterr().out)
        assert receipt["kind"] == "openclaw-mem.lifecycle.transition.v1"
        assert receipt["to"] == STALE

        cmd_db_info(conn, Namespace(json=True))
        info = json.loads(capsys.readouterr().out)
        assert info["lifecycle_state_distribution"][STALE] == 1

        cmd_profile(conn, Namespace(json=True, db=":memory:"))
        profile = json.loads(capsys.readouterr().out)
        assert profile["lifecycle_state_distribution"][STALE] == 1
    finally:
        conn.close()


def test_cli_parsers_expose_archived_override_and_lifecycle_command() -> None:
    parser = build_parser()
    assert parser.parse_args(["search", "beacon"]).include_archived is False
    assert parser.parse_args(["search", "beacon", "--include-archived"]).include_archived is True
    assert parser.parse_args(["recall", "beacon", "--include-archived"]).include_archived is True
    assert parser.parse_args(["pack", "--query", "beacon", "--include-archived"]).include_archived is True
    lifecycle_args = parser.parse_args(
        ["db", "lifecycle", "set", "7", "--state", "stale", "--reason", "review"]
    )
    assert lifecycle_args.func is cmd_db_lifecycle_set
