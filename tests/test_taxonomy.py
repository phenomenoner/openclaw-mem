from __future__ import annotations

import json
from pathlib import Path

import pytest

from openclaw_mem.cli import build_parser
from openclaw_mem.core.db import _connect
from openclaw_mem.core.records import (
    _insert_observation,
    _taxonomy_enabled_for_process,
    ingest_observations,
    store_memory,
)
from openclaw_mem.core.taxonomy import CANONICAL_KINDS, backfill_kinds, classify


CASES = [
    ("We decided to use SQLite", "decision"),
    ("The decision is to keep receipts", "decision"),
    ("We chose the local backend", "decision"),
    ("The team has chosen option B", "decision"),
    ("We choose deterministic ordering", "decision"),
    ("我們決定使用 SQLite", "decision"),
    ("這項决定已經核可", "decision"),
    ("決議保留相容入口", "decision"),
    ("團隊採用本地後端", "decision"),
    ("项目采用固定排序", "decision"),
    ("I prefer concise output", "preference"),
    ("Always use UTF-8", "preference"),
    ("My preference is dark mode", "preference"),
    ("I preferred the first layout", "preference"),
    ("I like deterministic receipts", "preference"),
    ("我偏好精簡輸出", "preference"),
    ("總是使用 UTF-8", "preference"),
    ("我喜歡深色模式", "preference"),
    ("用户偏好本地存储", "preference"),
    ("总是使用固定种子", "preference"),
    ("We plan to add a benchmark", "plan"),
    ("I will verify the release", "plan"),
    ("Planning to migrate tomorrow", "plan"),
    ("We intend to remove the alias", "plan"),
    ("TODO document the contract", "plan"),
    ("我們計畫加入基準", "plan"),
    ("明天將會驗證發版", "plan"),
    ("团队打算迁移资料", "plan"),
    ("預計下週完成", "plan"),
    ("待辦：補齊文件", "plan"),
    ("The parser error was fixed by quoting the token", "learning"),
    ("A failed migration was resolved with rollback", "learning"),
    ("Bug in cache; solution was revision triggers", "learning"),
    ("The broken index was repaired by rebuild", "learning"),
    ("Issue reproduced; workaround is readonly mode", "learning"),
    ("解析錯誤，解法是加上引號", "learning"),
    ("遷移失敗，已用回滾修正", "learning"),
    ("快取問題透過版本觸發器解決", "learning"),
    ("索引故障，重新建立後修復", "learning"),
    ("系统报错，解决方式是只读模式", "learning"),
    ("The repository contains a README", "note"),
    ("Meeting notes from Tuesday", "note"),
    ("SQLite has a query planner", "note"),
    ("A neutral capture without a rule", "note"),
    ("這是週二的會議記錄", "note"),
    ("專案包含一份說明文件", "note"),
    ("SQLite 有查詢規劃器", "note"),
    ("沒有強分類訊號的內容", "note"),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_bilingual_classifier_table(text: str, expected: str) -> None:
    kind, confidence, method = classify(text, "memory_store", "note")
    assert kind == expected
    assert 0.0 <= confidence <= 1.0
    assert method


@pytest.mark.parametrize("explicit", sorted((CANONICAL_KINDS - {"note"}) | {"task", "other"}))
def test_explicit_kind_is_never_overwritten(explicit: str) -> None:
    kind, confidence, method = classify("We decided and will change this", "memory_store", explicit)
    assert (kind, confidence, method) == (explicit, 1.0, "explicit")


def test_store_and_ingest_write_classification_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_TAXONOMY_ENABLED", "1")
    _taxonomy_enabled_for_process.cache_clear()
    conn = _connect(":memory:")
    try:
        receipt, _warnings = store_memory(
            conn,
            text="I prefer local deterministic storage",
            category=None,
            importance=0.8,
            model="fixture-model",
            memory_dir=None,
            embedding_skip_reason="test",
        )
        assert receipt["kind"] == "preference"

        ingest = ingest_observations(
            conn,
            [{"kind": "tool", "tool_name": "shell", "summary": "Error occurred; solution was retry"}],
        )
        assert ingest["inserted"] == 1
        rows = conn.execute("SELECT kind, detail_json FROM observations ORDER BY id").fetchall()
        assert [row["kind"] for row in rows] == ["preference", "learning"]
        assert all(json.loads(row["detail_json"])["classification"]["method"] for row in rows)
    finally:
        conn.close()


def test_taxonomy_disabled_preserves_legacy_write_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_TAXONOMY_ENABLED", "0")
    _taxonomy_enabled_for_process.cache_clear()
    conn = _connect(":memory:")
    try:
        row_id = _insert_observation(
            conn,
            {"kind": "tool", "tool_name": "memory_store", "summary": "I prefer tabs", "detail": {"x": 1}},
        )
        row = conn.execute("SELECT kind, detail_json FROM observations WHERE id = ?", (row_id,)).fetchone()
        assert row["kind"] == "tool"
        assert json.loads(row["detail_json"]) == {"x": 1}
    finally:
        conn.close()


def test_enabled_taxonomy_preserves_stronger_explicit_write_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_TAXONOMY_ENABLED", "1")
    _taxonomy_enabled_for_process.cache_clear()
    conn = _connect(":memory:")
    try:
        row_id = _insert_observation(
            conn,
            {"kind": "fact", "summary": "We decided but fact is explicit", "detail": {"x": 1}},
        )
        row = conn.execute("SELECT kind, detail_json FROM observations WHERE id = ?", (row_id,)).fetchone()
        assert row["kind"] == "fact"
        assert json.loads(row["detail_json"]) == {"x": 1}
    finally:
        conn.close()


def test_taxonomy_can_be_disabled_from_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[taxonomy]\nenabled = false\n", encoding="utf-8")
    monkeypatch.delenv("OPENCLAW_MEM_TAXONOMY_ENABLED", raising=False)
    monkeypatch.setenv("OPENCLAW_MEM_CONFIG", str(config_path))
    _taxonomy_enabled_for_process.cache_clear()
    conn = _connect(":memory:")
    try:
        row_id = _insert_observation(
            conn,
            {"kind": "note", "summary": "We decided to retain the legacy shape"},
        )
        row = conn.execute(
            "SELECT kind, detail_json FROM observations WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["kind"] == "note"
        assert json.loads(row["detail_json"]) == {}
    finally:
        conn.close()


def test_kind_backfill_dry_run_apply_and_idempotency() -> None:
    conn = _connect(":memory:")
    try:
        decision_id = _insert_observation(
            conn,
            {"kind": "note", "summary": "We decided to keep the API"},
            taxonomy_enabled=False,
        )
        note_id = _insert_observation(
            conn,
            {"kind": "tool", "summary": "neutral tool output"},
            taxonomy_enabled=False,
        )
        explicit_id = _insert_observation(
            conn,
            {"kind": "fact", "summary": "We decided but this is explicit"},
            taxonomy_enabled=False,
        )
        before = [tuple(row) for row in conn.execute("SELECT id, kind, detail_json FROM observations ORDER BY id")]

        preview = backfill_kinds(conn, dry_run=True, batch_size=1)
        after_preview = [tuple(row) for row in conn.execute("SELECT id, kind, detail_json FROM observations ORDER BY id")]
        assert preview["would_update"] == 2
        assert preview["updated"] == 0
        assert after_preview == before

        applied = backfill_kinds(conn, batch_size=1)
        assert applied["updated"] == 2
        assert conn.execute("SELECT kind FROM observations WHERE id = ?", (decision_id,)).fetchone()[0] == "decision"
        assert conn.execute("SELECT kind FROM observations WHERE id = ?", (note_id,)).fetchone()[0] == "note"
        assert conn.execute("SELECT kind FROM observations WHERE id = ?", (explicit_id,)).fetchone()[0] == "fact"
        assert backfill_kinds(conn)["idempotent"] is True
    finally:
        conn.close()


def test_cli_parser_exposes_auto_category_and_kind_backfill() -> None:
    parser = build_parser()
    assert parser.parse_args(["store", "I prefer tabs"]).category is None
    args = parser.parse_args(["db", "backfill", "--kind", "--dry-run"])
    assert args.kind is True
    assert args.dry_run is True
