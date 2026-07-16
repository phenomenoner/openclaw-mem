from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from openclaw_mem.cli import _connect, cmd_db_info


def _info(conn, db: Path) -> dict:
    output = StringIO()
    with redirect_stdout(output):
        cmd_db_info(conn, argparse.Namespace(db=str(db), json=True))
    return json.loads(output.getvalue())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_db_info_reports_empty_stamped_database(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    conn = _connect(str(db))
    try:
        payload = _info(conn, db)
    finally:
        conn.close()
    assert payload["kind"] == "openclaw-mem.db.info.v1"
    assert payload["user_version"] == 1
    assert payload["tables"]["observations"] == 0
    assert payload["fts_integrity"]["observations_fts"] is True
    assert payload["summary_en_coverage"] == {"present": 0, "total": 0, "ratio": 0.0}


def test_db_info_reports_rows_language_and_embedding_distribution(tmp_path: Path) -> None:
    db = tmp_path / "populated.sqlite"
    conn = _connect(str(db))
    try:
        conn.executemany(
            "INSERT INTO observations(ts, kind, summary, summary_en, lang, detail_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("2026-01-01T00:00:00Z", "note", "中文", "Chinese", "zh", "{}"),
                ("2026-01-02T00:00:00Z", "note", "English", None, "en", "{}"),
            ],
        )
        conn.execute(
            "INSERT INTO observation_embeddings(observation_id, model, dim, vector, norm, created_at) "
            "VALUES (1, 'fixture', 2, ?, 1.0, '2026-01-01T00:00:00Z')",
            (b"12345678",),
        )
        conn.commit()
        payload = _info(conn, db)
    finally:
        conn.close()
    assert payload["tables"]["observations"] == 2
    assert payload["lang_distribution"] == {"en": 1, "zh": 1}
    assert payload["summary_en_coverage"] == {"present": 1, "total": 2, "ratio": 0.5}
    assert payload["embeddings"]["observation_embeddings"]["distributions"] == [
        {"model": "fixture", "dim": 2, "count": 1}
    ]


def test_db_info_readonly_connection_does_not_change_file(tmp_path: Path) -> None:
    db = tmp_path / "readonly.sqlite"
    writable = _connect(str(db))
    writable.close()
    before = _sha256(db)
    with patch.dict("os.environ", {"OPENCLAW_MEM_READONLY_DB": "1"}, clear=False):
        readonly = _connect(str(db))
        try:
            payload = _info(readonly, db)
        finally:
            readonly.close()
    assert payload["user_version"] == 1
    assert _sha256(db) == before
