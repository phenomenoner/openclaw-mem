from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openclaw_mem.cli import _connect, _insert_observation, _invoke_cli_json
from openclaw_mem.graph.code_extract import extract_code_graph
from openclaw_mem.graph.refresh import refresh_topology
from openclaw_mem.mcp_server import TOOLS, call_tool, handle_jsonrpc


_VOLATILE_KEYS = {
    "ts",
    "durationms",
    "duration_ms",
    "elapsedms",
    "elapsed_ms",
    "latency",
    "latencyms",
    "latency_ms",
    "timing",
    "timingms",
    "timing_ms",
    "last_used_at",
    "used_count_before",
    "used_count_after",
}


def _without_transport_and_timing(value: Any, *, root: bool = True) -> Any:
    if isinstance(value, list):
        return [_without_transport_and_timing(item, root=False) for item in value]
    if not isinstance(value, dict):
        return value
    cleaned = {}
    for key, item in value.items():
        normalized = str(key).replace("-", "").lower()
        if root and key == "receipt":
            continue
        if normalized in _VOLATILE_KEYS or "latency" in normalized or "timing" in normalized:
            continue
        cleaned[key] = _without_transport_and_timing(item, root=False)
    return cleaned


def _mcp_payload(conn, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = handle_jsonrpc(
        conn,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response is not None
    assert "error" not in response
    return json.loads(response["result"]["content"][0]["text"])


def _seed(conn) -> None:
    for summary in (
        "MCP and CLI recall share one contract.",
        "ContextPack preserves cited memory evidence.",
        "Unrelated fixture for deterministic ranking.",
    ):
        _insert_observation(conn, {"kind": "fact", "summary": summary, "detail": {}})
    conn.commit()


def test_mem_recall_is_deeply_equivalent_to_cli_json() -> None:
    conn = _connect(":memory:")
    try:
        _seed(conn)
        cli = _invoke_cli_json(conn, ["recall", "contract", "--mode", "lexical", "--limit", "5"])
        mcp = _mcp_payload(conn, "mem_recall", {"query": "contract", "mode": "lexical", "limit": 5})
        assert _without_transport_and_timing(mcp) == _without_transport_and_timing(cli)
    finally:
        conn.close()


def test_mem_pack_is_deeply_equivalent_to_cli_json() -> None:
    conn = _connect(":memory:")
    try:
        _seed(conn)
        argv = ["pack", "--query", "ContextPack evidence", "--limit", "5", "--budget-tokens", "300"]
        cli = _invoke_cli_json(conn, argv)
        mcp = _mcp_payload(
            conn,
            "mem_pack",
            {"query": "ContextPack evidence", "limit": 5, "budgetTokens": 300},
        )
        assert _without_transport_and_timing(mcp) == _without_transport_and_timing(cli)
    finally:
        conn.close()


def test_graph_read_tools_wrap_existing_query_engines(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    topology = {
        "nodes": [
            {"id": "job.writer", "type": "cron_job"},
            {"id": "artifact.memory", "type": "artifact"},
            {"id": "service.reader", "type": "service"},
        ],
        "edges": [
            {"src": "job.writer", "dst": "artifact.memory", "type": "writes"},
            {"src": "artifact.memory", "dst": "service.reader", "type": "feeds"},
        ],
    }
    refresh_topology(topology, db_path=db_path)
    conn = _connect(str(db_path))
    try:
        neighbors = call_tool(conn, "graph_neighbors", {"nodeId": "artifact.memory"})
        assert neighbors["count"] == 2
        assert neighbors["upstream"]["edges"][0]["src"] == "job.writer"
        assert neighbors["downstream"]["edges"][0]["dst"] == "service.reader"

        subgraph = call_tool(
            conn,
            "graph_path",
            {"nodeId": "artifact.memory", "hops": 1, "direction": "both"},
        )
        assert subgraph["center_node_id"] == "artifact.memory"
        assert subgraph["node_count"] == 3
        assert subgraph["edge_count"] == 2
    finally:
        conn.close()


def test_graph_impact_wraps_portable_code_graph(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    graph = extract_code_graph(repo=repo)
    graph_path = tmp_path / "code-graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    conn = _connect(":memory:")
    try:
        impact = call_tool(
            conn,
            "graph_impact",
            {"graphPath": str(graph_path), "path": "app.py"},
        )
        assert impact["ok"] is True
        assert impact["node_id"] == "file.app.py"
        assert impact["node"] is not None
    finally:
        conn.close()


def test_new_graph_tools_are_read_only_and_invalid_args_map_to_jsonrpc() -> None:
    definitions = {tool.name: tool for tool in TOOLS}
    for name in ("mem_recall", "graph_neighbors", "graph_path", "graph_impact"):
        assert definitions[name].read_only is True
        assert definitions[name].approval_required is False

    conn = _connect(":memory:")
    try:
        response = handle_jsonrpc(
            conn,
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "mem_recall", "arguments": {}},
            },
        )
        assert response is not None
        assert response["error"]["code"] == -32602
        assert response["error"]["data"]["hint"]
    finally:
        conn.close()
