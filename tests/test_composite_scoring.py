from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timezone

import pytest

from openclaw_mem.cli import build_parser
from openclaw_mem.core.api import connect, store_observation
from openclaw_mem.core.pack import build_pack
from openclaw_mem.core.scoring import score_results
from openclaw_mem.core.search import lexical_search


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _store(conn, *, ts: str, kind: str, summary: str, detail: dict) -> int:
    return store_observation(
        conn,
        {"ts": ts, "kind": kind, "summary": summary, "detail": detail},
    )


def test_relevance_profile_is_an_exact_shape_and_order_golden() -> None:
    conn = connect(":memory:")
    try:
        _store(
            conn,
            ts="2026-07-17T00:00:00Z",
            kind="fact",
            summary="golden retrieval needle one",
            detail={"importance": {"label": "ignore", "score": 0.1}},
        )
        _store(
            conn,
            ts="2026-07-16T00:00:00Z",
            kind="fact",
            summary="golden retrieval needle two",
            detail={"importance": {"label": "must_remember", "score": 0.9}},
        )
        conn.commit()

        baseline = lexical_search(conn, "golden retrieval needle", limit=10)
        explicit = lexical_search(
            conn,
            "golden retrieval needle",
            limit=10,
            scoring_profile="relevance",
            scoring_relevance_enabled=False,
            scoring_importance_enabled=False,
            scoring_recency_enabled=False,
            scoring_use_enabled=False,
            scoring_state_enabled=False,
        )

        assert explicit == baseline
        assert all("score_components" not in item and "final_score" not in item for item in explicit)
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("details", "timestamps", "kinds", "enabled", "expected_first"),
    [
        (
            [{"importance": {"label": "ignore"}}, {"importance": {"label": "must_remember"}}],
            ["2026-07-17T00:00:00Z"] * 2,
            ["fact"] * 2,
            {"importance_enabled": True},
            2,
        ),
        (
            [{}, {}],
            ["2024-07-17T00:00:00Z", "2026-07-17T00:00:00Z"],
            ["event"] * 2,
            {"recency_enabled": True},
            2,
        ),
        (
            [{"lifecycle": {"used_count": 0}}, {"lifecycle": {"used_count": 20}}],
            ["2026-07-17T00:00:00Z"] * 2,
            ["fact"] * 2,
            {"use_enabled": True},
            2,
        ),
        (
            [{"lifecycle": {"state": "stale"}}, {"lifecycle": {"state": "active"}}],
            ["2026-07-17T00:00:00Z"] * 2,
            ["fact"] * 2,
            {"state_enabled": True},
            2,
        ),
    ],
)
def test_composite_factor_switches_change_order_deterministically(
    details, timestamps, kinds, enabled, expected_first
) -> None:
    conn = connect(":memory:")
    try:
        for index in range(2):
            _store(
                conn,
                ts=timestamps[index],
                kind=kinds[index],
                summary=f"factor fixture {index}",
                detail=details[index],
            )
        conn.commit()
        kwargs = {
            "relevance_enabled": False,
            "importance_enabled": False,
            "recency_enabled": False,
            "use_enabled": False,
            "state_enabled": False,
            **enabled,
        }

        scored = score_results(
            conn,
            [{"id": 1}, {"id": 2}],
            profile="composite",
            now=NOW,
            **kwargs,
        )

        assert scored[0]["id"] == expected_first
        assert scored[0]["score_components"]["enabled"] == {
            "relevance": kwargs["relevance_enabled"],
            "importance": kwargs["importance_enabled"],
            "recency": kwargs["recency_enabled"],
            "use": kwargs["use_enabled"],
            "state": kwargs["state_enabled"],
        }
    finally:
        conn.close()


def test_archived_state_is_a_zero_gate_when_explicitly_included() -> None:
    conn = connect(":memory:")
    try:
        _store(
            conn,
            ts="2026-07-17T00:00:00Z",
            kind="fact",
            summary="archived fixture",
            detail={"lifecycle": {"state": "soft-archived"}},
        )
        conn.commit()

        result = score_results(
            conn,
            [{"id": 1, "rrf_score": 0.5}],
            profile="composite",
            now=NOW,
        )[0]

        assert result["score_components"]["state_gate"] == 0.0
        assert result["final_score"] == 0.0
    finally:
        conn.close()


def test_composite_search_and_pack_emit_per_candidate_components() -> None:
    conn = connect(":memory:")
    try:
        _store(
            conn,
            ts="2026-07-17T00:00:00Z",
            kind="preference",
            summary="composite trace needle",
            detail={"importance": {"label": "must_remember", "score": 0.9}},
        )
        conn.commit()

        search = lexical_search(conn, "composite trace needle", scoring_profile="composite")
        pack = build_pack(
            conn,
            "composite trace needle",
            limit=2,
            budget_tokens=200,
            quota_enabled=False,
            scoring_profile="composite",
            scoring_relevance_enabled=True,
            scoring_importance_enabled=True,
            scoring_recency_enabled=True,
            scoring_use_enabled=True,
            scoring_state_enabled=True,
        )

        assert search[0]["score_components"]["importance_label"] == "must_remember"
        assert pack["scoring_profile"] == "composite"
        assert pack["items"][0]["score_components"]["final"] == pack["items"][0]["final_score"]
    finally:
        conn.close()


def test_cli_pack_trace_contains_composite_evidence(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_SCORING_PROFILE", "composite")
    conn = connect(":memory:")
    try:
        _store(
            conn,
            ts="2026-07-17T00:00:00Z",
            kind="decision",
            summary="trace evidence needle",
            detail={"importance": {"label": "nice_to_have", "score": 0.6}},
        )
        conn.commit()
        args = build_parser().parse_args(
            ["pack", "--query", "trace evidence needle", "--limit", "2", "--budget-tokens", "200", "--trace", "--json"]
        )
        output = io.StringIO()
        with redirect_stdout(output):
            args.func(conn, args)
        payload = json.loads(output.getvalue())

        assert payload["scoring_profile"] == "composite"
        assert payload["trace"]["candidates"][0]["score_components"]["final"] > 0.0
    finally:
        conn.close()
