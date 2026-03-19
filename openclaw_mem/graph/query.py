from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openclaw_mem.provenance_trust_schema import parse_provenance_ref

from .refresh import _load_topology_file, _normalize_edges, _normalize_nodes
from .schema import connect_graph_db_for_query


_MAX_RECEIPTS_LIMIT = 200
_MAX_LINEAGE_DEPTH = 8


def _parse_provenance_ref(raw: Any) -> Dict[str, Any]:
    return parse_provenance_ref(raw)


def _edge_provenance_ref(edge: Dict[str, Any]) -> Dict[str, Any]:
    raw = edge.get("provenance_ref")
    if isinstance(raw, dict):
        return _parse_provenance_ref(raw.get("raw"))
    return _parse_provenance_ref(edge.get("provenance"))


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


def _normalize_token_list(raw: Any) -> List[str]:
    """Normalize optional CLI-ish inputs into a stable de-duped list of non-empty strings.

    Accepts: None, str (comma-separated allowed), list/tuple/set of items.
    """
    if raw is None:
        return []
    tokens: List[str] = []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
        tokens = [p for p in parts if p]
    elif isinstance(raw, (list, tuple, set)):
        for item in raw:
            if item is None:
                continue
            if isinstance(item, str):
                parts = [p.strip() for p in item.split(",")]
                tokens.extend([p for p in parts if p])
            else:
                token = str(item).strip()
                if token:
                    tokens.append(token)
    else:
        token = str(raw).strip()
        if token:
            tokens.append(token)
    return sorted(set(tokens))

def _parse_limit(raw: int, *, max_limit: int) -> int:
    limit_int = int(raw)
    if limit_int <= 0:
        raise ValueError("limit must be > 0")
    if limit_int > max_limit:
        raise ValueError(f"limit must be <= {max_limit}")
    return limit_int


