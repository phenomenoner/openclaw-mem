"""Authenticated local HTTP gateway for openclaw-mem.

This module intentionally uses the Python standard library so the gateway can be
started from an existing checkout without installing a web framework.  It is a
small governed HTTP wrapper around the existing CLI contracts; the CLI remains
the store/pack/observe implementation owner.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

ROLE_RANK = {"read": 1, "write": 2, "admin": 3, "owner": 4}
ROLE_CAPABILITIES = {
    "read": frozenset({"status.read", "memory.search", "memory.pack", "episodes.query"}),
    "write": frozenset({
        "status.read",
        "memory.search",
        "memory.pack",
        "episodes.query",
        "episodes.append",
        "store.propose",
    }),
    "admin": frozenset({
        "status.read",
        "memory.search",
        "memory.pack",
        "episodes.query",
        "episodes.append",
        "store.propose",
        "archive.export",
    }),
    "owner": frozenset({
        "status.read",
        "memory.search",
        "memory.pack",
        "episodes.query",
        "episodes.append",
        "store.propose",
        "archive.export",
        "store.direct",
    }),
}
CAPABILITY_ALIASES = {
    "status": "status.read",
    "search": "memory.search",
    "pack": "memory.pack",
    "episodes.read": "episodes.query",
    "episodes.write": "episodes.append",
    "append": "episodes.append",
    "propose": "store.propose",
    "store_propose": "store.propose",
    "store.propose": "store.propose",
    "direct_store": "store.direct",
    "direct.store": "store.direct",
    "store_direct": "store.direct",
    "store.direct": "store.direct",
    "export": "archive.export",
    "archive": "archive.export",
}
KNOWN_CAPABILITIES = frozenset().union(*ROLE_CAPABILITIES.values())
_GATEWAY_WRITE_LOCK = threading.RLock()
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_MAX_BODY_BYTES = 128 * 1024
DEFAULT_EXPORT_ROOT = os.path.expanduser("~/.openclaw/workspace/.state/openclaw-mem-gateway-exports")
MIN_TOKEN_CHARS = 24
DEFAULT_AUDIT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_IDEMPOTENCY_TTL_SEC = 24 * 60 * 60


class GatewayTokenPolicy:
    def __init__(self, role: str, capabilities: Iterable[str]) -> None:
        self.capabilities = frozenset(capabilities)
        self.role = _role_for_capabilities(role, self.capabilities)

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


class GatewayConfig:
    def __init__(
        self,
        *,
        db: Optional[str],
        workspace: Optional[str],
        tokens: Mapping[str, str | GatewayTokenPolicy],
        allow_unauthenticated: bool = False,
        allow_direct_store: bool = False,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        cli_timeout_sec: float = 45.0,
        export_root: Optional[str] = None,
        audit_log: Optional[str] = None,
        audit_max_bytes: int = DEFAULT_AUDIT_MAX_BYTES,
        idempotency_ttl_sec: int = DEFAULT_IDEMPOTENCY_TTL_SEC,
        surface_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        default_scope: Optional[str] = None,
        auto_index_workspace_memory: bool = True,
    ) -> None:
        self.db = db
        self.workspace = workspace
        self.tokens = _normalize_token_policies(tokens)
        self.allow_unauthenticated = bool(allow_unauthenticated)
        self.allow_direct_store = bool(allow_direct_store)
        self.max_body_bytes = int(max_body_bytes)
        self.cli_timeout_sec = float(cli_timeout_sec)
        self.export_root = export_root or DEFAULT_EXPORT_ROOT
        self.audit_log = audit_log
        self.audit_max_bytes = int(audit_max_bytes)
        self.idempotency_ttl_sec = int(idempotency_ttl_sec)
        self.surface_id = (surface_id or "").strip() or None
        self.agent_id = (agent_id or "").strip() or None
        self.default_scope = (default_scope or "").strip() or None
        self.auto_index_workspace_memory = bool(auto_index_workspace_memory)


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _role_for_capabilities(requested_role: str, capabilities: Iterable[str]) -> str:
    caps = frozenset(capabilities)
    role = requested_role if requested_role in ROLE_RANK else "read"
    if caps.issubset(ROLE_CAPABILITIES.get(role, frozenset())):
        return role
    containing = [candidate for candidate, candidate_caps in ROLE_CAPABILITIES.items() if caps.issubset(candidate_caps)]
    if containing:
        return min(containing, key=lambda candidate: ROLE_RANK[candidate])
    return role


def _normalize_capability(raw: str) -> Optional[str]:
    cap = raw.strip().lower().replace("_", ".")
    if not cap:
        return None
    cap = CAPABILITY_ALIASES.get(cap, cap)
    if cap in ROLE_CAPABILITIES:
        return cap
    if cap in KNOWN_CAPABILITIES:
        return cap
    return None


def _policy_from_spec(spec: str) -> Optional[GatewayTokenPolicy]:
    parts = [part.strip().lower() for part in spec.replace("+", ",").split(",") if part.strip()]
    if not parts:
        parts = ["read"]
    role = "read"
    capabilities: set[str] = set()
    for part in parts:
        if part in ROLE_CAPABILITIES:
            if ROLE_RANK[part] > ROLE_RANK[role]:
                role = part
            capabilities.update(ROLE_CAPABILITIES[part])
            continue
        cap = _normalize_capability(part)
        if cap is None:
            return None
        capabilities.add(cap)
    if not capabilities:
        return None
    return GatewayTokenPolicy(role=role, capabilities=capabilities)


def _normalize_token_policies(tokens: Mapping[str, str | GatewayTokenPolicy]) -> Dict[str, GatewayTokenPolicy]:
    out: Dict[str, GatewayTokenPolicy] = {}
    for token, spec in tokens.items():
        if isinstance(spec, GatewayTokenPolicy):
            out[token] = spec
            continue
        policy = _policy_from_spec(str(spec or "read"))
        if policy is not None:
            out[token] = policy
    return out


def _parse_tokens(raw_multi: Optional[str], raw_single: Optional[str]) -> Dict[str, GatewayTokenPolicy]:
    """Parse token config without ever returning token text in receipts.

    Supported:
    - OPENCLAW_MEM_GATEWAY_TOKENS='tokenA:read,tokenB:write,tokenC:admin'
    - OPENCLAW_MEM_GATEWAY_TOKENS='tokenD:read+episodes.append+store.propose'
    - OPENCLAW_MEM_GATEWAY_TOKEN='one-token' (admin role, legacy)
    """

    out: Dict[str, GatewayTokenPolicy] = {}
    for item in str(raw_multi or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            token, role = item.rsplit(":", 1)
        elif "=" in item:
            token, role = item.rsplit("=", 1)
        else:
            token, role = item, "read"
        token = token.strip()
        policy = _policy_from_spec(role)
        if token and policy is not None:
            out[token] = policy
    single = str(raw_single or "").strip()
    if single:
        out[single] = GatewayTokenPolicy(role="admin", capabilities=ROLE_CAPABILITIES["admin"])
    return out


def config_from_env(args: argparse.Namespace) -> GatewayConfig:
    tokens = _parse_tokens(
        os.getenv("OPENCLAW_MEM_GATEWAY_TOKENS"),
        os.getenv("OPENCLAW_MEM_GATEWAY_TOKEN"),
    )
    allow_unauth = bool(args.allow_unauthenticated) or _truthy(os.getenv("OPENCLAW_MEM_GATEWAY_ALLOW_UNAUTHENTICATED"))
    if not tokens and not allow_unauth:
        raise SystemExit(
            "refusing to start without auth: set OPENCLAW_MEM_GATEWAY_TOKEN "
            "or OPENCLAW_MEM_GATEWAY_TOKENS, or pass --allow-unauthenticated for local dev only"
        )
    weak = [policy.role for token, policy in tokens.items() if len(token) < MIN_TOKEN_CHARS]
    if weak and not allow_unauth:
        raise SystemExit(f"refusing weak gateway token: minimum {MIN_TOKEN_CHARS} characters")
    return GatewayConfig(
        db=args.db or os.getenv("OPENCLAW_MEM_DB"),
        workspace=args.workspace or os.getenv("OPENCLAW_MEM_WORKSPACE"),
        tokens=tokens,
        allow_unauthenticated=allow_unauth,
        allow_direct_store=bool(args.allow_direct_store) or _truthy(os.getenv("OPENCLAW_MEM_GATEWAY_ALLOW_DIRECT_STORE")),
        max_body_bytes=int(args.max_body_bytes),
        cli_timeout_sec=float(args.cli_timeout_sec),
        export_root=args.export_root or os.getenv("OPENCLAW_MEM_GATEWAY_EXPORT_ROOT") or DEFAULT_EXPORT_ROOT,
        audit_log=args.audit_log or os.getenv("OPENCLAW_MEM_GATEWAY_AUDIT_LOG"),
        audit_max_bytes=int(os.getenv("OPENCLAW_MEM_GATEWAY_AUDIT_MAX_BYTES", str(DEFAULT_AUDIT_MAX_BYTES))),
        idempotency_ttl_sec=int(os.getenv("OPENCLAW_MEM_GATEWAY_IDEMPOTENCY_TTL_SEC", str(DEFAULT_IDEMPOTENCY_TTL_SEC))),
        surface_id=getattr(args, "surface_id", None) or os.getenv("OPENCLAW_MEM_GATEWAY_SURFACE_ID"),
        agent_id=getattr(args, "agent_id", None) or os.getenv("OPENCLAW_MEM_AGENT_ID"),
        default_scope=getattr(args, "default_scope", None) or os.getenv("OPENCLAW_MEM_DEFAULT_SCOPE"),
        auto_index_workspace_memory=not _truthy(os.getenv("OPENCLAW_MEM_GATEWAY_DISABLE_WORKSPACE_MEMORY_INDEX")),
    )


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _digest_payload(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _path_fingerprint(value: Optional[str]) -> Optional[str]:
    """Return a stable public-safe identifier for a local path without exposing it."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        canonical = str(Path(raw).expanduser().resolve())
    except Exception:
        canonical = raw
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _surface_identity(config: GatewayConfig, *, gateway_url_hint: Optional[str] = None) -> Dict[str, Any]:
    identity: Dict[str, Any] = {
        "schema": "openclaw-mem.gateway.surface-identity.v1",
        "service": "openclaw-mem-gateway",
        "surface_id": config.surface_id,
        "agent_id": config.agent_id,
        "default_scope": config.default_scope,
        "db_configured": bool(config.db),
        "db_fingerprint": _path_fingerprint(config.db),
        "workspace_configured": bool(config.workspace),
        "workspace_fingerprint": _path_fingerprint(config.workspace),
        "direct_store_enabled": config.allow_direct_store,
        "source_lanes": ["store", "episodes", "pack", "search", "docs_memory", "workspace_markdown"],
        "auto_index_workspace_memory": config.auto_index_workspace_memory,
    }
    if gateway_url_hint:
        identity["gateway_url_hint"] = gateway_url_hint
    return {k: v for k, v in identity.items() if v is not None}


