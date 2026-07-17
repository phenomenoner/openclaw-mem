from __future__ import annotations

import math
import random
import sqlite3

import pytest

from openclaw_mem.core.db import _connect
from openclaw_mem.core.search import vector_search
from openclaw_mem.core.vector_index import NumpyIndex, PurePythonIndex, create_vector_index
from openclaw_mem.vector import l2_norm, pack_f32


MODEL = "fixture-model"


def _seed(conn: sqlite3.Connection, *, rows: int, dim: int) -> list[list[float]]:
    rng = random.Random(20260717)
    vectors: list[list[float]] = []
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


def test_numpy_and_python_exact_backends_are_equivalent_for_1k_top20() -> None:
    pytest.importorskip("numpy")
    conn = _connect(":memory:")
    try:
        vectors = _seed(conn, rows=1_000, dim=16)
        query = vectors[417]

        expected = PurePythonIndex().search(
            conn, query, model=MODEL, limit=20
        )
        actual = NumpyIndex().search(conn, query, model=MODEL, limit=20)

        assert [row_id for row_id, _score in actual] == [row_id for row_id, _score in expected]
        assert [score for _row_id, score in actual] == pytest.approx(
            [score for _row_id, score in expected], rel=1e-6, abs=1e-7
        )
    finally:
        conn.close()


def test_numpy_backend_preserves_input_order_for_exact_score_ties() -> None:
    pytest.importorskip("numpy")
    conn = _connect(":memory:")
    try:
        for row_id in range(1, 7):
            conn.execute(
                "INSERT INTO observations(ts, summary) VALUES ('2026-01-01T00:00:00Z', ?)",
                (f"tie {row_id}",),
            )
            conn.execute(
                "INSERT INTO observation_embeddings "
                "(observation_id, model, dim, vector, norm, created_at) "
                "VALUES (?, ?, 2, ?, 1.0, '2026-01-01T00:00:00Z')",
                (row_id, MODEL, pack_f32([1.0, 0.0])),
            )
        conn.commit()

        assert [row_id for row_id, _ in NumpyIndex().search(
            conn, [1.0, 0.0], model=MODEL, limit=3
        )] == [1, 2, 3]
    finally:
        conn.close()


def test_numpy_cache_invalidates_when_embedding_rowcount_changes() -> None:
    pytest.importorskip("numpy")
    conn = _connect(":memory:")
    try:
        _seed(conn, rows=3, dim=2)
        index = NumpyIndex()
        first = index.search(conn, [1.0, 0.0], model=MODEL, limit=4)
        info_before = index.cache_info()
        conn.execute(
            "INSERT INTO observations(ts, summary) VALUES ('2026-01-01T00:00:00Z', 'new best')"
        )
        conn.execute(
            "INSERT INTO observation_embeddings "
            "(observation_id, model, dim, vector, norm, created_at) "
            "VALUES (4, ?, 2, ?, 1.0, '2026-01-01T00:00:00Z')",
            (MODEL, pack_f32([1.0, 0.0])),
        )
        conn.commit()

        second = index.search(conn, [1.0, 0.0], model=MODEL, limit=4)
        info_after = index.cache_info()

        assert len(first) == 3
        assert {row_id for row_id, _ in second} == {1, 2, 3, 4}
        assert info_after["loads"] == info_before["loads"] + 1
    finally:
        conn.close()


def test_auto_backend_falls_back_to_python_when_numpy_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "openclaw_mem.core.vector_index._load_sqlite_vec", lambda: None
    )
    monkeypatch.setattr(
        "openclaw_mem.core.vector_index._load_numpy", lambda: None
    )
    index = create_vector_index("auto")
    assert index.name == "python"


def test_backend_rejects_nonfinite_query_without_database_scan() -> None:
    conn = _connect(":memory:")
    try:
        _seed(conn, rows=2, dim=2)
        assert PurePythonIndex().search(conn, [math.nan, 0.0], model=MODEL) == []
    finally:
        conn.close()


def test_vector_search_receipt_reports_actual_backend() -> None:
    pytest.importorskip("numpy")
    conn = _connect(":memory:")
    try:
        _seed(conn, rows=4, dim=2)
        results = vector_search(
            conn,
            [1.0, 0.0],
            model=MODEL,
            limit=2,
            vector_backend="numpy",
        )
        assert results
        assert {item["vector_backend"] for item in results} == {"numpy"}
    finally:
        conn.close()
