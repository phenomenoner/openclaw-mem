from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


WORKSPACE_PATH_TOKEN_RE = re.compile(
    r"(/root/\.openclaw/workspace/[^\s'\"`<>]+|\$\{OPENCLAW_WORKSPACE\}/[^\s'\"`<>]+|\$OPENCLAW_WORKSPACE/[^\s'\"`<>]+)"
)


def _normalize_workspace_path_token(path_token: str, *, workspace_path: Path) -> str:
    token = str(path_token or "").strip()
    if token.startswith("${OPENCLAW_WORKSPACE}/"):
        rel = token[len("${OPENCLAW_WORKSPACE}/") :]
        return (workspace_path / rel).as_posix()
    if token.startswith("$OPENCLAW_WORKSPACE/"):
        rel = token[len("$OPENCLAW_WORKSPACE/") :]
        return (workspace_path / rel).as_posix()
    return token


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_slug(raw: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(raw or "").strip()).strip("-_.")
    return token.lower() or "unknown"


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _run_git(repo_path: Path, args: List[str]) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_path), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    return out or None


def _iter_repo_roots(workspace: Path) -> List[Path]:
    repos: List[Path] = []
    if not workspace.is_dir():
        return repos

    for child in sorted(workspace.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        git_marker = child / ".git"
        if git_marker.exists():
            repos.append(child)
    return repos


def _repo_node(repo_path: Path, workspace: Path) -> Dict[str, Any]:
    rel = repo_path.relative_to(workspace).as_posix()
    node_id = f"repo.{_safe_slug(rel.replace('/', '.'))}"
    return {
        "id": node_id,
        "type": "repo",
        "tags": ["workspace_repo"],
        "metadata": {
            "path": str(repo_path),
            "workspace_rel": rel,
            "git_remote": _run_git(repo_path, ["remote", "get-url", "origin"]),
            "default_branch": _run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]),
            "last_commit_ts": _run_git(repo_path, ["log", "-1", "--format=%cI"]),
        },
    }


def _load_cron_jobs(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"cron jobs file missing: {path}")

    obj = json.loads(path.read_text(encoding="utf-8"))
    jobs = obj.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("cron jobs root must include list key: jobs")

    cleaned: List[Dict[str, Any]] = []
    for raw in jobs:
        if not isinstance(raw, dict):
            continue
        job_id = str(raw.get("id") or "").strip()
        if not job_id:
            continue
        cleaned.append(raw)

    cleaned.sort(key=lambda j: str(j.get("id") or ""))
    return cleaned


