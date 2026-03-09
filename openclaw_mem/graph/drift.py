from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .schema import connect_graph_db_for_query


_NON_OK_STATUSES = {"stale", "error", "missing"}
_MAX_DRIFT_LIMIT = 200


def _normalize_status(raw: Any) -> str:
    token = str(raw or "").strip().lower()
    return token or "unknown"


def _parse_limit(raw: int, *, max_limit: int) -> int:
    limit_int = int(raw)
    if limit_int <= 0:
        raise ValueError("limit must be > 0")
    if limit_int > max_limit:
        raise ValueError(f"limit must be <= {max_limit}")
    return limit_int


def _bounded_ids(items: List[str], *, limit: int) -> Tuple[List[str], bool]:
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if len(items) <= limit:
        return items, False
    return items[:limit], True


def _load_runtime_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("nodes"), list):
            rows = payload.get("nodes") or []
        elif isinstance(payload.get("status_by_node"), dict):
            rows = [
                {"id": str(node_id), "status": status}
                for node_id, status in (payload.get("status_by_node") or {}).items()
            ]
        else:
            raise ValueError("runtime JSON object must include list key 'nodes' or object key 'status_by_node'")
    else:
        raise ValueError("runtime JSON root must be a list or object")

    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"runtime rows[{idx}] must be an object")
        node_id = str(row.get("id") or row.get("node_id") or row.get("node") or "").strip()
        if not node_id:
            raise ValueError(f"runtime rows[{idx}] missing id/node_id")
        status = _normalize_status(row.get("status"))
        out.append({"node_id": node_id, "status": status})

    return out


def _load_runtime_state(path: Path) -> Tuple[Dict[str, str], List[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid runtime JSON: {path}: {exc.msg}") from exc

    rows = _load_runtime_rows(payload)
    runtime_by_node: Dict[str, str] = {}
    duplicate_ids: List[str] = []
    for row in rows:
        node_id = row["node_id"]
        if node_id in runtime_by_node:
            duplicate_ids.append(node_id)
        runtime_by_node[node_id] = row["status"]
    return runtime_by_node, sorted(set(duplicate_ids))


def query_drift(*, db_path: str | Path, live_json_path: str | Path, limit: int = 50) -> Dict[str, Any]:
    limit_int = _parse_limit(limit, max_limit=_MAX_DRIFT_LIMIT)

    live_path = Path(str(live_json_path or "").strip())
    if not str(live_path):
        raise ValueError("live_json_path is required")
    if not live_path.is_file():
        raise ValueError(f"live runtime JSON not found: {live_path}")

    conn = connect_graph_db_for_query(db_path)
    try:
        rows = conn.execute("SELECT node_id FROM graph_nodes ORDER BY node_id").fetchall()
    finally:
        conn.close()

    topology_ids = sorted(str(row[0]) for row in rows)
    topology_set = set(topology_ids)

    runtime_by_node, duplicate_ids = _load_runtime_state(live_path)
    runtime_ids = sorted(runtime_by_node.keys())
    runtime_set = set(runtime_ids)

    missing = sorted(topology_set - runtime_set)
    runtime_only = sorted(runtime_set - topology_set)

    non_ok = sorted(
        node_id
        for node_id in sorted(topology_set & runtime_set)
        if runtime_by_node.get(node_id) in _NON_OK_STATUSES
    )

    missing_slice, missing_truncated = _bounded_ids(missing, limit=limit_int)
    runtime_only_slice, runtime_only_truncated = _bounded_ids(runtime_only, limit=limit_int)
    non_ok_slice, non_ok_truncated = _bounded_ids(non_ok, limit=limit_int)

    status_counts: Dict[str, int] = {}
    for node_id in runtime_ids:
        status = runtime_by_node.get(node_id, "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    non_ok_details = [
        {"node_id": node_id, "status": runtime_by_node.get(node_id, "unknown")}
        for node_id in non_ok_slice
    ]

    return {
        "ok": True,
        "query": "drift",
        "live_json_path": str(live_path),
        "topology_node_count": len(topology_ids),
        "runtime_node_count": len(runtime_ids),
        "status_counts": dict(sorted(status_counts.items())),
        "missing_in_runtime": {
            "count": len(missing),
            "node_ids": missing_slice,
            "truncated": missing_truncated,
        },
        "runtime_only": {
            "count": len(runtime_only),
            "node_ids": runtime_only_slice,
            "truncated": runtime_only_truncated,
        },
        "non_ok_nodes": {
            "count": len(non_ok),
            "items": non_ok_details,
            "truncated": non_ok_truncated,
            "statuses": sorted(_NON_OK_STATUSES),
        },
        "duplicate_runtime_ids": {
            "count": len(duplicate_ids),
            "node_ids": duplicate_ids,
        },
    }
