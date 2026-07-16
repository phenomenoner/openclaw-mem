from __future__ import annotations

import argparse
import json
import struct
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from openclaw_mem.cli import cmd_db_info, cmd_doctor
from openclaw_mem.core.db import _connect
from openclaw_mem.core.records import _insert_observation


def _vector(dim: int) -> bytes:
    return struct.pack(f"<{dim}f", *([1.0] + [0.0] * (dim - 1)))


def _insert_embedding(conn, table: str, observation_id: int, model: str, dim: int) -> None:
    conn.execute(
        f"INSERT INTO {table}(observation_id, model, dim, vector, norm, created_at) "
        "VALUES (?, ?, ?, ?, 1.0, '2026-01-01T00:00:00Z')",
        (observation_id, model, dim, _vector(dim)),
    )


def _bad_embedding_db():
    conn = _connect(":memory:")
    ids = [
        _insert_observation(conn, {"summary": f"fixture {index}", "detail": {}})
        for index in range(1, 5)
    ]
    _insert_embedding(conn, "observation_embeddings", ids[0], "model-a", 2)
    _insert_embedding(conn, "observation_embeddings", ids[1], "model-a", 2)
    _insert_embedding(conn, "observation_embeddings", ids[3], "model-b", 3)
    _insert_embedding(conn, "observation_embeddings_en", ids[0], "model-a", 2)
    _insert_embedding(conn, "observation_embeddings_en", ids[2], "model-a", 2)
    conn.execute("PRAGMA foreign_keys = OFF")
    _insert_embedding(conn, "observation_embeddings", 999, "model-a", 2)
    conn.commit()
    return conn


def test_db_info_reports_embedding_integrity_anomalies() -> None:
    conn = _bad_embedding_db()
    try:
        output = StringIO()
        with redirect_stdout(output):
            cmd_db_info(conn, argparse.Namespace(db=":memory:", json=True))
        payload = json.loads(output.getvalue())
        embeddings = payload["embeddings"]
        integrity = embeddings["integrity"]

        assert integrity["ok"] is False
        assert embeddings["orphan_count"] == 1
        assert embeddings["model_outlier_count"] == 1
        assert embeddings["dim_outlier_count"] == 1
        assert embeddings["model_dim_outlier_count"] == 1
        assert embeddings["english_missing_original_count"] == 1
        assert integrity["tables"]["observation_embeddings"] == {
            "count": 4,
            "orphan_count": 1,
            "dominant_model": "model-a",
            "dominant_dim": 2,
            "model_outlier_count": 1,
            "dim_outlier_count": 1,
            "model_dim_outlier_count": 1,
        }
    finally:
        conn.close()


def test_doctor_warns_on_embedding_integrity_anomalies(tmp_path: Path) -> None:
    conn = _bad_embedding_db()
    args = argparse.Namespace(
        db=":memory:",
        json=True,
        db_preexisted=True,
        harness_env_bridge={"enabled": False},
    )
    config = {
        "plugins": {
            "slots": {"memory": "memory-core"},
            "entries": {
                "memory-core": {"enabled": True},
                "memory-lancedb": {"enabled": False, "config": {}},
                "openclaw-mem": {"enabled": True},
            },
        }
    }
    output = StringIO()
    try:
        with (
            patch("openclaw_mem.cli._read_openclaw_config", return_value=config),
            patch("openclaw_mem.cli._resolve_openclaw_config_path", return_value=tmp_path / "config.json"),
            redirect_stdout(output),
        ):
            cmd_doctor(conn, args)
        payload = json.loads(output.getvalue())
        check = next(item for item in payload["checks"] if item["name"] == "embeddings.integrity")
        assert check["ok"] is False
        assert check["severity"] == "warn"
        assert check["integrity"]["english_missing_original_count"] == 1
        assert payload["summary"]["warnings"] >= 1
        assert payload["ok"] is True
    finally:
        conn.close()


def test_empty_embedding_tables_are_healthy() -> None:
    conn = _connect(":memory:")
    try:
        output = StringIO()
        with redirect_stdout(output):
            cmd_db_info(conn, argparse.Namespace(db=":memory:", json=True))
        integrity = json.loads(output.getvalue())["embeddings"]["integrity"]
        assert integrity["ok"] is True
        assert integrity["orphan_count"] == 0
        assert integrity["english_missing_original_count"] == 0
    finally:
        conn.close()
