from __future__ import annotations

from openclaw_mem.cli import (
    _PACK_GRAPH_SCOPE_CACHE,
    _connect,
    _insert_observation,
    _pack_graph_known_scopes,
)
from openclaw_mem.core.use_decay import refresh_selected_records


def test_pack_graph_scope_cache_is_bounded_and_invalidates_on_local_write() -> None:
    _PACK_GRAPH_SCOPE_CACHE.clear()
    conn = _connect(":memory:")
    try:
        _insert_observation(
            conn,
            {"summary": "alpha", "detail": {"scope": "team/alpha"}},
        )
        conn.commit()
        assert _pack_graph_known_scopes(conn) == ["team/alpha"]
        assert _pack_graph_known_scopes(conn) == ["team/alpha"]
        assert len(_PACK_GRAPH_SCOPE_CACHE) == 1

        _insert_observation(
            conn,
            {"summary": "beta", "detail": {"scope": "team/beta"}},
        )
        conn.commit()
        assert _pack_graph_known_scopes(conn) == ["team/alpha", "team/beta"]
        assert len(_PACK_GRAPH_SCOPE_CACHE) == 2
    finally:
        conn.close()
        _PACK_GRAPH_SCOPE_CACHE.clear()


def test_pack_use_tracking_does_not_invalidate_scope_cache_but_scope_update_does() -> None:
    _PACK_GRAPH_SCOPE_CACHE.clear()
    conn = _connect(":memory:")
    try:
        obs_id = _insert_observation(
            conn,
            {"summary": "alpha", "detail": {"scope": "team/alpha"}},
        )
        conn.commit()
        assert _pack_graph_known_scopes(conn) == ["team/alpha"]
        assert len(_PACK_GRAPH_SCOPE_CACHE) == 1

        receipt = refresh_selected_records(
            conn,
            selected_refs=[f"obs:{obs_id}"],
            ts="2026-07-17T00:00:00Z",
        )
        assert receipt["status"] == "updated"
        assert _pack_graph_known_scopes(conn) == ["team/alpha"]
        assert len(_PACK_GRAPH_SCOPE_CACHE) == 1

        conn.execute(
            "UPDATE observations SET detail_json = json_set(detail_json, '$.scope', ?) WHERE id = ?",
            ("team/beta", obs_id),
        )
        conn.commit()
        assert _pack_graph_known_scopes(conn) == ["team/beta"]
        assert len(_PACK_GRAPH_SCOPE_CACHE) == 2
    finally:
        conn.close()
        _PACK_GRAPH_SCOPE_CACHE.clear()
