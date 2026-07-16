from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from openclaw_mem.core.api import connect, pack, search, store_observation
from openclaw_mem.core.records import ingest_observations, store_memory


def test_importing_core_db_does_not_import_cli_monolith() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import openclaw_mem.core.db; "
            "raise SystemExit(1 if 'openclaw_mem.cli' in sys.modules else 0)",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert probe.returncode == 0, probe.stderr


def test_stable_core_api_round_trip() -> None:
    conn = connect(":memory:")
    try:
        record_id = store_observation(conn, {"kind": "fact", "summary": "alpha core memory"})
        conn.commit()

        results = search(conn, "alpha", limit=5)
        bundle = pack(conn, "alpha", limit=2, budget_tokens=200)

        assert record_id == 1
        assert results[0]["summary"] == "alpha core memory"
        assert bundle["context_pack"]["schema"] == "openclaw-mem.context-pack.v1"
    finally:
        conn.close()


def test_core_ingest_returns_cli_compatible_receipt() -> None:
    conn = connect(":memory:")
    try:
        receipt = ingest_observations(
            conn,
            [
                {"kind": "fact", "summary": "first"},
                {"kind": "preference", "summary": "second"},
            ],
            importance_scorer="off",
        )

        assert receipt == {
            "inserted": 2,
            "ids": [1, 2],
            "total_seen": 2,
            "graded_filled": 0,
            "skipped_existing": 0,
            "skipped_disabled": 2,
            "scorer_errors": 0,
            "label_counts": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "trivial": 0,
            },
        }
    finally:
        conn.close()


def test_core_store_returns_warnings_without_printing(tmp_path: Path, capsys) -> None:
    conn = connect(":memory:")
    try:
        receipt, warnings = store_memory(
            conn,
            text="core-owned memory",
            category="fact",
            importance=0.8,
            model="unused-without-api-key",
            memory_dir=tmp_path,
        )

        assert receipt["ok"] is True
        assert receipt["id"] == 1
        assert receipt["markdownWriteStatus"] == "written"
        assert warnings == ["No API key, skipping embedding"]
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
    finally:
        conn.close()
