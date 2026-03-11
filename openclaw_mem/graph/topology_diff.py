from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_tags(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw_items: List[Any] = [raw]
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


def _load_topology_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        obj = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional yaml install
            raise ValueError(f"topology file {path} is not JSON and PyYAML is unavailable") from exc
        obj = yaml.safe_load(text)

    if not isinstance(obj, dict):
        raise ValueError("topology root must be an object")
    return obj


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

        node_id = str(raw.get("id") or "").strip()
        if not node_id:
            raise ValueError(f"topology.nodes[{idx}] missing non-empty id")
        if node_id in seen:
            raise ValueError(f"duplicate node id: {node_id}")
        seen.add(node_id)

        nodes.append(
            {
                "id": node_id,
                "type": str(raw.get("type") or "unknown").strip() or "unknown",
                "tags": _normalize_tags(raw.get("tags")),
                "metadata": _json_obj(raw.get("metadata") or raw.get("meta")),
            }
        )

    nodes.sort(
        key=lambda n: (
            n["id"],
            n["type"],
            _stable_json(n["tags"]),
            _stable_json(n["metadata"]),
        )
    )
    return nodes


def _normalize_edges(raw_edges: Any, *, node_ids: set[str]) -> List[Dict[str, Any]]:
    if raw_edges is None:
        return []
    if not isinstance(raw_edges, list):
        raise ValueError("topology.edges must be a list")

    edges: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str, str]] = set()
    for idx, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ValueError(f"topology.edges[{idx}] must be an object")

        src = str(raw.get("src") or raw.get("from") or raw.get("source") or "").strip()
        dst = str(raw.get("dst") or raw.get("to") or raw.get("target") or "").strip()
        edge_type = str(raw.get("type") or "unknown").strip() or "unknown"
        provenance = str(raw.get("provenance") or "").strip()

        if not src or not dst:
            raise ValueError(f"topology.edges[{idx}] requires src/dst")
        if src not in node_ids:
            raise ValueError(f"topology.edges[{idx}] unknown src node: {src}")
        if dst not in node_ids:
            raise ValueError(f"topology.edges[{idx}] unknown dst node: {dst}")

        key = (src, dst, edge_type, provenance)
        if key in seen:
            provenance_label = provenance or "<empty>"
            raise ValueError(
                "duplicate edge key: "
                f"src={src}, dst={dst}, type={edge_type}, provenance={provenance_label}"
            )
        seen.add(key)

        edges.append(
            {
                "src": src,
                "dst": dst,
                "type": edge_type,
                "provenance": provenance,
                "metadata": _json_obj(raw.get("metadata") or raw.get("meta")),
            }
        )

    edges.sort(
        key=lambda e: (
            e["src"],
            e["dst"],
            e["type"],
            e["provenance"],
            _stable_json(e["metadata"]),
        )
    )
    return edges


def _edge_key(edge: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(edge.get("src") or ""),
        str(edge.get("dst") or ""),
        str(edge.get("type") or ""),
    )


def _apply_limit(items: List[Dict[str, Any]], limit: int) -> Tuple[List[Dict[str, Any]], bool]:
    if limit < 0:
        limit = 0
    truncated = len(items) > limit
    if limit == 0:
        return [], truncated
    return items[:limit], truncated


