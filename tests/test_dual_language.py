from __future__ import annotations

import argparse
import json
import sqlite3

import pytest

from openclaw_mem.cli import build_parser, cmd_profile
from openclaw_mem.core.db import _connect
from openclaw_mem.core.records import _insert_observation, backfill_lang, detect_lang
from openclaw_mem.core.search import lexical_search, lexical_search_with_receipt


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("durable memory governance", "en"),
        ("長期記憶治理", "zh"),
        ("記憶治理 open", "mixed"),
        ("這是中文內容很多 ok", "zh"),
        ("", "en"),
    ],
)
def test_detect_lang_table(text: str, expected: str) -> None:
    assert detect_lang(text) == expected


def _store(
    conn: sqlite3.Connection,
    summary: str,
    *,
    summary_en: str | None = None,
    lang: str | None = None,
) -> int:
    payload = {
        "ts": "2026-01-01T00:00:00Z",
        "kind": "fact",
        "summary": summary,
        "summary_en": summary_en,
        "tool_name": "fixture",
        "detail": {},
    }
    if lang is not None:
        payload["lang"] = lang
    row_id = _insert_observation(conn, payload)
    conn.commit()
    return row_id


def test_insert_fills_only_missing_language() -> None:
    conn = _connect(":memory:")
    try:
        detected_id = _store(conn, "長期記憶治理")
        explicit_id = _store(conn, "長期記憶治理", lang="custom")
        rows = conn.execute(
            "SELECT id, lang FROM observations ORDER BY id"
        ).fetchall()
        assert [(row["id"], row["lang"]) for row in rows] == [
            (detected_id, "zh"),
            (explicit_id, "custom"),
        ]
    finally:
        conn.close()


def test_lang_backfill_is_batched_and_idempotent() -> None:
    conn = _connect(":memory:")
    try:
        conn.executemany(
            "INSERT INTO observations(ts, kind, summary, lang, detail_json) "
            "VALUES ('2026-01-01T00:00:00Z', 'fact', ?, ?, '{}')",
            [
                ("長期記憶治理", None),
                ("durable memory", ""),
                ("記憶治理 open", "mixed"),
            ],
        )
        first = backfill_lang(conn, batch_size=1)
        conn.commit()
        second = backfill_lang(conn, batch_size=1)

        assert first == {
            "kind": "openclaw-mem.db.backfill.lang.v1",
            "field": "lang",
            "eligible": 2,
            "updated": 2,
            "counts": {"zh": 1, "en": 1, "mixed": 0},
            "batches": 2,
            "batch_size": 1,
            "idempotent": False,
        }
        assert second["updated"] == 0
        assert second["idempotent"] is True
        assert [
            row[0]
            for row in conn.execute("SELECT lang FROM observations ORDER BY id").fetchall()
        ] == ["zh", "en", "mixed"]
    finally:
        conn.close()


def test_dual_language_router_recovers_cjk_and_mixed_pain_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _connect(":memory:")
    try:
        monkeypatch.setenv("OPENCLAW_MEM_FTS_FALLBACK_BM25_THRESHOLD", "100")
        expected = {
            "記憶治理": _store(conn, "記憶治理需要可回滾收據"),
            "偏好": _store(conn, "使用者偏好本地優先"),
            "使用openclaw-mem做": _store(conn, "使用openclaw-mem做長期記憶"),
            "治理 openclaw": _store(conn, "治理 openclaw 的混合檢索路徑"),
        }
        translated_id = _store(
            conn,
            "跨語列只有中文摘要",
            summary_en="alpha translated durable memory",
        )

        for query, row_id in expected.items():
            assert row_id in {item["id"] for item in lexical_search(conn, query, limit=10)}

        receipt = lexical_search_with_receipt(conn, "記憶治理 alpha", limit=10)
        assert translated_id in {item["id"] for item in receipt["results"]}
        assert receipt["lane_hits"]["fts_en"] >= 1
        assert receipt["fallback_triggered"] is True
        assert receipt["cross_lang_recovered"] >= 1
    finally:
        conn.close()


def test_fallback_quality_threshold_is_observable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _connect(":memory:")
    try:
        _store(conn, "alpha durable memory")
        monkeypatch.setenv("OPENCLAW_MEM_FTS_FALLBACK_BM25_THRESHOLD", "1")
        assert lexical_search_with_receipt(conn, "alpha", limit=5)[
            "fallback_triggered"
        ] is True

        monkeypatch.setenv("OPENCLAW_MEM_FTS_FALLBACK_BM25_THRESHOLD", "0")
        assert lexical_search_with_receipt(conn, "alpha", limit=5)[
            "fallback_triggered"
        ] is False
    finally:
        conn.close()


def test_profile_exposes_bilingual_coverage(capsys: pytest.CaptureFixture[str]) -> None:
    conn = _connect(":memory:")
    try:
        _store(conn, "長期記憶", summary_en="durable memory")
        _store(conn, "english only")
        cmd_profile(
            conn,
            argparse.Namespace(
                db=":memory:",
                json=True,
                recent_limit=10,
                tool_limit=10,
                kind_limit=10,
            ),
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["lang_distribution"] == {"en": 1, "zh": 1}
        assert payload["summary_en_coverage"] == {
            "present": 1,
            "total": 2,
            "ratio": 0.5,
        }
    finally:
        conn.close()


def test_db_backfill_parser_contract() -> None:
    args = build_parser().parse_args(["db", "backfill", "--lang", "--batch-size", "7"])
    assert args.db_cmd == "backfill"
    assert args.lang is True
    assert args.batch_size == 7