def _query_variants(query: str) -> List[str]:
    raw = str(query or "").strip()
    variants: List[str] = []
    if not raw:
        return variants

    def add(value: str) -> None:
        cleaned = " ".join(str(value or "").strip().split())
        if cleaned and cleaned != raw and cleaned not in variants:
            variants.append(cleaned)

    punctuation_normalized = re.sub(r"[^\w\s]", " ", raw, flags=re.UNICODE)
    add(punctuation_normalized)
    # Common misspelling observed in cross-agent handoff: yijin-loop-engine -> yijing-loop-engine.
    if re.search(r"yijin", raw, flags=re.IGNORECASE):
        add(re.sub(r"yijin", "yijing", raw, flags=re.IGNORECASE))
    return variants[:5]


def _search_result_count(receipt: Mapping[str, Any]) -> int:
    result = receipt.get("result")
    if isinstance(result, list):
        return len(result)
    if isinstance(result, Mapping):
        docs_results = result.get("results")
        if isinstance(docs_results, list):
            return len(docs_results)
    return 0


def _pack_result_count(receipt: Mapping[str, Any]) -> int:
    result = receipt.get("result")
    if not isinstance(result, Mapping):
        return 0
    context_pack = result.get("context_pack")
    if isinstance(context_pack, Mapping):
        items = context_pack.get("items")
        if isinstance(items, list):
            return len(items)
    citations = result.get("citations")
    if isinstance(citations, list):
        return len(citations)
    return 0


