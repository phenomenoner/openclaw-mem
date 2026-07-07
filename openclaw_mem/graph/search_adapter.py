from __future__ import annotations

"""Deterministic opt-in graph assistance for ``openclaw-mem search``.

Ranking is intentionally small and explainable:
- lexical/store results remain authoritative and keep their existing order;
- graph candidates are read-only hints loaded from a derived portable graph;
- graph hits are sorted by score desc, then source path, then node id;
- missing, malformed, stale, or readiness-blocked graph input fails open.

The adapter never writes to Store/Observe/graph files. It only returns candidate
hits and machine-readable fallback reasons for the CLI to surface.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

HYBRID_SEARCH_KIND = "openclaw-mem.search.hybrid.v0"


def _tokens(query: str) -> List[str]:
    raw = re.findall(r"[\w\u3400-\u9fff]+", query.lower(), flags=re.UNICODE)
    out: List[str] = []
    seen: set[str] = set()
    for token in raw:
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _load_json_object(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("json_root_not_object")
    return obj


def _readiness_fallback(readiness_state_path: Optional[str | Path]) -> Optional[str]:
    if not readiness_state_path:
        return None
    path = Path(readiness_state_path)
    if not path.is_file():
        return "readiness_state_missing"
    try:
        state = _load_json_object(path)
    except Exception:
        return "readiness_state_malformed"
    status = str(state.get("status") or state.get("readiness") or state.get("state") or "").strip().lower()
    ready = state.get("ready")
    if status in {"green", "ready", "ok"} or ready is True:
        return None
    return status or "readiness_not_green"


def _parse_freshness(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw or raw == "snapshot":
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_stale(meta: Dict[str, Any], *, stale_after_days: int, now: Optional[datetime] = None) -> bool:
    dt = _parse_freshness(meta.get("freshness"))
    if dt is None:
        return False
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dt < current - timedelta(days=max(0, int(stale_after_days)))


def _required_provenance(meta: Dict[str, Any]) -> bool:
    return bool(str(meta.get("source_path") or "").strip()) and bool(str(meta.get("receipt_id") or "").strip())


def _node_text(node: Dict[str, Any]) -> str:
    meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    parts = [
        node.get("id"),
        node.get("type"),
        " ".join(str(x) for x in (node.get("tags") or [])),
        meta.get("source_path"),
        meta.get("path"),
        meta.get("name"),
        meta.get("qualname"),
        meta.get("kind"),
        meta.get("language"),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def _edge_bonus(node_id: str, edges: Iterable[Dict[str, Any]], tokens: List[str]) -> float:
    bonus = 0.0
    for edge in edges:
        if node_id not in {str(edge.get("src") or ""), str(edge.get("dst") or "")}:
            continue
        edge_text = " ".join(
            [
                str(edge.get("src") or ""),
                str(edge.get("dst") or ""),
                str(edge.get("type") or ""),
                str(edge.get("provenance") or ""),
                json.dumps(edge.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
            ]
        ).lower()
        if any(token in edge_text for token in tokens):
            bonus += 0.25
    return min(bonus, 1.0)


def graph_search_candidates(
    *,
    query: str,
    graph_path: str | Path,
    limit: int = 20,
    stale_after_days: int = 30,
    readiness_state_path: Optional[str | Path] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    tokens = _tokens(query)
    if not tokens:
        return {"ok": True, "candidates": [], "fallback_reason": "empty_graph_query"}

    readiness_reason = _readiness_fallback(readiness_state_path)
    if readiness_reason:
        return {"ok": True, "candidates": [], "fallback_reason": readiness_reason}

    path = Path(graph_path)
    if not path.is_file():
        return {"ok": True, "candidates": [], "fallback_reason": "graph_file_not_found"}

    try:
        graph = _load_json_object(path)
    except Exception:
        return {"ok": True, "candidates": [], "fallback_reason": "graph_file_malformed"}

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"ok": True, "candidates": [], "fallback_reason": "graph_schema_invalid"}

    candidates: List[Dict[str, Any]] = []
    dropped: Dict[str, int] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        if not _required_provenance(meta):
            dropped["missing_provenance"] = dropped.get("missing_provenance", 0) + 1
            continue
        if _is_stale(meta, stale_after_days=stale_after_days, now=now):
            dropped["stale"] = dropped.get("stale", 0) + 1
            continue
        text = _node_text(node)
        matched = [token for token in tokens if token in text]
        if not matched:
            continue
        score = float(len(matched)) + _edge_bonus(str(node.get("id") or ""), edges, tokens)
        candidates.append(
            {
                "lane": "graph",
                "node_id": str(node.get("id") or ""),
                "node_type": str(node.get("type") or ""),
                "source_path": str(meta.get("source_path") or ""),
                "span": meta.get("span"),
                "commit": meta.get("commit"),
                "confidence": meta.get("confidence"),
                "freshness": meta.get("freshness"),
                "receipt_id": str(meta.get("receipt_id") or ""),
                "score": score,
                "matched_terms": matched,
            }
        )

    candidates.sort(key=lambda item: (-float(item["score"]), str(item["source_path"]), str(item["node_id"])))
    selected = candidates[: max(1, int(limit))]
    return {
        "ok": True,
        "candidates": selected,
        "fallback_reason": None,
        "dropped": {k: dropped[k] for k in sorted(dropped)},
    }
