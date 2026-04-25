"""Canonical project/repository grounding helpers.

This module is intentionally local and deterministic.  Recall results may suggest
an adjacent project, but file-changing workflows need a small ground-truth check
against the filesystem and git remotes before acting.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_WORD_RE = re.compile(r"[\w\-\.]+", re.UNICODE)


@dataclass(frozen=True)
class ProjectCandidate:
    name: str
    path: str
    remote: str | None = None
    branch: str | None = None
    aliases: tuple[str, ...] = ()
    source: str = "scan"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "remote": self.remote,
            "branch": self.branch,
            "aliases": list(self.aliases),
            "source": self.source,
        }


@dataclass(frozen=True)
class ProjectResolution:
    query: str
    status: str
    candidate: ProjectCandidate | None
    confidence: float
    reasons: tuple[str, ...]
    alternatives: tuple[ProjectCandidate, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "status": self.status,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "alternatives": [item.to_dict() for item in self.alternatives],
        }


def normalize_token(text: str) -> str:
    raw = str(text or "").lower().replace("-", " ").replace("_", " ").replace(".", " ")
    return " ".join(_WORD_RE.findall(raw))


def compact_token(text: str) -> str:
    return re.sub(r"[\W_]+", "", str(text or "").lower(), flags=re.UNICODE)


def _run_git(path: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(path),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def _remote_url(path: Path) -> str | None:
    return _run_git(path, "config", "--get", "remote.origin.url")


def _branch(path: Path) -> str | None:
    return _run_git(path, "branch", "--show-current")


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _candidate_from_path(path: Path, *, aliases: Iterable[str] = (), source: str = "scan") -> ProjectCandidate:
    clean_aliases = tuple(dict.fromkeys(a.strip() for a in aliases if str(a).strip()))
    return ProjectCandidate(
        name=path.name,
        path=str(path),
        remote=_remote_url(path),
        branch=_branch(path),
        aliases=clean_aliases,
        source=source,
    )


def load_project_map(path: str | os.PathLike[str] | None) -> list[ProjectCandidate]:
    """Load optional public-safe project aliases.

    Accepted JSON shapes:
    - [{"name": "alpha", "path": "/repo", "aliases": ["a"]}]
    - {"projects": [...]}.
    """
    if not path:
        return []
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.get("projects") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("project map must be a list or object with a projects list")
    out: list[ProjectCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        repo_path = Path(raw_path).expanduser().resolve()
        aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
        name = str(item.get("name") or repo_path.name).strip() or repo_path.name
        candidate = _candidate_from_path(repo_path, aliases=[name, *[str(a) for a in aliases]], source="map")
        out.append(candidate)
    return out


def scan_git_repos(root: str | os.PathLike[str], *, max_depth: int = 2) -> list[ProjectCandidate]:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        return []
    out: list[ProjectCandidate] = []
    seen: set[str] = set()
    stack: list[tuple[Path, int]] = [(base, 0)]
    ignored = {".git", ".venv", "node_modules", "site", "dist", "__pycache__"}
    while stack:
        cur, depth = stack.pop()
        if cur.name in ignored:
            continue
        if _is_git_repo(cur):
            key = str(cur)
            if key not in seen:
                seen.add(key)
                out.append(_candidate_from_path(cur, aliases=[cur.name], source="scan"))
        if depth >= max_depth:
            continue
        try:
            children = sorted([p for p in cur.iterdir() if p.is_dir()], key=lambda p: p.name)
        except OSError:
            continue
        for child in reversed(children):
            if child.name not in ignored and not child.name.startswith("."):
                stack.append((child, depth + 1))
    return out


def _score(query_norm: str, candidate: ProjectCandidate) -> tuple[float, tuple[str, ...]]:
    reasons: list[str] = []
    names = [candidate.name, *candidate.aliases]
    best = 0.0
    for raw in names:
        alias = normalize_token(raw)
        if not alias:
            continue
        alias_compact = compact_token(alias)
        query_compact = compact_token(query_norm)
        if alias in query_norm or alias_compact in query_compact:
            score = 1.0 if alias == query_norm or alias_compact == query_compact else 0.88
            reasons.append(f"alias_match:{raw}")
        else:
            alias_tokens = set(alias.split())
            query_tokens = set(query_norm.split())
            overlap = alias_tokens & query_tokens
            score = min(0.72, len(overlap) / max(len(alias_tokens), 1)) if overlap else 0.0
            if overlap:
                reasons.append("token_overlap:" + ",".join(sorted(overlap)))
        best = max(best, score)
    return best, tuple(dict.fromkeys(reasons))


def resolve_project(
    query: str,
    *,
    workspace_root: str | os.PathLike[str] = ".",
    project_map: str | os.PathLike[str] | None = None,
    max_depth: int = 2,
    min_confidence: float = 0.74,
) -> ProjectResolution:
    query_norm = normalize_token(query)
    candidates_by_path: dict[str, ProjectCandidate] = {}
    for candidate in [*scan_git_repos(workspace_root, max_depth=max_depth), *load_project_map(project_map)]:
        existing = candidates_by_path.get(candidate.path)
        if existing:
            aliases = tuple(dict.fromkeys([*existing.aliases, *candidate.aliases, existing.name, candidate.name]))
            source = "map+scan" if "map" in {existing.source, candidate.source} else existing.source
            candidates_by_path[candidate.path] = ProjectCandidate(
                name=candidate.name or existing.name,
                path=candidate.path,
                remote=candidate.remote or existing.remote,
                branch=candidate.branch or existing.branch,
                aliases=aliases,
                source=source,
            )
        else:
            candidates_by_path[candidate.path] = candidate

    scored: list[tuple[float, tuple[str, ...], ProjectCandidate]] = []
    for candidate in candidates_by_path.values():
        score, reasons = _score(query_norm, candidate)
        if score > 0:
            scored.append((score, reasons, candidate))
    scored.sort(key=lambda item: (-item[0], item[2].name, item[2].path))

    if not scored:
        return ProjectResolution(query, "unresolved", None, 0.0, ("no_candidate_match",))
    top_score, top_reasons, top = scored[0]
    alternatives = tuple(item[2] for item in scored[1:4])
    if len(scored) > 1 and scored[1][0] >= top_score - 0.05:
        return ProjectResolution(query, "ambiguous", top, top_score, (*top_reasons, "near_tie"), alternatives)
    if top_score < min_confidence:
        return ProjectResolution(query, "low_confidence", top, top_score, (*top_reasons, "below_min_confidence"), alternatives)
    return ProjectResolution(query, "resolved", top, top_score, top_reasons, alternatives)


def evaluate_routing_probes(
    probes: Iterable[dict[str, Any]],
    *,
    workspace_root: str | os.PathLike[str],
    project_map: str | os.PathLike[str] | None = None,
    max_depth: int = 2,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    passed = 0
    total = 0
    for probe in probes:
        if not isinstance(probe, dict):
            continue
        query = str(probe.get("query") or "").strip()
        if not query:
            continue
        total += 1
        resolution = resolve_project(query, workspace_root=workspace_root, project_map=project_map, max_depth=max_depth)
        candidate = resolution.candidate
        expected_path = str(probe.get("expected_path") or "").strip()
        expected_remote_contains = str(probe.get("expected_remote_contains") or "").strip()
        forbidden_path = str(probe.get("forbidden_path") or "").strip()
        failures: list[str] = []
        if resolution.status != "resolved":
            failures.append(f"status:{resolution.status}")
        if expected_path and (not candidate or Path(candidate.path).resolve() != Path(expected_path).expanduser().resolve()):
            failures.append("expected_path_mismatch")
        if expected_remote_contains and (not candidate or expected_remote_contains not in str(candidate.remote or "")):
            failures.append("expected_remote_mismatch")
        if forbidden_path and candidate and Path(candidate.path).resolve() == Path(forbidden_path).expanduser().resolve():
            failures.append("forbidden_path_selected")
        ok = not failures
        if ok:
            passed += 1
        items.append({
            "query": query,
            "ok": ok,
            "failures": failures,
            "expected_path": expected_path or None,
            "forbidden_path": forbidden_path or None,
            "resolution": resolution.to_dict(),
        })
    return {
        "kind": "openclaw-mem.routing.eval.v0",
        "summary": {"total": total, "passed": passed, "failed": total - passed},
        "items": items,
    }


def load_probes(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    p = Path(path).expanduser()
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.get("probes") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("probe file must be a list or object with a probes list")
    return [item for item in items if isinstance(item, dict)]
