from __future__ import annotations

from openclaw_mem.cli import (
    _PACK_GRAPH_SCOPE_CACHE,
    _connect,
    _insert_observation,
    _pack_graph_known_scopes,
)


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
