from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from openclaw_mem import cli


def test_qdrant_status_reports_optional_dependency_missing(tmp_path: Path, capsys) -> None:
    db = tmp_path / "memory.sqlite"
    with patch("openclaw_mem.cli.importlib.util.find_spec", return_value=None):
        cli.cmd_qdrant_status(
            sqlite3.connect(":memory:"), argparse.Namespace(db=str(db), json=True)
        )
    payload = json.loads(capsys.readouterr().out)
    assert payload["qdrant"] == "not_installed"


def test_qdrant_recall_missing_extra_returns_actionable_error(tmp_path: Path, capsys) -> None:
    db = tmp_path / "memory.sqlite"
    (tmp_path / "qdrant-edge").mkdir()
    args = argparse.Namespace(db=str(db), json=True, vector="[0.1]", limit=5, query="")
    with patch("openclaw_mem.cli.importlib.util.find_spec", return_value=None):
        cli.cmd_qdrant_recall(sqlite3.connect(":memory:"), args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "qdrant_extra_not_installed"
    assert payload["hint"] == "pip install openclaw-context-pack[qdrant]"


def test_db_info_reports_optional_dependency_missing(tmp_path: Path, capsys) -> None:
    db = tmp_path / "memory.sqlite"
    conn = cli._connect(str(db))
    try:
        with patch("openclaw_mem.cli.importlib.util.find_spec", return_value=None):
            cli.cmd_db_info(conn, argparse.Namespace(db=str(db), json=True))
    finally:
        conn.close()
    assert json.loads(capsys.readouterr().out)["qdrant"] == "not_installed"
