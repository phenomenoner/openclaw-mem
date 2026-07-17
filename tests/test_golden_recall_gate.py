from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openclaw_mem.core.db import _connect
from openclaw_mem.core.records import _insert_observation, detect_lang
from openclaw_mem.core.search import (
    hybrid_search_with_receipt,
    lexical_search_with_receipt,
)


FIXTURE = Path(__file__).parent / "fixtures" / "golden_queries_zh.jsonl"
KPI_FIELDS = {
    "query_lang",
    "lane_hits",
    "fallback_triggered",
    "cross_lang_recovered",
}
LANES = {
    "fts_original",
    "fts_en",
    "cjk_like",
    "trigram",
    "vector",
    "vector_en",
}


def _cases() -> list[dict[str, str]]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line]


def _fixture_db():
    conn = _connect(":memory:")
    expected: dict[str, int] = {}
    for index, case in enumerate(_cases(), start=1):
        expected[case["key"]] = _insert_observation(
            conn,
            {
                "ts": f"2026-01-01T00:00:{index:02d}Z",
                "kind": "golden",
                "summary": case["summary"],
                "tool_name": case["key"],
                "detail": {"golden_key": case["key"]},
            },
        )
    conn.commit()
    return conn, expected


def test_golden_fixture_has_exact_language_balance_and_edge_queries() -> None:
    cases = _cases()
    assert len(cases) == 30
    assert Counter(case["category"] for case in cases) == {
        "zh": 10,
        "en": 10,
        "mixed": 10,
    }
    assert any(len(case["query"]) == 2 for case in cases if case["category"] == "zh")
    assert any(
        " " not in case["query"] and detect_lang(case["query"]) == "mixed"
        for case in cases
    )
    assert all(
        detect_lang(case["query"]) == case["category"]
        for case in cases
    )


def test_every_golden_query_recovers_expected_record_in_top_five() -> None:
    conn, expected = _fixture_db()
    try:
        failures = []
        for case in _cases():
            receipt = lexical_search_with_receipt(conn, case["query"], limit=5)
            ids = [int(item["id"]) for item in receipt["results"]]
            if expected[case["key"]] not in ids:
                failures.append({"key": case["key"], "query": case["query"], "ids": ids})
            assert KPI_FIELDS.issubset(receipt)
            assert set(receipt["lane_hits"]) == LANES
        assert failures == []
    finally:
        conn.close()


def test_hybrid_receipt_preserves_all_bilingual_kpis() -> None:
    conn, expected = _fixture_db()
    try:
        receipt = hybrid_search_with_receipt(
            conn,
            "治理 mem",
            limit=5,
            vector_ids=[expected["en-01"]],
            vector_en_ids=[expected["mixed-01"]],
        )
        assert KPI_FIELDS.issubset(receipt)
        assert set(receipt["lane_hits"]) == LANES
        assert receipt["lane_hits"]["vector"] == 1
        assert receipt["lane_hits"]["vector_en"] == 1
        assert expected["mixed-01"] in {item["id"] for item in receipt["results"]}
    finally:
        conn.close()
