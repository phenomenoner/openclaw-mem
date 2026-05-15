"""Deterministic symbolic task canvas helpers.

This module absorbs the useful part of TencentDB-Agent-Memory's symbolic
short-term memory idea into openclaw-mem's Store / Pack / Observe posture:
compact top-layer canvas, structured node index, and drill-down refs to raw
evidence.  It performs no capture, no model calls, and no live runtime writes.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA = "openclaw-mem.symbolic-canvas.v0"
_ALLOWED_STATES = {
    "pending",
    "running",
    "done",
    "blocked",
    "failed",
    "skipped",
    "unknown",
}
_STATE_STYLE = {
    "pending": "pending",
    "running": "running",
    "done": "done",
    "blocked": "blocked",
    "failed": "failed",
    "skipped": "skipped",
    "unknown": "unknown",
}


def _stable_hash(value: Any, length: int = 8) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _slug(value: str, *, default: str = "node", max_len: int = 36) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    if not text:
        text = default
    if text[0].isdigit():
        text = f"n_{text}"
    return text[:max_len].strip("_") or default


def _normalize_state(value: Any) -> str:
    state = str(value or "unknown").strip().lower().replace(" ", "_")
    return state if state in _ALLOWED_STATES else "unknown"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _refs_from_node(node: Mapping[str, Any]) -> List[str]:
    refs: List[str] = []
    for key in ("refs", "result_refs", "result_ref", "evidence_refs", "evidence_ref", "artifact", "artifacts"):
        for item in _as_list(node.get(key)):
            if isinstance(item, Mapping):
                raw = item.get("path") or item.get("ref") or item.get("href") or item.get("id")
            else:
                raw = item
            text = str(raw or "").strip()
            if text and text not in refs:
                refs.append(text)
    return refs


def _mermaid_label(text: str, *, max_len: int = 80) -> str:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    if len(clean) > max_len:
        clean = clean[: max_len - 1].rstrip() + "…"
    # Mermaid quoted labels tolerate most text, but escape characters that break
    # graph syntax or HTML-ish labels.
    return clean.replace("\\", "\\\\").replace('"', "'").replace("<", "‹").replace(">", "›")


def _extract_nodes(trace: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    raw = trace.get("nodes")
    if raw is None:
        raw = trace.get("steps")
    if raw is None:
        raw = trace.get("events")
    if not isinstance(raw, list):
        raise ValueError("trace must contain a list field: nodes, steps, or events")
    nodes: List[Mapping[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"node #{index} must be an object")
        nodes.append(item)
    return nodes


def _extract_edges(trace: Mapping[str, Any]) -> List[Tuple[str, str, str]]:
    raw = trace.get("edges") or trace.get("links") or []
    if not isinstance(raw, list):
        raise ValueError("edges/links must be a list when provided")
    edges: List[Tuple[str, str, str]] = []
    for index, edge in enumerate(raw, start=1):
        label = ""
        if isinstance(edge, Mapping):
            src = str(edge.get("from") or edge.get("source") or "").strip()
            dst = str(edge.get("to") or edge.get("target") or "").strip()
            label = str(edge.get("label") or "").strip()
        elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
            src = str(edge[0] or "").strip()
            dst = str(edge[1] or "").strip()
            if len(edge) >= 3:
                label = str(edge[2] or "").strip()
        else:
            raise ValueError(f"edge #{index} must be an object or [from, to, label?]")
        if not src or not dst:
            raise ValueError(f"edge #{index} is missing from/to")
        edges.append((src, dst, label))
    return edges


def _ref_exists(ref: str, base_dir: Optional[Path]) -> Optional[bool]:
    if not ref or "://" in ref or ref.startswith("artifact:") or ref.startswith("memory:"):
        return None
    path = Path(ref).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.exists()


def build_symbolic_canvas(trace: Mapping[str, Any], *, base_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    """Build a compact Mermaid canvas plus drill-down index from a trace object.

    The input is intentionally small and host-agnostic.  Supported node fields:
    `id`/`node_id`, `label`/`title`/`summary`, `state`, and refs/result_ref.
    Supported edge fields: `[from, to, label?]` or `{from/source, to/target}`.
    """

    if not isinstance(trace, Mapping):
        raise ValueError("trace must be a JSON object")

    base_path = Path(base_dir).expanduser().resolve() if base_dir else None
    raw_nodes = _extract_nodes(trace)
    raw_edges = _extract_edges(trace)

    warnings: List[Dict[str, Any]] = []
    id_map: Dict[str, str] = {}
    used_ids: Dict[str, int] = {}
    seen_source_ids: Dict[str, int] = {}
    nodes: List[Dict[str, Any]] = []

    for index, node in enumerate(raw_nodes, start=1):
        raw_id = str(node.get("node_id") or node.get("id") or "").strip()
        if raw_id:
            if raw_id in seen_source_ids:
                raise ValueError(f"duplicate node source id: {raw_id}")
            seen_source_ids[raw_id] = index
        label = str(node.get("label") or node.get("title") or node.get("summary") or raw_id or f"step {index}").strip()
        if raw_id:
            node_id = _slug(raw_id, default=f"n{index:03d}")
        else:
            node_id = f"n{index:03d}_{_slug(label, max_len=24)}_{_stable_hash({'i': index, 'label': label}, 6)}"
        count = used_ids.get(node_id, 0)
        used_ids[node_id] = count + 1
        if count:
            base = node_id
            node_id = f"{base}_{count + 1}"
            warnings.append({"code": "duplicate_node_id", "raw_id": raw_id, "resolved_node_id": node_id})

        if raw_id:
            id_map[raw_id] = node_id
        id_map[node_id] = node_id

        refs = _refs_from_node(node)
        missing_refs: List[str] = []
        for ref in refs:
            exists = _ref_exists(ref, base_path)
            if exists is False:
                missing_refs.append(ref)
        if missing_refs:
            warnings.append({"code": "missing_refs", "node_id": node_id, "refs": missing_refs})

        nodes.append(
            {
                "node_id": node_id,
                "source_id": raw_id or None,
                "label": label,
                "state": _normalize_state(node.get("state") or node.get("status")),
                "summary": str(node.get("summary") or "").strip() or None,
                "refs": refs,
                "missing_refs": missing_refs,
            }
        )

    edges: List[Dict[str, str]] = []
    for src_raw, dst_raw, label in raw_edges:
        src = id_map.get(src_raw) or _slug(src_raw)
        dst = id_map.get(dst_raw) or _slug(dst_raw)
        if src not in {n["node_id"] for n in nodes} or dst not in {n["node_id"] for n in nodes}:
            warnings.append({"code": "edge_unknown_node", "from": src_raw, "to": dst_raw, "resolved_from": src, "resolved_to": dst})
        edges.append({"from": src, "to": dst, "label": label})

    mermaid_lines = ["graph LR"]
    for node in nodes:
        refs_suffix = f"\\nrefs:{len(node['refs'])}" if node["refs"] else ""
        label = _mermaid_label(f"{node['label']}\\n[{node['state']}]{refs_suffix}")
        mermaid_lines.append(f"    {node['node_id']}[\"{label}\"]")
    for edge in edges:
        if edge["label"]:
            mermaid_lines.append(f"    {edge['from']} -- \"{_mermaid_label(edge['label'], max_len=40)}\" --> {edge['to']}")
        else:
            mermaid_lines.append(f"    {edge['from']} --> {edge['to']}")

    states = sorted({node["state"] for node in nodes})
    for state in states:
        mermaid_lines.append(f"    classDef {state} fill:#f8fafc,stroke:#94a3b8,color:#0f172a")
    for node in nodes:
        mermaid_lines.append(f"    class {node['node_id']} {_STATE_STYLE[node['state']]}")

    task_id = str(trace.get("task_id") or trace.get("id") or f"task-{_stable_hash({'nodes': nodes, 'edges': edges}, 10)}").strip()
    out = {
        "kind": SCHEMA,
        "ok": True,
        "task_id": task_id,
        "topology": "unchanged",
        "store_pack_observe": {
            "store": "raw evidence remains in refs/artifacts; canvas does not become canonical memory",
            "pack": "Mermaid canvas and node index are compact candidates for bounded context injection",
            "observe": "node_id + refs provide drill-down receipts for debugging and rollback",
        },
        "mermaid": "\n".join(mermaid_lines) + "\n",
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "refs": sum(len(node["refs"]) for node in nodes),
            "missing_refs": sum(len(node["missing_refs"]) for node in nodes),
        },
    }
    return out


def load_trace_file(path: str | Path) -> Dict[str, Any]:
    with Path(path).expanduser().open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError("trace file must contain a JSON object")
    return data


def write_canvas_outputs(result: Mapping[str, Any], *, out: Optional[str | Path] = None, mermaid_out: Optional[str | Path] = None) -> Dict[str, str]:
    written: Dict[str, str] = {}
    if out:
        path = Path(out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written["json"] = str(path)
    if mermaid_out:
        path = Path(mermaid_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(result.get("mermaid") or ""), encoding="utf-8")
        written["mermaid"] = str(path)
    return written