def _cron_job_node(job: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(job.get("id") or "").strip()
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    delivery = job.get("delivery") if isinstance(job.get("delivery"), dict) else {}
    return {
        "id": f"cron.job.{job_id}",
        "type": "cron_job",
        "tags": ["enabled"] if bool(job.get("enabled")) else ["disabled"],
        "metadata": {
            "job_id": job_id,
            "name": str(job.get("name") or "").strip(),
            "agent_id": str(job.get("agentId") or "").strip(),
            "enabled": bool(job.get("enabled")),
            "session_target": str(job.get("sessionTarget") or "").strip(),
            "wake_mode": str(job.get("wakeMode") or "").strip(),
            "schedule": {
                "kind": str(schedule.get("kind") or "").strip(),
                "expr": str(schedule.get("expr") or "").strip(),
                "tz": str(schedule.get("tz") or "").strip(),
            },
            "delivery": {
                "mode": str(delivery.get("mode") or "").strip(),
                "channel": str(delivery.get("channel") or "").strip(),
                "to": str(delivery.get("to") or "").strip(),
            },
        },
    }


def _iter_spec_files(spec_dir: Path) -> List[Path]:
    if not spec_dir.is_dir():
        return []
    return sorted([p for p in spec_dir.glob("*.md") if p.is_file()], key=lambda p: p.name.lower())


def _extract_workspace_paths_from_spec(spec_path: Path, *, workspace_path: Path) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for idx, raw_line in enumerate(spec_path.read_text(encoding="utf-8").splitlines(), start=1):
        for match in WORKSPACE_PATH_TOKEN_RE.findall(raw_line):
            token = _normalize_workspace_path_token(match.rstrip(".,;:)]}"), workspace_path=workspace_path)
            if token:
                hits.append((idx, token))
    return hits


def _path_node(path_token: str) -> Dict[str, Any]:
    p = Path(path_token)
    suffix = p.suffix.lower()
    is_script = suffix in {".py", ".sh", ".bash"}
    node_type = "script" if is_script else "artifact"
    edge_role = "runs" if is_script else "reads"
    node_id = f"{node_type}.path.{_safe_slug(p.as_posix())}"
    return {
        "node": {
            "id": node_id,
            "type": node_type,
            "tags": ["derived"],
            "metadata": {
                "path": p.as_posix(),
                "basename": p.name,
                "suffix": suffix,
            },
        },
        "edge_role": edge_role,
    }


def _provenance_group(
    provenance: str,
    *,
    workspace_path: Path,
    cron_jobs_file: Path,
    spec_dir_path: Path,
) -> str:
    token = str(provenance or "").strip()
    if not token:
        return "unknown"

    source = token.split("#", 1)[0].strip()
    if not source:
        return "unknown"

    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = workspace_path / source_path
    source_path = source_path.resolve()

    if source_path == cron_jobs_file:
        return "cron_jobs"
    if source_path.parent == spec_dir_path:
        return "cron_spec"
    return "other"


def extract_topology_seed(
    *,
    workspace: str | Path,
    cron_jobs_path: str | Path,
    spec_dir: str | Path,
) -> Dict[str, Any]:
    workspace_path = Path(workspace).resolve()
    cron_jobs_file = Path(cron_jobs_path).resolve()
    spec_dir_path = Path(spec_dir).resolve()

    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    edge_seen: set[Tuple[str, str, str, str]] = set()

    def upsert_node(node: Dict[str, Any]) -> None:
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            return
        existing = nodes_by_id.get(node_id)
        if existing is None:
            nodes_by_id[node_id] = {
                "id": node_id,
                "type": str(node.get("type") or "unknown").strip() or "unknown",
                "tags": sorted(set(str(x).strip() for x in list(node.get("tags") or []) if str(x).strip())),
                "metadata": node.get("metadata") if isinstance(node.get("metadata"), dict) else {},
            }
            return

        merged_tags = set(existing.get("tags") or [])
        merged_tags.update(str(x).strip() for x in list(node.get("tags") or []) if str(x).strip())
        existing["tags"] = sorted(merged_tags)
        existing_meta = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
        new_meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        if new_meta:
            merged_meta = dict(existing_meta)
            merged_meta.update({k: v for k, v in new_meta.items() if v is not None and v != ""})
            existing["metadata"] = merged_meta

    def add_edge(src: str, dst: str, edge_type: str, provenance: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        s = str(src or "").strip()
        d = str(dst or "").strip()
        t = str(edge_type or "unknown").strip() or "unknown"
        p = str(provenance or "").strip()
        if not s or not d:
            return
        key = (s, d, t, p)
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append(
            {
                "src": s,
                "dst": d,
                "type": t,
                "provenance": p,
                "metadata": metadata or {},
            }
        )

    repo_nodes: List[Dict[str, Any]] = []
    repo_by_basename: Dict[str, str] = {}
    for repo_path in _iter_repo_roots(workspace_path):
        node = _repo_node(repo_path, workspace_path)
        upsert_node(node)
        repo_nodes.append(node)
        repo_by_basename[repo_path.name.lower()] = node["id"]

    cron_jobs = _load_cron_jobs(cron_jobs_file)
    jobs_by_id: Dict[str, Dict[str, Any]] = {}
    for job in cron_jobs:
        job_node = _cron_job_node(job)
        upsert_node(job_node)
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        jobs_by_id[job_id] = job

        job_text = "\n".join(
            [
                str(job.get("name") or ""),
                str(job.get("payload", {}).get("message") if isinstance(job.get("payload"), dict) else ""),
            ]
        ).lower()
        for basename, repo_node_id in repo_by_basename.items():
            if basename and basename in job_text:
                add_edge(
                    job_node["id"],
                    repo_node_id,
                    "targets_repo",
                    f"{cron_jobs_file.as_posix()}#job={job_id}",
                )

    spec_files = _iter_spec_files(spec_dir_path)
    for spec_path in spec_files:
        job_id = spec_path.stem
        if job_id not in jobs_by_id:
            continue

        job_node_id = f"cron.job.{job_id}"
        spec_rel = spec_path.relative_to(workspace_path).as_posix() if spec_path.is_relative_to(workspace_path) else spec_path.as_posix()
        spec_node_id = f"artifact.cron-spec.{_safe_slug(job_id)}"
        upsert_node(
            {
                "id": spec_node_id,
                "type": "artifact",
                "tags": ["cron_spec", "derived"],
                "metadata": {
                    "path": spec_path.as_posix(),
                    "workspace_rel": spec_rel,
                    "job_id": job_id,
                },
            }
        )
        add_edge(job_node_id, spec_node_id, "reads", f"{spec_rel}")

        for line_no, path_token in _extract_workspace_paths_from_spec(spec_path, workspace_path=workspace_path):
            parsed = _path_node(path_token)
            path_node = parsed["node"]
            edge_role = parsed["edge_role"]
            upsert_node(path_node)
            add_edge(
                job_node_id,
                path_node["id"],
                edge_role,
                f"{spec_rel}#L{line_no}",
            )

    nodes = sorted(
        nodes_by_id.values(),
        key=lambda n: (
            str(n.get("id") or ""),
            str(n.get("type") or ""),
            _stable_json(list(n.get("tags") or [])),
            _stable_json(n.get("metadata") if isinstance(n.get("metadata"), dict) else {}),
        ),
    )
    edges.sort(
        key=lambda e: (
            str(e.get("src") or ""),
            str(e.get("dst") or ""),
            str(e.get("type") or ""),
            str(e.get("provenance") or ""),
            _stable_json(e.get("metadata") if isinstance(e.get("metadata"), dict) else {}),
        )
    )

    node_type_counts: Dict[str, int] = {}
    for node in nodes:
        t = str(node.get("type") or "unknown")
        node_type_counts[t] = node_type_counts.get(t, 0) + 1

    edge_type_counts: Dict[str, int] = {}
    for edge in edges:
        t = str(edge.get("type") or "unknown")
        edge_type_counts[t] = edge_type_counts.get(t, 0) + 1

    provenance_group_counts: Dict[str, int] = {}
    for edge in edges:
        group = _provenance_group(
            str(edge.get("provenance") or ""),
            workspace_path=workspace_path,
            cron_jobs_file=cron_jobs_file,
            spec_dir_path=spec_dir_path,
        )
        provenance_group_counts[group] = provenance_group_counts.get(group, 0) + 1

    return {
        "kind": "openclaw-mem.graph.topology-seed.v0",
        "generated_at": _utc_now_iso(),
        "sources": {
            "workspace": workspace_path.as_posix(),
            "cron_jobs": cron_jobs_file.as_posix(),
            "spec_dir": spec_dir_path.as_posix(),
        },
        "counts": {
            "repos": len(repo_nodes),
            "cron_jobs": len(jobs_by_id),
            "spec_files": len([s for s in spec_files if s.stem in jobs_by_id]),
            "nodes": len(nodes),
            "edges": len(edges),
            "node_types": node_type_counts,
            "edge_types": edge_type_counts,
            "provenance_groups": {
                group: provenance_group_counts[group]
                for group in sorted(provenance_group_counts)
            },
        },
        "nodes": nodes,
        "edges": edges,
    }