def _workspace_memory_paths(config: GatewayConfig) -> List[str]:
    workspace = str(config.workspace or "").strip()
    if not workspace:
        return []
    root = Path(workspace).expanduser()
    candidates = [
        root / "MEMORY.md",
        root / "memory",
        root / "AGENTS.md",
        root / "SOUL.md",
        root / "USER.md",
    ]
    return [str(p) for p in candidates if p.exists()]


def _workspace_memory_file_count(paths: Iterable[str]) -> int:
    count = 0
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file() and p.suffix.lower() == ".md":
            count += 1
        elif p.is_dir():
            count += sum(1 for child in p.rglob("*.md") if child.is_file())
    return count


def _corpus_status(config: GatewayConfig) -> Dict[str, Any]:
    paths = _workspace_memory_paths(config)
    source_files = _workspace_memory_file_count(paths)
    if config.workspace and not config.auto_index_workspace_memory:
        parity_state = "partial"
    elif config.workspace and paths:
        # Status is honest by default: configured sources exist, but a plain
        # status read does not prove the current DB has indexed every source.
        # Read endpoints attach a refreshed corpus_status after successful ingest.
        parity_state = "unknown"
    else:
        parity_state = "unknown"
    return {
        "schema": "openclaw-mem.gateway.corpus-status.v1",
        "parity_state": parity_state,
        "workspace_memory_index_enabled": bool(config.auto_index_workspace_memory and config.workspace),
        "workspace_memory_sources_configured": len(paths),
        "workspace_memory_files_configured": source_files,
        "source_path_fingerprints": [_path_fingerprint(p) for p in paths],
        "indexed_files": None,
        "missing_paths": None,
        "skipped_private_chunks": None,
        "skipped_secret_like_chunks": None,
        "redaction_policy": {
            "deny_tags": ["[SECRET]", "[PRIVATE]", "[NOEXPORT]", "[NOMEM]"],
            "secret_like_chunks": "skipped",
        },
    }



_DENY_MARKERS = ("[SECRET]", "[PRIVATE]", "[NOEXPORT]", "[NOMEM]")


def _contains_deny_marker(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in _DENY_MARKERS)


def _workspace_markdown_files(config: GatewayConfig) -> List[Path]:
    files: List[Path] = []
    for raw in _workspace_memory_paths(config):
        path = Path(raw).expanduser()
        try:
            root = path.resolve()
            if path.is_file() and path.suffix.lower() == ".md":
                files.append(root)
            elif path.is_dir():
                for child in sorted(path.rglob("*.md")):
                    try:
                        resolved = child.resolve()
                    except OSError:
                        continue
                    if not child.is_file():
                        continue
                    if resolved != root and root not in resolved.parents:
                        continue
                    files.append(resolved)
        except OSError:
            continue
    return files


def _markdown_chunks(text: str, *, max_chars: int = 1600) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for part in re.split(r"\n\s*\n", text):
        piece = part.strip()
        if not piece:
            continue
        if _contains_deny_marker(piece):
            continue
        if current and current_len + len(piece) + 2 > max_chars:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_len = 0
        if len(piece) > max_chars:
            for idx in range(0, len(piece), max_chars):
                sub = piece[idx : idx + max_chars].strip()
                if sub and not _contains_deny_marker(sub):
                    chunks.append(sub)
            continue
        current.append(piece)
        current_len += len(piece) + 2
    if current:
        chunks.append("\n\n".join(current).strip())
    return chunks


def _query_terms(query: str) -> List[str]:
    normalized = re.sub(r"[^\w]+", " ", query.lower(), flags=re.UNICODE)
    terms: List[str] = []
    for term in normalized.split():
        if len(term) < 2:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def _workspace_markdown_search_receipt(config: GatewayConfig, query: str, *, limit: int) -> Dict[str, Any]:
    terms = _query_terms(query)
    if not terms:
        return {"ok": True, "exit_code": 0, "result": []}
    rows: List[Dict[str, Any]] = []
    workspace = Path(str(config.workspace or "")).expanduser() if config.workspace else None
    for file_path in _workspace_markdown_files(config):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for chunk_index, chunk in enumerate(_markdown_chunks(text)):
            haystack_terms = set(_query_terms(chunk))
            matched = [term for term in terms if term in haystack_terms]
            if not matched:
                continue
            # Deterministic lightweight ranking: token coverage + exact phrase bonus + shorter chunk tie-break.
            coverage = len(matched) / max(1, len(terms))
            phrase_bonus = 0.25 if query.lower().strip() in chunk.lower() else 0.0
            score = coverage + phrase_bonus - min(len(chunk), 5000) / 1_000_000
            rel_path = str(file_path)
            if workspace:
                try:
                    rel_path = str(file_path.resolve().relative_to(workspace.resolve()))
                except Exception:
                    rel_path = str(file_path)
            summary = " ".join(chunk.split())[:700]
            if _contains_deny_marker(summary):
                continue
            rows.append({
                "id": f"workspace:{rel_path}:{chunk_index}",
                "kind": "workspace_markdown",
                "ts": None,
                "tool_name": "workspace_markdown_readthrough",
                "summary": summary,
                "summary_en": None,
                "lang": None,
                "score": score,
                "snippet": summary,
                "snippet_en": "",
                "detail_json": json.dumps({
                    "schema": "openclaw-mem.gateway.workspace-markdown-readthrough.v1",
                    "path": rel_path,
                    "chunk_index": chunk_index,
                    "matched_terms": matched,
                    "source": "workspace_markdown",
                }, ensure_ascii=False, sort_keys=True),
            })
    rows.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("id") or "")))
    return {"ok": True, "exit_code": 0, "result": rows[:limit]}

