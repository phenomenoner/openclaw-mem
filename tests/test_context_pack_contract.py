from __future__ import annotations

import json
from pathlib import Path

import pytest

from openclaw_mem.context_pack_contract import (
    AGENT_HARNESS_CONTEXT_PACK_SCHEMA,
    ContextPackContractError,
    require_context_pack_v1,
    to_agent_harness_context_pack_v1,
    validate_context_pack_v1,
)
from openclaw_mem.context_pack_v1 import CONTEXT_PACK_V1_SCHEMA


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "context_pack"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_official_openclaw_mem_context_pack_v1_fixture_is_valid():
    payload = _load_fixture("openclaw_mem_context_pack_v1.json")

    result = validate_context_pack_v1(payload)

    assert result.ok, result.errors
    assert result.schema == CONTEXT_PACK_V1_SCHEMA
    assert payload["items"][0]["citations"]["recordRef"] == payload["items"][0]["recordRef"]
    assert payload["items"][0]["text"]


def test_unknown_future_context_pack_schema_is_rejected_with_typed_error():
    payload = _load_fixture("unknown_future_context_pack.json")

    result = validate_context_pack_v1(payload)

    assert not result.ok
    assert any("unsupported ContextPack schema" in error for error in result.errors)
    with pytest.raises(ContextPackContractError, match="unsupported ContextPack schema"):
        require_context_pack_v1(payload)


def test_agent_harness_adapter_preserves_citation_id_and_text():
    payload = _load_fixture("openclaw_mem_context_pack_v1.json")

    adapted = to_agent_harness_context_pack_v1(payload)

    assert adapted["schema"] == AGENT_HARNESS_CONTEXT_PACK_SCHEMA
    assert adapted["sourceSchema"] == CONTEXT_PACK_V1_SCHEMA
    assert adapted["items"][0]["citationId"] == "obs:compat-001"
    assert adapted["items"][0]["chunk"]["id"] == "obs:compat-001"
    assert adapted["items"][0]["chunk"]["text"] == payload["items"][0]["text"]
    assert adapted["items"][0]["chunk"]["sourceUri"] == payload["items"][0]["citations"]["url"]
