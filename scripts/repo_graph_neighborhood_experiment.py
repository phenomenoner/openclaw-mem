#!/usr/bin/env python3
"""Compare lexical repo search with UA graph-neighborhood expansion.

This is an experimental, file-only Pack-lane harness. It reads an upstream
Understand-Anything `knowledge-graph.json`, scores queries against graph nodes,
adds bounded 1-hop neighborhood context, and compares those hits with a simple
lexical scan over repository files.

It performs local file reads, artifact writes, and a bounded `git rev-parse HEAD` invocation; it does not access live runtime surfaces.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "openclaw.experiment.repo_graph_neighborhood.v0"
PACK_SCHEMA = "openclaw.context_pack.repo_graph_ingest.v0"
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
DEFAULT_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "site", ".pytest_cache", "__pycache__", ".understand-anything"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".toml", ".yaml", ".yml",
    ".txt", ".rst", ".sh", ".sql", ".css", ".html", ".ini", ".cfg",
}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tokens(text: str) -> list[str]:
    out: list[str] = []
    normalized = text.replace("-", " ").replace("/", " ").replace(".", " ").replace(":", " ")
    for raw in TOKEN_RE.findall(normalized):
        for part in CAMEL_RE.sub(" ", raw).replace("_", " ").split():
            token = part.lower()
            if len(token) > 1:
                out.append(token)
    return out


def load_graph(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("graph root must be a JSON object")
    if not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
        raise SystemExit("graph must contain list fields: nodes, edges")
    return data


def git_commit(repo_root: Path) -> str:
    if not (repo_root / ".git").exists():
        return ""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def iter_repo_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(repo_root).parts)
        if parts & DEFAULT_SKIP_DIRS:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README", "LICENSE", "CHANGELOG"}:
            continue
        yield path


def read_text(path: Path, max_chars: int = 200_000) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


@dataclass(frozen=True)
class GraphIndexes:
    by_id: dict[str, dict[str, Any]]
    outgoing: dict[str, list[dict[str, Any]]]
    incoming: dict[str, list[dict[str, Any]]]


def graph_indexes(graph: dict[str, Any]) -> GraphIndexes:
    by_id = {str(n.get("id")): n for n in graph.get("nodes", []) if isinstance(n, dict)}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        outgoing[source].append(edge)
        incoming[target].append(edge)
    return GraphIndexes(by_id, outgoing, incoming)


def validate_graph(graph: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    ids = {str(n.get("id")) for n in graph.get("nodes", []) if isinstance(n, dict)}
    missing_file_refs: list[str] = []
    bad_line_ranges: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or not node.get("filePath"):
            continue
        path = repo_root / str(node["filePath"])
        if not path.exists():
            missing_file_refs.append(str(node.get("id")))
            continue
        line_range = node.get("lineRange")
        if isinstance(line_range, list) and len(line_range) == 2:
            line_count = len(read_text(path).splitlines())
            if not (1 <= int(line_range[0]) <= int(line_range[1]) <= max(line_count, 1)):
                bad_line_ranges.append({"id": node.get("id"), "lineRange": line_range, "lines": line_count})
    dangling_edges = [
        edge for edge in graph.get("edges", [])
        if isinstance(edge, dict) and (str(edge.get("source")) not in ids or str(edge.get("target")) not in ids)
    ]
    return {
        "ok": not missing_file_refs and not bad_line_ranges and not dangling_edges,
        "missingFileRefs": missing_file_refs,
        "badLineRanges": bad_line_ranges,
        "danglingEdges": dangling_edges[:100],
    }


def baseline_scan(repo_root: Path, query: str, k: int) -> list[dict[str, Any]]:
    query_tokens = set(tokens(query))
    scored: list[tuple[float, str, list[str]]] = []
    for path in iter_repo_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        text = read_text(path)
        hay = set(tokens(rel + "\n" + text))
        overlap = query_tokens & hay
        if not overlap:
            continue
        path_bonus = sum(1 for t in query_tokens if t in rel.lower()) * 0.25
        score = float(len(overlap)) + path_bonus
        snippets = []
        lowered = text.lower().splitlines()
        for idx, line in enumerate(lowered, start=1):
            if any(t in line for t in query_tokens):
                snippets.append(f"{idx}:{line[:160]}")
            if len(snippets) >= 2:
                break
        scored.append((score, rel, snippets))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{"path": rel, "score": round(score, 3), "snippets": snippets} for score, rel, snippets in scored[:k]]


def node_text(node: dict[str, Any]) -> str:
    return " ".join(
        str(node.get(key, "")) for key in ("id", "type", "name", "filePath", "summary", "tags")
    )


def graph_hits(graph: dict[str, Any], query: str, k: int, depth: int) -> list[dict[str, Any]]:
    idx = graph_indexes(graph)
    query_tokens = set(tokens(query))
    scored: list[tuple[float, str]] = []
    for node_id, node in idx.by_id.items():
        hay = set(tokens(node_text(node)))
        overlap = query_tokens & hay
        if not overlap:
            continue
        score = float(len(overlap))
        if node.get("type") in {"file", "document", "config", "pipeline"}:
            score += 0.25
        score += min(len(idx.outgoing[node_id]) + len(idx.incoming[node_id]), 5) * 0.05
        scored.append((score, node_id))
    scored.sort(key=lambda item: (-item[0], item[1]))

    hits = []
    for score, node_id in scored[:k]:
        node = idx.by_id[node_id]
        neighborhood = expand_neighborhood(node_id, idx, depth=depth, limit=12)
        hits.append({
            "id": node_id,
            "path": node.get("filePath"),
            "type": node.get("type"),
            "name": node.get("name"),
            "score": round(score, 3),
            "summary": node.get("summary"),
            "neighborhood": neighborhood,
        })
    return hits


def expand_neighborhood(node_id: str, idx: GraphIndexes, depth: int, limit: int) -> list[dict[str, Any]]:
    if depth <= 0:
        return []
    seen = {node_id}
    frontier = [(node_id, 0)]
    out: list[dict[str, Any]] = []
    while frontier and len(out) < limit:
        current, dist = frontier.pop(0)
        if dist >= depth:
            continue
        for edge in idx.outgoing[current] + idx.incoming[current]:
            source = str(edge.get("source"))
            target = str(edge.get("target"))
            other = target if source == current else source
            if other in seen:
                continue
            seen.add(other)
            other_node = idx.by_id.get(other, {})
            out.append({
                "distance": dist + 1,
                "edge": edge.get("type"),
                "id": other,
                "path": other_node.get("filePath"),
                "type": other_node.get("type"),
                "name": other_node.get("name"),
            })
            frontier.append((other, dist + 1))
            if len(out) >= limit:
                break
    return out


def paths_from_baseline(hits: list[dict[str, Any]]) -> set[str]:
    return {str(hit.get("path")) for hit in hits if hit.get("path")}


def paths_from_graph(hits: list[dict[str, Any]]) -> set[str]:
    paths = {str(hit.get("path")) for hit in hits if hit.get("path")}
    for hit in hits:
        for item in hit.get("neighborhood", []):
            if item.get("path"):
                paths.add(str(item["path"]))
    return paths


def compact_pack(graph: dict[str, Any], graph_path: Path, repo_root: Path, validation: dict[str, Any]) -> dict[str, Any]:
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    edges = [e for e in graph.get("edges", []) if isinstance(e, dict)]
    return {
        "schema": PACK_SCHEMA,
        "source": {
            "upstream": "Understand-Anything knowledge-graph.json",
            "graphSha256": sha256_path(graph_path),
            "repoCommit": git_commit(repo_root),
            "authority": "candidate Pack/Observe context only; not durable Store truth",
        },
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "nodeTypes": dict(Counter(str(n.get("type")) for n in nodes)),
            "edgeTypes": dict(Counter(str(e.get("type")) for e in edges)),
            "validationOk": validation["ok"],
        },
        "nodes": [
            {
                "id": n.get("id"),
                "kind": n.get("type"),
                "name": n.get("name"),
                "path": n.get("filePath"),
                "lineRange": n.get("lineRange"),
                "summary": n.get("summary"),
            }
            for n in nodes
        ],
        "relations": [
            {"source": e.get("source"), "target": e.get("target"), "kind": e.get("type"), "weight": e.get("weight")}
            for e in edges
        ],
    }


def run_experiment(graph_path: Path, repo_root: Path, out_dir: Path, queries: list[str], k: int, depth: int) -> dict[str, Any]:
    graph = load_graph(graph_path)
    validation = validate_graph(graph, repo_root)
    comparisons = []
    for query in queries:
        baseline = baseline_scan(repo_root, query, k)
        graph_result = graph_hits(graph, query, k, depth)
        baseline_paths = paths_from_baseline(baseline)
        graph_paths = paths_from_graph(graph_result)
        comparisons.append({
            "query": query,
            "baseline": baseline,
            "graph": graph_result,
            "metrics": {
                "baselinePathCount": len(baseline_paths),
                "graphPathCountIncludingNeighbors": len(graph_paths),
                "novelGraphPaths": sorted(graph_paths - baseline_paths)[:50],
                "overlapPaths": sorted(graph_paths & baseline_paths)[:50],
                "noveltyFromNeighborhoodRate": round((len(graph_paths - baseline_paths) / max(len(graph_paths), 1)), 4),
            },
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    pack = compact_pack(graph, graph_path, repo_root, validation)
    comparison = {
        "schema": SCHEMA,
        "parameters": {"k": k, "depth": depth, "queries": queries},
        "validation": validation,
        "comparisons": comparisons,
    }
    (out_dir / "pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "schema": f"{SCHEMA}.manifest",
        "graph": str(graph_path),
        "graphSha256": sha256_path(graph_path),
        "repoRoot": str(repo_root),
        "repoCommit": git_commit(repo_root),
        "outputs": {
            "pack": "pack.json",
            "comparison": "comparison.json",
            "report": "report.md",
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(out_dir / "report.md", comparison, manifest, pack)
    return {"manifest": manifest, "comparison": comparison, "pack": pack}


def write_report(path: Path, comparison: dict[str, Any], manifest: dict[str, Any], pack: dict[str, Any]) -> None:
    lines = [
        "# Repo graph neighborhood experiment",
        "",
        "This report compares a deterministic lexical repository scan with bounded graph-neighborhood expansion from an upstream Understand-Anything graph.",
        "",
        "Authority: candidate Pack/Observe context only; not durable Store truth.",
        "",
        "## Inputs",
        "",
        f"- Graph SHA-256: `{manifest['graphSha256']}`",
        f"- Repo commit: `{manifest['repoCommit']}`",
        f"- Pack artifact: `{manifest['outputs']['pack']}`",
        f"- Comparison artifact: `{manifest['outputs']['comparison']}`",
        "",
        "## Graph stats",
        "",
        f"- Nodes: {pack['stats']['nodes']} — {pack['stats']['nodeTypes']}",
        f"- Edges: {pack['stats']['edges']} — {pack['stats']['edgeTypes']}",
        f"- Validation OK: {pack['stats']['validationOk']}",
        "",
        "## Query comparisons",
        "",
    ]
    for item in comparison["comparisons"]:
        lines.append(f"### {item['query']}")
        metrics = item["metrics"]
        lines.append(f"- Baseline path count: {metrics['baselinePathCount']}")
        lines.append(f"- Graph path count including neighbors: {metrics['graphPathCountIncludingNeighbors']}")
        lines.append(f"- Novel graph paths: {len(metrics['novelGraphPaths'])}")
        lines.append(f"- Neighborhood novelty rate: {metrics['noveltyFromNeighborhoodRate']}")
        lines.append("- Top baseline paths: " + ", ".join(f"`{x['path']}`" for x in item["baseline"][:3]))
        lines.append("- Top graph hits: " + ", ".join(f"`{x.get('path') or x['id']}`" for x in item["graph"][:3]))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a file-only UA graph-neighborhood Pack-lane experiment.")
    parser.add_argument("--graph", required=True, type=Path, help="Understand-Anything knowledge-graph.json")
    parser.add_argument("--repo-root", required=True, type=Path, help="Repository root to scan and validate against")
    parser.add_argument("--out-dir", required=True, type=Path, help="Directory for pack/comparison/report/manifest artifacts")
    parser.add_argument("--query", action="append", required=True, help="Query to compare; repeatable")
    parser.add_argument("--k", type=int, default=10, help="Top-k hits per lane")
    parser.add_argument("--depth", type=int, default=1, help="Graph neighborhood expansion depth")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_experiment(args.graph.resolve(), args.repo_root.resolve(), args.out_dir.resolve(), args.query, args.k, args.depth)
    print(json.dumps({
        "schema": SCHEMA,
        "outDir": str(args.out_dir),
        "validationOk": result["comparison"]["validation"]["ok"],
        "queries": len(result["comparison"]["comparisons"]),
    }, ensure_ascii=False))
    return 0 if result["comparison"]["validation"]["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