def _refresh_workspace_memory_corpus(config: GatewayConfig) -> Dict[str, Any]:
    paths = _workspace_memory_paths(config)
    status: Dict[str, Any] = _corpus_status(config)
    status.update({"refresh_attempted": False, "refresh_ok": None})
    if not config.auto_index_workspace_memory or not paths:
        return status
    argv = ["docs", "ingest", "--no-embed", "--json"]
    if config.db:
        argv.extend(["--db", config.db])
    for path in paths:
        argv.extend(["--path", path])
    try:
        receipt = _run_cli(config, argv)
    except RuntimeError:
        status.update({
            "refresh_attempted": True,
            "refresh_ok": False,
            "parity_state": "partial",
            "refresh_error": "cli_failed",
        })
        return status
    result = receipt.get("result") if isinstance(receipt, Mapping) else None
    result_map = result if isinstance(result, Mapping) else {}
    files_seen = int(result_map.get("files_seen") or 0)
    files_ingested = int(result_map.get("files_ingested") or 0)
    missing_paths = list(result_map.get("missing_paths") or []) if isinstance(result_map.get("missing_paths"), list) else []
    refresh_ok = bool(receipt.get("ok"))
    complete = refresh_ok and files_seen == files_ingested and not missing_paths and files_seen >= int(status.get("workspace_memory_files_configured") or 0)
    status.update({
        "refresh_attempted": True,
        "refresh_ok": refresh_ok,
        "parity_state": "healthy" if complete else "partial",
        "indexed_files": files_ingested,
        "missing_paths": len(missing_paths),
        "skipped_private_chunks": int(result_map.get("chunks_skipped_private") or 0),
        "skipped_secret_like_chunks": int(result_map.get("chunks_skipped_secret_like") or 0),
        "last_refresh": result_map or None,
    })
    return status


