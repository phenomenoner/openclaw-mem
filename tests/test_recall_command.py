from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from openclaw_mem.cli import build_parser
from openclaw_mem.core.db import _connect
from openclaw_mem.core.embeddings import MissingEmbeddingCredentials
from openclaw_mem.core.recall import RECALL_KIND, recall
from openclaw_mem.core.records import _insert_observation
from openclaw_mem.core.search import hybrid_search, lexical_search
from openclaw_mem.graph.search_adapter import blend_lexical_graph, graph_search_candidates
from openclaw_mem.vector import l2_norm, pack_f32


MODEL = "fixture-recall-v1"


class FakeProvider:
    provider_name = "fixture"
    model_id = MODEL

    def embed(self, texts, model=None):
        del texts, model
        return [[1.0, 0.0]]


def _provider(**kwargs):
    del kwargs
    return FakeProvider()


@pytest.fixture()
def conn():
    value = _connect(":memory:")
    ids = []
    for summary in ("alpha memory first", "alpha memory second", "unrelated note"):
        ids.append(
            _insert_observation(
                value,
                {
                    "ts": "2026-07-17T00:00:00Z",
                    "kind": "note",
                    "tool_name": "fixture",
                    "summary": summary,
                    "detail": {"scope": "project:test"},
                },
            )
        )
    for row_id, vector in zip(ids, ([1.0, 0.0], [0.8, 0.2], [0.0, 1.0])):
        value.execute(
            "INSERT INTO observation_embeddings "
            "(observation_id, model, dim, vector, norm, created_at) "
            "VALUES (?, ?, 2, ?, ?, '2026-07-17T00:00:00Z')",
            (row_id, MODEL, pack_f32(vector), l2_norm(vector)),
        )
    value.commit()
    yield value
    value.close()


def test_lexical_mode_matches_existing_search_ids(conn) -> None:
    receipt = recall(conn, "alpha", mode="lexical", limit=5)
    assert receipt["kind"] == RECALL_KIND
    assert receipt["mode_effective"] == "lexical"
    assert [row["id"] for row in receipt["results"]] == [
        row["id"] for row in lexical_search(conn, "alpha", limit=5)
    ]


def test_vector_mode_matches_existing_vector_order(conn) -> None:
    receipt = recall(conn, "alpha", mode="vector", provider_factory=_provider)
    assert receipt["mode_effective"] == "vector"
    assert [row["id"] for row in receipt["results"]] == [1, 2, 3]
    assert receipt["lanes_used"] == ["vector"]


def test_hybrid_mode_matches_existing_hybrid_ids(conn) -> None:
    receipt = recall(conn, "alpha", mode="hybrid", provider_factory=_provider)
    expected = hybrid_search(conn, "alpha", vector_ids=[1, 2, 3], limit=20)
    assert receipt["mode_effective"] == "hybrid"
    assert [row["id"] for row in receipt["results"]] == [row["id"] for row in expected]


def test_graph_mode_uses_existing_adapter(tmp_path: Path, conn) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "module.alpha",
                        "type": "module",
                        "metadata": {
                            "source_path": "src/alpha.py",
                            "receipt_id": "fixture-receipt",
                            "freshness": "snapshot",
                        },
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    receipt = recall(conn, "alpha", mode="graph", graph_path=graph)
    assert receipt["mode_effective"] == "graph"
    assert receipt["results"][0]["node_id"] == "module.alpha"
    expected = blend_lexical_graph(
        lexical_search(conn, "alpha", limit=20),
        graph_search_candidates(query="alpha", graph_path=graph, limit=20)["candidates"],
    )
    assert receipt["results"] == expected


def test_auto_routes_to_hybrid_when_embeddings_are_usable(conn) -> None:
    receipt = recall(conn, "alpha", mode="auto", provider_factory=_provider)
    assert receipt["mode_requested"] == "auto"
    assert receipt["mode_effective"] == "hybrid"
    assert receipt["routing_reason"] == "embedding_provider:fixture"


def test_auto_routes_to_lexical_without_stored_embeddings(monkeypatch) -> None:
    monkeypatch.setattr("openclaw_mem.core.recall.get_api_key", lambda: None)
    monkeypatch.delenv("OPENCLAW_MEM_EMBED_PROVIDER", raising=False)
    empty = _connect(":memory:")
    try:
        receipt = recall(empty, "alpha", mode="auto")
        assert receipt["mode_effective"] == "lexical"
        assert receipt["routing_reason"] == "no_stored_embeddings"
    finally:
        empty.close()


def test_auto_routes_to_hybrid_when_provider_is_configured_without_vectors(monkeypatch) -> None:
    monkeypatch.setattr("openclaw_mem.core.recall.get_api_key", lambda: "configured")
    empty = _connect(":memory:")
    try:
        receipt = recall(empty, "alpha", mode="auto")
        assert receipt["mode_effective"] == "hybrid"
        assert receipt["routing_reason"] == "embedding_provider_configured_no_stored_vectors"
    finally:
        empty.close()


def test_unavailable_vector_lane_degrades_to_lexical(conn) -> None:
    def unavailable(**kwargs):
        del kwargs
        raise MissingEmbeddingCredentials("missing")

    receipt = recall(conn, "alpha", mode="vector", provider_factory=unavailable)
    assert receipt["mode_effective"] == "lexical"
    assert receipt["degraded_from"] == "vector"
    assert receipt["routing_reason"].startswith("embedding_unavailable:")
    assert [row["id"] for row in receipt["results"]] == [1, 2]


def test_scope_is_applied_to_vector_results(conn) -> None:
    receipt = recall(
        conn,
        "alpha",
        mode="vector",
        scope="project:other",
        provider_factory=_provider,
    )
    assert receipt["results"] == []


def test_incompatible_vector_dimension_degrades_without_throwing(conn) -> None:
    class WrongDimensionProvider(FakeProvider):
        def embed(self, texts, model=None):
            del texts, model
            return [[1.0, 0.0, 0.0]]

    receipt = recall(
        conn,
        "alpha",
        mode="vector",
        provider_factory=lambda **kwargs: WrongDimensionProvider(),
    )
    assert receipt["mode_effective"] == "lexical"
    assert receipt["degraded_from"] == "vector"
    assert receipt["routing_reason"] == "vector_index_no_compatible_rows"


def test_cli_emits_versioned_recall_receipt(conn, monkeypatch) -> None:
    monkeypatch.setattr("openclaw_mem.core.recall.create_embedding_provider", _provider)
    args = build_parser().parse_args(["recall", "alpha", "--mode", "hybrid", "--json"])
    out = StringIO()
    with redirect_stdout(out):
        args.func(conn, args)
    receipt = json.loads(out.getvalue())
    assert receipt["kind"] == RECALL_KIND
    assert receipt["mode_effective"] == "hybrid"


def test_core_recall_is_output_free(conn, capsys) -> None:
    recall(conn, "alpha", mode="hybrid", provider_factory=_provider)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
