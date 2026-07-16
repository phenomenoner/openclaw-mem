from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from openclaw_mem.core.api import connect, pack, search, store_observation
from openclaw_mem.core.episodes import query as query_episodes, replay as replay_episodes
from openclaw_mem.core.records import harvest_observations, ingest_observations, store_memory


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


def test_core_harvest_recovers_processing_file_without_output(tmp_path: Path, capsys) -> None:
    conn = connect(":memory:")
    source = tmp_path / "observations.jsonl"
    processing = tmp_path / "observations.jsonl.20260717_010203.processing"
    archive = tmp_path / "archive"
    processing.write_text('{"kind":"fact","summary":"recovered"}\n', encoding="utf-8")
    try:
        receipt, warnings = harvest_observations(
            conn,
            source=source,
            version="test",
            archive_dir=archive,
            update_index=False,
        )

        assert receipt["ok"] is True
        assert receipt["ingested"] == 1
        assert receipt["processed_files"] == 1
        assert receipt["recovered"] is True
        assert receipt["rotated"] is False
        assert warnings == []
        assert (archive / processing.name).exists()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
    finally:
        conn.close()


def test_core_harvest_empty_source_receipt(tmp_path: Path) -> None:
    conn = connect(":memory:")
    try:
        receipt, warnings = harvest_observations(
            conn,
            source=tmp_path / "missing.jsonl",
            version="test",
            update_index=False,
        )

        assert receipt["ok"] is True
        assert receipt["processed_files"] == 0
        assert receipt["ingested"] == 0
        assert receipt["reason"] == "source empty/missing"
        assert warnings == []
    finally:
        conn.close()


def test_core_harvest_index_and_embedding_fail_open(tmp_path: Path) -> None:
    conn = connect(":memory:")
    source = tmp_path / "observations.jsonl"
    source.write_text('{"kind":"fact","summary":"fail open"}\n', encoding="utf-8")

    def fail_index(*_args) -> None:
        raise RuntimeError("index unavailable")

    try:
        receipt, warnings = harvest_observations(
            conn,
            source=source,
            version="test",
            update_index=True,
            index_path=tmp_path / "index.json",
            build_index=fail_index,
            embed=True,
            api_key_provider=lambda: None,
        )

        assert receipt["ok"] is True
        assert receipt["ingested"] == 1
        assert receipt["embedded"] == 0
        assert receipt["embed_error"] == "missing_api_key"
        assert warnings == ["failed to update index: index unavailable"]
        assert not source.exists()
    finally:
        conn.close()


def test_core_episodes_query_and_replay_are_output_free(capsys) -> None:
    conn = connect(":memory:")
    conn.execute(
        """
        INSERT INTO episodic_events (
            event_id, ts_ms, scope, session_id, agent_id, type, summary,
            payload_json, refs_json, redacted, schema_version, created_at, search_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """,
        (
            "evt-core-1",
            1234,
            "project:core",
            "session-1",
            "main",
            "ops.observation",
            "core episode",
            '{"value":1}',
            '{"source":"test"}',
            "openclaw-mem.episodic.v0",
            "2026-07-17T00:00:00+00:00",
            "core episode",
        ),
    )
    conn.commit()
    try:
        query_receipt = query_episodes(
            conn,
            raw_scope="project:core",
            global_scope=False,
            raw_types=["ops.observation"],
            include_payload=True,
        )
        replay_receipt = replay_episodes(
            conn,
            raw_scope="project:core",
            global_scope=False,
            session_id="session-1",
        )

        assert query_receipt["count"] == 1
        assert query_receipt["items"][0]["payload"] == {"value": 1}
        assert replay_receipt["count"] == 1
        assert replay_receipt["items"][0]["refs"] == {"source": "test"}
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
    finally:
        conn.close()


def test_core_episodes_validation_happens_before_query() -> None:
    conn = connect(":memory:")
    try:
        try:
            query_episodes(
                conn,
                raw_scope=None,
                global_scope=False,
                from_ts_ms=20,
                to_ts_ms=10,
            )
        except ValueError as exc:
            assert str(exc) == "scope is required (or pass --global)"
        else:
            raise AssertionError("missing scope should fail")
    finally:
        conn.close()
