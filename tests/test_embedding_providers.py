from __future__ import annotations

import argparse
import io
import json
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pytest

from openclaw_mem.cli import cmd_embed, cmd_store, cmd_vsearch
from openclaw_mem.core.db import _connect
from openclaw_mem.core.embeddings import (
    EmbeddingProviderError,
    LOCAL_FASTEMBED_MODEL_ID,
    MissingEmbeddingCredentials,
    create_embedding_provider,
    embedding_provider_name,
)
from openclaw_mem.core.records import _insert_observation


class _FakeTextEmbedding:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def embed(self, texts):
        for text in texts:
            value = [0.0] * 384
            if "alpha" in text.casefold():
                value[0] = 1.0
            else:
                value[1] = 1.0
            yield value


def _fastembed_module() -> types.ModuleType:
    module = types.ModuleType("fastembed")
    module.TextEmbedding = _FakeTextEmbedding
    return module


def test_provider_selection_defaults_to_openai_and_validates_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_MEM_EMBED_PROVIDER", raising=False)
    assert embedding_provider_name() == "openai"
    with pytest.raises(MissingEmbeddingCredentials):
        create_embedding_provider(api_key=None, model="remote-model")
    monkeypatch.setenv("OPENCLAW_MEM_EMBED_PROVIDER", "invalid")
    with pytest.raises(EmbeddingProviderError, match="expected openai or local"):
        embedding_provider_name()


def test_local_provider_needs_no_api_key_and_emits_384_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_EMBED_PROVIDER", "local")
    with patch.dict(sys.modules, {"fastembed": _fastembed_module()}):
        provider = create_embedding_provider(api_key=None, model="ignored")
        vectors = provider.embed(["alpha", "beta"])
    assert provider.provider_name == "local"
    assert provider.model_id == LOCAL_FASTEMBED_MODEL_ID
    assert [len(vector) for vector in vectors] == [384, 384]
    assert vectors[0][0] == 1.0
    assert vectors[1][1] == 1.0


def test_local_embed_to_vsearch_flow_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_EMBED_PROVIDER", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    conn = _connect(":memory:")
    try:
        alpha_id = _insert_observation(conn, {"summary": "alpha memory", "detail": {}})
        _insert_observation(conn, {"summary": "beta memory", "detail": {}})
        embed_args = argparse.Namespace(
            model="remote-default",
            limit=10,
            batch=2,
            base_url="https://example.invalid/v1",
            field="original",
            json=True,
        )
        with (
            patch.dict(sys.modules, {"fastembed": _fastembed_module()}),
            patch("openclaw_mem.cli._get_api_key", return_value=None),
            redirect_stdout(io.StringIO()) as embed_output,
        ):
            cmd_embed(conn, embed_args)
        receipt = json.loads(embed_output.getvalue())
        assert receipt["provider"] == "local"
        assert receipt["model"] == LOCAL_FASTEMBED_MODEL_ID
        assert receipt["embedded"] == 2
        assert tuple(
            conn.execute(
                "SELECT DISTINCT model, dim FROM observation_embeddings"
            ).fetchall()[0]
        ) == (LOCAL_FASTEMBED_MODEL_ID, 384)

        search_args = argparse.Namespace(
            query="alpha",
            query_vector_json=None,
            query_vector_file=None,
            model="remote-default",
            limit=2,
            base_url="https://example.invalid/v1",
            vector_backend="python",
            json=True,
        )
        with (
            patch.dict(sys.modules, {"fastembed": _fastembed_module()}),
            patch("openclaw_mem.cli._get_api_key", return_value=None),
            redirect_stdout(io.StringIO()) as search_output,
        ):
            cmd_vsearch(conn, search_args)
        results = json.loads(search_output.getvalue())
        assert results[0]["id"] == alpha_id
        assert results[0]["embedding_provider"] == "local"
    finally:
        conn.close()


def test_store_uses_local_provider_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_MEM_EMBED_PROVIDER", "local")
    conn = _connect(":memory:")
    args = argparse.Namespace(
        text="alpha durable memory",
        text_en=None,
        lang="en",
        category="fact",
        importance=0.8,
        model="remote-default",
        base_url="https://example.invalid/v1",
        workspace=None,
        no_file_write=True,
        memory_notes_dir=None,
        json=True,
    )
    try:
        with (
            patch.dict(sys.modules, {"fastembed": _fastembed_module()}),
            patch("openclaw_mem.cli._get_api_key", return_value=None),
            redirect_stdout(io.StringIO()) as output,
            redirect_stderr(io.StringIO()) as error_output,
        ):
            cmd_store(conn, args)
        receipt = json.loads(output.getvalue())
        assert receipt["embedded"] is True
        assert receipt["embedding_provider"] == "local"
        assert receipt["embedding_model"] == LOCAL_FASTEMBED_MODEL_ID
        assert error_output.getvalue() == ""
        assert tuple(
            conn.execute(
                "SELECT model, dim FROM observation_embeddings WHERE observation_id = ?",
                (receipt["id"],),
            ).fetchone()
        ) == (LOCAL_FASTEMBED_MODEL_ID, 384)
    finally:
        conn.close()
