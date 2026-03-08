from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .schema import ensure_graph_schema


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_tags(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw_items: Iterable[Any] = [raw]
    elif isinstance(raw, list):
        raw_items = raw
    else:
        raw_items = [raw]
    out: List[str] = []
    for item in raw_items:
        token = str(item).strip()
        if token:
            out.append(token)
    return sorted(set(out))


def _json_obj(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def _normalize_nodes(raw_nodes: Any) -> List[Dict[str, Any]]:
    if raw_nodes is None:
        return []
    if not isinstance(raw_nodes, list):
        raise ValueError("topology.nodes must be a list")

    nodes: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise ValueError(f"topology.nodes[{idx}] must be an object")
        node_id = str(raw.get("id", "")).strip()
        if not node_id:
            raise ValueError(f"topology.nodes[{idx}] missing non-empty id")
        if node_id in seen:
            raise ValueError(f"duplicate node id: {node_id}")
        seen.add(node_id)
        node_type = str(raw.get("type") or "unknown").strip() or "unknown"
        tags = _normalize_tags(raw.get("tags"))
        metadata = _json_obj(raw.get("metadata") or raw.get("meta"))
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "tags": tags,
                "metadata": metadata,
            }
        )

    nodes.sort(
        key=lambda n: (
            n["id"],
            n["type"],
            json.dumps(n["tags"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            json.dumps(n["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    )
    return nodes


def _normalize_edges(raw_edges: Any, node_ids: set[str]) -> List[Dict[str, Any]]:
    if raw_edges is None:
        return []
    if not isinstance(raw_edges, list):
        raise ValueError("topology.edges must be a list")

    edges: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ValueError(f"topology.edges[{idx}] must be an object")

        src = str(raw.get("src") or raw.get("from") or raw.get("source") or "").strip()
        dst = str(raw.get("dst") or raw.get("to") or raw.get("target") or "").strip()
        edge_type = str(raw.get("type") or "unknown").strip() or "unknown"
        provenance = str(raw.get("provenance") or "").strip()
        metadata = _json_obj(raw.get("metadata") or raw.get("meta"))

        if not src or not dst:
            raise ValueError(f"topology.edges[{idx}] requires src/dst")
        if src not in node_ids:
            raise ValueError(f"topology.edges[{idx}] unknown src node: {src}")
        if dst not in node_ids:
            raise ValueError(f"topology.edges[{idx}] unknown dst node: {dst}")

        edges.append(
            {
                "src": src,
                "dst": dst,
                "type": edge_type,
                "provenance": provenance,
                "metadata": metadata,
            }
        )

    edges.sort(
        key=lambda e: (
            e["src"],
            e["dst"],
            e["type"],
            e["provenance"],
            json.dumps(e["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    )
    return edges


def _canonical_digest(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    payload = {"nodes": nodes, "edges": edges}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _load_topology_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".json":
        obj = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - exercised only when yaml missing
            raise ValueError(
                f"topology file {path} is not JSON and PyYAML is unavailable"
            ) from exc
        obj = yaml.safe_load(text)

    if not isinstance(obj, dict):
        raise ValueError("topology root must be an object")
    return obj


def _upsert_meta(conn: sqlite3.Connection, items: Dict[str, str]) -> None:
    for key, value in items.items():
        conn.execute(
            "INSERT INTO graph_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def refresh_topology(topology: Dict[str, Any], *, db_path: str | Path, source_path: str | None = None) -> Dict[str, Any]:
    if not isinstance(topology, dict):
        raise ValueError("topology must be an object")

    nodes = _normalize_nodes(topology.get("nodes"))
    node_ids = {n["id"] for n in nodes}
    edges = _normalize_edges(topology.get("edges"), node_ids)
    digest = _canonical_digest(nodes, edges)
    refreshed_at = _utc_now_iso()

    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db))
    try:
        ensure_graph_schema(conn)
        with conn:
            conn.execute("DELETE FROM graph_edges")
            conn.execute("DELETE FROM graph_nodes")

            conn.executemany(
                "INSERT INTO graph_nodes(node_id, node_type, tags_json, metadata_json) VALUES(?, ?, ?, ?)",
                [
                    (
                        node["id"],
                        node["type"],
                        json.dumps(node["tags"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        json.dumps(node["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    )
                    for node in nodes
                ],
            )
            conn.executemany(
                "INSERT INTO graph_edges(src_id, dst_id, edge_type, provenance, metadata_json) VALUES(?, ?, ?, ?, ?)",
                [
                    (
                        edge["src"],
                        edge["dst"],
                        edge["type"],
                        edge["provenance"],
                        json.dumps(edge["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    )
                    for edge in edges
                ],
            )
            _upsert_meta(
                conn,
                {
                    "last_refresh_ts": refreshed_at,
                    "last_source_path": source_path or "",
                    "topology_digest": digest,
                    "node_count": str(len(nodes)),
                    "edge_count": str(len(edges)),
                },
            )
    finally:
        conn.close()

    return {
        "ok": True,
        "db_path": str(db),
        "source_path": source_path,
        "refreshed_at": refreshed_at,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "topology_digest": digest,
    }


def refresh_topology_file(*, topology_path: str | Path, db_path: str | Path) -> Dict[str, Any]:
    path = Path(topology_path)
    topology = _load_topology_file(path)
    return refresh_topology(topology, db_path=db_path, source_path=str(path))
