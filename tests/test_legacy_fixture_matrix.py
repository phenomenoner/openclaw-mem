from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from openclaw_mem.core.db import _connect, migrate_database, rollback_database
from openclaw_mem.core.search import lexical_search


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "legacy_dbs"
TAGS = ("v1.9.26", "v1.9.31")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _golden_ids(conn: sqlite3.Connection, lane: str, query: str) -> set[int]:
    if lane == "observations":
        return {int(item["id"]) for item in lexical_search(conn, query, limit=50)}
    if lane == "episodes":
        return {
            int(row[0])
            for row in conn.execute(
                "SELECT rowid FROM episodic_events_fts "
                "WHERE episodic_events_fts MATCH ? ORDER BY rowid",
                (query,),
            ).fetchall()
        }
    raise AssertionError(f"unknown golden query lane: {lane}")


def _assert_golden(conn: sqlite3.Connection, golden_queries: list[dict]) -> None:
    for case in golden_queries:
        assert _golden_ids(conn, case["lane"], case["query"]) == set(case["expected_ids"])


def test_legacy_fixture_manifest_is_complete_and_content_addressed() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "openclaw-mem.legacy-fixtures.v1"
    assert [item["tag"] for item in manifest["fixtures"]] == list(TAGS)
    for item in manifest["fixtures"]:
        fixture = FIXTURE_ROOT / item["file"]
        assert fixture.exists()
        assert _sha256(fixture) == item["sha256"]
        assert item["observations"] == 16
        assert item["episodic_events"] == 4
        assert item["total_records"] == 20


@pytest.mark.parametrize("tag", TAGS)
def test_legacy_fixture_read_query_migrate_and_rollback_matrix(
    tag: str, tmp_path: Path
) -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    golden_queries = manifest["golden_queries"]
    source = FIXTURE_ROOT / f"{tag}.sqlite"
    db = tmp_path / f"{tag}.sqlite"
    shutil.copy2(source, db)
    pristine_hash = _sha256(db)

    with patch.dict("os.environ", {"OPENCLAW_MEM_READONLY_DB": "1"}, clear=False):
        readonly = _connect(str(db))
        try:
            assert readonly.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 16
            assert readonly.execute("SELECT COUNT(*) FROM episodic_events").fetchone()[0] == 4
            _assert_golden(readonly, golden_queries)
        finally:
            readonly.close()
    assert _sha256(db) == pristine_hash

    plan = migrate_database(db, dry_run=True)
    assert plan["from_version"] == 0
    assert [step["id"] for step in plan["steps"]] == [1, 2]
    assert _sha256(db) == pristine_hash

    receipt_path = tmp_path / f"{tag}-migration.json"
    receipt = migrate_database(db, receipt_path=receipt_path)
    assert receipt["row_counts_before"] == receipt["row_counts_after"]
    migrated = sqlite3.connect(db)
    migrated.row_factory = sqlite3.Row
    try:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 2
        assert migrated.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 16
        assert migrated.execute("SELECT COUNT(*) FROM episodic_events").fetchone()[0] == 4
        _assert_golden(migrated, golden_queries)
    finally:
        migrated.close()

    rollback = rollback_database(db, receipt_path)
    assert Path(rollback["rolled_back_path"]).exists()
    restored = sqlite3.connect(db)
    try:
        assert restored.execute("PRAGMA user_version").fetchone()[0] == 0
        assert restored.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 16
        assert restored.execute("SELECT COUNT(*) FROM episodic_events").fetchone()[0] == 4
    finally:
        restored.close()