def _docs_pack_receipt_from_search(query: str, docs_receipt: Mapping[str, Any], *, limit: int, budget_tokens: int) -> Dict[str, Any]:
    result = docs_receipt.get("result")
    docs_results = result.get("results") if isinstance(result, Mapping) else []
    if not isinstance(docs_results, list):
        docs_results = []
    items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    used = 0
    for row in docs_results[: max(1, int(limit))]:
        if not isinstance(row, Mapping):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        estimated = max(1, len(text) // 4)
        if used + estimated > max(1, int(budget_tokens)) and items:
            break
        used += estimated
        record_ref = str(row.get("recordRef") or f"docs://{row.get('repo')}/{row.get('path')}#{row.get('chunk_id')}")
        item = {
            "recordRef": record_ref,
            "layer": "L1",
            "type": "docs_memory",
            "summary": text,
            "text": text,
            "kind": row.get("doc_kind"),
            "repo": row.get("repo"),
            "path": row.get("path"),
            "heading_path": row.get("heading_path"),
        }
        items.append(item)
        citations.append({"recordRef": record_ref, "url": None})
    bundle_text = "\n".join(f"- [{item['recordRef']}] {item['text']}" for item in items)
    return {
        "ok": True,
        "exit_code": 0,
        "result": {
            "bundle_text": bundle_text,
            "items": items,
            "citations": citations,
            "context_pack": {
                "schema": "openclaw-mem.context-pack.v1",
                "meta": {"query": query, "budgetTokens": int(budget_tokens), "maxItems": int(limit), "source": "docs_memory_fallback"},
                "bundle_text": bundle_text,
                "items": items,
            },
            "source": "docs_memory_fallback",
        },
    }


def _not_found_diagnostic(
    *,
    endpoint: str,
    query: str,
    result_count: int,
    config: GatewayConfig,
    gateway_url_hint: Optional[str] = None,
    searched_routes: Optional[List[str]] = None,
    fallback_attempts: Optional[List[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "schema": "openclaw-mem.gateway.query-diagnostic.v1",
        "endpoint": endpoint,
        "query": query,
        "normalized_query": " ".join(str(query or "").strip().split()),
        "result_count": int(result_count),
        "empty": int(result_count) == 0,
        "query_variants": _query_variants(query),
        "searched_routes": searched_routes or [],
        "fallback_attempts": list(fallback_attempts or []),
        "surface_identity": _surface_identity(config, gateway_url_hint=gateway_url_hint),
        "hint": "Empty results mean this specific surface had no match; compare db_fingerprint/surface_id/scope across agents before concluding shared memory is missing." if int(result_count) == 0 else None,
    }


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _coerce_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 500) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_float(value: Any, *, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _require_text(body: Mapping[str, Any], key: str, *, max_chars: int = 12000) -> str:
    value = str(body.get(key) or "").strip()
    if not value:
        raise ValueError(f"missing required field: {key}")
    if len(value) > max_chars:
        raise ValueError(f"field too large: {key}")
    return value


def _optional_text(body: Mapping[str, Any], key: str, *, max_chars: int = 12000) -> Optional[str]:
    if key not in body or body.get(key) is None:
        return None
    value = str(body.get(key) or "").strip()
    if not value:
        return None
    if len(value) > max_chars:
        raise ValueError(f"field too large: {key}")
    return value


def _read_only_cli_argv(argv: List[str]) -> bool:
    if not argv:
        return False
    first = argv[0]
    if first in {"search", "pack", "vsearch", "hybrid"}:
        return True
    if first == "docs" and len(argv) > 1 and argv[1] == "search":
        return True
    if first == "episodes" and len(argv) > 1 and argv[1] == "query":
        return True
    return False


def _run_cli(config: GatewayConfig, argv: Iterable[str], *, stdin: Optional[str] = None) -> Dict[str, Any]:
    argv_list = list(argv)
    cmd = [sys.executable, "-m", "openclaw_mem", *argv_list]
    env = os.environ.copy()
    if config.workspace:
        env["OPENCLAW_MEM_WORKSPACE"] = config.workspace
    if _read_only_cli_argv(argv_list):
        env["OPENCLAW_MEM_SKIP_INIT_DB"] = "1"
        env["OPENCLAW_MEM_READONLY_DB"] = "1"
    proc = subprocess.run(
        cmd,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=config.cli_timeout_sec,
        env=env,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = {"text": stdout}
    receipt: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "result": parsed,
    }
    if stderr:
        # Never echo CLI stderr to remote clients; it can contain local paths or internals.
        safe_tail = stderr[-2000:].replace("\n", "\\n")
        sys.stderr.write(f"openclaw-mem-gateway cli stderr tail: {safe_tail}\n")
    if proc.returncode != 0:
        raise RuntimeError(json.dumps({"ok": False, "exit_code": proc.returncode}, ensure_ascii=False))
    return receipt


class MemoryGatewayHandler(BaseHTTPRequestHandler):
    server_version = "openclaw-mem-gateway/0.1"

    @property
    def config(self) -> GatewayConfig:
        return getattr(self.server, "gateway_config")  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - stdlib hook
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def _policy_and_token_id(self) -> Tuple[Optional[GatewayTokenPolicy], Optional[str]]:
        if self.config.allow_unauthenticated:
            return GatewayTokenPolicy(role="owner", capabilities=ROLE_CAPABILITIES["owner"]), "dev-unauthenticated"
        auth = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not auth.startswith(prefix):
            return None, None
        token = auth[len(prefix) :].strip()
        matched_policy: Optional[GatewayTokenPolicy] = None
        for configured_token, configured_policy in self.config.tokens.items():
            if hmac.compare_digest(token, configured_token):
                matched_policy = configured_policy
        if matched_policy is None:
            return None, None
        return matched_policy, _token_id(token)

    def _role_and_token_id(self) -> Tuple[Optional[str], Optional[str]]:
        policy, token_id = self._policy_and_token_id()
        return (policy.role if policy else None), token_id

    def _gateway_url_hint(self) -> Optional[str]:
        host = str(self.headers.get("Host") or "").strip()
        if not host:
            return None
        return f"http://{host}"

    def _capabilities_for_request(self) -> Tuple[Optional[frozenset[str]], Optional[str], Optional[str]]:
        policy, token_id = self._policy_and_token_id()
        if policy is None:
            return None, None, None
        return policy.capabilities, policy.role, token_id

    def _require_role(self, required: str) -> Optional[str]:
        role, _token = self._role_and_token_id()
        if role is None:
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "missing_or_invalid_bearer_token"})
            return None
        if ROLE_RANK.get(role, 0) < ROLE_RANK[required]:
            _json_response(self, HTTPStatus.FORBIDDEN, {"ok": False, "error": "insufficient_role", "required": required})
            return None
        return role

    def _require_capability(self, required: str) -> Optional[str]:
        capabilities, role, _token = self._capabilities_for_request()
        if capabilities is None or role is None:
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "missing_or_invalid_bearer_token"})
            return None
        if required not in capabilities:
            _json_response(self, HTTPStatus.FORBIDDEN, {"ok": False, "error": "insufficient_capability", "required": required})
            return None
        return role

    def _read_json_body(self) -> Dict[str, Any]:
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except Exception as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0:
            raise ValueError("invalid Content-Length")
        if length > self.config.max_body_bytes:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON body must be an object")
        return parsed

    def _write_audit(self, *, endpoint: str, action: str, body: Mapping[str, Any], ok: bool, result: str) -> None:
        audit_log = self.config.audit_log
        if not audit_log:
            return
        role, token_id = self._role_and_token_id()
        row = {
            "schema": "openclaw-mem.gateway.audit.v1",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "endpoint": endpoint,
            "action": action,
            "role": role,
            "token_id": token_id,
            "payload_sha256": _digest_payload(body),
            "ok": bool(ok),
            "result": result,
        }
        path = Path(audit_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._append_jsonl(path, row)

    def _append_jsonl(self, path: Path, row: Mapping[str, Any]) -> None:
        with _GATEWAY_WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and self.config.audit_max_bytes > 0 and path.stat().st_size > self.config.audit_max_bytes:
                rotated = path.with_suffix(path.suffix + ".1")
                try:
                    rotated.unlink()
                except FileNotFoundError:
                    pass
                path.rename(rotated)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    def _resolve_export_to(self, raw: str) -> str:
        root = Path(self.config.export_root).expanduser().resolve()
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("export path outside configured export root")
        return str(resolved)

    def _idempotency_store_path(self) -> Optional[Path]:
        if self.config.audit_log:
            return Path(self.config.audit_log).with_name("idempotency.jsonl")
        return Path(self.config.export_root).expanduser() / "idempotency.jsonl"

    def _idempotency_lookup(self, *, endpoint: str, body: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        key = (self.headers.get("Idempotency-Key") or "").strip()
        if not key:
            return None
        if len(key) > 200:
            raise ValueError("Idempotency-Key too large")
        path = self._idempotency_store_path()
        if path is None or not path.exists():
            return None
        _role, token_id = self._role_and_token_id()
        request_id = hashlib.sha256(f"{endpoint}\0{token_id}\0{key}".encode("utf-8")).hexdigest()
        payload_hash = _digest_payload(body)
        now = time.time()
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            try:
                row_ts = float(row.get("created_unix", 0))
            except Exception:
                row_ts = 0.0
            if self.config.idempotency_ttl_sec > 0 and row_ts and now - row_ts > self.config.idempotency_ttl_sec:
                continue
            if row.get("request_id") == request_id:
                if row.get("payload_sha256") != payload_hash:
                    raise ValueError("Idempotency-Key reused with different payload")
                response = row.get("response")
                if isinstance(response, dict):
                    return response
        return None

    def _idempotency_record(self, *, endpoint: str, body: Mapping[str, Any], response: Mapping[str, Any]) -> None:
        key = (self.headers.get("Idempotency-Key") or "").strip()
        if not key:
            return
        path = self._idempotency_store_path()
        if path is None:
            return
        _role, token_id = self._role_and_token_id()
        request_id = hashlib.sha256(f"{endpoint}\0{token_id}\0{key}".encode("utf-8")).hexdigest()
        row = {
            "schema": "openclaw-mem.gateway.idempotency.v1",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "created_unix": time.time(),
            "request_id": request_id,
            "endpoint": endpoint,
            "token_id": token_id,
            "payload_sha256": _digest_payload(body),
            "response": response,
        }
        self._append_jsonl(path, row)

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            _json_response(self, HTTPStatus.OK, {"ok": True, "service": "openclaw-mem-gateway"})
            return
        if path == "/v1/status":
            role = self._require_capability("status.read")
            if role is None:
                return
            capabilities, _role, _token = self._capabilities_for_request()
            payload = {
                "ok": True,
                "service": "openclaw-mem-gateway",
                "auth": "enabled" if not self.config.allow_unauthenticated else "disabled-dev",
                "role": role,
                "capabilities": sorted(capabilities or []),
                "db_configured": bool(self.config.db),
                "workspace_configured": bool(self.config.workspace),
                "direct_store_enabled": self.config.allow_direct_store,
                "surface_identity": _surface_identity(self.config, gateway_url_hint=self._gateway_url_hint()),
                "corpus_status": _corpus_status(self.config),
            }
            _json_response(self, HTTPStatus.OK, payload)
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib method name
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/v1/search":
                self._handle_search()
            elif path == "/v1/pack":
                self._handle_pack()
            elif path == "/v1/episodes/query":
                self._handle_episodes_query()
            elif path == "/v1/episodes/append":
                self._handle_episodes_append()
            elif path == "/v1/store/propose":
                self._handle_store_propose()
            elif path == "/v1/store":
                self._handle_store()
            elif path == "/v1/archive/export-canonical":
                self._handle_archive_export_canonical()
            else:
                _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except subprocess.TimeoutExpired:
            _json_response(self, HTTPStatus.GATEWAY_TIMEOUT, {"ok": False, "error": "cli_timeout"})
        except RuntimeError:
            _json_response(self, HTTPStatus.BAD_GATEWAY, {"ok": False, "error": "cli_failed"})
        except Exception as exc:  # pragma: no cover - defensive boundary
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": type(exc).__name__})

    def _handle_search(self) -> None:
        if self._require_capability("memory.search") is None:
            return
        body = self._read_json_body()
        query = _require_text(body, "query", max_chars=2000)
        limit = _coerce_int(body.get("limit"), default=10, maximum=100)
        corpus_status = _refresh_workspace_memory_corpus(self.config)

        def run_search(search_query: str) -> Dict[str, Any]:
            argv = ["search", "--limit", str(limit), "--json"]
            if self.config.db:
                argv.extend(["--db", self.config.db])
            argv.extend(["--", search_query])
            return _run_cli(self.config, argv)

        def run_docs_search(search_query: str) -> Dict[str, Any]:
            argv = ["docs", "search", "--limit", str(limit), "--json"]
            if self.config.db:
                argv.extend(["--db", self.config.db])
            argv.append(search_query)
            return _run_cli(self.config, argv)

        fallback_attempts: List[Mapping[str, Any]] = []
        searched_routes = ["cli.search"]
        try:
            receipt = run_search(query)
            result_count = _search_result_count(receipt)
        except RuntimeError:
            receipt = {"ok": False, "exit_code": 1, "result": []}
            result_count = 0
            fallback_attempts.append({"route": "cli.search", "query": query, "result_count": 0, "error": "cli_failed"})
        if result_count == 0:
            for variant in _query_variants(query):
                try:
                    variant_receipt = run_search(variant)
                    variant_count = _search_result_count(variant_receipt)
                except RuntimeError:
                    variant_receipt = {"ok": False, "exit_code": 1, "result": []}
                    variant_count = 0
                    fallback_attempts.append({"route": "cli.search", "query": variant, "result_count": 0, "error": "cli_failed"})
                    continue
                fallback_attempts.append({"route": "cli.search", "query": variant, "result_count": variant_count})
                if variant_count > 0:
                    receipt = variant_receipt
                    result_count = variant_count
                    break
        if result_count == 0:
            searched_routes.append("cli.docs.search")
            try:
                docs_receipt = run_docs_search(query)
                docs_count = _search_result_count(docs_receipt)
            except RuntimeError:
                docs_receipt = {"ok": False, "exit_code": 1, "result": []}
                docs_count = 0
                fallback_attempts.append({"route": "cli.docs.search", "query": query, "result_count": 0, "error": "cli_failed"})
            else:
                fallback_attempts.append({"route": "cli.docs.search", "query": query, "result_count": docs_count})
            if docs_count > 0:
                receipt = docs_receipt
                result_count = docs_count
            else:
                for variant in _query_variants(query):
                    try:
                        variant_docs_receipt = run_docs_search(variant)
                        variant_docs_count = _search_result_count(variant_docs_receipt)
                    except RuntimeError:
                        fallback_attempts.append({"route": "cli.docs.search", "query": variant, "result_count": 0, "error": "cli_failed"})
                        continue
                    fallback_attempts.append({"route": "cli.docs.search", "query": variant, "result_count": variant_docs_count})
                    if variant_docs_count > 0:
                        receipt = variant_docs_receipt
                        result_count = variant_docs_count
                        break
        if result_count == 0:
            searched_routes.append("workspace_markdown_readthrough")
            md_receipt = _workspace_markdown_search_receipt(self.config, query, limit=limit)
            md_count = _search_result_count(md_receipt)
            fallback_attempts.append({"route": "workspace_markdown_readthrough", "query": query, "result_count": md_count})
            if md_count > 0:
                receipt = md_receipt
                result_count = md_count
            else:
                for variant in _query_variants(query):
                    variant_md_receipt = _workspace_markdown_search_receipt(self.config, variant, limit=limit)
                    variant_md_count = _search_result_count(variant_md_receipt)
                    fallback_attempts.append({"route": "workspace_markdown_readthrough", "query": variant, "result_count": variant_md_count})
                    if variant_md_count > 0:
                        receipt = variant_md_receipt
                        result_count = variant_md_count
                        break
        diagnostic = _not_found_diagnostic(
            endpoint="/v1/search",
            query=query,
            result_count=result_count,
            config=self.config,
            gateway_url_hint=self._gateway_url_hint(),
            searched_routes=searched_routes,
            fallback_attempts=fallback_attempts,
        )
        diagnostic["corpus_status"] = corpus_status
        _json_response(self, HTTPStatus.OK, {"ok": True, "receipt": receipt, "diagnostic": diagnostic})

    def _handle_pack(self) -> None:
        if self._require_capability("memory.pack") is None:
            return
        body = self._read_json_body()
        query = _require_text(body, "query", max_chars=4000)
        corpus_status = _refresh_workspace_memory_corpus(self.config)
        limit = _coerce_int(body.get("limit"), default=12, maximum=50)
        budget_tokens = _coerce_int(body.get("budget_tokens"), default=1200, maximum=20000)
        argv = [
            "pack",
            "--json",
            "--query",
            query,
            "--limit",
            str(limit),
            "--budget-tokens",
            str(budget_tokens),
        ]
        query_en = _optional_text(body, "query_en", max_chars=4000)
        if query_en:
            argv.extend(["--query-en", query_en])
        graph_scope = _optional_text(body, "graph_scope", max_chars=200)
        if graph_scope:
            argv.extend(["--graph-scope", graph_scope])
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        searched_routes = ["cli.pack"]
        fallback_attempts: List[Mapping[str, Any]] = []
        result_count = _pack_result_count(receipt)
        if result_count == 0:
            docs_argv = ["docs", "search", "--limit", str(limit), "--json"]
            if self.config.db:
                docs_argv.extend(["--db", self.config.db])
            docs_argv.append(query)
            docs_receipt = _run_cli(self.config, docs_argv)
            docs_count = _search_result_count(docs_receipt)
            searched_routes.append("cli.docs.search")
            fallback_attempts.append({"route": "cli.docs.search", "query": query, "result_count": docs_count})
            if docs_count > 0:
                receipt = _docs_pack_receipt_from_search(query, docs_receipt, limit=limit, budget_tokens=budget_tokens)
                result_count = _pack_result_count(receipt)
            else:
                for variant in _query_variants(query):
                    variant_docs_argv = ["docs", "search", "--limit", str(limit), "--json"]
                    if self.config.db:
                        variant_docs_argv.extend(["--db", self.config.db])
                    variant_docs_argv.append(variant)
                    variant_docs_receipt = _run_cli(self.config, variant_docs_argv)
                    variant_docs_count = _search_result_count(variant_docs_receipt)
                    fallback_attempts.append({"route": "cli.docs.search", "query": variant, "result_count": variant_docs_count})
                    if variant_docs_count > 0:
                        receipt = _docs_pack_receipt_from_search(variant, variant_docs_receipt, limit=limit, budget_tokens=budget_tokens)
                        result_count = _pack_result_count(receipt)
                        break
        diagnostic = _not_found_diagnostic(
            endpoint="/v1/pack",
            query=query,
            result_count=result_count,
            config=self.config,
            gateway_url_hint=self._gateway_url_hint(),
            searched_routes=searched_routes,
            fallback_attempts=fallback_attempts,
        )
        diagnostic["corpus_status"] = corpus_status
        _json_response(self, HTTPStatus.OK, {"ok": True, "receipt": receipt, "diagnostic": diagnostic})

    def _handle_episodes_query(self) -> None:
        if self._require_capability("episodes.query") is None:
            return
        body = self._read_json_body()
        argv = ["episodes", "query", "--json", "--limit", str(_coerce_int(body.get("limit"), default=50, maximum=500))]
        scope = _optional_text(body, "scope", max_chars=200)
        if scope:
            argv.extend(["--scope", scope])
        elif body.get("global") is True:
            argv.append("--global")
        else:
            raise ValueError("missing required field: scope")
        session_id = _optional_text(body, "session_id", max_chars=500)
        if session_id:
            argv.extend(["--session-id", session_id])
        types = body.get("types") or []
        if not isinstance(types, list) or not all(isinstance(typ, str) for typ in types):
            raise ValueError("types must be a list of strings")
        for typ in types:
            argv.extend(["--type", str(typ)])
        if body.get("include_payload") is True:
            argv.append("--include-payload")
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        _json_response(self, HTTPStatus.OK, {"ok": True, "receipt": receipt})

    def _handle_episodes_append(self) -> None:
        if self._require_capability("episodes.append") is None:
            return
        body = self._read_json_body()
        with _GATEWAY_WRITE_LOCK:
            cached = self._idempotency_lookup(endpoint="/v1/episodes/append", body=body)
            if cached is not None:
                _json_response(self, HTTPStatus.OK, cached)
                return
            argv = [
                "episodes",
                "append",
                "--json",
                "--scope",
                _require_text(body, "scope", max_chars=200),
                "--session-id",
                _require_text(body, "session_id", max_chars=500),
                "--agent-id",
                _require_text(body, "agent_id", max_chars=200),
                "--type",
                _require_text(body, "type", max_chars=80),
                "--summary",
                _require_text(body, "summary", max_chars=2000),
            ]
            if "payload" in body:
                argv.extend(["--payload-json", json.dumps(body.get("payload"), ensure_ascii=False)])
            if "refs" in body:
                argv.extend(["--refs-json", json.dumps(body.get("refs"), ensure_ascii=False)])
            if self.config.db:
                argv.extend(["--db", self.config.db])
            receipt = _run_cli(self.config, argv)
            response = {"ok": True, "receipt": receipt}
            self._idempotency_record(endpoint="/v1/episodes/append", body=body, response=response)
            self._write_audit(endpoint="/v1/episodes/append", action="episodes.append", body=body, ok=True, result="ok")
        _json_response(self, HTTPStatus.OK, response)

    def _handle_store_propose(self) -> None:
        if self._require_capability("store.propose") is None:
            return
        body = self._read_json_body()
        with _GATEWAY_WRITE_LOCK:
            cached = self._idempotency_lookup(endpoint="/v1/store/propose", body=body)
            if cached is not None:
                _json_response(self, HTTPStatus.OK, cached)
                return
            scope = _require_text(body, "scope", max_chars=200)
            agent_id = _require_text(body, "agent_id", max_chars=200)
            text = _require_text(body, "text", max_chars=8000)
            category = str(body.get("category") or "other").strip().lower()
            if category not in {"fact", "preference", "decision", "entity", "task", "other"}:
                raise ValueError("invalid category")
            detail = {
                "schema": "openclaw-mem.gateway.store-proposal.v0",
                "scope": scope,
                "agent_id": agent_id,
                "category": category,
                "importance": _coerce_float(body.get("importance"), default=0.5),
                "text": text,
                "provenance": body.get("provenance") if isinstance(body.get("provenance"), dict) else {},
                "created_ms": int(time.time() * 1000),
            }
            row = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "kind": "memory.proposal",
                "tool_name": "gateway.store.propose",
                "summary": f"[{scope}] {text[:500]}",
                "detail": detail,
            }
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False) as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                temp_path = fh.name
            try:
                argv = ["ingest", "--file", temp_path, "--json"]
                if self.config.db:
                    argv.extend(["--db", self.config.db])
                receipt = _run_cli(self.config, argv)
            finally:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
            response = {"ok": True, "mode": "proposal", "receipt": receipt}
            self._idempotency_record(endpoint="/v1/store/propose", body=body, response=response)
            self._write_audit(endpoint="/v1/store/propose", action="store.propose", body=body, ok=True, result="ok")
        _json_response(self, HTTPStatus.OK, response)

    def _handle_store(self) -> None:
        role = self._require_capability("store.direct")
        if role is None:
            return
        if not self.config.allow_direct_store:
            _json_response(
                self,
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "direct_store_disabled", "hint": "set OPENCLAW_MEM_GATEWAY_ALLOW_DIRECT_STORE=1 and use an owner-capability token"},
            )
            return
        body = self._read_json_body()
        text = _require_text(body, "text", max_chars=8000)
        category = str(body.get("category") or "fact").strip().lower()
        if category not in {"fact", "preference", "decision", "entity", "task", "other"}:
            raise ValueError("invalid category")
        argv = [
            "store",
            text,
            "--category",
            category,
            "--importance",
            str(_coerce_float(body.get("importance"), default=0.6)),
            "--json",
        ]
        text_en = _optional_text(body, "text_en", max_chars=8000)
        if text_en:
            argv.extend(["--text-en", text_en])
        lang = _optional_text(body, "lang", max_chars=20)
        if lang:
            argv.extend(["--lang", lang])
        workspace = _optional_text(body, "workspace", max_chars=2000) or self.config.workspace
        if workspace:
            argv.extend(["--workspace", workspace])
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        self._write_audit(endpoint="/v1/store", action="store.direct", body=body, ok=True, result="ok")
        _json_response(self, HTTPStatus.OK, {"ok": True, "mode": "direct_store", "receipt": receipt})

    def _handle_archive_export_canonical(self) -> None:
        if self._require_capability("archive.export") is None:
            return
        body = self._read_json_body()
        dry_run = body.get("dry_run", True) is not False
        argv = ["capsule", "export-canonical", "--json"]
        if dry_run:
            argv.append("--dry-run")
        to_path = _optional_text(body, "to", max_chars=2000)
        if to_path:
            argv.extend(["--to", self._resolve_export_to(to_path)])
        if self.config.db:
            argv.extend(["--db", self.config.db])
        receipt = _run_cli(self.config, argv)
        self._write_audit(endpoint="/v1/archive/export-canonical", action="archive.export_canonical", body=body, ok=True, result="dry_run" if dry_run else "ok")
        _json_response(self, HTTPStatus.OK, {"ok": True, "dry_run": dry_run, "receipt": receipt})


