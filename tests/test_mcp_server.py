from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation
from openclaw_mem.context_pack_v1 import CONTEXT_PACK_V1_SCHEMA
from openclaw_mem.mcp_server import TOOLS, call_tool, handle_jsonrpc, tool_manifest


def test_tool_manifest_has_stable_description_hashes():
    manifest = tool_manifest()
    assert manifest["schema"] == "openclaw-mem.mcp.tools.v1"
    assert manifest["contractVersion"] == 1
    assert manifest["errorShape"]["ok"] is False
    assert len(manifest["tools"]) >= 7
    for tool in manifest["tools"]:
        assert tool["name"]
        assert tool["description"]
        assert len(tool["descriptionSha256"]) == 64
        assert len(tool["inputSchemaSha256"]) == 64
        assert isinstance(tool["approvalRequired"], bool)
        assert isinstance(tool["readOnly"], bool)
        assert isinstance(tool["timeoutMs"], int)
    store = next(tool for tool in manifest["tools"] if tool["name"] == "mem_store")
    assert store["approvalRequired"] is True
    assert store["readOnly"] is False
    for tool in manifest["tools"]:
        if tool["name"] != "mem_store":
            assert tool["approvalRequired"] is False
            assert tool["readOnly"] is True


def test_committed_tool_description_manifest_stays_in_sync():
    path = Path(__file__).resolve().parents[1] / "docs" / "fixtures" / "mcp-tool-descriptions.v1.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    live = tool_manifest()
    live_compact = {
        "schema": live["schema"],
        "contractVersion": live["contractVersion"],
        "errorShape": live["errorShape"],
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "descriptionSha256": tool["descriptionSha256"],
                "inputSchemaSha256": tool["inputSchemaSha256"],
                "approvalRequired": tool["approvalRequired"],
                "readOnly": tool["readOnly"],
                "timeoutMs": tool["timeoutMs"],
            }
            for tool in live["tools"]
        ],
    }
    assert committed == live_compact


def test_tool_descriptions_accept_json_flag():
    proc = subprocess.run(
        [sys.executable, "-m", "openclaw_mem.mcp_server", "--tool-descriptions", "--json"],
        check=True,
        text=True, encoding="utf-8", errors="replace",
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "openclaw-mem.mcp.tools.v1"


def test_tools_list_jsonrpc_contract():
    conn = _connect(":memory:")
    try:
        resp = handle_jsonrpc(conn, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert resp["result"]["tools"][0]["name"] == TOOLS[0].name
    finally:
        conn.close()


def test_mcp_search_pack_store_status_roundtrip():
    conn = _connect(":memory:")
    try:
        stored = call_tool(conn, "mem_store", {"text": "CK prefers cited ContextPack fixtures.", "kind": "preference"})
        assert stored["ok"] is True
        found = call_tool(conn, "mem_search", {"query": "ContextPack", "limit": 5})
        assert found["count"] == 1
        packed = call_tool(conn, "mem_pack", {"query": "ContextPack fixtures", "limit": 5, "budgetTokens": 300})
        assert packed["context_pack"]["schema"] == CONTEXT_PACK_V1_SCHEMA
        status = call_tool(conn, "mem_status", {})
        assert status["counts"]["observations"] == 1
    finally:
        conn.close()


def test_mcp_store_skips_private_marker():
    conn = _connect(":memory:")
    try:
        out = call_tool(conn, "mem_store", {"text": "<private> do not keep", "kind": "fact"})
        assert out["ok"] is False
        assert out["reason"] == "private_marker"
        status = call_tool(conn, "mem_status", {})
        assert status["counts"]["observations"] == 0
    finally:
        conn.close()


def test_tools_call_jsonrpc_returns_text_content():
    conn = _connect(":memory:")
    try:
        _insert_observation(conn, {"kind": "fact", "summary": "MCP JSON-RPC smoke row", "detail": {}})
        conn.commit()
        resp = handle_jsonrpc(
            conn,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "mem_search", "arguments": {"query": "smoke"}},
            },
        )
        text = resp["result"]["content"][0]["text"]
        payload = json.loads(text)
        assert payload["ok"] is True
        assert payload["count"] == 1
    finally:
        conn.close()
