from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _json_load_object(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
        except Exception:
            return {}
        if isinstance(obj, dict):
            return obj
    return {}


def _json_load_tags(raw: Any) -> List[str]:
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
        except Exception:
            return []
        if isinstance(obj, list):
            out: List[str] = []
            for item in obj:
                token = str(item).strip()
                if token:
                    out.append(token)
            return sorted(set(out))
    return []


def _load_node_map(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    rows = conn.execute(
        "SELECT node_id, node_type, tags_json, metadata_json FROM graph_nodes ORDER BY node_id"
    ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        node_id = str(row[0])
        out[node_id] = {
            "id": node_id,
            "type": str(row[1]),
            "tags": _json_load_tags(row[2]),
            "metadata": _json_load_object(row[3]),
        }
    return out


def _edge_rows(
    conn: sqlite3.Connection,
    *,
    where_sql: str,
    where_args: Tuple[Any, ...],
) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT src_id, dst_id, edge_type, provenance, metadata_json "
        "FROM graph_edges "
        f"WHERE {where_sql} "
        "ORDER BY src_id, dst_id, edge_type, provenance",
        where_args,
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "src": str(row[0]),
                "dst": str(row[1]),
                "type": str(row[2]),
                "provenance": str(row[3]),
                "metadata": _json_load_object(row[4]),
            }
        )
    return out


def _attach_nodes(
    edges: List[Dict[str, Any]],
    node_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for edge in edges:
        item = dict(edge)
        item["src_node"] = node_map.get(edge["src"])
        item["dst_node"] = node_map.get(edge["dst"])
        out.append(item)
    return out


def _query_edges(
    *,
    db_path: str | Path,
    where_sql: str,
    where_args: Tuple[Any, ...],
) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(str(Path(db_path)))
    try:
        node_map = _load_node_map(conn)
        edges = _edge_rows(conn, where_sql=where_sql, where_args=where_args)
        return _attach_nodes(edges, node_map)
    finally:
        conn.close()


def query_upstream(*, db_path: str | Path, node_id: str) -> Dict[str, Any]:
    node = str(node_id or "").strip()
    if not node:
        raise ValueError("node_id is required")
    edges = _query_edges(db_path=db_path, where_sql="dst_id = ?", where_args=(node,))
    return {
        "ok": True,
        "query": "upstream",
        "node_id": node,
        "count": len(edges),
        "edges": edges,
    }


def query_downstream(*, db_path: str | Path, node_id: str) -> Dict[str, Any]:
    node = str(node_id or "").strip()
    if not node:
        raise ValueError("node_id is required")
    edges = _query_edges(db_path=db_path, where_sql="src_id = ?", where_args=(node,))
    return {
        "ok": True,
        "query": "downstream",
        "node_id": node,
        "count": len(edges),
        "edges": edges,
    }


def query_writers(*, db_path: str | Path, artifact_id: str) -> Dict[str, Any]:
    artifact = str(artifact_id or "").strip()
    if not artifact:
        raise ValueError("artifact_id is required")
    edges = _query_edges(
        db_path=db_path,
        where_sql="dst_id = ? AND edge_type = ?",
        where_args=(artifact, "writes"),
    )
    return {
        "ok": True,
        "query": "writers",
        "artifact_id": artifact,
        "count": len(edges),
        "edges": edges,
    }


def query_filter_nodes(
    *,
    db_path: str | Path,
    tag: Optional[str] = None,
    not_tag: Optional[str] = None,
    node_type: Optional[str] = None,
) -> Dict[str, Any]:
    include_tag = (tag or "").strip()
    exclude_tag = (not_tag or "").strip()
    only_type = (node_type or "").strip()

    conn = sqlite3.connect(str(Path(db_path)))
    try:
        node_map = _load_node_map(conn)
    finally:
        conn.close()

    nodes: List[Dict[str, Any]] = []
    for node_id in sorted(node_map.keys()):
        node = node_map[node_id]
        tags = set(str(x) for x in node.get("tags") or [])
        if include_tag and include_tag not in tags:
            continue
        if exclude_tag and exclude_tag in tags:
            continue
        if only_type and str(node.get("type")) != only_type:
            continue
        nodes.append(node)

    return {
        "ok": True,
        "query": "filter",
        "filters": {
            "tag": include_tag or None,
            "not_tag": exclude_tag or None,
            "node_type": only_type or None,
        },
        "count": len(nodes),
        "nodes": nodes,
    }


def query_lineage(*, db_path: str | Path, node_id: str) -> Dict[str, Any]:
    node = str(node_id or "").strip()
    if not node:
        raise ValueError("node_id is required")

    upstream = _query_edges(db_path=db_path, where_sql="dst_id = ?", where_args=(node,))
    downstream = _query_edges(db_path=db_path, where_sql="src_id = ?", where_args=(node,))

    return {
        "ok": True,
        "query": "lineage",
        "node_id": node,
        "upstream_count": len(upstream),
        "downstream_count": len(downstream),
        "upstream": upstream,
        "downstream": downstream,
    }
