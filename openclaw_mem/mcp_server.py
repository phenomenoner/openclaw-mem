"""Minimal stdio MCP server for openclaw-mem.

The implementation intentionally avoids a runtime dependency on an MCP SDK.
It speaks the JSON-RPC methods needed by MCP clients:

- initialize
- tools/list
- tools/call

Tool descriptions are stable text. Do not interpolate version numbers or
runtime paths into them; harness consumers may pin the description hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from openclaw_mem.core.api import connect as _connect, store_observation as _insert_observation
from openclaw_mem.core.db import DEFAULT_DB
from openclaw_mem.core.privacy import is_private_text
from openclaw_mem.core.recall import recall as core_recall
from openclaw_mem.graph.code_extract import query_impact as query_code_impact
from openclaw_mem.graph.query import query_downstream, query_subgraph, query_upstream


SCHEMA = "openclaw-mem.mcp.tools.v1"


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    approval_required: bool = False
    read_only: bool = True
    timeout_ms: int = 3000


TOOLS: tuple[ToolDef, ...] = (
    ToolDef(
        name="mem_search",
        description="Search local openclaw-mem observations and return compact cited matches.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="mem_timeline",
        description="Return recent local openclaw-mem observations in timestamp order.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "kind": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="mem_get",
        description="Get one local openclaw-mem observation by record reference or numeric id.",
        input_schema={
            "type": "object",
            "properties": {"recordRef": {"type": "string"}},
            "required": ["recordRef"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="mem_pack",
        description="Build a bounded ContextPack v1 with citations for an agent query.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 8},
                "budgetTokens": {"type": "integer", "minimum": 64, "maximum": 8000, "default": 1200},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="mem_recall",
        description="Recall memories through the shared lexical, vector, hybrid, or graph router.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["auto", "lexical", "vector", "hybrid", "graph"],
                    "default": "auto",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "scope": {"type": "string"},
                "model": {"type": "string"},
                "baseUrl": {"type": "string"},
                "vectorBackend": {
                    "type": "string",
                    "enum": ["auto", "python", "numpy"],
                    "default": "auto",
                },
                "graphPath": {"type": "string"},
                "graphReadinessState": {"type": "string"},
                "graphStaleAfterDays": {"type": "integer", "minimum": 0, "default": 30},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="graph_neighbors",
        description="Read immediate upstream, downstream, or bidirectional neighbors from the graph store.",
        input_schema={
            "type": "object",
            "properties": {
                "dbPath": {"type": "string"},
                "nodeId": {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["upstream", "downstream", "both"],
                    "default": "both",
                },
            },
            "required": ["nodeId"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="graph_path",
        description="Read a bounded multi-hop subgraph around one node from the graph store.",
        input_schema={
            "type": "object",
            "properties": {
                "dbPath": {"type": "string"},
                "nodeId": {"type": "string"},
                "hops": {"type": "integer", "minimum": 0, "maximum": 6, "default": 2},
                "direction": {
                    "type": "string",
                    "enum": ["upstream", "downstream", "both"],
                    "default": "both",
                },
                "maxNodes": {"type": "integer", "minimum": 1, "maximum": 500, "default": 40},
                "maxEdges": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 80},
            },
            "required": ["nodeId"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="graph_impact",
        description="Read the bounded code-graph impact neighborhood for one repository-relative file path.",
        input_schema={
            "type": "object",
            "properties": {
                "graphPath": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["graphPath", "path"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="mem_store",
        description="Store one local observation without requiring embedding availability.",
        approval_required=True,
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "kind": {"type": "string", "default": "fact"},
                "importance": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.7},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    ),
    ToolDef(
        name="mem_status",
        description="Return local openclaw-mem store health, counts, and latency receipt.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolDef(
        name="mem_trust_inspect",
        description="Inspect trust metadata for one local observation and explain pack eligibility hints.",
        input_schema={
            "type": "object",
            "properties": {"recordRef": {"type": "string"}},
            "required": ["recordRef"],
            "additionalProperties": False,
        },
    ),
)


def tool_manifest() -> dict[str, Any]:
    tools = []
    for tool in TOOLS:
        desc_hash = hashlib.sha256(tool.description.encode("utf-8")).hexdigest()
        schema_json = json.dumps(tool.input_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        schema_hash = hashlib.sha256(schema_json.encode("utf-8")).hexdigest()
        tools.append(
            {
                "name": tool.name,
                "description": tool.description,
                "descriptionSha256": desc_hash,
                "inputSchemaSha256": schema_hash,
                "inputSchema": tool.input_schema,
                "approvalRequired": tool.approval_required,
                "readOnly": tool.read_only,
                "timeoutMs": tool.timeout_ms,
            }
        )
    return {
        "schema": SCHEMA,
        "contractVersion": 1,
        "errorShape": {
            "ok": False,
            "error": {"type": "string", "message": "string"},
            "receipt": {"tool": "string", "latencyMs": "integer"},
        },
        "tools": tools,
    }


def _record_id(record_ref: Any) -> int:
    text = str(record_ref or "").strip()
    if text.startswith("obs:"):
        text = text[4:]
    return int(text)


def _row_to_observation(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    detail: dict[str, Any]
    try:
        detail = json.loads(row["detail_json"] or "{}")
        if not isinstance(detail, dict):
            detail = {"_raw": row["detail_json"]}
    except Exception:
        detail = {"_raw": row["detail_json"]}
    return {
        "recordRef": f"obs:{int(row['id'])}",
        "id": int(row["id"]),
        "ts": row["ts"],
        "kind": row["kind"],
        "summary": row["summary"],
        "summary_en": row["summary_en"],
        "lang": row["lang"],
        "tool_name": row["tool_name"],
        "detail": detail,
    }


def _safe_like(query: str) -> str:
    return "%" + query.replace("%", "\\%").replace("_", "\\_") + "%"


def mem_search(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    limit = max(1, min(50, int(args.get("limit") or 8)))
    like = _safe_like(query)
    rows = conn.execute(
        """
        SELECT id, ts, kind, summary, summary_en, lang, tool_name, detail_json
        FROM observations
        WHERE summary LIKE ? ESCAPE '\\'
           OR COALESCE(summary_en, '') LIKE ? ESCAPE '\\'
           OR COALESCE(tool_name, '') LIKE ? ESCAPE '\\'
           OR COALESCE(detail_json, '') LIKE ? ESCAPE '\\'
        ORDER BY id DESC
        LIMIT ?
        """,
        (like, like, like, like, limit),
    ).fetchall()
    items = []
    for row in rows:
        item = _row_to_observation(row)
        if item and isinstance(item.get("summary"), str) and len(item["summary"]) > 240:
            item["summary"] = item["summary"][:237].rstrip() + "..."
        items.append(item)
    return {
        "ok": True,
        "query": query,
        "count": len(rows),
        "estimatedTokens": sum(max(1, (len(str((item or {}).get("summary") or "")) + 3) // 4) for item in items),
        "items": items,
    }


def mem_timeline(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(100, int(args.get("limit") or 20)))
    kind = str(args.get("kind") or "").strip()
    params: list[Any] = []
    where = ""
    if kind:
        where = "WHERE kind = ?"
        params.append(kind)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, ts, kind, summary, summary_en, lang, tool_name, detail_json
        FROM observations
        {where}
        ORDER BY ts DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return {"ok": True, "count": len(rows), "items": [_row_to_observation(r) for r in rows]}


def mem_get(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    rid = _record_id(args.get("recordRef"))
    row = conn.execute(
        "SELECT id, ts, kind, summary, summary_en, lang, tool_name, detail_json FROM observations WHERE id = ?",
        (rid,),
    ).fetchone()
    return {"ok": row is not None, "item": _row_to_observation(row)}


def mem_store(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")
    if is_private_text(text):
        return {"ok": False, "skipped": True, "reason": "private_marker"}
    kind = str(args.get("kind") or "fact").strip() or "fact"
    importance = float(args.get("importance") if args.get("importance") is not None else 0.7)
    rid = _insert_observation(
        conn,
        {
            "kind": kind,
            "summary": text,
            "tool_name": "mcp.mem_store",
            "detail": {"importance": {"score": importance, "method": "mcp.mem_store", "label": "unknown"}},
        },
    )
    conn.commit()
    return {"ok": True, "recordRef": f"obs:{rid}", "id": rid}


def mem_status(conn: sqlite3.Connection, _args: dict[str, Any]) -> dict[str, Any]:
    observations = int(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] or 0)
    embeddings = int(conn.execute("SELECT COUNT(*) FROM observation_embeddings").fetchone()[0] or 0)
    docs = int(conn.execute("SELECT COUNT(*) FROM docs_chunks").fetchone()[0] or 0)
    return {
        "ok": True,
        "schema": "openclaw-mem.mcp.status.v1",
        "counts": {"observations": observations, "embeddings": embeddings, "docs_chunks": docs},
    }


def mem_trust_inspect(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    item = mem_get(conn, args).get("item")
    if not item:
        return {"ok": False, "error": "not_found"}
    detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
    trust = detail.get("trust") or detail.get("trust_tier") or "unknown"
    quarantine = bool(detail.get("quarantined") or detail.get("quarantine"))
    return {
        "ok": True,
        "recordRef": item["recordRef"],
        "trust": trust,
        "quarantined": quarantine,
        "packEligibility": "excluded_by_quarantine" if quarantine else "eligible_subject_to_pack_policy",
    }


def mem_pack(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    # The CLI handler owns the full pack policy (trust, graph, trace, tails,
    # budget accounting).  Invoke that handler in-process so MCP cannot drift
    # into a second implementation of the product contract.
    from openclaw_mem.cli import _invoke_cli_json

    return _invoke_cli_json(
        conn,
        [
            "pack",
            "--query",
            query,
            "--limit",
            str(max(1, min(30, int(args.get("limit") or 8)))),
            "--budget-tokens",
            str(max(64, min(8000, int(args.get("budgetTokens") or 1200)))),
        ],
    )


def mem_recall(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    return core_recall(
        conn,
        query,
        mode=str(args.get("mode") or "auto"),
        limit=max(1, min(100, int(args.get("limit") or 20))),
        scope=str(args["scope"]) if args.get("scope") is not None else None,
        model=str(args["model"]) if args.get("model") is not None else None,
        base_url=str(args["baseUrl"]) if args.get("baseUrl") is not None else None,
        vector_backend=str(args.get("vectorBackend") or "auto"),
        graph_path=str(args["graphPath"]) if args.get("graphPath") is not None else None,
        graph_readiness_state=(
            str(args["graphReadinessState"])
            if args.get("graphReadinessState") is not None
            else None
        ),
        graph_stale_after_days=max(0, int(args.get("graphStaleAfterDays") or 30)),
    )


def _graph_db_path(conn: sqlite3.Connection, args: dict[str, Any]) -> str:
    explicit = str(args.get("dbPath") or "").strip()
    if explicit:
        return explicit
    row = conn.execute("PRAGMA database_list").fetchone()
    inferred = str(row[2] if row is not None and len(row) > 2 else "").strip()
    if not inferred:
        raise ValueError("dbPath is required when the MCP database is in-memory")
    return inferred


def graph_neighbors(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    db_path = _graph_db_path(conn, args)
    node_id = str(args.get("nodeId") or "").strip()
    if not node_id:
        raise ValueError("nodeId is required")
    direction = str(args.get("direction") or "both").strip().lower()
    if direction == "upstream":
        return query_upstream(db_path=db_path, node_id=node_id)
    if direction == "downstream":
        return query_downstream(db_path=db_path, node_id=node_id)
    if direction != "both":
        raise ValueError("direction must be one of: upstream, downstream, both")
    upstream = query_upstream(db_path=db_path, node_id=node_id)
    downstream = query_downstream(db_path=db_path, node_id=node_id)
    return {
        "ok": True,
        "query": "neighbors",
        "node_id": node_id,
        "direction": "both",
        "count": int(upstream["count"]) + int(downstream["count"]),
        "upstream": upstream,
        "downstream": downstream,
    }


def graph_path(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    return query_subgraph(
        db_path=_graph_db_path(conn, args),
        node_id=str(args.get("nodeId") or ""),
        hops=int(args.get("hops") if args.get("hops") is not None else 2),
        direction=str(args.get("direction") or "both"),
        max_nodes=int(args.get("maxNodes") if args.get("maxNodes") is not None else 40),
        max_edges=int(args.get("maxEdges") if args.get("maxEdges") is not None else 80),
    )


def graph_impact(_conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    graph_path_value = str(args.get("graphPath") or "").strip()
    path = str(args.get("path") or "").strip()
    if not graph_path_value:
        raise ValueError("graphPath is required")
    if not path:
        raise ValueError("path is required")
    return query_code_impact(graph_path=graph_path_value, path=path)


TOOL_HANDLERS: dict[str, Callable[[sqlite3.Connection, dict[str, Any]], dict[str, Any]]] = {
    "mem_search": mem_search,
    "mem_timeline": mem_timeline,
    "mem_get": mem_get,
    "mem_pack": mem_pack,
    "mem_recall": mem_recall,
    "graph_neighbors": graph_neighbors,
    "graph_path": graph_path,
    "graph_impact": graph_impact,
    "mem_store": mem_store,
    "mem_status": mem_status,
    "mem_trust_inspect": mem_trust_inspect,
}


def _mcp_tool_def(tool: ToolDef) -> dict[str, Any]:
    return {"name": tool.name, "description": tool.description, "inputSchema": tool.input_schema}


def call_tool(conn: sqlite3.Connection, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    out = handler(conn, dict(arguments or {}))
    out.setdefault("receipt", {})
    out["receipt"].update({"tool": name, "latencyMs": int((time.perf_counter() - started) * 1000)})
    return out


def handle_jsonrpc(conn: sqlite3.Connection, request: dict[str, Any]) -> dict[str, Any] | None:
    rid = request.get("id")
    method = str(request.get("method") or "")
    params = request.get("params") if isinstance(request.get("params"), dict) else {}

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "openclaw-mem", "version": "mcp-v1"},
                "capabilities": {"tools": {}},
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": [_mcp_tool_def(tool) for tool in TOOLS]}
        elif method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            payload = call_tool(conn, name, arguments)
            result = {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, sort_keys=True)}],
                "isError": False,
            }
        else:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": rid, "result": result}
    except ValueError as exc:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {
                "code": -32602,
                "message": str(exc),
                "data": {"hint": "check the tool input schema and required arguments"},
            },
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {
                "code": -32000,
                "message": str(exc),
                "data": {"hint": "run openclaw-mem doctor --json and verify local paths"},
            },
        }


def serve(db_path: str) -> None:
    conn = _connect(db_path)
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            else:
                resp = handle_jsonrpc(conn, req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False, sort_keys=True) + "\n")
                sys.stdout.flush()
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="openclaw-mem stdio MCP server")
    parser.add_argument("--db", default=None, help="SQLite DB path (default: openclaw-mem default)")
    parser.add_argument("--tool-descriptions", action="store_true", help="Print stable tool description hash manifest and exit")
    parser.add_argument("--json", action="store_true", help="Accepted with --tool-descriptions for CLI contract symmetry")
    args = parser.parse_args(argv)
    if args.tool_descriptions:
        print(json.dumps(tool_manifest(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    serve(args.db or DEFAULT_DB)


if __name__ == "__main__":
    main()
