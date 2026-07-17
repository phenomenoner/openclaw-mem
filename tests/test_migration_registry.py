from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from openclaw_mem import cli


def test_unstamped_database_runs_baseline_and_stamps_version(tmp_path: Path) -> None:
    db = tmp_path / "v0.sqlite"
    raw = sqlite3.connect(db)
    raw.execute("CREATE TABLE legacy_marker(value TEXT)")
    raw.commit()
    raw.close()

    conn = cli._connect(str(db))
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute(
            "SELECT value FROM meta WHERE key = 'min_reader_version'"
        ).fetchone()[0] == "1"
    finally:
        conn.close()


def test_stamped_database_uses_connect_fast_path(tmp_path: Path) -> None:
    db = tmp_path / "v1.sqlite"
    first = cli._connect(str(db))
    first.close()

    with patch("openclaw_mem.cli._init_db") as init_db:
        second = cli._connect(str(db))
        second.close()
    init_db.assert_not_called()


def test_newer_database_version_fails_with_actionable_error(tmp_path: Path) -> None:
    db = tmp_path / "future.sqlite"
    raw = sqlite3.connect(db)
    raw.execute("PRAGMA user_version = 99")
    raw.commit()
    raw.close()

    with pytest.raises(RuntimeError, match="db_version_unsupported.*read-only"):
        cli._connect(str(db))


def test_db_info_reports_migration_application(tmp_path: Path, capsys) -> None:
    db = tmp_path / "info.sqlite"
    conn = cli._connect(str(db))
    try:
        cli.cmd_db_info(conn, type("Args", (), {"db": str(db), "json": True})())
    finally:
        conn.close()
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["migrations"] == [
        {"id": 1, "description": "baseline schema", "cost": "cheap", "applied": True},
        {
            "id": 2,
            "description": "rebuild bilingual and episodic FTS indexes",
            "cost": "expensive",
            "applied": True,
        },
        {
            "id": 3,
            "description": "build CJK trigram FTS index",
            "cost": "expensive",
            "applied": True,
        },
    ]
