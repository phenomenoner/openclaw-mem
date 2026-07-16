from __future__ import annotations

import sqlite3

from openclaw_mem.core.db import (
    CURRENT_DB_VERSION,
    MIGRATIONS,
    _apply_trigram_migration,
    _connect,
)
from openclaw_mem.core.records import _insert_observation
from openclaw_mem.core.search import lexical_search


def _store(conn: sqlite3.Connection, summary: str, *, summary_en: str | None = None) -> int:
    row_id = _insert_observation(
        conn,
        {
            "ts": "2026-01-01T00:00:00Z",
            "kind": "fact",
            "summary": summary,
            "summary_en": summary_en,
            "tool_name": "fixture",
            "detail": {},
        },
    )
    conn.commit()
    return row_id


def test_trigram_migration_registry_and_new_database_generation() -> None:
    assert CURRENT_DB_VERSION == 3
    assert [(item.id, item.cost) for item in MIGRATIONS] == [
        (1, "cheap"),
        (2, "expensive"),
        (3, "expensive"),
    ]
    conn = _connect(":memory:")
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'observations_fts_tri'"
        ).fetchone()
    finally:
        conn.close()


def test_cjk_query_router_recovers_four_pain_points_after_migration() -> None:
    conn = _connect(":memory:")
    try:
        expected = {
            "記憶治理": _store(conn, "記憶治理需要可回滾收據"),
            "偏好": _store(conn, "使用者偏好本地優先"),
            "使用openclaw-mem做": _store(conn, "使用openclaw-mem做長期記憶"),
            "治理 openclaw": _store(conn, "治理 openclaw 的混合檢索路徑"),
        }

        for query, row_id in expected.items():
            results = lexical_search(conn, query, limit=10)
            assert row_id in {item["id"] for item in results}, query
            lanes = {lane for item in results for lane in item["lanes_used"]}
            if query == "偏好":
                assert "like" in lanes
            else:
                assert "trigram" in lanes
        mixed = lexical_search(conn, "治理 openclaw", limit=10)
        assert {"unicode61", "trigram"}.issubset(
            {lane for item in mixed for lane in item["lanes_used"]}
        )
    finally:
        conn.close()


def test_post_migration_writes_are_synchronized_to_trigram_index() -> None:
    conn = _connect(":memory:")
    try:
        row_id = _store(conn, "新增資料立即同步三元索引")
        assert conn.execute(
            "SELECT rowid FROM observations_fts_tri "
            "WHERE observations_fts_tri MATCH ?",
            ('"立即同步"',),
        ).fetchone()[0] == row_id
        assert lexical_search(conn, "立即同步", limit=5)[0]["id"] == row_id
    finally:
        conn.close()


def test_nonmigrated_database_keeps_existing_cjk_fail_open_behavior() -> None:
    conn = _connect(":memory:")
    try:
        conn.execute("DROP TABLE observations_fts_tri")
        conn.execute("PRAGMA user_version = 2")
        row_id = _store(conn, "未遷移仍可查記憶治理")
        results = lexical_search(conn, "記憶治理", limit=5)
        assert row_id in {item["id"] for item in results}
        assert all("trigram" not in item["lanes_used"] for item in results)
    finally:
        conn.close()


def test_english_result_order_is_unchanged_by_trigram_lane() -> None:
    conn = _connect(":memory:")
    try:
        _store(conn, "alpha memory first")
        _store(conn, "alpha memory second")
        before = [item["id"] for item in lexical_search(conn, "alpha", limit=10)]
        _apply_trigram_migration(conn)
        conn.commit()
        after = [item["id"] for item in lexical_search(conn, "alpha", limit=10)]
        assert after == before
    finally:
        conn.close()

