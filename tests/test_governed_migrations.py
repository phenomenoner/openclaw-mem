from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from openclaw_mem.core import db as db_core
from openclaw_mem.core.search import lexical_search


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_v1(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT,
            summary TEXT,
            summary_en TEXT,
            lang TEXT,
            tool_name TEXT,
            detail_json TEXT
        );
        CREATE VIRTUAL TABLE observations_fts
        USING fts5(summary, tool_name, detail_json, content='observations', content_rowid='id');
        CREATE TABLE episodic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            ts_ms INTEGER NOT NULL,
            scope TEXT NOT NULL,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            type TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_json TEXT,
            refs_json TEXT,
            redacted INTEGER NOT NULL DEFAULT 0,
            schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE episodic_events_fts
        USING fts5(summary, type, session_id, agent_id, content='episodic_events', content_rowid='id');
        INSERT INTO observations(ts, kind, summary, summary_en, lang, tool_name, detail_json)
        VALUES ('2026-01-01T00:00:00Z', 'fact', '舊庫記憶', 'legacy memory', 'zh', 'fixture', '{}');
        INSERT INTO observations_fts(rowid, summary, tool_name, detail_json)
        VALUES (1, '舊庫記憶', 'fixture', '{}');
        INSERT INTO episodic_events(
            event_id, ts_ms, scope, session_id, agent_id, type, summary,
            payload_json, refs_json, schema_version, created_at
        ) VALUES (
            'evt-1', 1, 'fixture', 's1', 'a1', 'decision', '保留回填內容',
            '{"decision":"use sqlite"}', '["obs:1"]', 'v1', '2026-01-01T00:00:00Z'
        );
        INSERT INTO episodic_events_fts(rowid, summary, type, session_id, agent_id)
        VALUES (1, '保留回填內容', 'decision', 's1', 'a1');
        PRAGMA user_version = 1;
        """
    )
    conn.commit()
    conn.close()


def test_connect_legacy_v1_is_compat_read_without_hidden_rebuild(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    _legacy_v1(path)
    before = _sha256(path)

    conn = db_core._connect(str(path))
    try:
        state = db_core.migration_state(conn)
        assert state["compat_mode"] is True
        assert state["pending"] == [2]
        assert "db migrate" in state["hint"]
        assert conn.execute("SELECT summary FROM observations WHERE id = 1").fetchone()[0] == "舊庫記憶"
        assert lexical_search(conn, "舊庫", limit=5)[0]["id"] == 1
    finally:
        conn.close()

    assert _sha256(path) == before


def test_migrate_dry_run_is_zero_write(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    _legacy_v1(path)
    before = _sha256(path)

    plan = db_core.migrate_database(path, dry_run=True)

    assert plan["kind"] == "openclaw-mem.db.migration.plan.v1"
    assert plan["from_version"] == 1
    assert plan["to_version"] == 2
    assert plan["steps"][0]["cost"] == "expensive"
    assert not Path(plan["backup_path"]).exists()
    assert _sha256(path) == before


def test_migrate_preserves_rows_rebuilds_search_and_writes_receipt(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    receipt_path = tmp_path / "migration.json"
    _legacy_v1(path)

    receipt = db_core.migrate_database(path, receipt_path=receipt_path)

    assert receipt["kind"] == "openclaw-mem.db.migration.receipt.v1"
    assert receipt["from_version"] == 1
    assert receipt["to_version"] == 2
    assert receipt["row_counts_before"] == receipt["row_counts_after"]
    assert receipt_path.exists()
    assert Path(receipt["backup_path"]).exists()
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert "summary_en" in {
            row[1] for row in conn.execute("PRAGMA table_info(observations_fts)")
        }
        assert "search_text" in {
            row[1] for row in conn.execute("PRAGMA table_info(episodic_events_fts)")
        }
        search_text = conn.execute(
            "SELECT search_text FROM episodic_events WHERE id = 1"
        ).fetchone()[0]
        assert "use sqlite" in search_text
        assert conn.execute(
            "SELECT rowid FROM observations_fts WHERE observations_fts MATCH 'legacy'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT rowid FROM episodic_events_fts WHERE episodic_events_fts MATCH 'sqlite'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_rollback_restores_backup_and_keeps_migrated_copy(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    receipt_path = tmp_path / "migration.json"
    _legacy_v1(path)
    receipt = db_core.migrate_database(path, receipt_path=receipt_path)
    backup_hash = _sha256(Path(receipt["backup_path"]))

    rollback = db_core.rollback_database(path, receipt_path)

    assert rollback["kind"] == "openclaw-mem.db.rollback.receipt.v1"
    assert Path(rollback["rolled_back_path"]).exists()
    assert _sha256(path) == backup_hash
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(kind="not-a-receipt"),
        lambda payload: payload.update(db_path="elsewhere.sqlite"),
        lambda payload: payload.update(backup_sha256="0" * 64),
    ],
)
def test_invalid_rollback_receipt_is_denied_without_mutation(tmp_path: Path, mutate) -> None:
    path = tmp_path / "legacy.sqlite"
    receipt_path = tmp_path / "migration.json"
    _legacy_v1(path)
    receipt = db_core.migrate_database(path, receipt_path=receipt_path)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    mutate(payload)
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    before = _sha256(path)

    with pytest.raises((RuntimeError, ValueError)):
        db_core.rollback_database(path, receipt_path)

    assert _sha256(path) == before
    assert Path(receipt["backup_path"]).exists()
