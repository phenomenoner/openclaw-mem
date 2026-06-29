from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


CODE_GRAPH_KIND = "openclaw-mem.graph.code-extract.v0"
CODE_GRAPH_EXTRACTOR = "openclaw-mem.code-graph"
CODE_GRAPH_EXTRACTOR_VERSION = "0.1.0"

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_repo_id(repo: Path) -> str:
    token = "".join(ch.lower() if ch.isalnum() else "-" for ch in repo.name).strip("-")
    return token or "repo"


def _repo_commit(repo: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    return out or None


def _repo_commit_ts(repo: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "log", "-1", "--format=%cI"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    return out or None


def _rel(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def _file_node_id(rel_path: str) -> str:
    return f"file.{rel_path}"


def _symbol_node_id(rel_path: str, qualname: str) -> str:
    return f"symbol.{rel_path}:{qualname}"


def _provenance(rel_path: str, line: int | None = None) -> str:
    if line and line > 0:
        return f"{rel_path}#L{line}"
    return rel_path


def _base_metadata(
    *,
    source_path: str,
    span: Optional[Dict[str, int]],
    commit: Optional[str],
    receipt_id: str,
    created_at: str,
    confidence: float = 1.0,
) -> Dict[str, Any]:
    return {
        "source_path": source_path,
        "span": span,
        "commit": commit,
        "extractor": CODE_GRAPH_EXTRACTOR,
        "extractor_version": CODE_GRAPH_EXTRACTOR_VERSION,
        "confidence": confidence,
        "freshness": "snapshot",
        "receipt_id": receipt_id,
        "created_at": created_at,
        "canonicalWritesAllowed": False,
        "policySource": "openclaw-mem-engine",
    }


def _iter_source_files(repo: Path) -> List[Path]:
    files: List[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if path.suffix.lower() in {".py", ".rs"}:
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(repo).as_posix())


def _python_module_name(rel_path: str) -> str:
    if not rel_path.endswith(".py"):
        return ""
    parts = rel_path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(part for part in parts if part)


def _module_candidates(module: str, imported_name: Optional[str] = None) -> List[str]:
    token = str(module or "").strip(".")
    candidates: List[str] = []
    if token:
        candidates.append(token)
        if imported_name:
            candidates.append(f"{token}.{imported_name}")
    elif imported_name:
        candidates.append(imported_name)
    return candidates


def _resolve_imported_file(
    *,
    module: str,
    imported_name: Optional[str],
    module_to_file: Dict[str, str],
) -> Optional[str]:
    for candidate in _module_candidates(module, imported_name):
        parts = candidate.split(".")
        while parts:
            mod = ".".join(parts)
            rel = module_to_file.get(mod)
            if rel:
                return rel
            parts.pop()
    return None


def _top_level_symbols(tree: ast.AST, rel_path: str, *, commit: Optional[str], receipt_id: str, created_at: str) -> List[Dict[str, Any]]:
    symbols: List[Dict[str, Any]] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            span = {
                "line_start": int(getattr(node, "lineno", 0) or 0),
                "line_end": int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0),
            }
            symbols.append(
                {
                    "id": _symbol_node_id(rel_path, node.name),
                    "type": "symbol",
                    "tags": sorted({"code", "python", kind}),
                    "metadata": {
                        **_base_metadata(
                            source_path=rel_path,
                            span=span,
                            commit=commit,
                            receipt_id=receipt_id,
                            created_at=created_at,
                        ),
                        "name": node.name,
                        "qualname": node.name,
                        "language": "python",
                        "kind": kind,
                    },
                }
            )
    return symbols


def _python_import_edges(
    tree: ast.AST,
    rel_path: str,
    *,
    module_to_file: Dict[str, str],
    commit: Optional[str],
    receipt_id: str,
    created_at: str,
) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    src_id = _file_node_id(rel_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_imported_file(
                    module=alias.name,
                    imported_name=None,
                    module_to_file=module_to_file,
                )
                if target and target != rel_path:
                    edges.append(
                        _edge(
                            src_id,
                            _file_node_id(target),
                            "imports",
                            rel_path=rel_path,
                            line=getattr(node, "lineno", None),
                            commit=commit,
                            receipt_id=receipt_id,
                            created_at=created_at,
                            metadata={"module": alias.name},
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if getattr(node, "level", 0):
                continue
            module = str(node.module or "")
            for alias in node.names:
                target = _resolve_imported_file(
                    module=module,
                    imported_name=alias.name,
                    module_to_file=module_to_file,
                )
                if target and target != rel_path:
                    edges.append(
                        _edge(
                            src_id,
                            _file_node_id(target),
                            "imports",
                            rel_path=rel_path,
                            line=getattr(node, "lineno", None),
                            commit=commit,
                            receipt_id=receipt_id,
                            created_at=created_at,
                            metadata={"module": module, "name": alias.name},
                        )
                    )
    return edges


def _python_call_edges(
    tree: ast.AST,
    rel_path: str,
    *,
    symbol_index: Dict[str, List[str]],
    commit: Optional[str],
    receipt_id: str,
    created_at: str,
) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    src_file_id = _file_node_id(rel_path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if not name:
            continue
        targets = symbol_index.get(name) or []
        for dst in targets:
            if dst.startswith(f"symbol.{rel_path}:"):
                continue
            edges.append(
                _edge(
                    src_file_id,
                    dst,
                    "calls",
                    rel_path=rel_path,
                    line=getattr(node, "lineno", None),
                    commit=commit,
                    receipt_id=receipt_id,
                    created_at=created_at,
                    metadata={"symbol": name},
                    confidence=0.6,
                )
            )
    return edges


def _rust_mod_names(text: str) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("mod ") and stripped.endswith(";"):
            name = stripped[4:-1].strip()
            if name:
                out.append((name, idx))
    return out


def _edge(
    src: str,
    dst: str,
    edge_type: str,
    *,
    rel_path: str,
    line: int | None,
    commit: Optional[str],
    receipt_id: str,
    created_at: str,
    metadata: Optional[Dict[str, Any]] = None,
    confidence: float = 1.0,
) -> Dict[str, Any]:
    edge_meta = {
        **_base_metadata(
            source_path=rel_path,
            span={"line_start": int(line), "line_end": int(line)} if line else None,
            commit=commit,
            receipt_id=receipt_id,
            created_at=created_at,
            confidence=confidence,
        ),
        **(metadata or {}),
    }
    return {
        "src": src,
        "dst": dst,
        "type": edge_type,
        "provenance": _provenance(rel_path, line),
        "metadata": edge_meta,
    }


def _dedupe_edges(edges: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for edge in edges:
        key = (
            str(edge.get("src") or ""),
            str(edge.get("dst") or ""),
            str(edge.get("type") or ""),
            str(edge.get("provenance") or ""),
        )
        if "" in key:
            continue
        by_key.setdefault(key, edge)
    return sorted(by_key.values(), key=lambda e: (e["src"], e["dst"], e["type"], e["provenance"], _stable_json(e.get("metadata"))))


def _counts(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    node_types: Dict[str, int] = {}
    edge_types: Dict[str, int] = {}
    for node in nodes:
        node_type = str(node.get("type") or "unknown")
        node_types[node_type] = int(node_types.get(node_type, 0)) + 1
    for edge in edges:
        edge_type = str(edge.get("type") or "unknown")
        edge_types[edge_type] = int(edge_types.get(edge_type, 0)) + 1
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "node_types": {k: node_types[k] for k in sorted(node_types)},
        "edge_types": {k: edge_types[k] for k in sorted(edge_types)},
    }


def _graph_digest(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(_stable_json({"nodes": nodes, "edges": edges}).encode("utf-8")).hexdigest()


def extract_code_graph(*, repo: str | Path) -> Dict[str, Any]:
    repo_path = Path(repo).resolve()
    if not repo_path.is_dir():
        raise ValueError(f"repo not found: {repo_path}")

    commit = _repo_commit(repo_path)
    created_at = _repo_commit_ts(repo_path) or "unknown"
    receipt_seed = f"{repo_path.as_posix()}|{commit or 'no-commit'}|{CODE_GRAPH_EXTRACTOR_VERSION}"
    receipt_id = "ocm-code-graph-" + hashlib.sha256(receipt_seed.encode("utf-8")).hexdigest()[:16]

    source_files = _iter_source_files(repo_path)
    python_files = [p for p in source_files if p.suffix.lower() == ".py"]
    module_to_file = {_python_module_name(_rel(path, repo_path)): _rel(path, repo_path) for path in python_files}
    module_to_file = {k: v for k, v in module_to_file.items() if k}

    nodes: List[Dict[str, Any]] = [
        {
            "id": f"repo.{_safe_repo_id(repo_path)}",
            "type": "repo",
            "tags": ["code", "repo"],
            "metadata": {
                **_base_metadata(
                    source_path=".",
                    span=None,
                    commit=commit,
                    receipt_id=receipt_id,
                    created_at=created_at,
                ),
                "path": repo_path.as_posix(),
                "name": repo_path.name,
            },
        }
    ]
    edges: List[Dict[str, Any]] = []
    parsed_python: Dict[str, ast.AST] = {}
    symbol_index: Dict[str, List[str]] = {}
    repo_node_id = nodes[0]["id"]

    for path in source_files:
        rel_path = _rel(path, repo_path)
        language = "python" if path.suffix.lower() == ".py" else "rust"
        file_id = _file_node_id(rel_path)
        nodes.append(
            {
                "id": file_id,
                "type": "file",
                "tags": sorted({"code", language, "test"} if _is_test_path(rel_path) else {"code", language}),
                "metadata": {
                    **_base_metadata(
                        source_path=rel_path,
                        span=None,
                        commit=commit,
                        receipt_id=receipt_id,
                        created_at=created_at,
                    ),
                    "path": rel_path,
                    "language": language,
                },
            }
        )
        edges.append(
            _edge(
                repo_node_id,
                file_id,
                "contains",
                rel_path=rel_path,
                line=None,
                commit=commit,
                receipt_id=receipt_id,
                created_at=created_at,
            )
        )

        if language == "python":
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
            except SyntaxError:
                continue
            parsed_python[rel_path] = tree
            for symbol in _top_level_symbols(
                tree,
                rel_path,
                commit=commit,
                receipt_id=receipt_id,
                created_at=created_at,
            ):
                nodes.append(symbol)
                symbol_name = str(symbol.get("metadata", {}).get("name") or "")
                symbol_index.setdefault(symbol_name, []).append(symbol["id"])
                edges.append(
                    _edge(
                        file_id,
                        symbol["id"],
                        "defines",
                        rel_path=rel_path,
                        line=int(symbol["metadata"]["span"]["line_start"]),
                        commit=commit,
                        receipt_id=receipt_id,
                        created_at=created_at,
                    )
                )
        elif language == "rust":
            text = path.read_text(encoding="utf-8", errors="replace")
            for mod_name, line_no in _rust_mod_names(text):
                candidate = path.parent / f"{mod_name}.rs"
                if candidate.is_file():
                    target_rel = _rel(candidate, repo_path)
                    edges.append(
                        _edge(
                            file_id,
                            _file_node_id(target_rel),
                            "imports",
                            rel_path=rel_path,
                            line=line_no,
                            commit=commit,
                            receipt_id=receipt_id,
                            created_at=created_at,
                            metadata={"module": mod_name},
                            confidence=0.7,
                        )
                    )

    for rel_path, tree in parsed_python.items():
        edges.extend(
            _python_import_edges(
                tree,
                rel_path,
                module_to_file=module_to_file,
                commit=commit,
                receipt_id=receipt_id,
                created_at=created_at,
            )
        )
        edges.extend(
            _python_call_edges(
                tree,
                rel_path,
                symbol_index=symbol_index,
                commit=commit,
                receipt_id=receipt_id,
                created_at=created_at,
            )
        )

    edges.extend(
        _test_edges(
            source_files=source_files,
            repo=repo_path,
            module_to_file=module_to_file,
            commit=commit,
            receipt_id=receipt_id,
            created_at=created_at,
        )
    )

    nodes = sorted(nodes, key=lambda n: (n["id"], n["type"], _stable_json(n.get("tags")), _stable_json(n.get("metadata"))))
    edges = _dedupe_edges(edges)
    digest = _graph_digest(nodes, edges)

    return {
        "kind": CODE_GRAPH_KIND,
        "schema": "openclaw-mem.graph.topology.v1",
        "repo": repo_path.as_posix(),
        "commit": commit,
        "receipt_id": receipt_id,
        "topology_digest": digest,
        "counts": _counts(nodes, edges),
        "nodes": nodes,
        "edges": edges,
    }


def _is_test_path(rel_path: str) -> bool:
    name = Path(rel_path).name
    return rel_path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py") or name.endswith("_test.rs")


def _test_edges(
    *,
    source_files: List[Path],
    repo: Path,
    module_to_file: Dict[str, str],
    commit: Optional[str],
    receipt_id: str,
    created_at: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in source_files:
        rel_path = _rel(path, repo)
        if not _is_test_path(rel_path):
            continue
        src_id = _file_node_id(rel_path)
        if path.suffix.lower() == ".py":
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
            except SyntaxError:
                continue
            for edge in _python_import_edges(
                tree,
                rel_path,
                module_to_file=module_to_file,
                commit=commit,
                receipt_id=receipt_id,
                created_at=created_at,
            ):
                out.append({**edge, "type": "tests"})

        name = path.name
        for prefix in ("test_",):
            if name.startswith(prefix):
                target_name = name[len(prefix) :]
                for candidate in source_files:
                    candidate_rel = _rel(candidate, repo)
                    if candidate_rel == rel_path:
                        continue
                    if candidate.name == target_name:
                        out.append(
                            _edge(
                                src_id,
                                _file_node_id(candidate_rel),
                                "tests",
                                rel_path=rel_path,
                                line=None,
                                commit=commit,
                                receipt_id=receipt_id,
                                created_at=created_at,
                                metadata={"heuristic": "test_filename"},
                                confidence=0.7,
                            )
                        )
    return out


def load_code_graph(path: str | Path) -> Dict[str, Any]:
    graph_path = Path(path)
    if not graph_path.is_file():
        raise ValueError(f"graph file not found: {graph_path}")
    obj = json.loads(graph_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("graph root must be an object")
    if not isinstance(obj.get("nodes"), list) or not isinstance(obj.get("edges"), list):
        raise ValueError("graph requires nodes and edges lists")
    return obj


def query_symbol(*, graph_path: str | Path, symbol: str) -> Dict[str, Any]:
    name = str(symbol or "").strip()
    if not name:
        raise ValueError("symbol is required")
    graph = load_code_graph(graph_path)
    matches = []
    for node in list(graph.get("nodes") or []):
        meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        node_name = str(meta.get("name") or "")
        qualname = str(meta.get("qualname") or "")
        if str(node.get("type") or "") == "symbol" and name in {node_name, qualname}:
            matches.append(node)
    matches.sort(key=lambda n: str(n.get("id") or ""))
    return {
        "ok": True,
        "query": "symbol",
        "symbol": name,
        "count": len(matches),
        "nodes": matches,
    }


def query_impact(*, graph_path: str | Path, path: str) -> Dict[str, Any]:
    rel_path = str(path or "").replace("\\", "/").strip("/")
    if not rel_path:
        raise ValueError("path is required")
    graph = load_code_graph(graph_path)
    file_id = _file_node_id(rel_path)
    nodes_by_id = {str(node.get("id") or ""): node for node in list(graph.get("nodes") or [])}
    edges = [
        edge
        for edge in list(graph.get("edges") or [])
        if str(edge.get("src") or "") == file_id or str(edge.get("dst") or "") == file_id
    ]
    edges.sort(key=lambda e: (str(e.get("src") or ""), str(e.get("dst") or ""), str(e.get("type") or ""), str(e.get("provenance") or "")))
    node_ids = {file_id}
    for edge in edges:
        node_ids.add(str(edge.get("src") or ""))
        node_ids.add(str(edge.get("dst") or ""))
    return {
        "ok": True,
        "query": "impact",
        "path": rel_path,
        "node_id": file_id,
        "node": nodes_by_id.get(file_id),
        "node_count": len([nid for nid in node_ids if nid in nodes_by_id]),
        "edge_count": len(edges),
        "nodes": [nodes_by_id[nid] for nid in sorted(node_ids) if nid in nodes_by_id],
        "edges": edges,
    }