def build_server(host: str, port: int, config: GatewayConfig) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, int(port)), MemoryGatewayHandler)
    setattr(server, "gateway_config", config)
    return server


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated HTTP gateway for openclaw-mem")
    parser.add_argument("--host", default=os.getenv("OPENCLAW_MEM_GATEWAY_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("OPENCLAW_MEM_GATEWAY_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--db", default=None, help="SQLite DB path (default: OPENCLAW_MEM_DB / CLI default)")
    parser.add_argument("--workspace", default=None, help="Workspace root for direct store markdown append")
    parser.add_argument("--max-body-bytes", type=int, default=int(os.getenv("OPENCLAW_MEM_GATEWAY_MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))))
    parser.add_argument("--cli-timeout-sec", type=float, default=float(os.getenv("OPENCLAW_MEM_GATEWAY_CLI_TIMEOUT_SEC", "45")))
    parser.add_argument("--allow-direct-store", action="store_true", help="Enable admin-only /v1/store durable writes")
    parser.add_argument("--export-root", default=None, help="Allowlisted root for admin canonical exports")
    parser.add_argument("--audit-log", default=None, help="Append-only JSONL audit log for gateway write/admin actions")
    parser.add_argument("--surface-id", default=None, help="Public-safe label for this memory surface, returned in diagnostics")
    parser.add_argument("--agent-id", default=None, help="Public-safe agent id label for diagnostics")
    parser.add_argument("--default-scope", default=None, help="Default memory scope label for diagnostics")
    parser.add_argument("--allow-unauthenticated", action="store_true", help="INSECURE local dev only; disables bearer auth")
    args = parser.parse_args(argv)

    config = config_from_env(args)
    if args.host not in {"127.0.0.1", "localhost", "::1"} and config.allow_unauthenticated:
        raise SystemExit("refusing unauthenticated non-local bind")
    server = build_server(args.host, args.port, config)
    print(
        json.dumps(
            {
                "ok": True,
                "service": "openclaw-mem-gateway",
                "bind": f"{args.host}:{args.port}",
                "auth": "enabled" if not config.allow_unauthenticated else "disabled-dev",
                "direct_store_enabled": config.allow_direct_store,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
