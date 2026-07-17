from __future__ import annotations

import pytest

from openclaw_mem.cli import _cached_invoke_parser, _invoke_cli_json
from openclaw_mem.core.db import _connect
from openclaw_mem.core.pack import build_pack
from openclaw_mem.core.quotas import apply_soft_quotas
from openclaw_mem.core.records import _insert_observation


def _seed_quota_fixture(conn) -> tuple[list[int], int]:
    event_ids = []
    for index in range(5):
        event_ids.append(
            _insert_observation(
                conn,
                {
                    "kind": "event",
                    "summary": f"quota beacon event {index}",
                    "detail": {
                        "importance": {"score": 0.95, "label": "must_remember"}
                    },
                },
            )
        )
    preference_id = _insert_observation(
        conn,
        {
            "kind": "preference",
            "summary": "quota beacon preference",
            "detail": {"importance": {"score": 0.1, "label": "ignore"}},
        },
    )
    conn.commit()
    return event_ids, preference_id


def test_soft_quota_helper_reserves_required_kinds_and_caps_events() -> None:
    baseline = [
        {"id": 1, "kind": "event"},
        {"id": 2, "kind": "event"},
        {"id": 3, "kind": "event"},
        {"id": 4, "kind": "preference"},
        {"id": 5, "kind": "decision"},
    ]
    ordered, hits = apply_soft_quotas(baseline, limit=3, enabled=True)
    assert [item["kind"] for item in ordered[:2]] == ["preference", "decision"]
    assert [hit["action"] for hit in hits] == ["reserved", "reserved", "capped"]
    assert [item["id"] for item in ordered if item.get("quota_capped")] == [2, 3]


def test_quota_disabled_is_bitwise_candidate_equivalent() -> None:
    baseline = [{"id": 1, "kind": "event"}, {"id": 2, "kind": "preference"}]
    ordered, hits = apply_soft_quotas(baseline, limit=1, enabled=False)
    assert ordered == baseline
    assert hits == []


def test_programmatic_pack_prevents_event_washout_and_disabled_matches_baseline() -> None:
    conn = _connect(":memory:")
    try:
        event_ids, preference_id = _seed_quota_fixture(conn)
        disabled = build_pack(
            conn,
            "quota beacon",
            limit=3,
            quota_enabled=False,
            quota_preference_min=1,
            quota_decision_min=1,
            quota_event_max_ratio=0.4,
            scoring_profile="relevance",
        )
        assert [item["id"] for item in disabled["items"]] == list(reversed(event_ids))[:3]
        assert "quota_hits" not in disabled

        enabled = build_pack(
            conn,
            "quota beacon",
            limit=3,
            quota_enabled=True,
            quota_preference_min=1,
            quota_decision_min=1,
            quota_event_max_ratio=0.4,
            scoring_profile="relevance",
        )
        selected_ids = [item["id"] for item in enabled["items"]]
        assert preference_id in selected_ids
        assert len(set(selected_ids).intersection(event_ids)) <= 1
        assert {hit["action"] for hit in enabled["quota_hits"]} == {"reserved", "capped"}
    finally:
        conn.close()


def test_cli_pack_trace_exposes_reserved_and_capped_refs() -> None:
    conn = _connect(":memory:")
    try:
        event_ids, preference_id = _seed_quota_fixture(conn)
        payload = _invoke_cli_json(
            conn,
            [
                "pack",
                "--query",
                "quota beacon",
                "--limit",
                "3",
                "--trace",
                "--pack-lifecycle-shadow",
                "off",
            ],
        )
        selected_refs = {item["recordRef"] for item in payload["items"]}
        assert f"obs:{preference_id}" in selected_refs
        quota_hits = payload["trace"]["quota_hits"]
        reserved = next(hit for hit in quota_hits if hit["action"] == "reserved")
        capped = next(hit for hit in quota_hits if hit["action"] == "capped")
        assert reserved == {
            "kind": "preference",
            "action": "reserved",
            "refs": [f"obs:{preference_id}"],
        }
        assert set(capped["refs"]).issubset({f"obs:{row_id}" for row_id in event_ids})
        assert any(
            "quota_event_capped" in candidate["decision"]["reason"]
            for candidate in payload["trace"]["candidates"]
        )
    finally:
        conn.close()


def test_cli_quota_config_off_preserves_baseline_selection_and_trace_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_QUOTA_ENABLED", "0")
    _cached_invoke_parser.cache_clear()
    conn = _connect(":memory:")
    try:
        event_ids, _preference_id = _seed_quota_fixture(conn)
        payload = _invoke_cli_json(
            conn,
            [
                "pack",
                "--query",
                "quota beacon",
                "--limit",
                "3",
                "--trace",
                "--pack-lifecycle-shadow",
                "off",
            ],
        )
        selected_ids = [item["id"] for item in payload["items"]]
        assert len(selected_ids) == 3
        assert set(selected_ids).issubset(set(event_ids))
        assert "quota_hits" not in payload["trace"]
    finally:
        conn.close()
        _cached_invoke_parser.cache_clear()
