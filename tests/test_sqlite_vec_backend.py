from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from openclaw_mem.cli import cmd_db_info, cmd_db_reindex
from openclaw_mem.core.db import _connect
from openclaw_mem.core.vector_index import (
    NumpyIndex,
    PurePythonIndex,
    SqliteVecIndex,
    create_vector_index,
    rebuild_sqlite_vec_indexes,
    sqlite_vec_index_status,
)
from openclaw_mem.vector import l2_norm, pack_f32


MODEL = "sqlite-vec/fixture:model"


def _seed(conn: sqlite3.Connection, *, rows: int = 100, dim: int = 16) -> list[list[float]]:
    rng = random.Random(20260717)
    vectors = []
    for observation_id in range(1, rows + 1):
        vector = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
        vectors.append(vector)
        conn.execute(
            "INSERT INTO observations(ts, summary) VALUES ('2026-01-01T00:00:00Z', ?)",
            (f"row {observation_id}",),
        )
        conn.execute(
            "INSERT INTO observation_embeddings "
            "(observation_id, model, dim, vector, norm, created_at) "
            "VALUES (?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')",
            (observation_id, MODEL, dim, pack_f32(vector), l2_norm(vector)),
        )
    conn.commit()
    return vectors


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sqlite_vec_top10_matches_numpy_exact_backend() -> None:
    pytest.importorskip("sqlite_vec")
    pytest.importorskip("numpy")
    conn = _connect(":memory:")
    try:
        vectors = _seed(conn)
        rebuild_sqlite_vec_indexes(conn)
        conn.commit()
        query = vectors[41]
        expected = NumpyIndex().search(conn, query, model=MODEL, limit=10)
        actual = SqliteVecIndex().search(conn, query, model=MODEL, limit=10)
        assert [row_id for row_id, _ in actual] == [row_id for row_id, _ in expected]
        assert [score for _, score in actual] == pytest.approx(
            [score for _, score in expected], abs=1e-5, rel=1e-5
        )
    finally:
        conn.close()


def test_auto_chain_uses_fresh_sqlite_vec_then_falls_back_when_stale() -> None:
    pytest.importorskip("sqlite_vec")
    conn = _connect(":memory:")
    try:
        vectors = _seed(conn, rows=12, dim=4)
        rebuild_sqlite_vec_indexes(conn)
        conn.commit()

        fresh = create_vector_index("auto")
        fresh.search(conn, vectors[2], model=MODEL, limit=5)
        assert fresh.name == "sqlite-vec"
        assert fresh.receipt["fallback_reason"] is None

        conn.execute(
            "INSERT INTO observations(ts, summary) VALUES ('2026-01-01T00:00:00Z', 'new row')"
        )
        conn.execute(
            "INSERT INTO observation_embeddings "
            "(observation_id, model, dim, vector, norm, created_at) "
            "VALUES (13, ?, 4, ?, 1.0, '2026-01-01T00:00:00Z')",
            (MODEL, pack_f32([1.0, 0.0, 0.0, 0.0])),
        )
        conn.commit()
        stale = create_vector_index("auto")
        assert stale.search(conn, [1.0, 0.0, 0.0, 0.0], model=MODEL, limit=20)
        assert stale.name == "numpy"
        assert stale.receipt["fallback_reason"] == "sqlite_vec_index_stale"
        assert "db reindex --vec" in stale.receipt["hint"]
    finally:
        conn.close()


def test_auto_chain_falls_through_numpy_and_python(monkeypatch) -> None:
    numpy = pytest.importorskip("numpy")
    monkeypatch.setattr("openclaw_mem.core.vector_index._load_sqlite_vec", lambda: None)
    monkeypatch.setattr("openclaw_mem.core.vector_index._load_numpy", lambda: numpy)
    assert create_vector_index("auto").name == "numpy"

    monkeypatch.setattr("openclaw_mem.core.vector_index._load_numpy", lambda: None)
    assert create_vector_index("auto").name == "python"
    assert isinstance(create_vector_index("python"), PurePythonIndex)


def test_readonly_auto_never_attempts_to_create_missing_index(tmp_path: Path) -> None:
    pytest.importorskip("sqlite_vec")
    db_path = tmp_path / "readonly.sqlite"
    conn = _connect(str(db_path))
    vectors = _seed(conn, rows=10, dim=4)
    conn.close()
    before = _sha256(db_path)

    readonly = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    try:
        index = create_vector_index("auto")
        assert index.search(readonly, vectors[0], model=MODEL, limit=3)
        assert index.name in {"numpy", "python"}
        assert index.receipt["fallback_reason"] == "sqlite_vec_index_missing"
        assert readonly.total_changes == 0
        assert not sqlite_vec_index_status(readonly)["indexes"][0]["present"]
    finally:
        readonly.close()
    assert _sha256(db_path) == before


def test_reindex_receipt_and_db_info_report_persisted_rows(tmp_path: Path) -> None:
    pytest.importorskip("sqlite_vec")
    db_path = tmp_path / "indexed.sqlite"
    conn = _connect(str(db_path))
    try:
        _seed(conn, rows=17, dim=6)
        output = StringIO()
        with redirect_stdout(output):
            cmd_db_reindex(conn, argparse.Namespace(fts=False, vec=True, json=True))
        receipt = json.loads(output.getvalue())
        assert receipt["backend"] == "sqlite-vec"
        assert receipt["sqlite_vec"]["row_count"] == 17

        output = StringIO()
        with redirect_stdout(output):
            cmd_db_info(conn, argparse.Namespace(db=str(db_path), json=True))
        status = json.loads(output.getvalue())["embeddings"]["sqlite_vec"]
        assert status["installed"] is True
        assert status["fresh"] is True
        assert status["index_count"] == 1
        assert status["row_count"] == 17
    finally:
        conn.close()