def compare_topology_files(*, seed_path: str | Path, curated_path: str | Path, limit: int = 50) -> Dict[str, Any]:
    seed_file = Path(seed_path).resolve()
    curated_file = Path(curated_path).resolve()

    seed_obj = _load_topology_file(seed_file)
    curated_obj = _load_topology_file(curated_file)

    seed_nodes = _normalize_nodes(seed_obj.get("nodes"))
    curated_nodes = _normalize_nodes(curated_obj.get("nodes"))

    seed_nodes_by_id = {str(n["id"]): n for n in seed_nodes}
    curated_nodes_by_id = {str(n["id"]): n for n in curated_nodes}

    seed_ids = set(seed_nodes_by_id.keys())
    curated_ids = set(curated_nodes_by_id.keys())

    missing_nodes_full = [seed_nodes_by_id[node_id] for node_id in sorted(seed_ids - curated_ids)]
    stale_nodes_full = [curated_nodes_by_id[node_id] for node_id in sorted(curated_ids - seed_ids)]

    contract_mismatches_full: List[Dict[str, Any]] = []
    for node_id in sorted(seed_ids.intersection(curated_ids)):
        seed_node = seed_nodes_by_id[node_id]
        curated_node = curated_nodes_by_id[node_id]
        seed_contract = {
            "type": seed_node.get("type"),
            "tags": list(seed_node.get("tags") or []),
        }
        curated_contract = {
            "type": curated_node.get("type"),
            "tags": list(curated_node.get("tags") or []),
        }
        if seed_contract != curated_contract:
            contract_mismatches_full.append(
                {
                    "id": node_id,
                    "seed": seed_contract,
                    "curated": curated_contract,
                }
            )

    seed_edges = _normalize_edges(seed_obj.get("edges"), node_ids=seed_ids)
    curated_edges = _normalize_edges(curated_obj.get("edges"), node_ids=curated_ids)

    seed_edges_by_key = {_edge_key(edge): edge for edge in seed_edges}
    curated_edges_by_key = {_edge_key(edge): edge for edge in curated_edges}

    seed_edge_keys = set(seed_edges_by_key.keys())
    curated_edge_keys = set(curated_edges_by_key.keys())

    missing_edges_full = [seed_edges_by_key[key] for key in sorted(seed_edge_keys - curated_edge_keys)]
    stale_edges_full = [curated_edges_by_key[key] for key in sorted(curated_edge_keys - seed_edge_keys)]

    edge_contract_mismatches_full: List[Dict[str, Any]] = []
    for key in sorted(seed_edge_keys.intersection(curated_edge_keys)):
        seed_edge = seed_edges_by_key[key]
        curated_edge = curated_edges_by_key[key]
        seed_contract = {
            'provenance': str(seed_edge.get('provenance') or ''),
            'metadata': _json_obj(seed_edge.get('metadata')),
        }
        curated_contract = {
            'provenance': str(curated_edge.get('provenance') or ''),
            'metadata': _json_obj(curated_edge.get('metadata')),
        }
        if seed_contract != curated_contract:
            edge_contract_mismatches_full.append(
                {
                    'src': key[0],
                    'dst': key[1],
                    'type': key[2],
                    'seed': seed_contract,
                    'curated': curated_contract,
                }
            )

    bounded_missing_nodes, trunc_missing_nodes = _apply_limit(missing_nodes_full, limit)
    bounded_stale_nodes, trunc_stale_nodes = _apply_limit(stale_nodes_full, limit)
    bounded_contract_mismatches, trunc_contract_mismatches = _apply_limit(contract_mismatches_full, limit)
    bounded_missing_edges, trunc_missing_edges = _apply_limit(missing_edges_full, limit)
    bounded_stale_edges, trunc_stale_edges = _apply_limit(stale_edges_full, limit)
    bounded_edge_contract_mismatches, trunc_edge_contract_mismatches = _apply_limit(edge_contract_mismatches_full, limit)

    return {
        "ok": True,
        "seed": {
            "path": seed_file.as_posix(),
            "node_count": len(seed_nodes),
            "edge_count": len(seed_edges),
        },
        "curated": {
            "path": curated_file.as_posix(),
            "node_count": len(curated_nodes),
            "edge_count": len(curated_edges),
        },
        "diff": {
            "counts": {
                "missing_nodes": len(missing_nodes_full),
                "stale_nodes": len(stale_nodes_full),
                "node_contract_mismatches": len(contract_mismatches_full),
                "missing_edges": len(missing_edges_full),
                "stale_edges": len(stale_edges_full),
                "edge_contract_mismatches": len(edge_contract_mismatches_full),
            },
            "limit": max(0, int(limit)),
            "truncated": {
                "missing_nodes": trunc_missing_nodes,
                "stale_nodes": trunc_stale_nodes,
                "node_contract_mismatches": trunc_contract_mismatches,
                "missing_edges": trunc_missing_edges,
                "stale_edges": trunc_stale_edges,
                "edge_contract_mismatches": trunc_edge_contract_mismatches,
            },
            "missing_nodes": bounded_missing_nodes,
            "stale_nodes": bounded_stale_nodes,
            "node_contract_mismatches": bounded_contract_mismatches,
            "missing_edges": bounded_missing_edges,
            "stale_edges": bounded_stale_edges,
            "edge_contract_mismatches": bounded_edge_contract_mismatches,
        },
    }