def _sql_like_prefix(token: str) -> str:
    """Escape a literal token for SQL LIKE prefix matching (ESCAPE '\\')."""
    return (
        token.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        + "%"
    )


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
        provenance = str(row[3])
        out.append(
            {
                "src": str(row[0]),
                "dst": str(row[1]),
                "type": str(row[2]),
                "provenance": provenance,
                "provenance_ref": _parse_provenance_ref(provenance),
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
    conn = connect_graph_db_for_query(db_path)
    try:
        node_map = _load_node_map(conn)
        edges = _edge_rows(conn, where_sql=where_sql, where_args=where_args)
        return _attach_nodes(edges, node_map)
    finally:
        conn.close()


def _load_topology_snapshot(topology_path: str | Path) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    path = Path(topology_path)
    topology = _load_topology_file(path)
    nodes = _normalize_nodes(topology.get("nodes"))
    node_map = {node["id"]: node for node in nodes}
    edges = _normalize_edges(topology.get("edges"), set(node_map.keys()))
    attached = _attach_nodes(
        [
            {
                "src": edge["src"],
                "dst": edge["dst"],
                "type": edge["type"],
                "provenance": edge["provenance"],
                "provenance_ref": _parse_provenance_ref(edge["provenance"]),
                "metadata": dict(edge.get("metadata") or {}),
            }
            for edge in edges
        ],
        node_map,
    )
    return node_map, attached


def query_upstream_topology(*, topology_path: str | Path, node_id: str) -> Dict[str, Any]:
    node = str(node_id or "").strip()
    if not node:
        raise ValueError("node_id is required")
    _, edges = _load_topology_snapshot(topology_path)
    matched = [edge for edge in edges if edge["dst"] == node]
    return {
        "ok": True,
        "query": "upstream",
        "node_id": node,
        "count": len(matched),
        "edges": matched,
    }


def query_downstream_topology(*, topology_path: str | Path, node_id: str) -> Dict[str, Any]:
    node = str(node_id or "").strip()
    if not node:
        raise ValueError("node_id is required")
    _, edges = _load_topology_snapshot(topology_path)
    matched = [edge for edge in edges if edge["src"] == node]
    return {
        "ok": True,
        "query": "downstream",
        "node_id": node,
        "count": len(matched),
        "edges": matched,
    }


def query_writers_topology(*, topology_path: str | Path, artifact_id: str) -> Dict[str, Any]:
    artifact = str(artifact_id or "").strip()
    if not artifact:
        raise ValueError("artifact_id is required")
    _, edges = _load_topology_snapshot(topology_path)
    matched = [edge for edge in edges if edge["dst"] == artifact and edge["type"] == "writes"]
    return {
        "ok": True,
        "query": "writers",
        "artifact_id": artifact,
        "count": len(matched),
        "edges": matched,
    }


def query_filter_nodes_topology(
    *,
    topology_path: str | Path,
    tag: Optional[str] = None,
    not_tag: Optional[str] = None,
    node_type: Optional[str] = None,
) -> Dict[str, Any]:
    include_tag = (tag or "").strip()
    exclude_tag = (not_tag or "").strip()
    only_type = (node_type or "").strip()

    node_map, _ = _load_topology_snapshot(topology_path)

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

    conn = connect_graph_db_for_query(db_path)
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


def _edge_identity(edge: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(edge.get("src") or ""),
        str(edge.get("dst") or ""),
        str(edge.get("type") or ""),
        str(edge.get("provenance") or ""),
    )


def _lineage_traverse(
    *,
    start_node: str,
    adjacency: Dict[str, List[Dict[str, Any]]],
    node_map: Dict[str, Dict[str, Any]],
    max_depth: int,
    next_node_field: str,
) -> List[Dict[str, Any]]:
    frontier = {start_node}
    visited_nodes = {start_node}
    seen_edges: set[Tuple[str, str, str, str]] = set()
    out: List[Dict[str, Any]] = []

    for depth in range(1, max_depth + 1):
        if not frontier:
            break

        next_frontier: set[str] = set()
        for current in sorted(frontier):
            candidates = adjacency.get(current) or []
            for edge in candidates:
                identity = _edge_identity(edge)
                if identity in seen_edges:
                    continue
                seen_edges.add(identity)

                item = dict(edge)
                item["depth"] = depth
                item["src_node"] = node_map.get(str(edge.get("src") or ""))
                item["dst_node"] = node_map.get(str(edge.get("dst") or ""))
                out.append(item)

                next_node = str(edge.get(next_node_field) or "")
                if next_node and next_node not in visited_nodes:
                    next_frontier.add(next_node)

        visited_nodes.update(next_frontier)
        frontier = next_frontier

    out.sort(
        key=lambda edge: (
            int(edge.get("depth", 0)),
            str(edge.get("src") or ""),
            str(edge.get("dst") or ""),
            str(edge.get("type") or ""),
            str(edge.get("provenance") or ""),
        )
    )
    return out


def query_lineage(*, db_path: str | Path, node_id: str, max_depth: int = 1) -> Dict[str, Any]:
    node = str(node_id or "").strip()
    if not node:
        raise ValueError("node_id is required")

    depth_int = _parse_limit(max_depth, max_limit=_MAX_LINEAGE_DEPTH)

    conn = connect_graph_db_for_query(db_path)
    try:
        node_map = _load_node_map(conn)
        all_edges = _edge_rows(conn, where_sql="1 = 1", where_args=())
    finally:
        conn.close()

    upstream_by_dst: Dict[str, List[Dict[str, Any]]] = {}
    downstream_by_src: Dict[str, List[Dict[str, Any]]] = {}
    for edge in all_edges:
        src = str(edge.get("src") or "")
        dst = str(edge.get("dst") or "")
        upstream_by_dst.setdefault(dst, []).append(edge)
        downstream_by_src.setdefault(src, []).append(edge)

    for mapping in (upstream_by_dst, downstream_by_src):
        for key in list(mapping.keys()):
            mapping[key].sort(key=_edge_identity)

    upstream = _lineage_traverse(
        start_node=node,
        adjacency=upstream_by_dst,
        node_map=node_map,
        max_depth=depth_int,
        next_node_field="src",
    )
    downstream = _lineage_traverse(
        start_node=node,
        adjacency=downstream_by_src,
        node_map=node_map,
        max_depth=depth_int,
        next_node_field="dst",
    )

    return {
        "ok": True,
        "query": "lineage",
        "node_id": node,
        "max_depth": depth_int,
        "upstream_count": len(upstream),
        "downstream_count": len(downstream),
        "upstream": upstream,
        "downstream": downstream,
    }


def query_provenance(
    *,
    db_path: str | Path,
    node_id: Optional[str] = None,
    edge_type: Optional[str] = None,
    source_path: Optional[str] = None,
    source_path_prefix: Optional[str] = None,
    limit: int = 20,
    min_edge_count: int = 1,
    group_by_source: bool = False,
) -> Dict[str, Any]:
    limit_int = _parse_limit(limit, max_limit=_MAX_RECEIPTS_LIMIT)
    min_edges = int(min_edge_count)
    if min_edges <= 0:
        raise ValueError("min_edge_count must be > 0")

    node = (node_id or "").strip()
    edge_kind = (edge_type or "").strip()
    source = (source_path or "").strip()
    source_prefix = (source_path_prefix or "").strip()

    source_expr = (
        "TRIM(CASE "
        "WHEN INSTR(TRIM(provenance), '#') > 0 "
        "THEN SUBSTR(TRIM(provenance), 1, INSTR(TRIM(provenance), '#') - 1) "
        "ELSE TRIM(provenance) "
        "END)"
    )

    group_expr = "TRIM(provenance)"
    if group_by_source:
        group_expr = source_expr

    where_parts = [f"{group_expr} != ''"]
    where_args: List[Any] = []
    if node:
        where_parts.append("(src_id = ? OR dst_id = ?)")
        where_args.extend([node, node])
    if edge_kind:
        where_parts.append("edge_type = ?")
        where_args.append(edge_kind)
    if source:
        where_parts.append(f"{source_expr} = ?")
        where_args.append(source)
    if source_prefix:
        where_parts.append(f"{source_expr} LIKE ? ESCAPE '\\'")
        where_args.append(_sql_like_prefix(source_prefix))

    where_sql = " AND ".join(where_parts)
    where_args_tuple = tuple(where_args)

    conn = connect_graph_db_for_query(db_path)
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM ("
            f"SELECT {group_expr} AS provenance_group FROM graph_edges WHERE {where_sql} "
            "GROUP BY provenance_group HAVING COUNT(*) >= ?"
            ")",
            where_args_tuple + (min_edges,),
        ).fetchone()

        rows = conn.execute(
            f"SELECT {group_expr} AS provenance_group, COUNT(*) AS edge_count FROM graph_edges WHERE {where_sql} "
            "GROUP BY provenance_group HAVING COUNT(*) >= ? "
            "ORDER BY edge_count DESC, provenance_group ASC LIMIT ?",
            where_args_tuple + (min_edges, limit_int),
        ).fetchall()

        selected_groups = [str(row[0]) for row in rows]
        detail_rows: List[Tuple[Any, Any, Any]] = []
        if selected_groups:
            placeholders = ", ".join(["?"] * len(selected_groups))
            detail_rows = conn.execute(
                f"SELECT {group_expr} AS provenance_group, edge_type, COUNT(*) AS edge_count "
                f"FROM graph_edges WHERE {where_sql} "
                f"AND {group_expr} IN ({placeholders}) "
                "GROUP BY provenance_group, edge_type "
                "ORDER BY provenance_group ASC, edge_count DESC, edge_type ASC",
                where_args_tuple + tuple(selected_groups),
            ).fetchall()
    finally:
        conn.close()

    edge_types_by_group: Dict[str, List[Dict[str, Any]]] = {}
    for row in detail_rows:
        group_key = str(row[0])
        edge_types_by_group.setdefault(group_key, []).append(
            {
                "edge_type": str(row[1]),
                "edge_count": int(row[2]),
            }
        )

    items: List[Dict[str, Any]] = []
    kind_counts: Dict[str, int] = {}
    structured_edge_count = 0
    covered_edge_count = 0

    for row in rows:
        group_key = str(row[0])
        edge_count = int(row[1])
        provenance_ref = _parse_provenance_ref(group_key)
        kind = str(provenance_ref.get("kind") or "none")
        kind_counts[kind] = int(kind_counts.get(kind, 0)) + edge_count
        if bool(provenance_ref.get("is_structured")):
            structured_edge_count += edge_count
        covered_edge_count += edge_count

        item: Dict[str, Any] = {
            "provenance": group_key,
            "provenance_ref": provenance_ref,
            "edge_count": edge_count,
            "edge_types": edge_types_by_group.get(group_key, []),
        }
        if group_by_source:
            item["source_path"] = group_key
        items.append(item)

    total_distinct = int(total_row[0]) if total_row and total_row[0] is not None else 0

    return {
        "ok": True,
        "query": "provenance",
        "filters": {
            "node_id": node or None,
            "edge_type": edge_kind or None,
            "source_path": source or None,
            "source_path_prefix": source_prefix or None,
            "min_edge_count": min_edges,
            "group_by_source": bool(group_by_source),
        },
        "count": len(items),
        "total_distinct": total_distinct,
        "provenance_quality": {
            "edge_count": covered_edge_count,
            "structured_edge_count": structured_edge_count,
            "kind_counts": {k: int(kind_counts[k]) for k in sorted(kind_counts.keys())},
        },
        "items": items,
    }


def query_refresh_receipts(
    *,
    db_path: str | Path,
    limit: int = 10,
    source_path: Optional[str] = None,
    topology_digest: Optional[str] = None,
) -> Dict[str, Any]:
    limit_int = _parse_limit(limit, max_limit=_MAX_RECEIPTS_LIMIT)
    source = (source_path or "").strip()
    digest = (topology_digest or "").strip()

    where_parts: List[str] = []
    where_args: List[Any] = []
    if source:
        where_parts.append("source_path = ?")
        where_args.append(source)
    if digest:
        where_parts.append("topology_digest = ?")
        where_args.append(digest)

    where_sql = ""
    if where_parts:
        where_sql = " WHERE " + " AND ".join(where_parts)

    conn = connect_graph_db_for_query(db_path)
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM graph_refresh_receipts" + where_sql,
            tuple(where_args),
        ).fetchone()
        rows = conn.execute(
            "SELECT id, refreshed_at, source_path, topology_digest, node_count, edge_count "
            "FROM graph_refresh_receipts"
            + where_sql
            + " ORDER BY id DESC LIMIT ?",
            tuple(where_args) + (limit_int,),
        ).fetchall()
    finally:
        conn.close()

    receipts: List[Dict[str, Any]] = []
    for row in rows:
        receipts.append(
            {
                "id": int(row[0]),
                "refreshed_at": str(row[1]),
                "source_path": str(row[2]),
                "topology_digest": str(row[3]),
                "node_count": int(row[4]),
                "edge_count": int(row[5]),
            }
        )

    total_count = int(total_row[0]) if total_row and total_row[0] is not None else 0

    return {
        "ok": True,
        "query": "receipts",
        "filters": {
            "source_path": source or None,
            "topology_digest": digest or None,
        },
        "count": len(receipts),
        "total_count": total_count,
        "receipts": receipts,
    }


_MAX_SUBGRAPH_HOPS = 6
_MAX_SUBGRAPH_NODES_LIMIT = 500
_MAX_SUBGRAPH_EDGES_LIMIT = 1000


def _latest_refresh_receipt(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT id, refreshed_at, source_path, topology_digest, node_count, edge_count "
        "FROM graph_refresh_receipts ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "refreshed_at": str(row[1]),
        "source_path": str(row[2]),
        "topology_digest": str(row[3]),
        "node_count": int(row[4]),
        "edge_count": int(row[5]),
    }


def _summarize_provenance_for_edges(edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_prov: Dict[str, Dict[str, Any]] = {}
    kind_counts: Dict[str, int] = {}
    with_provenance = 0
    structured_edge_count = 0

    for edge in edges:
        prov = str(edge.get("provenance") or "").strip()
        if not prov:
            continue

        with_provenance += 1
        provenance_ref = _edge_provenance_ref(edge)
        kind = str(provenance_ref.get("kind") or "none")
        kind_counts[kind] = int(kind_counts.get(kind, 0)) + 1
        if bool(provenance_ref.get("is_structured")):
            structured_edge_count += 1

        entry = by_prov.setdefault(
            prov,
            {
                "provenance": prov,
                "provenance_ref": provenance_ref,
                "edge_count": 0,
                "edge_types": {},
            },
        )
        entry["edge_count"] += 1
        edge_type = str(edge.get("type") or "").strip() or "unknown"
        edge_types: Dict[str, int] = entry["edge_types"]
        edge_types[edge_type] = int(edge_types.get(edge_type, 0)) + 1

    items: List[Dict[str, Any]] = []
    for prov in sorted(by_prov.keys()):
        entry = by_prov[prov]
        edge_types = entry.get("edge_types") or {}
        edge_types_list = [
            {"edge_type": k, "edge_count": int(v)}
            for k, v in sorted(edge_types.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
        ]
        items.append(
            {
                "provenance": prov,
                "provenance_ref": dict(entry.get("provenance_ref") or {}),
                "edge_count": int(entry.get("edge_count", 0)),
                "edge_types": edge_types_list,
            }
        )

    items.sort(key=lambda item: (-int(item.get("edge_count", 0)), str(item.get("provenance"))))
    missing_provenance = max(0, len(edges) - with_provenance)

    return {
        "count": len(items),
        "items": items,
        "coverage": {
            "edge_count": len(edges),
            "with_provenance": with_provenance,
            "missing_provenance": missing_provenance,
            "structured_edge_count": structured_edge_count,
        },
        "kind_counts": {k: int(kind_counts[k]) for k in sorted(kind_counts.keys())},
    }


def _edge_rows_for_frontier(
    conn: sqlite3.Connection,
    *,
    frontier: List[str],
    direction: str,
) -> List[Dict[str, Any]]:
    if not frontier:
        return []

    ids = [str(x).strip() for x in frontier if str(x).strip()]
    ids = sorted(set(ids))
    placeholders = ", ".join(["?"] * len(ids))

    if direction == "upstream":
        where_sql = f"dst_id IN ({placeholders})"
        where_args: Tuple[Any, ...] = tuple(ids)
    elif direction == "downstream":
        where_sql = f"src_id IN ({placeholders})"
        where_args = tuple(ids)
    elif direction == "both":
        where_sql = f"(src_id IN ({placeholders}) OR dst_id IN ({placeholders}))"
        where_args = tuple(ids) + tuple(ids)
    else:
        raise ValueError("direction must be one of: upstream, downstream, both")

    return _edge_rows(conn, where_sql=where_sql, where_args=where_args)


def _render_subgraph_bundle_text(
    *,
    center: str,
    hops: int,
    direction: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    edge_types: Optional[List[str]] = None,
    include_node_types: Optional[List[str]] = None,
    require_structured_provenance: bool = False,
) -> str:
    lines: List[str] = []
    edge_types_norm = sorted(set(edge_types or []))
    node_types_norm = sorted(set(include_node_types or []))
    filters: List[str] = []
    if edge_types_norm:
        filters.append("edge_types=" + ",".join(edge_types_norm))
    if node_types_norm:
        filters.append("include_node_types=" + ",".join(node_types_norm))
    if require_structured_provenance:
        filters.append("require_structured_provenance=true")
    filters_suffix = (" " + " ".join(filters)) if filters else ""

    lines.append(
        "# Topology (bounded subgraph)\n"
        f"center={center} hops={hops} direction={direction} nodes={len(nodes)} edges={len(edges)}{filters_suffix}\n"
    )
    if nodes:
        lines.append("## Nodes")
        for node in nodes:
            tags = ",".join(node.get("tags") or [])
            tag_suffix = f" tags={tags}" if tags else ""
            lines.append(f"- {node.get('id')} type={node.get('type')}{tag_suffix}")
        lines.append("")

    lines.append("## Edges (with provenance)")
    for edge in edges:
        prov = str(edge.get("provenance") or "").strip()
        prov_suffix = f"  [{prov}]" if prov else ""
        lines.append(
            f"- {edge.get('src')} --{edge.get('type')}--> {edge.get('dst')}{prov_suffix}"
        )

    return "\n".join(lines).rstrip() + "\n"


def query_subgraph(
    *,
    db_path: str | Path,
    node_id: str,
    hops: int = 2,
    direction: str = "both",
    max_nodes: int = 40,
    max_edges: int = 80,
    edge_types: Optional[List[str]] = None,
    include_node_types: Optional[List[str]] = None,
    require_structured_provenance: bool = False,
) -> Dict[str, Any]:
    center = str(node_id or "").strip()
    if not center:
        raise ValueError("node_id is required")

    hops_int = int(hops)
    if hops_int < 0:
        raise ValueError("hops must be >= 0")
    if hops_int > _MAX_SUBGRAPH_HOPS:
        raise ValueError(f"hops must be <= {_MAX_SUBGRAPH_HOPS}")

    direction_norm = str(direction or "").strip().lower() or "both"
    if direction_norm not in {"upstream", "downstream", "both"}:
        raise ValueError("direction must be one of: upstream, downstream, both")

    max_nodes_int = int(max_nodes)
    max_edges_int = int(max_edges)
    if max_nodes_int <= 0 or max_edges_int <= 0:
        raise ValueError("max_nodes/max_edges must be > 0")
    if max_nodes_int > _MAX_SUBGRAPH_NODES_LIMIT:
        raise ValueError(f"max_nodes must be <= {_MAX_SUBGRAPH_NODES_LIMIT}")
    if max_edges_int > _MAX_SUBGRAPH_EDGES_LIMIT:
        raise ValueError(f"max_edges must be <= {_MAX_SUBGRAPH_EDGES_LIMIT}")

    edge_type_allow = set(_normalize_token_list(edge_types))
    include_type_allow = set(_normalize_token_list(include_node_types))
    require_structured_provenance_bool = bool(require_structured_provenance)

    conn = connect_graph_db_for_query(db_path)
    try:
        node_map = _load_node_map(conn)
        if center not in node_map:
            raise ValueError(f"unknown node_id: {center}")

        refresh_receipt = _latest_refresh_receipt(conn)

        seen_nodes: set[str] = {center}
        frontier: set[str] = {center}
        seen_edges: set[Tuple[str, str, str, str]] = set()
        selected_edges: List[Dict[str, Any]] = []
        skipped_unstructured_provenance = 0
        stopped_reason: Optional[str] = None

        for _depth in range(hops_int):
            if not frontier:
                break

            batch_edges = _edge_rows_for_frontier(
                conn,
                frontier=sorted(frontier),
                direction=direction_norm,
            )

            next_frontier: set[str] = set()
            for edge in batch_edges:
                if edge_type_allow and str(edge.get("type") or "") not in edge_type_allow:
                    continue

                if include_type_allow:
                    src_id = str(edge.get("src") or "")
                    dst_id = str(edge.get("dst") or "")
                    src_type = str((node_map.get(src_id) or {}).get("type") or "")
                    dst_type = str((node_map.get(dst_id) or {}).get("type") or "")
                    if src_id != center and src_type not in include_type_allow:
                        continue
                    if dst_id != center and dst_type not in include_type_allow:
                        continue

                provenance_ref = _edge_provenance_ref(edge)
                if require_structured_provenance_bool and not bool(provenance_ref.get("is_structured")):
                    skipped_unstructured_provenance += 1
                    continue

                key = (edge["src"], edge["dst"], edge["type"], edge["provenance"])
                if key in seen_edges:
                    continue

                candidate_nodes = {str(edge["src"]), str(edge["dst"])}
                projected_nodes = seen_nodes | next_frontier | candidate_nodes
                if len(projected_nodes) > max_nodes_int:
                    stopped_reason = "max_nodes"
                    break

                seen_edges.add(key)
                selected_edges.append(edge)
                next_frontier.update(candidate_nodes)

                if len(selected_edges) >= max_edges_int:
                    stopped_reason = "max_edges"
                    break

            next_frontier = next_frontier - seen_nodes
            if next_frontier:
                seen_nodes.update(next_frontier)

            if stopped_reason:
                break

            frontier = next_frontier if next_frontier else set()

        node_ids = sorted(seen_nodes)
        nodes = [node_map[nid] for nid in node_ids if nid in node_map]
        selected_edges.sort(key=lambda e: (e["src"], e["dst"], e["type"], e["provenance"]))
        edges_with_nodes = _attach_nodes(selected_edges, node_map)

        provenance_summary = _summarize_provenance_for_edges(selected_edges)
        bundle_text = _render_subgraph_bundle_text(
            center=center,
            hops=hops_int,
            direction=direction_norm,
            nodes=nodes,
            edges=selected_edges,
            edge_types=sorted(edge_type_allow),
            include_node_types=sorted(include_type_allow),
            require_structured_provenance=require_structured_provenance_bool,
        )

        return {
            "ok": True,
            "query": "subgraph",
            "center_node_id": center,
            "hops": hops_int,
            "direction": direction_norm,
            "bounds": {
                "max_nodes": max_nodes_int,
                "max_edges": max_edges_int,
            },
            "filters": {
                "edge_types": sorted(edge_type_allow) or None,
                "include_node_types": sorted(include_type_allow) or None,
                "require_structured_provenance": require_structured_provenance_bool,
            },
            "node_count": len(nodes),
            "edge_count": len(edges_with_nodes),
            "skipped_unstructured_provenance": skipped_unstructured_provenance,
            "stopped_reason": stopped_reason,
            "refresh_receipt": refresh_receipt,
            "provenance": provenance_summary,
            "nodes": nodes,
            "edges": edges_with_nodes,
            "bundle_text": bundle_text,
        }
    finally:
        conn.close()
