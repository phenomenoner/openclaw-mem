#!/usr/bin/env python3
"""openclaw-mem CLI

AI-native design:
- Non-interactive (no prompts)
- Structured output via --json
- Rich examples in help
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional, Tuple

from openclaw_mem import __version__
from openclaw_mem import defaults
from openclaw_mem import pack_trace_v1
from openclaw_mem.artifact_sidecar import (
    fetch_artifact,
    parse_artifact_handle,
    peek_artifact,
    stash_artifact,
)
from openclaw_mem.docs_memory import (
    chunk_content_hash,
    chunk_markdown,
    detect_doc_kind,
    fuse_rankings_rrf,
    make_doc_id,
    make_record_ref,
    parse_ts_hint,
    rrf_components,
)
from openclaw_mem.vector import l2_norm, pack_f32, rank_cosine, rank_rrf
from openclaw_mem.optimization import build_memory_health_review, render_memory_health_review
from openclaw_mem.graph.drift import query_drift
from openclaw_mem.graph.query import (
    query_downstream,
    query_filter_nodes,
    query_lineage,
    query_provenance,
    query_refresh_receipts,
    query_subgraph,
    query_upstream,
    query_writers,
)
from openclaw_mem.graph.topology_diff import compare_topology_files
from openclaw_mem.graph.topology_extract import extract_topology_seed
from openclaw_mem.scope import normalize_scope_token as _normalize_scope_token
from openclaw_mem.task_markers import summary_has_task_marker as _summary_has_task_marker_impl

def _resolve_home_dir() -> str:
    """Best-effort OpenClaw-style home resolution.

    - OPENCLAW_HOME wins
    - then OS/user home (~)
    """

    explicit = (os.getenv("OPENCLAW_HOME") or "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.abspath(os.path.expanduser("~"))


def _resolve_state_dir() -> str:
    """Resolve OpenClaw state dir (best-effort).

    If the user overrides OpenClaw with OPENCLAW_STATE_DIR, openclaw-mem should
    follow it to avoid splitting state across directories.
    """

    override = (os.getenv("OPENCLAW_STATE_DIR") or os.getenv("CLAWDBOT_STATE_DIR") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(_resolve_home_dir(), ".openclaw")


def _resolve_openclaw_config_path() -> str:
    override = (os.getenv("OPENCLAW_CONFIG_PATH") or os.getenv("CLAWDBOT_CONFIG_PATH") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(_resolve_state_dir(), "openclaw.json")


STATE_DIR = _resolve_state_dir()
DEFAULT_INDEX_PATH = os.path.join(STATE_DIR, "memory", "openclaw-mem", "observations-index.md")
DEFAULT_GRAPH_CAPTURE_STATE_PATH = os.path.join(
    STATE_DIR,
    "memory",
    "openclaw-mem",
    "graph-capture-state.json",
)
DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH = os.path.join(
    STATE_DIR,
    "memory",
    "openclaw-mem",
    "graph-capture-md-state.json",
)
DEFAULT_EPISODIC_SPOOL_PATH = os.path.join(STATE_DIR, "memory", "openclaw-mem-episodes.jsonl")
DEFAULT_EPISODIC_INGEST_STATE_PATH = os.path.join(
    STATE_DIR,
    "memory",
    "openclaw-mem",
    "episodes-ingest-state.json",
)
DEFAULT_EPISODIC_EXTRACT_STATE_PATH = os.path.join(
    STATE_DIR,
    "memory",
    "openclaw-mem",
    "episodes-extract-state.json",
)
DEFAULT_OPENCLAW_SESSIONS_ROOT = os.path.join(STATE_DIR, "sessions")
DEFAULT_CRON_JOBS_JSON = os.path.join(STATE_DIR, "cron", "jobs.json")
DEFAULT_DB = os.path.join(STATE_DIR, "memory", "openclaw-mem.sqlite")
DEFAULT_WORKSPACE = Path.cwd()  # Fallback if not in openclaw workspace
DEFAULT_GRAPH_CAPTURE_MD_INCLUDES = (".md",)
DEFAULT_GRAPH_CAPTURE_MD_EXCLUDES = (
    "**/node_modules/**",
    "**/.venv/**",
    "**/.git/**",
    "**/dist/**",
)
_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _utcnow_iso() -> str:
    """Return UTC timestamp in ISO format with timezone info."""

    return datetime.now(timezone.utc).isoformat()


EPISODIC_SCHEMA_VERSION = "openclaw-mem.episodic.v0"
EPISODIC_INGEST_STATE_SCHEMA = "openclaw-mem.episodes.ingest.state.v0"
EPISODIC_EXTRACT_STATE_SCHEMA = "openclaw-mem.episodes.extract.state.v0"
EPISODIC_SPOOL_SCHEMA = "openclaw-mem.episodes.spool.v0"
EPISODIC_ALLOWED_TYPES = {
    "conversation.user",
    "conversation.assistant",
    "tool.call",
    "tool.result",
    "ops.decision",
    "ops.alert",
}
EPISODIC_DEFAULT_PAYLOAD_CAP_BYTES = 8 * 1024
EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES = 4 * 1024
EPISODIC_DEFAULT_REFS_CAP_BYTES = 4 * 1024
EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES = 8 * 1024
EPISODIC_FOLLOW_DEFAULT_POLL_INTERVAL_MS = 1000
EPISODIC_FOLLOW_MIN_POLL_INTERVAL_MS = 100
EPISODIC_FOLLOW_DEFAULT_ROTATE_ON_IDLE_SECONDS = 0.0  # disabled
EPISODIC_FOLLOW_DEFAULT_ROTATE_MIN_BYTES = 1 * 1024 * 1024
EPISODIC_FOLLOW_ROTATE_LOCK_SUFFIX = ".lock"
EPISODIC_MAX_QUERY_LIMIT = 500
EPISODIC_REDACT_PLACEHOLDER = "[REDACTED]"
EPISODIC_DEFAULT_RETENTION_DAYS = {
    "conversation.user": 60,
    "conversation.assistant": 90,
    "tool.call": 30,
    "tool.result": 30,
    "ops.decision": None,
    "ops.alert": 90,
}
EPISODIC_SECRET_LIKE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|pwd|secret)\b\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
)
EPISODIC_PII_LITE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"(?<!\d)(?:\+?\d[\d\-\s()]{7,}\d)(?!\d)"),
        "[REDACTED_PHONE]",
    ),
)
EPISODIC_TOOL_OUTPUT_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^```(?:json|bash|sh|shell|log|output|yaml)?", re.IGNORECASE),
    re.compile(r"\b(?:stdout|stderr|exit\s*code|traceback|stack\s*trace)\b", re.IGNORECASE),
    re.compile(r"\b(?:tool[_\s-]?call|tool[_\s-]?result|command output)\b", re.IGNORECASE),
)


def _utcnow_ts_ms() -> int:
    return int(time.time() * 1000)



def _normalize_episodic_scope(raw: Any) -> str:
    normalized = _normalize_scope_token(raw)
    if not normalized:
        raise ValueError("invalid scope")
    return normalized


def _normalize_episodic_type(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value not in EPISODIC_ALLOWED_TYPES:
        allowed = ", ".join(sorted(EPISODIC_ALLOWED_TYPES))
        raise ValueError(f"invalid type: {value or '<empty>'}; allowed: {allowed}")
    return value


def _parse_ts_ms(raw: Any) -> int:
    if raw is None:
        return _utcnow_ts_ms()
    try:
        value = int(raw)
    except Exception as e:
        raise ValueError(f"invalid ts_ms: {raw}") from e
    if value <= 0:
        raise ValueError("ts_ms must be > 0")
    return value


def _json_compact_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_optional_json_arg(raw_json: Optional[str], raw_file: Optional[str], label: str) -> Tuple[Any, Optional[str], int]:
    if raw_json and raw_file:
        raise ValueError(f"provide only one of --{label}-json or --{label}-file")

    if raw_json:
        source = raw_json
    elif raw_file:
        path = Path(str(raw_file)).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"{label} file not found: {path}")
        source = path.read_text(encoding="utf-8")
    else:
        return None, None, 0

    try:
        parsed = json.loads(source)
    except Exception as e:
        raise ValueError(f"invalid {label} JSON") from e

    parsed = _sanitize_jsonable_surrogates(parsed)
    serialized = _json_compact_dumps(parsed)
    size_bytes = len(serialized.encode("utf-8"))
    return parsed, serialized, size_bytes


def _looks_like_secret(text: str) -> bool:
    compact = str(text or "").strip()
    if not compact:
        return False
    return any(p.search(compact) for p in EPISODIC_SECRET_LIKE_PATTERNS)


def _redact_pii_lite(text: str) -> str:
    out = str(text or "")
    if not out:
        return out
    for pattern, repl in EPISODIC_PII_LITE_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def _contains_pii_lite(text: str) -> bool:
    compact = str(text or "").strip()
    if not compact:
        return False
    return any(pattern.search(compact) for pattern, _ in EPISODIC_PII_LITE_PATTERNS)


def _split_scope_prefixed_text(raw: Any) -> Tuple[Optional[str], str]:
    text = _sanitize_str_surrogates(str(raw or "")).strip()
    if not text:
        return None, ""

    m = re.match(r"^\s*\[\s*SCOPE\s*:\s*([^\]]+)\]\s*(.*)$", text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None, text

    scope_raw = _normalize_scope_token(m.group(1))
    body = _sanitize_str_surrogates(m.group(2) or "").strip()
    return scope_raw, body


def _looks_like_tool_output(text: str) -> bool:
    compact = str(text or "").strip()
    if not compact:
        return True
    if "<relevant-memories>" in compact:
        return True
    if re.search(r'^\{[\s\S]*\}$', compact) and re.search(r'"(?:stdout|stderr|exitCode|command|tool)"', compact):
        return True
    return any(p.search(compact) for p in EPISODIC_TOOL_OUTPUT_PATTERNS)


def _episodic_guard_text_fragments(summary: str, payload_serialized: Optional[str], refs_serialized: Optional[str], allow_tool_output: bool) -> None:
    if allow_tool_output:
        return

    if _looks_like_secret(summary):
        raise ValueError("summary appears to contain secret-like content; pass --allow-tool-output to override")
    if _contains_pii_lite(summary):
        raise ValueError("summary appears to contain pii-like content; pass --allow-tool-output to override")

    payload_fragments: List[str] = []
    if payload_serialized is not None:
        payload_fragments.append(payload_serialized)
    if refs_serialized is not None:
        payload_fragments.append(refs_serialized)

    for fragment in payload_fragments:
        if _looks_like_secret(fragment):
            raise ValueError("payload appears to contain secret-like content; pass --allow-tool-output to override")
        if _contains_pii_lite(fragment):
            raise ValueError("payload appears to contain pii-like content; pass --allow-tool-output to override")
        if _looks_like_tool_output(fragment):
            raise ValueError("payload appears to contain tool-output-like content; pass --allow-tool-output to override")


def _resolve_query_scope(raw_scope: Optional[str], allow_global: bool) -> str:
    if raw_scope is None or not str(raw_scope).strip():
        if allow_global:
            return "global"
        raise ValueError("scope is required (or pass --global)")

    normalized = _normalize_episodic_scope(raw_scope)
    if allow_global and normalized != "global":
        raise ValueError("--global cannot be combined with non-global --scope")
    return normalized


def _normalize_types_filter(raw_types: Optional[List[str]]) -> Optional[List[str]]:
    if not raw_types:
        return None

    out: List[str] = []
    seen = set()
    for raw in raw_types:
        parts = [p.strip() for p in str(raw).split(",") if p.strip()]
        for part in parts:
            t = _normalize_episodic_type(part)
            if t in seen:
                continue
            seen.add(t)
            out.append(t)

    return out or None


def _episodes_row_to_item(row: sqlite3.Row, include_payload: bool) -> Dict[str, Any]:
    refs_obj: Any = None
    refs_raw = row["refs_json"]
    if refs_raw is not None:
        try:
            refs_obj = json.loads(refs_raw)
        except Exception:
            refs_obj = None

    item: Dict[str, Any] = {
        "id": int(row["id"]),
        "event_id": row["event_id"],
        "ts_ms": int(row["ts_ms"]),
        "scope": row["scope"],
        "session_id": row["session_id"],
        "agent_id": row["agent_id"],
        "type": row["type"],
        "summary": row["summary"],
        "refs": refs_obj,
        "redacted": bool(row["redacted"]),
        "schema_version": row["schema_version"],
        "created_at": row["created_at"],
    }

    if include_payload:
        payload_obj: Any = None
        payload_raw = row["payload_json"]
        if payload_raw is not None:
            try:
                payload_obj = json.loads(payload_raw)
            except Exception:
                payload_obj = None
        item["payload"] = payload_obj

    return item

_IMPORTANCE_LABEL_KEYS = ("must_remember", "nice_to_have", "ignore", "unknown")


_EPISODIC_FORBIDDEN_PAYLOAD_KEYS = {
    "stdout",
    "stderr",
    "raw_stdout",
    "raw_stderr",
    "command_output",
    "tool_output",
}


def _sanitize_episodic_payload(
    value: Any,
    *,
    depth: int = 0,
    max_depth: int = 5,
    max_items: int = 48,
    max_string_chars: int = EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES,
) -> Any:
    if depth > max_depth:
        return "[TRUNCATED_DEPTH]"

    if isinstance(value, str):
        compact = _sanitize_str_surrogates(value)
        if _looks_like_secret(compact):
            return "[REDACTED_SECRET]"
        compact = _redact_pii_lite(compact)
        string_cap = max(160, int(max_string_chars or EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES))
        if len(compact) > string_cap:
            return compact[:string_cap] + "…"
        return compact

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        redacted_output_fields = 0
        for i, (k, v) in enumerate(value.items()):
            if i >= max_items:
                out["_truncated_items"] = True
                break
            key = _sanitize_str_surrogates(str(k))
            if key.strip().lower() in _EPISODIC_FORBIDDEN_PAYLOAD_KEYS:
                redacted_output_fields += 1
                continue
            out[key] = _sanitize_episodic_payload(
                v,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
        if redacted_output_fields > 0:
            out["_redacted_output_fields"] = redacted_output_fields
        return out

    if isinstance(value, list):
        return [
            _sanitize_episodic_payload(
                v,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
            for v in value[:max_items]
        ]

    return value


def _episodic_bounded_json(
    value: Any,
    *,
    cap_bytes: int,
    label: str,
    max_string_chars: int = EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES,
) -> Tuple[Optional[str], int, bool]:
    if value is None:
        return None, 0, False

    sanitized = _sanitize_jsonable_surrogates(
        _sanitize_episodic_payload(value, max_string_chars=max_string_chars)
    )
    serialized = _json_compact_dumps(sanitized)
    size = len(serialized.encode("utf-8"))
    if size <= cap_bytes:
        return serialized, size, False

    preview = serialized[: min(256, max(32, cap_bytes // 2))]
    truncated_obj = {
        "_truncated": True,
        "reason": f"{label}_cap",
        "original_bytes": size,
        "preview": preview,
    }
    serialized = _json_compact_dumps(truncated_obj)
    size = len(serialized.encode("utf-8"))
    if size > cap_bytes:
        serialized = _json_compact_dumps({"_truncated": True, "reason": f"{label}_cap", "original_bytes": size})
        size = len(serialized.encode("utf-8"))
    return serialized, size, True


def _normalize_episodic_spool_event(
    obj: Dict[str, Any],
    *,
    fallback_event_id: str,
    payload_cap: int,
    conversation_payload_cap: int,
    refs_cap: int,
) -> Dict[str, Any]:
    event_id = str(obj.get("event_id") or "").strip() or fallback_event_id
    ts_ms = _parse_ts_ms(obj.get("ts_ms"))
    session_id = _sanitize_str_surrogates(str(obj.get("session_id") or "").strip())
    agent_id = _sanitize_str_surrogates(str(obj.get("agent_id") or "").strip())
    event_type = _normalize_episodic_type(obj.get("type"))

    summary_raw = _sanitize_str_surrogates(str(obj.get("summary") or "").strip())
    scope_from_summary, summary_body = _split_scope_prefixed_text(summary_raw)

    raw_scope = _normalize_scope_token(obj.get("scope"))
    scope_token = raw_scope or scope_from_summary or "global"
    scope = _normalize_episodic_scope(scope_token)

    summary = _redact_pii_lite(summary_body or summary_raw)
    if _looks_like_secret(summary):
        summary = "[REDACTED_SECRET]"

    if not session_id:
        raise ValueError("session_id is required")
    if not agent_id:
        raise ValueError("agent_id is required")
    if not summary:
        raise ValueError("summary is required")

    generic_payload_cap = min(max(256, int(payload_cap)), EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES)
    conversation_cap = min(max(256, int(conversation_payload_cap)), EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES)
    effective_payload_cap = generic_payload_cap
    if event_type.startswith("conversation."):
        effective_payload_cap = min(generic_payload_cap, conversation_cap)

    payload_serialized, payload_size, payload_truncated = _episodic_bounded_json(
        obj.get("payload"),
        cap_bytes=effective_payload_cap,
        label="payload",
        max_string_chars=effective_payload_cap,
    )
    refs_serialized, refs_size, refs_truncated = _episodic_bounded_json(
        obj.get("refs"),
        cap_bytes=max(128, int(refs_cap)),
        label="refs",
        max_string_chars=max(256, int(refs_cap)),
    )

    redacted_late = bool(obj.get("redacted"))
    for fragment in (payload_serialized, refs_serialized):
        if not fragment:
            continue
        if _looks_like_secret(fragment) or _contains_pii_lite(fragment):
            payload_serialized = None
            payload_size = 0
            refs_serialized = None
            refs_size = 0
            redacted_late = True
            break

    if not redacted_late and event_type.startswith("conversation."):
        raw_payload = obj.get("payload")
        payload_probe = ""
        if isinstance(raw_payload, dict):
            payload_probe = _sanitize_str_surrogates(str(raw_payload.get("text") or ""))
        elif isinstance(raw_payload, str):
            payload_probe = _sanitize_str_surrogates(raw_payload)
        elif payload_serialized:
            payload_probe = payload_serialized
        if _looks_like_tool_output(f"{summary}\n{payload_probe}".strip()):
            payload_serialized = None
            payload_size = 0
            redacted_late = True

    return {
        "event_id": event_id,
        "ts_ms": ts_ms,
        "scope": scope,
        "session_id": session_id,
        "agent_id": agent_id,
        "type": event_type,
        "summary": summary,
        "payload_json": payload_serialized,
        "payload_bytes": payload_size,
        "payload_truncated": payload_truncated,
        "refs_json": refs_serialized,
        "refs_bytes": refs_size,
        "refs_truncated": refs_truncated,
        "redacted": redacted_late,
    }


def _read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"invalid state file JSON: {path}") from e
    if isinstance(data, dict):
        return data
    raise ValueError(f"state file must be an object: {path}")


def _write_json_file_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass





def _episodic_lock_path(target: Path) -> Path:
    return target.with_name(target.name + EPISODIC_FOLLOW_ROTATE_LOCK_SUFFIX)


@contextmanager
def _episodic_flock(lock_path: Path, *, exclusive: bool, timeout_s: float = 5.0):
    """Best-effort advisory file lock (POSIX flock).

    Uses a dedicated lock file so rotations don't race writers holding the
    spool file descriptor.

    timeout_s=0 blocks indefinitely; otherwise it retries until timeout.
    """

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fp = lock_path.open("a", encoding="utf-8")
    try:
        import fcntl  # POSIX only

        flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if timeout_s <= 0:
            fcntl.flock(fp.fileno(), flags)
        else:
            deadline = time.monotonic() + float(timeout_s)
            while True:
                try:
                    fcntl.flock(fp.fileno(), flags | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"timed out acquiring lock: {lock_path}")
                    time.sleep(0.05)

        yield fp
    finally:
        try:
            fp.close()
        except Exception:
            pass


@dataclass
class IngestRunSummary:
    """Aggregate ingest/harvest stats for importance autograde.

    These are intended for ops receipts and trend-friendly dashboards.
    """

    total_seen: int = 0
    graded_filled: int = 0
    skipped_existing: int = 0
    skipped_disabled: int = 0
    scorer_errors: int = 0
    label_counts: Dict[str, int] = field(default_factory=dict)

    def bump_label(self, label: str) -> None:
        raw = label or ""
        try:
            from openclaw_mem.importance import normalize_label

            normalized = normalize_label(raw)
        except Exception:
            normalized = None

        if normalized:
            key = normalized
        else:
            key = unicodedata.normalize("NFKC", raw).strip().lower() or "unknown"

        self.label_counts[key] = int(self.label_counts.get(key, 0)) + 1

    def normalized_label_counts(self) -> Dict[str, int]:
        """Return deterministic label counts for receipts.

        Always includes the canonical importance labels with zero defaults, and
        preserves any non-canonical labels (sorted for deterministic output).
        """

        out: Dict[str, int] = {k: int(self.label_counts.get(k, 0)) for k in _IMPORTANCE_LABEL_KEYS}
        for key in sorted(self.label_counts):
            if key in out:
                continue
            out[key] = int(self.label_counts.get(key, 0))
        return out


def _normalize_importance_scorer_value(value: str) -> str:
    """Normalize importance autograde scorer values.

    Accepts minor aliases (e.g., heuristic_v1) while keeping a
    single canonical value for storage/receipts.
    """

    v = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if not v:
        return ""

    v = v.replace("_", "-").replace(" ", "")
    if v in {"heuristicv1", "heuristic-v1"}:
        return "heuristic-v1"
    if v in {"heuristicv2", "heuristic-v2"}:
        return "heuristic-v2"
    return v


def _apply_importance_scorer_override(args: argparse.Namespace) -> None:
    """Optionally override importance autograde scorer for this process.

    Precedence:
    - If the subcommand provides --importance-scorer, it wins.
    - Otherwise the env var OPENCLAW_MEM_IMPORTANCE_SCORER is used (existing behavior).

    Supported values:
    - heuristic-v1: enable deterministic heuristic grading
    - off|none: disable autograde even if env var is set

    Notes:
    - This is process-local (does not mutate any config files).
    - _insert_observation reads OPENCLAW_MEM_IMPORTANCE_SCORER at insert time.
    """

    raw = getattr(args, "importance_scorer", None)
    if raw is None:
        return

    v = _normalize_importance_scorer_value(str(raw))
    if not v:
        return

    if v in {"off", "none", "disable", "disabled", "0"}:
        os.environ.pop("OPENCLAW_MEM_IMPORTANCE_SCORER", None)
        return

    os.environ["OPENCLAW_MEM_IMPORTANCE_SCORER"] = v


def _read_openclaw_config() -> Dict[str, Any]:
    """Read OpenClaw config (cached).

    Prefers OPENCLAW_CONFIG_PATH when set; otherwise reads from the resolved
    OpenClaw state dir.
    """

    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    try:
        config_path = _resolve_openclaw_config_path()
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                _CONFIG_CACHE = json.load(f)
                return _CONFIG_CACHE
    except Exception:
        pass

    _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def _connect(db_path: str) -> sqlite3.Connection:
    # Allow in-memory DB and relative paths without a directory component.
    # (Useful for unit tests and quick experiments.)
    dir_ = os.path.dirname(db_path)
    if db_path not in (":memory:", "") and dir_:
        os.makedirs(dir_, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    _init_db(conn)
    return conn



def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT,
            summary TEXT,
            summary_en TEXT,
            lang TEXT,
            tool_name TEXT,
            detail_json TEXT
        );
        """
    )

    # Backward-compatible migration for existing DBs.
    obs_cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)").fetchall()}
    if "summary_en" not in obs_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN summary_en TEXT")
    if "lang" not in obs_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN lang TEXT")

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
        USING fts5(summary, summary_en, tool_name, detail_json, content='observations', content_rowid='id');
        """
    )

    # If this DB already had an older FTS schema, rebuild once with summary_en included.
    fts_cols = [r[1] for r in conn.execute("PRAGMA table_info(observations_fts)").fetchall()]
    if "summary_en" not in fts_cols:
        conn.execute("DROP TABLE IF EXISTS observations_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE observations_fts
            USING fts5(summary, summary_en, tool_name, detail_json, content='observations', content_rowid='id');
            """
        )
        conn.execute(
            """
            INSERT INTO observations_fts(rowid, summary, summary_en, tool_name, detail_json)
            SELECT id, summary, summary_en, tool_name, detail_json
            FROM observations;
            """
        )

    # Phase 3: vector embeddings (stored as float32 BLOB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observation_embeddings (
            observation_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_embeddings_model ON observation_embeddings(model);")

    # Backward-compatible parallel table for English embeddings.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observation_embeddings_en (
            observation_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_embeddings_en_model ON observation_embeddings_en(model);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_capture_git_seen (
            repo TEXT NOT NULL,
            sha TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            PRIMARY KEY(repo, sha)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_capture_md_seen (
            fingerprint TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            mtime REAL NOT NULL
        );
        """
    )

    # Docs memory sidecar (hybrid retrieval over operator-authored markdown).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS docs_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            repo TEXT NOT NULL,
            path TEXT NOT NULL,
            doc_kind TEXT NOT NULL,
            heading_path TEXT,
            title TEXT,
            text TEXT NOT NULL,
            source_kind TEXT NOT NULL DEFAULT 'operator',
            source_ref TEXT NOT NULL,
            ts_hint TEXT,
            content_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(doc_id, chunk_id)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunks_doc_id ON docs_chunks(doc_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunks_kind ON docs_chunks(doc_kind);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunks_repo_path ON docs_chunks(repo, path);")

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_chunks_fts
        USING fts5(text, title, heading_path, path, repo, doc_kind, content='docs_chunks', content_rowid='id');
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS docs_embeddings (
            chunk_rowid INTEGER NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            norm REAL NOT NULL,
            text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(chunk_rowid, model)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_embeddings_model ON docs_embeddings(model);")

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS docs_chunks_ai
        AFTER INSERT ON docs_chunks
        BEGIN
            INSERT INTO docs_chunks_fts(rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES (new.id, new.text, new.title, new.heading_path, new.path, new.repo, new.doc_kind);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS docs_chunks_ad
        AFTER DELETE ON docs_chunks
        BEGIN
            INSERT INTO docs_chunks_fts(docs_chunks_fts, rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES ('delete', old.id, old.text, old.title, old.heading_path, old.path, old.repo, old.doc_kind);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS docs_chunks_au
        AFTER UPDATE ON docs_chunks
        BEGIN
            INSERT INTO docs_chunks_fts(docs_chunks_fts, rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES ('delete', old.id, old.text, old.title, old.heading_path, old.path, old.repo, old.doc_kind);
            INSERT INTO docs_chunks_fts(rowid, text, title, heading_path, path, repo, doc_kind)
            VALUES (new.id, new.text, new.title, new.heading_path, new.path, new.repo, new.doc_kind);
        END;
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS episodic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            ts_ms INTEGER NOT NULL,
            scope TEXT NOT NULL,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            type TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_json TEXT,
            refs_json TEXT,
            redacted INTEGER NOT NULL DEFAULT 0,
            schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_episodic_event_id ON episodic_events(event_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_scope_ts ON episodic_events(scope, ts_ms);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_session_ts ON episodic_events(session_id, ts_ms);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_scope_type_ts ON episodic_events(scope, type, ts_ms);")

    conn.commit()


_SURROGATE_MIN = 0xD800
_SURROGATE_MAX = 0xDFFF


def _sanitize_str_surrogates(s: str) -> str:
    """Replace any lone surrogate codepoints to keep SQLite bindings UTF-8 safe.

    Python's json decoder can legally produce unpaired surrogate codepoints when
    the input contains an invalid unicode escape (e.g. "\\ud83d"). Those values
    cannot be encoded to UTF-8 for SQLite, so we replace them with U+FFFD.
    """

    if not s:
        return s
    # Fast path
    for ch in s:
        o = ord(ch)
        if _SURROGATE_MIN <= o <= _SURROGATE_MAX:
            return "".join(
                ("\ufffd" if _SURROGATE_MIN <= ord(c) <= _SURROGATE_MAX else c) for c in s
            )
    return s


def _sanitize_jsonable_surrogates(x: Any) -> Any:
    if isinstance(x, str):
        return _sanitize_str_surrogates(x)
    if isinstance(x, dict):
        out: Dict[Any, Any] = {}
        for k, v in x.items():
            kk = _sanitize_str_surrogates(k) if isinstance(k, str) else k
            out[kk] = _sanitize_jsonable_surrogates(v)
        return out
    if isinstance(x, list):
        return [_sanitize_jsonable_surrogates(v) for v in x]
    return x


def _insert_observation(conn: sqlite3.Connection, obs: Dict[str, Any], run_summary: IngestRunSummary | None = None) -> int:
    ts = obs.get("ts") or _utcnow_iso()

    kind = obs.get("kind")
    kind = _sanitize_str_surrogates(str(kind)) if kind is not None else None

    summary = obs.get("summary")
    summary = _sanitize_str_surrogates(str(summary)) if summary is not None else None

    summary_en = obs.get("summary_en") or obs.get("text_en")
    summary_en = _sanitize_str_surrogates(str(summary_en)) if summary_en is not None else None

    lang = obs.get("lang")
    lang = _sanitize_str_surrogates(str(lang)) if lang is not None else None

    tool_name = obs.get("tool_name") or obs.get("tool")
    tool_name = _sanitize_str_surrogates(str(tool_name)) if tool_name is not None else None

    base_detail = obs.get("detail")
    if base_detail is None:
        base_detail = obs.get("detail_json") or {}

    if isinstance(base_detail, str):
        try:
            detail_obj: Dict[str, Any] = json.loads(base_detail)
            if not isinstance(detail_obj, dict):
                detail_obj = {"_raw_detail": base_detail}
        except Exception:
            detail_obj = {"_raw_detail": base_detail}
    elif isinstance(base_detail, dict):
        detail_obj = dict(base_detail)
    else:
        detail_obj = {"_detail": base_detail}

    known_keys = {
        "ts",
        "kind",
        "summary",
        "summary_en",
        "text_en",
        "lang",
        "tool_name",
        "tool",
        "detail",
        "detail_json",
    }
    extras = {k: v for k, v in obs.items() if k not in known_keys}
    if extras:
        detail_obj.update(extras)

    # Sanitize any invalid unicode surrogate codepoints before binding to SQLite.
    detail_obj = _sanitize_jsonable_surrogates(detail_obj)

    if run_summary is not None:
        run_summary.total_seen += 1

    try:
        from openclaw_mem.importance import is_parseable_importance

        had_importance = is_parseable_importance(detail_obj.get("importance"))
    except Exception:
        # Conservative fallback: if the helper import fails for any reason,
        # preserve prior behavior (treat presence of the field as 'existing').
        had_importance = "importance" in detail_obj
    if run_summary is not None and had_importance:
        run_summary.skipped_existing += 1
        try:
            from openclaw_mem.importance import parse_importance_score, label_from_score

            existing = detail_obj.get("importance")
            if isinstance(existing, dict) and isinstance(existing.get("label"), str) and existing.get("label").strip():
                run_summary.bump_label(existing.get("label"))
            else:
                run_summary.bump_label(label_from_score(parse_importance_score(existing)))
        except Exception:
            # Never break ingestion for reporting.
            run_summary.bump_label("unknown")

    # Optional: auto-grade importance behind a feature flag (non-destructive).
    #
    # MVP rules:
    # - default OFF
    # - only populate missing `detail_json.importance`
    # - fail-open on any grading error
    scorer = _normalize_importance_scorer_value(os.environ.get("OPENCLAW_MEM_IMPORTANCE_SCORER") or "")

    if scorer == "heuristic-v1":
        if not had_importance:
            try:
                # Test hook: force a grading failure to prove fail-open behavior.
                if (os.environ.get("OPENCLAW_MEM_IMPORTANCE_TEST_RAISE") or "").strip() == "1":
                    raise RuntimeError("forced importance autograde failure (test)")

                from openclaw_mem.heuristic_v1 import grade_observation

                r = grade_observation(
                    {
                        "ts": ts,
                        "kind": kind,
                        "summary": summary,
                        "summary_en": summary_en,
                        "lang": lang,
                        "tool_name": tool_name,
                        "detail": detail_obj,
                    }
                )
                imp = r.as_importance()
                detail_obj["importance"] = imp

                if run_summary is not None:
                    run_summary.graded_filled += 1
                    run_summary.bump_label(str(imp.get("label") or "unknown"))
            except Exception as e:
                if run_summary is not None:
                    run_summary.scorer_errors += 1
                print(f"Warning: importance autograde failed: {e}", file=sys.stderr)
    else:
        if run_summary is not None and not had_importance:
            run_summary.skipped_disabled += 1

    detail_json = json.dumps(detail_obj, ensure_ascii=False)

    cur = conn.execute(
        "INSERT INTO observations (ts, kind, summary, summary_en, lang, tool_name, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, kind, summary, summary_en, lang, tool_name, detail_json),
    )
    rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO observations_fts (rowid, summary, summary_en, tool_name, detail_json) VALUES (?, ?, ?, ?, ?)",
        (rowid, summary, summary_en, tool_name, detail_json),
    )
    return int(rowid)


def _iter_jsonl(fp) -> Iterable[Dict[str, Any]]:
    for line in fp:
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def cmd_status(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    row = conn.execute("SELECT COUNT(*) AS n, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM observations").fetchone()
    emb_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings").fetchone()
    emb_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings GROUP BY model ORDER BY n DESC"
    ).fetchall()
    emb_en_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings_en").fetchone()
    emb_en_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings_en GROUP BY model ORDER BY n DESC"
    ).fetchall()

    data = {
        "db": args.db,
        "count": row["n"],
        "min_ts": row["min_ts"],
        "max_ts": row["max_ts"],
        "embeddings": {
            "count": emb_row["n"],
            "models": [{"model": r["model"], "count": r["n"]} for r in emb_models],
        },
        "embeddings_en": {
            "count": emb_en_row["n"],
            "models": [{"model": r["model"], "count": r["n"]} for r in emb_en_models],
        },
    }
    _emit(data, args.json)


def cmd_profile(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Ops-friendly profile surface (counts, ranges, labels, recent rows).

    This stays deterministic/local-first and does not call remote services.
    """

    recent_limit = max(1, min(200, int(getattr(args, "recent_limit", 10) or 10)))
    tool_limit = max(1, min(200, int(getattr(args, "tool_limit", 10) or 10)))
    kind_limit = max(1, min(200, int(getattr(args, "kind_limit", 10) or 10)))

    row = conn.execute("SELECT COUNT(*) AS n, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM observations").fetchone()

    kinds = conn.execute(
        """
        SELECT coalesce(kind, '') AS kind, COUNT(*) AS n
        FROM observations
        GROUP BY kind
        ORDER BY n DESC, kind ASC
        LIMIT ?
        """,
        (kind_limit,),
    ).fetchall()

    tools = conn.execute(
        """
        SELECT coalesce(tool_name, '') AS tool_name, COUNT(*) AS n
        FROM observations
        GROUP BY tool_name
        ORDER BY n DESC, tool_name ASC
        LIMIT ?
        """,
        (tool_limit,),
    ).fetchall()

    recent_rows = conn.execute(
        """
        SELECT id, ts, kind, tool_name, summary
        FROM observations
        ORDER BY id DESC
        LIMIT ?
        """,
        (recent_limit,),
    ).fetchall()

    emb_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings").fetchone()
    emb_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings GROUP BY model ORDER BY n DESC"
    ).fetchall()

    emb_en_row = conn.execute("SELECT COUNT(*) AS n FROM observation_embeddings_en").fetchone()
    emb_en_models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM observation_embeddings_en GROUP BY model ORDER BY n DESC"
    ).fetchall()

    from openclaw_mem.importance import is_parseable_importance, parse_importance_score, label_from_score

    label_counts: Dict[str, int] = {
        "must_remember": 0,
        "nice_to_have": 0,
        "ignore": 0,
        "unknown": 0,
    }
    importance_present = 0
    score_total = 0.0

    for r in conn.execute("SELECT detail_json FROM observations"):
        raw = r["detail_json"]
        try:
            detail_obj = json.loads(raw or "{}")
        except Exception:
            label_counts["unknown"] += 1
            continue

        if not isinstance(detail_obj, dict) or "importance" not in detail_obj:
            label_counts["unknown"] += 1
            continue

        importance_present += 1

        importance_value = detail_obj.get("importance")
        if not is_parseable_importance(importance_value):
            label_counts["unknown"] += 1
            continue

        score = parse_importance_score(importance_value)
        label = label_from_score(score)
        label_counts[label] = int(label_counts.get(label, 0)) + 1
        score_total += float(score)

    scored_count = int(label_counts["must_remember"] + label_counts["nice_to_have"] + label_counts["ignore"])
    total_count = int(row["n"] or 0)

    data = {
        "kind": "openclaw-mem.profile.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "db": args.db,
        "observations": {
            "count": total_count,
            "min_ts": row["min_ts"],
            "max_ts": row["max_ts"],
            "kinds": [{"kind": r["kind"], "count": int(r["n"])} for r in kinds],
            "tools": [{"tool_name": r["tool_name"], "count": int(r["n"])} for r in tools],
        },
        "importance": {
            "present": importance_present,
            "missing": max(0, total_count - importance_present),
            "label_counts": label_counts,
            "avg_score": (score_total / scored_count) if scored_count else None,
        },
        "embeddings": {
            "original": {
                "count": int(emb_row["n"] or 0),
                "models": [{"model": r["model"], "count": int(r["n"])} for r in emb_models],
            },
            "english": {
                "count": int(emb_en_row["n"] or 0),
                "models": [{"model": r["model"], "count": int(r["n"])} for r in emb_en_models],
            },
        },
        "recent": [dict(r) for r in recent_rows],
    }

    _emit(data, args.json)


def _resolve_memory_slot(config: Dict[str, Any]) -> str:
    slot = config.get("plugins", {}).get("slots", {}).get("memory")
    if isinstance(slot, str) and slot:
        return slot
    return "memory-core"


def _is_enabled_entry(config: Dict[str, Any], plugin_id: str) -> bool:
    entry = config.get("plugins", {}).get("entries", {}).get(plugin_id)
    if not isinstance(entry, dict):
        return False
    return entry.get("enabled", True) is not False


def _lancedb_api_key_ready(config: Dict[str, Any]) -> bool:
    entry = config.get("plugins", {}).get("entries", {}).get("memory-lancedb")
    if not isinstance(entry, dict):
        return False
    cfg = entry.get("config", {})
    if not isinstance(cfg, dict):
        return False
    embedding = cfg.get("embedding", {})
    if not isinstance(embedding, dict):
        return False

    api_key = embedding.get("apiKey")
    if not isinstance(api_key, str) or not api_key.strip():
        return False

    if "${" in api_key and "}" in api_key:
        # Supports ${OPENAI_API_KEY}-style expansion in memory-lancedb.
        var_name = api_key.strip().removeprefix("${").removesuffix("}").strip()
        return bool(var_name and os.environ.get(var_name))

    return True


def cmd_backend(_conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    cfg = _read_openclaw_config()

    slot = _resolve_memory_slot(cfg)
    memory_core_enabled = _is_enabled_entry(cfg, "memory-core")
    memory_lancedb_enabled = _is_enabled_entry(cfg, "memory-lancedb")
    openclaw_mem_enabled = _is_enabled_entry(cfg, "openclaw-mem")

    out = {
        "memory_slot": slot,
        "entries": {
            "memory-core": {"enabled": memory_core_enabled},
            "memory-lancedb": {
                "enabled": memory_lancedb_enabled,
                "embedding_api_key_ready": _lancedb_api_key_ready(cfg),
            },
            "openclaw-mem": {"enabled": openclaw_mem_enabled},
        },
        "fallback": {
            "recommended_slot": "memory-core",
            "reason": "Fast rollback path if memory-lancedb has runtime issues",
        },
    }

    _emit(out, args.json)


def cmd_optimize_review(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    report = build_memory_health_review(
        conn,
        limit=int(getattr(args, "limit", 1000)),
        stale_days=int(getattr(args, "stale_days", 60)),
        duplicate_min_count=int(getattr(args, "duplicate_min_count", 2)),
        bloat_summary_chars=int(getattr(args, "bloat_summary_chars", 240)),
        bloat_detail_bytes=int(getattr(args, "bloat_detail_bytes", 4096)),
        orphan_min_tokens=int(getattr(args, "orphan_min_tokens", 2)),
        miss_min_count=int(getattr(args, "miss_min_count", 2)),
        top=int(getattr(args, "top", 10)),
        scope=getattr(args, "scope", None),
    )

    if args.json:
        _emit(report, True)
        return

    print(render_memory_health_review(report))


def cmd_ingest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _apply_importance_scorer_override(args)

    if args.file:
        fp = open(args.file, "r", encoding="utf-8")
    else:
        fp = sys.stdin

    summary = IngestRunSummary()

    inserted: List[int] = []
    for obs in _iter_jsonl(fp):
        inserted.append(_insert_observation(conn, obs, summary))

    conn.commit()
    if args.file:
        fp.close()

    _emit(
        {
            "inserted": len(inserted),
            "ids": inserted[:50],
            "total_seen": summary.total_seen,
            "graded_filled": summary.graded_filled,
            "skipped_existing": summary.skipped_existing,
            "skipped_disabled": summary.skipped_disabled,
            "scorer_errors": summary.scorer_errors,
            "label_counts": summary.normalized_label_counts(),
        },
        args.json,
    )


def _has_cjk(text: str) -> bool:
    import re

    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def _cjk_terms(query: str, max_terms: int = 16) -> List[str]:
    """Extract CJK-aware fallback terms for LIKE matching.

    Strategy:
    - keep CJK runs (length>=2)
    - add overlapping bigrams for longer runs
    """
    import re

    runs = re.findall(r"[\u3400-\u9fff]+", query or "")
    terms: List[str] = []

    for run in runs:
        if len(run) < 2:
            continue
        terms.append(run)
        if len(run) > 2:
            terms.extend(run[i : i + 2] for i in range(len(run) - 1))

    # stable de-dup
    out: List[str] = []
    seen = set()
    for t in terms:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_terms:
            break
    return out


def _search_cjk_fallback(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    scope: Optional[str] = None,
) -> List[sqlite3.Row]:
    terms = _cjk_terms(query)
    if not terms:
        return []

    like_vals = [f"%{t}%" for t in terms]

    # score = negative matched-term count (so more matches = smaller score = higher rank)
    score_expr = " + ".join(["CASE WHEN o.summary LIKE ? THEN 1 ELSE 0 END" for _ in like_vals])
    where_expr = " OR ".join(["o.summary LIKE ?" for _ in like_vals])

    scope_norm = _normalize_scope_token(scope)
    scope_clause = ""
    params: List[Any] = [*like_vals, *like_vals]
    if scope_norm:
        scope_clause = (
            " AND lower(json_extract("
            "CASE WHEN json_valid(o.detail_json) THEN o.detail_json ELSE '{}' END, '$.scope')) = ?"
        )
        params.append(scope_norm)

    sql = f"""
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               o.summary AS snippet,
               o.summary_en AS snippet_en,
               -1.0 * ({score_expr}) AS score,
               o.detail_json AS detail_json
        FROM observations o
        WHERE ({where_expr}){scope_clause}
        ORDER BY score ASC, o.id DESC
        LIMIT ?;
    """

    params.append(int(limit))
    return conn.execute(sql, params).fetchall()


def cmd_search(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    q = args.query.strip()
    if not q:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    rows = conn.execute(
        """
        SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
               snippet(observations_fts, 0, '[', ']', '…', 12) AS snippet,
               snippet(observations_fts, 1, '[', ']', '…', 12) AS snippet_en,
               bm25(observations_fts) AS score
        FROM observations_fts
        JOIN observations o ON o.id = observations_fts.rowid
        WHERE observations_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?;
        """,
        (q, args.limit),
    ).fetchall()

    # Fallback for CJK keyword queries when FTS5 tokenizer cannot split terms well.
    if not rows and _has_cjk(q):
        rows = _search_cjk_fallback(conn, q, args.limit)

    out = [dict(r) for r in rows]
    _emit(out, args.json)


def _docs_collect_markdown_files(raw_paths: List[str]) -> Tuple[List[Path], List[str]]:
    files: List[Path] = []
    missing: List[str] = []
    seen: set[str] = set()

    for raw in raw_paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            missing.append(str(p))
            continue

        candidates: List[Path]
        if p.is_file():
            candidates = [p] if p.suffix.lower() == ".md" else []
        else:
            candidates = [x for x in p.rglob("*.md") if x.is_file()]

        for fp in sorted(candidates):
            key = str(fp)
            if key in seen:
                continue
            seen.add(key)
            files.append(fp)

    return files, missing


def _docs_git_root(path: Path, cache: Dict[str, Optional[Path]]) -> Optional[Path]:
    key = str(path.parent.resolve())
    if key in cache:
        return cache[key]

    p = subprocess.run(
        ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        cache[key] = None
        return None

    root_raw = (p.stdout or "").strip()
    if not root_raw:
        cache[key] = None
        return None

    root = Path(root_raw).expanduser().resolve()
    cache[key] = root
    return root


def _docs_repo_relpath(path: Path, git_cache: Dict[str, Optional[Path]]) -> Tuple[str, str]:
    root = _docs_git_root(path, git_cache)
    if root is not None:
        try:
            rel = path.resolve().relative_to(root).as_posix()
            return root.name, rel
        except Exception:
            pass

    return "local", path.name


def _docs_embedding_input(*, title: str, heading_path: str, text: str) -> str:
    parts = [p.strip() for p in [title, heading_path, text] if (p or "").strip()]
    return "\n".join(parts)


def cmd_docs_ingest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    files, missing = _docs_collect_markdown_files(list(getattr(args, "path", []) or []))
    max_chars = max(200, int(getattr(args, "max_chars", 1400) or 1400))

    stats: Dict[str, Any] = {
        "ok": True,
        "files_seen": len(files),
        "missing_paths": missing,
        "files_ingested": 0,
        "chunks_total": 0,
        "chunks_inserted": 0,
        "chunks_updated": 0,
        "chunks_unchanged": 0,
        "chunks_deleted": 0,
        "embedded": 0,
    }

    embed_rows: List[Tuple[int, str, str]] = []
    now = _utcnow_iso()
    git_cache: Dict[str, Optional[Path]] = {}
    model = str(getattr(args, "model", defaults.embed_model()))

    for fp in files:
        raw_text = fp.read_text(encoding="utf-8")
        repo, rel_path = _docs_repo_relpath(fp, git_cache)
        doc_id = make_doc_id(repo, rel_path)
        doc_kind = detect_doc_kind(rel_path)
        ts_hint = parse_ts_hint(raw_text, rel_path)

        chunks = chunk_markdown(raw_text, default_title=fp.stem, max_chars=max_chars)
        stats["chunks_total"] = int(stats["chunks_total"]) + len(chunks)

        existing_rows = conn.execute(
            "SELECT id, chunk_id, content_hash FROM docs_chunks WHERE doc_id = ?",
            (doc_id,),
        ).fetchall()
        existing_map = {str(r["chunk_id"]): dict(r) for r in existing_rows}

        seen_chunk_ids: set[str] = set()
        for chunk in chunks:
            seen_chunk_ids.add(chunk.chunk_id)
            chunk_hash = chunk_content_hash(
                heading_path=chunk.heading_path,
                title=chunk.title,
                text=chunk.text,
            )
            existing = existing_map.get(chunk.chunk_id)

            if existing is None:
                cur = conn.execute(
                    """
                    INSERT INTO docs_chunks (
                        doc_id, chunk_id, repo, path, doc_kind, heading_path, title,
                        text, source_kind, source_ref, ts_hint, content_hash, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        chunk.chunk_id,
                        repo,
                        rel_path,
                        doc_kind,
                        chunk.heading_path,
                        chunk.title,
                        chunk.text,
                        "operator",
                        f"{repo}/{rel_path}",
                        ts_hint,
                        chunk_hash,
                        now,
                    ),
                )
                rowid = int(cur.lastrowid)
                stats["chunks_inserted"] = int(stats["chunks_inserted"]) + 1
                if bool(getattr(args, "embed", True)):
                    embed_rows.append(
                        (
                            rowid,
                            _docs_embedding_input(
                                title=chunk.title,
                                heading_path=chunk.heading_path,
                                text=chunk.text,
                            ),
                            chunk_hash,
                        )
                    )
                continue

            rowid = int(existing["id"])
            existing_hash = str(existing.get("content_hash") or "")
            if existing_hash == chunk_hash:
                stats["chunks_unchanged"] = int(stats["chunks_unchanged"]) + 1
                continue

            conn.execute(
                """
                UPDATE docs_chunks
                SET repo = ?,
                    path = ?,
                    doc_kind = ?,
                    heading_path = ?,
                    title = ?,
                    text = ?,
                    source_kind = ?,
                    source_ref = ?,
                    ts_hint = ?,
                    content_hash = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    repo,
                    rel_path,
                    doc_kind,
                    chunk.heading_path,
                    chunk.title,
                    chunk.text,
                    "operator",
                    f"{repo}/{rel_path}",
                    ts_hint,
                    chunk_hash,
                    now,
                    rowid,
                ),
            )
            stats["chunks_updated"] = int(stats["chunks_updated"]) + 1
            if bool(getattr(args, "embed", True)):
                embed_rows.append(
                    (
                        rowid,
                        _docs_embedding_input(
                            title=chunk.title,
                            heading_path=chunk.heading_path,
                            text=chunk.text,
                        ),
                        chunk_hash,
                    )
                )

        stale_ids = [
            int(r["id"])
            for r in existing_rows
            if str(r["chunk_id"] or "") not in seen_chunk_ids
        ]
        if stale_ids:
            placeholders = ",".join(["?"] * len(stale_ids))
            conn.execute(
                f"DELETE FROM docs_embeddings WHERE chunk_rowid IN ({placeholders})",
                stale_ids,
            )
            conn.execute(
                f"DELETE FROM docs_chunks WHERE id IN ({placeholders})",
                stale_ids,
            )
            stats["chunks_deleted"] = int(stats["chunks_deleted"]) + len(stale_ids)

        stats["files_ingested"] = int(stats["files_ingested"]) + 1

    embed_error: Optional[str] = None
    if bool(getattr(args, "embed", True)) and embed_rows:
        api_key = _get_api_key()
        if not api_key:
            embed_error = "missing_api_key"
        else:
            try:
                client = OpenAIEmbeddingsClient(api_key=api_key, base_url=getattr(args, "base_url", defaults.openai_base_url()))
                batch = max(1, int(getattr(args, "batch", 32) or 32))

                for i in range(0, len(embed_rows), batch):
                    batch_rows = embed_rows[i : i + batch]
                    texts = [x[1] for x in batch_rows]
                    vecs = client.embed(texts, model=model)
                    for (rowid, _text, text_hash), vec in zip(batch_rows, vecs):
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO docs_embeddings
                            (chunk_rowid, model, dim, vector, norm, text_hash, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (rowid, model, len(vec), pack_f32(vec), l2_norm(vec), text_hash, now),
                        )
                        stats["embedded"] = int(stats["embedded"]) + 1
            except Exception as e:
                embed_error = str(e)

    conn.commit()
    if embed_error:
        stats["embed_error"] = embed_error

    _emit(stats, args.json)


def _docs_fts_rows(conn: sqlite3.Connection, query: str, top_k: int) -> List[Dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.doc_id, c.chunk_id, c.repo, c.path, c.doc_kind, c.heading_path, c.title, c.text,
                   bm25(docs_chunks_fts) AS score
            FROM docs_chunks_fts
            JOIN docs_chunks c ON c.id = docs_chunks_fts.rowid
            WHERE docs_chunks_fts MATCH ?
            ORDER BY score ASC, c.id ASC
            LIMIT ?
            """,
            (query, int(top_k)),
        ).fetchall()
    except sqlite3.OperationalError:
        q2 = query
        if "-" in query and not query.strip().startswith('"'):
            q2 = f'"{query}"'
        try:
            rows = conn.execute(
                """
                SELECT c.id, c.doc_id, c.chunk_id, c.repo, c.path, c.doc_kind, c.heading_path, c.title, c.text,
                       bm25(docs_chunks_fts) AS score
                FROM docs_chunks_fts
                JOIN docs_chunks c ON c.id = docs_chunks_fts.rowid
                WHERE docs_chunks_fts MATCH ?
                ORDER BY score ASC, c.id ASC
                LIMIT ?
                """,
                (q2, int(top_k)),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

    return [dict(r) for r in rows]


def _docs_vec_rows(
    conn: sqlite3.Connection,
    *,
    query_vec: List[float],
    model: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    emb_rows = conn.execute(
        "SELECT chunk_rowid, vector, norm FROM docs_embeddings WHERE model = ?",
        (model,),
    ).fetchall()

    ranked = rank_cosine(
        query_vec=query_vec,
        items=((int(r["chunk_rowid"]), r["vector"], float(r["norm"])) for r in emb_rows),
        limit=max(1, int(top_k)),
    )
    if not ranked:
        return []

    ids = [rid for rid, _ in ranked]
    q = f"SELECT id, doc_id, chunk_id, repo, path, doc_kind, heading_path, title, text FROM docs_chunks WHERE id IN ({','.join(['?']*len(ids))})"
    chunk_rows = conn.execute(q, ids).fetchall()
    by_id = {int(r["id"]): dict(r) for r in chunk_rows}

    out: List[Dict[str, Any]] = []
    for rid, score in ranked:
        row = by_id.get(int(rid))
        if row is None:
            continue
        row["score"] = float(score)
        out.append(row)
    return out


def cmd_docs_search(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (getattr(args, "query", "") or "").strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    limit = max(1, int(getattr(args, "limit", 10) or 10))
    fts_k = max(limit, int(getattr(args, "fts_k", limit * 2) or (limit * 2)))
    vec_k = max(limit, int(getattr(args, "vec_k", limit * 2) or (limit * 2)))
    rrf_k = max(1, int(getattr(args, "k", 60) or 60))
    model = str(getattr(args, "model", defaults.embed_model()))

    fts_rows = _docs_fts_rows(conn, query, fts_k)
    fts_ids = [int(r["id"]) for r in fts_rows]

    vec_rows: List[Dict[str, Any]] = []
    vec_error: Optional[str] = None

    api_key = _get_api_key()
    if api_key:
        try:
            client = OpenAIEmbeddingsClient(api_key=api_key, base_url=getattr(args, "base_url", defaults.openai_base_url()))
            query_vec = client.embed([query], model=model)[0]
            vec_rows = _docs_vec_rows(conn, query_vec=query_vec, model=model, top_k=vec_k)
        except Exception as e:
            vec_error = str(e)
    else:
        vec_error = "missing_api_key"

    vec_ids = [int(r["id"]) for r in vec_rows]

    fused = fuse_rankings_rrf(
        fts_ids=fts_ids,
        vec_ids=vec_ids,
        k=rrf_k,
        limit=max(limit, fts_k, vec_k),
    )

    fused_ids = [rid for rid, _ in fused]
    if fused_ids:
        q = f"SELECT id, doc_id, chunk_id, repo, path, doc_kind, heading_path, title, text FROM docs_chunks WHERE id IN ({','.join(['?']*len(fused_ids))})"
        fused_rows = conn.execute(q, fused_ids).fetchall()
        fused_map = {int(r["id"]): dict(r) for r in fused_rows}
    else:
        fused_map = {}

    selected_ids = [rid for rid, _ in fused[:limit]]
    selected_map = {rid: fused_map[rid] for rid in selected_ids if rid in fused_map}

    final: List[Dict[str, Any]] = []
    for rid, rrf_score in fused[:limit]:
        row = selected_map.get(int(rid))
        if not row:
            continue

        row["recordRef"] = make_record_ref(
            repo=str(row.get("repo") or "local"),
            rel_path=str(row.get("path") or ""),
            chunk_id=str(row.get("chunk_id") or ""),
        )
        row["rrf_score"] = float(rrf_score)
        row["match"] = []
        if rid in fts_ids:
            row["match"].append("fts")
        if rid in vec_ids:
            row["match"].append("vector")
        final.append(row)

    payload: Dict[str, Any] = {
        "query": query,
        "results": final,
    }

    if bool(getattr(args, "trace", False)):
        fts_top = []
        for r in fts_rows[:fts_k]:
            fts_top.append(
                {
                    "id": int(r["id"]),
                    "recordRef": make_record_ref(
                        repo=str(r.get("repo") or "local"),
                        rel_path=str(r.get("path") or ""),
                        chunk_id=str(r.get("chunk_id") or ""),
                    ),
                    "score": float(r.get("score") or 0.0),
                }
            )

        vec_top = []
        for r in vec_rows[:vec_k]:
            vec_top.append(
                {
                    "id": int(r["id"]),
                    "recordRef": make_record_ref(
                        repo=str(r.get("repo") or "local"),
                        rel_path=str(r.get("path") or ""),
                        chunk_id=str(r.get("chunk_id") or ""),
                    ),
                    "score": float(r.get("score") or 0.0),
                }
            )

        fused_trace = rrf_components(fused=fused, fts_ids=fts_ids, vec_ids=vec_ids, k=rrf_k)
        for item in fused_trace:
            row = fused_map.get(int(item["id"]))
            if row is None:
                ref = None
            else:
                ref = make_record_ref(
                    repo=str(row.get("repo") or "local"),
                    rel_path=str(row.get("path") or ""),
                    chunk_id=str(row.get("chunk_id") or ""),
                )
            item["recordRef"] = ref

        payload["trace"] = {
            "query": query,
            "fts_top_k": fts_top,
            "vec_top_k": vec_top,
            "fused_ranking": fused_trace,
            "selected_chunks": [
                {
                    "id": int(r.get("id") or 0),
                    "recordRef": str(r.get("recordRef") or ""),
                    "text": (str(r.get("text") or "").strip()[:240] + ("…" if len(str(r.get("text") or "").strip()) > 240 else "")),
                }
                for r in final
            ],
        }

    if vec_error:
        payload["vector_status"] = vec_error

    if args.json:
        _emit(payload, True)
        return

    for item in final:
        text = str(item.get("text") or "").replace("\n", " ").strip()
        if len(text) > 140:
            text = text[:137] + "…"
        print(f"{item['recordRef']} :: {text}")


def cmd_get(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    ids = args.ids
    rows = conn.execute(
        f"SELECT * FROM observations WHERE id IN ({','.join(['?']*len(ids))}) ORDER BY id",
        ids,
    ).fetchall()
    _emit([dict(r) for r in rows], args.json)


def cmd_timeline(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    window = args.window
    seen = set()
    out = []
    for id_ in args.ids:
        lo, hi = id_ - window, id_ + window
        rows = conn.execute(
            "SELECT * FROM observations WHERE id BETWEEN ? AND ? ORDER BY id",
            (lo, hi),
        ).fetchall()
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            out.append(dict(r))
    out.sort(key=lambda x: x["id"])
    _emit(out, args.json)


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, list):
        for item in payload:
            _print_row(item)
        return
    if isinstance(payload, dict):
        for k, v in payload.items():
            print(f"{k}: {v}")
        return
    print(payload)


def _print_row(item: Dict[str, Any]) -> None:
    _id = item.get("id")
    ts = item.get("ts")
    kind = item.get("kind")
    tool = item.get("tool_name")
    summary = item.get("summary") or item.get("snippet")
    print(f"#{_id} {ts} [{kind}] {tool} :: {summary}")


def _get_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    """Get API key from env or ~/.openclaw/openclaw.json."""
    # 1. Try env
    api_key = os.environ.get(env_var)
    if api_key:
        return api_key

    # 2. Try config file
    data = _read_openclaw_config()
    # Traversing: agents -> defaults -> memorySearch -> remote -> apiKey
    key = (
        data.get("agents", {})
        .get("defaults", {})
        .get("memorySearch", {})
        .get("remote", {})
        .get("apiKey")
    )
    if key and isinstance(key, str):
        return key

    return None


def _get_gateway_config(args: argparse.Namespace, *, want_v1: bool = True) -> Dict[str, str]:
    """Resolve Gateway connection details (URL, token, agent_id).

    want_v1:
      - True: returns base URL ending with /v1
      - False: returns raw gateway base URL (no forced /v1)
    """
    config = _read_openclaw_config()

    # 1. URL
    url = getattr(args, "gateway_url", None)
    if not url:
        url = os.environ.get("OPENCLAW_GATEWAY_URL")
    if not url:
        # Construct from config port
        port = config.get("gateway", {}).get("http", {}).get("port") or config.get("gateway", {}).get("port", 18789)
        url = f"http://127.0.0.1:{port}"

    url = url.rstrip("/")
    if want_v1 and not url.endswith("/v1"):
        url = f"{url}/v1"

    # 2. Token
    token = getattr(args, "gateway_token", None)
    if not token:
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if not token:
        token = config.get("gateway", {}).get("auth", {}).get("token")

    # 3. Agent ID
    agent_id = getattr(args, "agent_id", None)
    if not agent_id:
        agent_id = os.environ.get("OPENCLAW_AGENT_ID", "main")

    return {
        "url": url,
        "token": token or "",
        "agent_id": agent_id,
    }


def _gateway_tools_invoke(
    args: argparse.Namespace,
    *,
    tool: str,
    tool_args: Dict[str, Any],
    session_key: str = "main",
    timeout: int = 120,
) -> Any:
    """Call OpenClaw Gateway `POST /tools/invoke`.

    This is the recommended black-box path for embeddings/memorySearch.
    """
    gw = _get_gateway_config(args, want_v1=False)
    if not gw["token"]:
        raise RuntimeError("Gateway token not found (set OPENCLAW_GATEWAY_TOKEN or configure gateway.auth.token)")

    url = gw["url"].rstrip("/") + "/tools/invoke"
    payload = {
        "tool": tool,
        "args": tool_args,
        "sessionKey": session_key,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {gw['token']}",
            "Content-Type": "application/json",
            "x-openclaw-agent-id": gw["agent_id"],
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gateway tools/invoke error ({e.code}): {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"Error calling Gateway tools/invoke: {e}") from e

    data = json.loads(body)
    if not isinstance(data, dict) or not data.get("ok"):
        raise RuntimeError(f"tools/invoke returned error: {body[:2000]}")
    return data.get("result")


def cmd_summarize(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Run AI compression on observations (requires compress_memory.py)."""
    try:
        # Import compress_memory module
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from compress_memory import OpenAIClient, compress_daily_note, CompressError
    except ImportError as e:
        _emit({"error": f"Failed to import compress_memory: {e}"}, args.json)
        sys.exit(1)

    use_gateway = bool(getattr(args, "gateway", False) or os.environ.get("OPENCLAW_MEM_USE_GATEWAY") == "1")

    api_key: Optional[str] = None
    base_url: str = defaults.openai_base_url()
    extra_headers: Dict[str, str] = {}
    model = args.model if hasattr(args, "model") else defaults.summary_model()

    if use_gateway:
        gw_conf = _get_gateway_config(args)
        base_url = gw_conf["url"]
        api_key = gw_conf["token"]
        extra_headers["x-openclaw-agent-id"] = gw_conf["agent_id"]
        
        # Switch default model if user didn't override it (heuristic: check against default)
        # If model is the configured default, we can switch to "openclaw:<agent>".
        if model == defaults.summary_model():
             model = f"openclaw:{gw_conf['agent_id']}"
             
        if not api_key:
             _emit({"error": "Gateway token not found (check ~/.openclaw/openclaw.json or use --gateway-token)"}, args.json)
             sys.exit(1)
    else:
        # Get API key (standard OpenAI path)
        api_key = _get_api_key()
        if not api_key:
            _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"}, args.json)
            sys.exit(1)
        base_url = args.base_url if hasattr(args, "base_url") else defaults.openai_base_url()

    # Determine workspace
    workspace = Path(args.workspace) if hasattr(args, "workspace") and args.workspace else DEFAULT_WORKSPACE

    memory_dir = workspace / "memory"
    memory_file = workspace / "MEMORY.md"
    prompt_file = workspace / "scripts/prompts/compress_memory.txt"

    # Determine date
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Create client
    client = OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        extra_headers=extra_headers,
    )

    # Run compression
    try:
        result = compress_daily_note(
            date=target_date,
            memory_dir=memory_dir,
            memory_file=memory_file,
            prompt_file=prompt_file,
            client=client,
            model=model,
            max_tokens=args.max_tokens if hasattr(args, "max_tokens") else 700,
            temperature=args.temperature if hasattr(args, "temperature") else 0.2,
            dry_run=args.dry_run if hasattr(args, "dry_run") else False,
        )
        _emit(result, args.json)
    except CompressError as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)


def _atomic_append_file(path_: Path, content: str) -> None:
    """Append to a file atomically (write-to-temp + replace)."""
    path_.parent.mkdir(parents=True, exist_ok=True)
    existing = path_.read_text(encoding="utf-8") if path_.exists() else ""

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".txt",
    ) as tmp:
        tmp.write(existing + content)
        tmp_path = Path(tmp.name)

    tmp_path.replace(path_)


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Export observations to a file (Markdown by default).

    Safety:
    - Writing to MEMORY.md requires --yes.
    """
    out_path = Path(args.to)

    # Safety: exporting to MEMORY.md requires explicit confirmation
    if out_path.name == "MEMORY.md" and not args.yes:
        _emit(
            {
                "error": "Export to MEMORY.md requires --yes flag",
                "hint": "See docs/privacy-export-rules.md",
            },
            args.json,
        )
        sys.exit(2)

    ids: Optional[List[int]] = getattr(args, "ids", None)
    limit: int = int(getattr(args, "limit", 50))
    include_detail: bool = bool(getattr(args, "include_detail", False))

    if ids:
        q = f"SELECT * FROM observations WHERE id IN ({','.join(['?']*len(ids))}) ORDER BY id"
        rows = conn.execute(q, ids).fetchall()
    else:
        rows = conn.execute("SELECT * FROM observations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        rows = list(reversed(rows))

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = f"\n\n## Exported observations ({ts})\n"

    md = [header]
    for r in rows:
        rid = r["id"]
        rts = r["ts"]
        kind = r["kind"] or ""
        tool = r["tool_name"] or ""
        summary = (r["summary"] or "").strip()
        md.append(f"- #{rid} {rts} [{kind}] {tool} :: {summary}\n")
        if include_detail:
            md.append("\n```json\n")
            md.append((r["detail_json"] or "{}").strip() + "\n")
            md.append("```\n")

    _atomic_append_file(out_path, "".join(md))

    _emit(
        {
            "ok": True,
            "exported": len(rows),
            "to": str(out_path),
            "include_detail": include_detail,
        },
        args.json,
    )


class OpenAIEmbeddingsClient:
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = (base_url or defaults.openai_base_url()).rstrip("/")

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        url = self.base_url + "/embeddings"
        payload = {"model": model, "input": texts}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI embeddings API error ({e.code}): {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"Error calling OpenAI embeddings API: {e}") from e

        data = json.loads(body)
        out: List[List[float]] = []
        for item in data.get("data", []):
            out.append(item["embedding"])
        return out


def _embed_targets(field: str) -> List[Dict[str, str]]:
    if field == "original":
        return [{"name": "original", "text_col": "summary", "table": "observation_embeddings"}]
    if field == "english":
        return [{"name": "english", "text_col": "summary_en", "table": "observation_embeddings_en"}]
    return [
        {"name": "original", "text_col": "summary", "table": "observation_embeddings"},
        {"name": "english", "text_col": "summary_en", "table": "observation_embeddings_en"},
    ]


def cmd_embed(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Compute/store embeddings for observations."""
    api_key = _get_api_key()
    if not api_key:
        _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json"}, args.json)
        sys.exit(1)

    model = args.model
    limit = int(args.limit)
    batch = int(args.batch)
    base_url = args.base_url
    field = getattr(args, "field", "original")

    client = OpenAIEmbeddingsClient(api_key=api_key, base_url=base_url)

    per_field: Dict[str, Dict[str, Any]] = {}
    inserted_total = 0
    ids: List[int] = []
    now = _utcnow_iso()

    for target in _embed_targets(field):
        _warn_embedding_model_mismatch(
            conn,
            table=target["table"],
            requested_model=model,
            label=target["name"],
        )

        rows = conn.execute(
            f"""
            SELECT id, tool_name, {target['text_col']} AS text_value
            FROM observations
            WHERE id NOT IN (
                SELECT observation_id FROM {target['table']} WHERE model = ?
            )
            AND trim(coalesce({target['text_col']}, '')) <> ''
            ORDER BY id
            LIMIT ?
            """,
            (model, limit),
        ).fetchall()

        todo = [dict(r) for r in rows]
        inserted = 0
        field_ids: List[int] = []

        for i in range(0, len(todo), batch):
            chunk = todo[i : i + batch]
            texts = []
            chunk_ids = []
            for r in chunk:
                tid = int(r["id"])
                tool = (r.get("tool_name") or "").strip()
                summary = (r.get("text_value") or "").strip()
                text = f"{tool}: {summary}".strip(": ")
                texts.append(text)
                chunk_ids.append(tid)

            vecs = client.embed(texts, model=model)
            for tid, vec in zip(chunk_ids, vecs):
                blob = pack_f32(vec)
                norm = l2_norm(vec)
                dim = len(vec)
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {target['table']}
                    (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tid, model, dim, blob, norm, now),
                )
                inserted += 1
                inserted_total += 1
                field_ids.append(tid)
                ids.append(tid)

            conn.commit()

        per_field[target["name"]] = {
            "embedded": inserted,
            "ids": field_ids[:50],
            "total_candidates": len(todo),
        }

    _emit(
        {
            "ok": True,
            "model": model,
            "field": field,
            "embedded": inserted_total,
            "ids": ids[:50],
            "per_field": per_field,
        },
        args.json,
    )


def _warn_embedding_model_availability(
    conn: sqlite3.Connection,
    *,
    table: str,
    requested_model: str,
    label: str,
) -> None:
    try:
        rows = conn.execute(
            f"SELECT model, COUNT(*) AS n FROM {table} GROUP BY model ORDER BY n DESC"
        ).fetchall()
    except Exception:
        return

    if not rows:
        return

    available = {str(r[0]): int(r[1]) for r in rows}
    if requested_model in available:
        return

    preview = ", ".join([f"{m}({n})" for m, n in list(available.items())[:5]])
    print(
        f"[openclaw-mem] Warning: requested {label} embedding model '{requested_model}' not found; "
        f"available: {preview}",
        file=sys.stderr,
    )


def _warn_embedding_model_mismatch(
    conn: sqlite3.Connection,
    *,
    table: str,
    requested_model: str,
    label: str,
) -> None:
    """Warn when multiple embedding models exist in the same table.

    This is not an error, but it is a common source of silent quality drift:
    operators change the default model and later wonder why recall differs.
    """

    try:
        rows = conn.execute(
            f"SELECT model, COUNT(*) AS n FROM {table} GROUP BY model ORDER BY n DESC"
        ).fetchall()
    except Exception:
        return

    if not rows:
        return

    available = {str(r[0]): int(r[1]) for r in rows}
    if requested_model not in available:
        return

    others = {m: n for m, n in available.items() if m != requested_model and n > 0}
    if not others:
        return

    preview = ", ".join([f"{m}({n})" for m, n in list(others.items())[:5]])
    print(
        f"[openclaw-mem] Warning: {label} embeddings include multiple models. "
        f"Using '{requested_model}', but also saw: {preview}",
        file=sys.stderr,
    )


def cmd_vsearch(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Vector search over stored embeddings (cosine similarity)."""
    model = args.model
    limit = int(args.limit)

    _warn_embedding_model_availability(
        conn,
        table="observation_embeddings",
        requested_model=model,
        label="original",
    )

    # Get query vector from file/json or via OpenAI API
    query_vec: Optional[List[float]] = None

    if getattr(args, "query_vector_json", None):
        query_vec = json.loads(args.query_vector_json)
    elif getattr(args, "query_vector_file", None):
        query_vec = json.loads(Path(args.query_vector_file).read_text(encoding="utf-8"))
    else:
        api_key = _get_api_key()
        if not api_key:
            _emit({"error": "OPENAI_API_KEY not set and no key found in ~/.openclaw/openclaw.json (or provide --query-vector-json/--query-vector-file)"}, args.json)
            sys.exit(1)
        client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
        query_vec = client.embed([args.query], model=model)[0]

    # Load embeddings
    items = conn.execute(
        "SELECT observation_id, vector, norm FROM observation_embeddings WHERE model = ?",
        (model,),
    ).fetchall()

    ranked = rank_cosine(
        query_vec=query_vec,
        items=((int(r[0]), r[1], float(r[2])) for r in items),
        limit=limit,
    )

    if not ranked:
        _emit([], args.json)
        return

    ids = [rid for rid, _ in ranked]
    q = f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?']*len(ids))})"
    rows = conn.execute(q, ids).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    out = []
    for rid, score in ranked:
        r = obs_map.get(rid)
        if not r:
            continue
        r["score"] = score
        out.append(r)

    _emit(out, args.json)


def _resolve_rerank_api_key(provider: str, args: argparse.Namespace) -> Optional[str]:
    cli_key = getattr(args, "rerank_api_key", None)
    if cli_key:
        return str(cli_key)

    env_map = {
        "jina": "JINA_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    env_key = env_map.get(provider)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val

    return None


def _default_rerank_url(provider: str) -> str:
    if provider == "jina":
        return "https://api.jina.ai/v1/rerank"
    if provider == "cohere":
        return "https://api.cohere.com/v2/rerank"
    raise ValueError(f"unsupported rerank provider: {provider}")


def _call_rerank_provider(
    *,
    provider: str,
    query: str,
    documents: List[str],
    model: str,
    top_n: int,
    api_key: str,
    base_url: Optional[str] = None,
    timeout_sec: int = 15,
) -> List[Tuple[int, float]]:
    url = (base_url or _default_rerank_url(provider)).rstrip("/")

    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": int(top_n),
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"rerank HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"rerank network error: {e}") from e

    parsed = json.loads(raw)
    rows = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return []

    out: List[Tuple[int, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        score = row.get("relevance_score", row.get("score", 0.0))
        try:
            out.append((int(idx), float(score)))
        except Exception:
            continue

    return out


def _hybrid_retrieve(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    *,
    candidate_limit_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Shared Hybrid retrieval core (FTS + Vector + RRF + optional rerank)."""
    model = str(getattr(args, "model", defaults.embed_model()))
    limit = max(1, int(getattr(args, "limit", 20)))
    k = int(getattr(args, "k", 60))
    query = (getattr(args, "query", None) or "").strip()
    query_en = (getattr(args, "query_en", None) or "").strip() or None

    rerank_provider = str(getattr(args, "rerank_provider", "none") or "none").lower()
    rerank_enabled = rerank_provider != "none"

    _warn_embedding_model_availability(
        conn,
        table="observation_embeddings",
        requested_model=model,
        label="original",
    )
    _warn_embedding_model_mismatch(
        conn,
        table="observation_embeddings",
        requested_model=model,
        label="original",
    )
    if query_en:
        _warn_embedding_model_availability(
            conn,
            table="observation_embeddings_en",
            requested_model=model,
            label="english",
        )
        _warn_embedding_model_mismatch(
            conn,
            table="observation_embeddings_en",
            requested_model=model,
            label="english",
        )
    rerank_topn = max(1, int(getattr(args, "rerank_topn", limit) or limit))

    candidate_limit = int(candidate_limit_override) if candidate_limit_override is not None else limit * 2
    candidate_limit = max(1, candidate_limit)
    if rerank_enabled:
        # Keep a wider candidate pool before final rerank.
        candidate_limit = max(candidate_limit, rerank_topn * 3)

    # Vector lane is optional: if no API key (or no stored embeddings), we
    # fall back to FTS-only retrieval.
    vec_ids: List[int] = []
    vec_en_ids: List[int] = []

    vec_rows = conn.execute(
        "SELECT observation_id, vector, norm FROM observation_embeddings WHERE model = ?",
        (model,),
    ).fetchall()

    vec_en_rows = []
    if query_en:
        vec_en_rows = conn.execute(
            "SELECT observation_id, vector, norm FROM observation_embeddings_en WHERE model = ?",
            (model,),
        ).fetchall()

    need_vec = bool(vec_rows)
    need_vec_en = bool(query_en and (vec_en_rows or vec_rows))

    api_key = _get_api_key()
    if api_key and (need_vec or need_vec_en):
        client = OpenAIEmbeddingsClient(
            api_key=api_key,
            base_url=getattr(args, "base_url", defaults.openai_base_url()),
        )
        try:
            embed_inputs = [query] + ([query_en] if query_en else [])
            embed_vecs = client.embed(embed_inputs, model=model)
            query_vec = embed_vecs[0]
            query_en_vec = embed_vecs[1] if query_en else None
        except Exception as e:
            raise RuntimeError(str(e)) from e

        if need_vec:
            vec_ranked = rank_cosine(
                query_vec=query_vec,
                items=((int(r[0]), r[1], float(r[2])) for r in vec_rows),
                limit=candidate_limit,
            )
            vec_ids = [rid for rid, _ in vec_ranked]

        if query_en_vec is not None and need_vec_en:
            # Backward-compatible fallback when dedicated EN table is not populated.
            search_rows = vec_en_rows if vec_en_rows else vec_rows

            vec_en_ranked = rank_cosine(
                query_vec=query_en_vec,
                items=((int(r[0]), r[1], float(r[2])) for r in search_rows),
                limit=candidate_limit,
            )
            vec_en_ids = [rid for rid, _ in vec_en_ranked]
    else:
        if not api_key and (need_vec or need_vec_en):
            print("Warning: No API key, skipping vector retrieval", file=sys.stderr)

    fts_rows = []
    try:
        fts_rows = conn.execute(
            """
            SELECT rowid
            FROM observations_fts
            WHERE observations_fts MATCH ?
            ORDER BY bm25(observations_fts) ASC
            LIMIT ?;
            """,
            (query, candidate_limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # FTS syntax can fail for edge-case query strings (hyphens/operators/punctuation).
        # Prefer fail-open behavior:
        # 1) retry once with a best-effort sanitized query
        # 2) if it still fails, skip the FTS lane (instead of crashing)
        sanitized = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
        sanitized = " ".join(sanitized.split())
        retry_query = sanitized if sanitized else query

        if retry_query != query:
            try:
                fts_rows = conn.execute(
                    """
                    SELECT rowid
                    FROM observations_fts
                    WHERE observations_fts MATCH ?
                    ORDER BY bm25(observations_fts) ASC
                    LIMIT ?;
                    """,
                    (retry_query, candidate_limit),
                ).fetchall()
            except sqlite3.OperationalError:
                print(
                    f"[openclaw-mem] FTS query parse failed; skipping FTS lane (query={query!r}).",
                    file=sys.stderr,
                )
        else:
            print(
                f"[openclaw-mem] FTS query parse failed; skipping FTS lane (query={query!r}).",
                file=sys.stderr,
            )
    fts_ids = [int(r["rowid"]) for r in fts_rows]

    # If the query is a multi-token natural-language string, FTS5 MATCH defaults
    # to an implicit AND, which can easily yield zero hits. As a best-effort
    # fallback (especially when vector search is unavailable), retry with an OR
    # query to recover some signal.
    if not fts_ids:
        tokens = [t for t in re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE).split() if t]
        if len(tokens) > 1:
            or_query = " OR ".join(tokens)
            try:
                fts_rows = conn.execute(
                    """
                    SELECT rowid
                    FROM observations_fts
                    WHERE observations_fts MATCH ?
                    ORDER BY bm25(observations_fts) ASC
                    LIMIT ?;
                    """,
                    (or_query, candidate_limit),
                ).fetchall()
                fts_ids = [int(r["rowid"]) for r in fts_rows]
            except sqlite3.OperationalError:
                pass

    ranked_lists = [fts_ids, vec_ids]
    if vec_en_ids:
        ranked_lists.append(vec_en_ids)

    rrf_ranking = rank_rrf(ranked_lists, k=k, limit=candidate_limit)
    if not rrf_ranking:
        return {
            "ordered_ids": [],
            "obs_map": {},
            "rrf_scores": {},
            "fts_ids": fts_ids,
            "vec_ids": vec_ids,
            "vec_en_ids": vec_en_ids,
            "rerank_scores": {},
            "rerank_applied": False,
            "rerank_provider": rerank_provider,
            "rerank_enabled": rerank_enabled,
            "candidate_limit": candidate_limit,
        }

    rrf_scores = {rid: score for rid, score in rrf_ranking}
    ordered_ids = [rid for rid, _ in rrf_ranking]

    q_sql = f"SELECT id, ts, kind, tool_name, summary, summary_en, lang FROM observations WHERE id IN ({','.join(['?']*len(ordered_ids))})"
    rows = conn.execute(q_sql, ordered_ids).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    rerank_scores: Dict[int, float] = {}
    rerank_applied = False

    if rerank_enabled and ordered_ids:
        if rerank_provider not in {"jina", "cohere"}:
            print(
                f"[openclaw-mem] rerank provider '{rerank_provider}' unsupported; using base RRF ranking.",
                file=sys.stderr,
            )
        else:
            rerank_api_key = _resolve_rerank_api_key(rerank_provider, args)
            if not rerank_api_key:
                print(
                    f"[openclaw-mem] rerank provider '{rerank_provider}' enabled but API key missing; using base RRF ranking.",
                    file=sys.stderr,
                )
            else:
                docs = [
                    (obs_map.get(rid, {}).get("summary_en") or obs_map.get(rid, {}).get("summary") or "")
                    for rid in ordered_ids
                ]
                try:
                    rerank_rows = _call_rerank_provider(
                        provider=rerank_provider,
                        query=query_en or query,
                        documents=docs,
                        model=str(getattr(args, "rerank_model", defaults.rerank_model())),
                        top_n=min(rerank_topn, len(docs)),
                        api_key=rerank_api_key,
                        base_url=getattr(args, "rerank_base_url", None),
                        timeout_sec=int(getattr(args, "rerank_timeout_sec", 15) or 15),
                    )
                    if rerank_rows:
                        seen: set[int] = set()
                        reranked: List[int] = []

                        for idx, score in rerank_rows:
                            if idx < 0 or idx >= len(ordered_ids):
                                continue
                            rid = ordered_ids[idx]
                            if rid in seen:
                                continue
                            seen.add(rid)
                            reranked.append(rid)
                            rerank_scores[rid] = float(score)

                        for rid in ordered_ids:
                            if rid not in seen:
                                reranked.append(rid)

                        ordered_ids = reranked
                        rerank_applied = True
                except Exception as e:
                    print(
                        f"[openclaw-mem] rerank failed ({type(e).__name__}: {e}); using base RRF ranking.",
                        file=sys.stderr,
                    )

    return {
        "ordered_ids": ordered_ids,
        "obs_map": obs_map,
        "rrf_scores": rrf_scores,
        "fts_ids": fts_ids,
        "vec_ids": vec_ids,
        "vec_en_ids": vec_en_ids,
        "rerank_scores": rerank_scores,
        "rerank_applied": rerank_applied,
        "rerank_provider": rerank_provider,
        "rerank_enabled": rerank_enabled,
        "candidate_limit": candidate_limit,
    }


def cmd_hybrid(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Hybrid search (FTS + Vector) using RRF.

    Optional post-retrieval rerank (opt-in):
    - provider: none|jina|cohere
    - fail-open: rerank errors do not break search
    """
    limit = int(args.limit)

    try:
        state = _hybrid_retrieve(conn, args)
    except RuntimeError as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)

    ordered_ids = state["ordered_ids"]
    if not ordered_ids:
        _emit([], args.json)
        return

    out = []
    for rid in ordered_ids[:limit]:
        r = state["obs_map"].get(rid)
        if not r:
            continue

        r["rrf_score"] = float(state["rrf_scores"].get(rid, 0.0))
        r["match"] = []
        if rid in state["fts_ids"]:
            r["match"].append("text")
        if rid in state["vec_ids"]:
            r["match"].append("vector")
        if rid in state["vec_en_ids"]:
            r["match"].append("vector_en")

        if state["rerank_enabled"]:
            r["rerank_provider"] = state["rerank_provider"]
            if rid in state["rerank_scores"]:
                r["rerank_score"] = float(state["rerank_scores"][rid])
            if state["rerank_applied"]:
                r["rank_stage"] = "rerank" if rid in state["rerank_scores"] else "rrf-fallback"

        out.append(r)

    _emit(out, args.json)


def _pack_item_text(row: Dict[str, Any]) -> str:
    return ((row.get("summary_en") or row.get("summary") or "").replace("\n", " ").strip())


def _pack_parse_detail_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_importance_label(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None

    key = raw.strip().lower()
    if not key:
        return None

    aliases = {
        "must remember": "must_remember",
        "must-remember": "must_remember",
        "nice to have": "nice_to_have",
        "nice-to-have": "nice_to_have",
        "low": "ignore",
        "medium": "nice_to_have",
        "high": "must_remember",
    }
    key = aliases.get(key, key)
    key = key.replace("-", "_").replace(" ", "_")

    if key in {"must_remember", "nice_to_have", "ignore", "unknown"}:
        return key
    return None


def _pack_importance_label(detail_obj: Dict[str, Any]) -> str:
    if not isinstance(detail_obj, dict) or "importance" not in detail_obj:
        return "unknown"

    importance = detail_obj.get("importance")
    normalized_label = None

    if isinstance(importance, dict):
        normalized_label = _normalize_importance_label(importance.get("label"))
        if normalized_label:
            return normalized_label

        score = importance.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            from openclaw_mem.importance import label_from_score

            return label_from_score(float(score))
        return "unknown"

    if isinstance(importance, (int, float)) and not isinstance(importance, bool):
        from openclaw_mem.importance import label_from_score

        return label_from_score(float(importance))

    return "unknown"


def _normalize_trust_tier(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None

    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "quarantine": "quarantined",
    }
    key = aliases.get(key, key)

    if key in {"trusted", "untrusted", "quarantined"}:
        return key
    return None


def _pack_trust_tier(detail_obj: Dict[str, Any]) -> str:
    if not isinstance(detail_obj, dict):
        return "unknown"

    candidates: List[Any] = [
        detail_obj.get("trust"),
        detail_obj.get("trust_tier"),
        detail_obj.get("trustTier"),
    ]

    provenance = detail_obj.get("provenance")
    if isinstance(provenance, dict):
        candidates.extend(
            [
                provenance.get("trust"),
                provenance.get("trust_tier"),
                provenance.get("trustTier"),
            ]
        )

    for value in candidates:
        normalized = _normalize_trust_tier(value)
        if normalized:
            return normalized

    return "unknown"


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)




_ACK_RE = re.compile(r"^(yes|no|y|n|ok|done|lgtm|k|thx|thanks|👍)$", re.IGNORECASE)


def _pack_graph_stage0_anti_trigger(query: str) -> str | None:
    """Return anti-trigger reason or None.

    Keep this conservative: we only skip when it is *very* likely not a retrieval request.
    """
    q = (query or "").strip()
    if not q:
        return "empty"

    # Token count heuristic.
    toks = [t for t in re.split(r"\s+", q) if t]
    if len(toks) < 3:
        if _ACK_RE.match(q):
            return "ack_pattern"
        return "too_short"

    # If user pasted tool output / stack traces, treat as "not asking".
    if q.startswith("```") or q.startswith("Traceback") or q.startswith("Error:"):
        return "paste_detect"

    return None


def _pack_graph_stage1_keywords(query: str) -> dict:
    q = (query or "").lower()

    buckets = {
        "A": [
            "spec",
            "docs",
            "documentation",
            "roadmap",
            "decision",
            "tech note",
            "design",
            "architecture",
            "prd",
            "sop",
            "runbook",
            "文件",
            "文檔",
            "規格",
            "決策",
            "紀錄",
            "技術筆記",
            "架構",
            "設計",
            "流程",
        ],
        "B": [
            "where is",
            "where are",
            "find",
            "locate",
            "which file",
            "link to",
            "point me to",
            "在哪",
            "哪裡",
            "搜尋",
            "定位",
            "哪個檔",
            "連結",
            "指到",
            "出處",
        ],
        "C": [
            "dependency",
            "depends on",
            "related",
            "relationship",
            "connect",
            "tie to",
            "依賴",
            "關聯",
            "之間關係",
            "相關",
            "影響範圍",
            "串起來",
        ],
        "D": [
            "confirm",
            "verify",
            "is it true",
            "did we",
            "current status",
            "latest",
            "what changed",
            "changelog",
            "確認",
            "驗證",
            "是不是真的",
            "我們有沒有",
            "目前狀態",
            "最新",
            "改了什麼",
            "變更",
        ],
        "E": [
            "decisions",
            "tech_notes",
            "tech notes",
            "pm",
            "status",
            "index",
            "quickstart",
            "changelog",
            "docs/specs/",
            "projects/",
        ],
    }

    categories = []
    matched = []

    for cat, toks in buckets.items():
        for t in toks:
            if t and t in q:
                if cat not in categories:
                    categories.append(cat)
                if len(matched) < 5:
                    matched.append(t)

    return {
        "hit": bool(categories),
        "categories": categories,
        "matched_keywords": matched,
    }


def _pack_graph_probe_observations(
    conn: sqlite3.Connection,
    query: str,
    *,
    probe_limit: int,
    scope: Optional[str] = None,
) -> dict:
    """Lightweight deterministic FTS probe (semantic-by-retrieval).

    Returns redaction-safe aggregate-only stats.
    """
    q = (query or "").strip()

    # Keep probe robust to pasted code fences / URLs.
    q = q.replace("```", " ")
    q = re.sub(r"https?://\S+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    if not q:
        return {"ran": False, "reason": "empty_after_strip"}

    started = time.perf_counter()
    rows = _graph_search_rows(conn, q, int(max(1, probe_limit)), scope=scope)
    dt_ms = int((time.perf_counter() - started) * 1000)

    scores = []
    for r in rows:
        s = r["score"] if isinstance(r, sqlite3.Row) else None
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            scores.append(float(s))

    best = min(scores) if scores else None

    return {
        "ran": True,
        "latency_ms": dt_ms,
        "hit_count": len(rows),
        "best_score": best,
        "scores": scores,
    }


def _pack_graph_preflight_optional(conn: sqlite3.Connection, *, query: str, args: argparse.Namespace) -> dict:
    """Optional Graphic Memory preflight for `pack` (default OFF; fail-open).

    Returns:
    - triggered + reason
    - preflight payload (if triggered)
    - trace extension (redaction-safe)
    """

    use_graph = str(getattr(args, "use_graph", "off") or "off").strip().lower()

    # Default: no-op
    out = {
        "use_graph": use_graph,
        "triggered": False,
        "trigger_reason": "off",
        "fail_open": True,
        "error_first_line": None,
        "selection_count": 0,
        "budget_tokens": int(max(1, int(getattr(args, "graph_budget_tokens", 1200) or 1200))),
        "take": int(max(1, int(getattr(args, "graph_take", 12) or 12))),
        "scope": (str(getattr(args, "graph_scope", "") or "").strip() or None),
        "probe": {"ran": False},
        "stage0": {"fired": False, "reason": None},
        "stage1": {"hit": False, "categories": [], "matched_keywords": []},
        "probe_decision": None,
        "payload": None,
    }

    if use_graph not in {"off", "auto", "on"}:
        return out

    if use_graph == "off":
        return out

    # Stage 0
    anti = _pack_graph_stage0_anti_trigger(query)
    if anti:
        out["stage0"] = {"fired": True, "reason": anti}
        if use_graph != "on":
            out["triggered"] = False
            out["trigger_reason"] = f"anti:{anti}"
            return out

    # Stage 1
    stage1 = _pack_graph_stage1_keywords(query)
    out["stage1"] = stage1

    # Forced
    if use_graph == "on":
        out["triggered"] = True
        out["trigger_reason"] = "forced_on"
    elif bool(stage1.get("hit")):
        out["triggered"] = True
        out["trigger_reason"] = "keyword:" + "+".join(stage1.get("categories") or [])
    else:
        # Stage 2 probe (auto only)
        probe_flag = getattr(args, "graph_probe", None)
        probe_enabled = True if probe_flag is None else (str(probe_flag).strip().lower() == "on")
        if not probe_enabled:
            out["triggered"] = False
            out["trigger_reason"] = "auto_probe_off"
            return out

        probe_limit = int(max(1, int(getattr(args, "graph_probe_limit", 5) or 5)))
        t_high = float(getattr(args, "graph_probe_t_high", -5.0) or -5.0)
        t_marginal = float(getattr(args, "graph_probe_t_marginal", -2.0) or -2.0)
        n_min = int(max(1, int(getattr(args, "graph_probe_n_min", 3) or 3)))

        probe = _pack_graph_probe_observations(
            conn,
            query,
            probe_limit=probe_limit,
            scope=out.get("scope"),
        )
        out["probe"] = {
            "ran": bool(probe.get("ran")),
            "latency_ms": int(probe.get("latency_ms") or 0),
            "hit_count": int(probe.get("hit_count") or 0),
            "best_score": probe.get("best_score"),
        }

        scores = list(probe.get("scores") or [])
        best = probe.get("best_score")
        marginal_count = sum(1 for s in scores if isinstance(s, (int, float)) and float(s) <= float(t_marginal))

        if not scores:
            out["triggered"] = False
            out["trigger_reason"] = "probe_empty"
            out["probe_decision"] = "skip_empty"
        elif isinstance(best, (int, float)) and float(best) <= float(t_high):
            out["triggered"] = True
            out["trigger_reason"] = "probe_strong"
            out["probe_decision"] = "fire_probe_strong"
        elif isinstance(best, (int, float)) and float(best) <= float(t_marginal) and marginal_count >= n_min:
            out["triggered"] = True
            out["trigger_reason"] = "probe_breadth"
            out["probe_decision"] = "fire_probe_breadth"
        else:
            out["triggered"] = False
            out["trigger_reason"] = "probe_weak"
            out["probe_decision"] = "skip_weak"

    if not out["triggered"]:
        return out

    # If triggered: run preflight (fail-open)
    try:
        index_payload = _graph_index_payload(
            conn,
            query=query,
            scope=out["scope"],
            limit=12,
            window=2,
            suggest_limit=6,
            budget_tokens=int(out["budget_tokens"]),
        )
        selected_refs = _graph_preflight_selection(index_payload, take=int(out["take"]))
        pack_payload = _graph_pack_payload(
            conn,
            raw_ids=selected_refs,
            budget_tokens=int(out["budget_tokens"]),
            max_items=int(out["take"]),
            allow_empty=True,
        )

        out["selection_count"] = len(selected_refs)
        out["payload"] = {
            "kind": "openclaw-mem.graph.preflight.v0",
            "query": {"text": query, "scope": out["scope"]},
            "selection": {"take": int(out["take"]), "selectedCount": len(selected_refs), "recordRefs": selected_refs},
            "budget": {"budgetTokens": int(out["budget_tokens"]), "estimatedTokens": _estimate_tokens(pack_payload.get("bundle_text", "") or "")},
            "pack": pack_payload,
            "items": pack_payload.get("items", []),
            "bundle_text": pack_payload.get("bundle_text", "") or "",
        }

        out["fail_open"] = False
    except Exception as e:
        line = (str(e).splitlines() or [str(e)])[:1][0]
        out["error_first_line"] = line[:200]
        out["fail_open"] = True

    return out


def _pack_graph_trace_extension(graph_state: dict) -> dict:
    """Redaction-safe graph trigger/probe receipt for pack --trace."""
    if not isinstance(graph_state, dict):
        return {}

    pre = graph_state.get("payload") or {}
    return {
        "triggered": bool(graph_state.get("triggered")),
        "trigger_reason": graph_state.get("trigger_reason"),
        "stage0": graph_state.get("stage0"),
        "stage1": graph_state.get("stage1"),
        "probe": graph_state.get("probe"),
        "probe_decision": graph_state.get("probe_decision"),
        "selected_refs_count": int(graph_state.get("selection_count") or 0),
        "budget_tokens": int(graph_state.get("budget_tokens") or 0),
        "take": int(graph_state.get("take") or 0),
        "scope": graph_state.get("scope"),
        "fail_open": bool(graph_state.get("fail_open")),
        "error_first_line": graph_state.get("error_first_line"),
        "preflight_kind": pre.get("kind"),
    }


def cmd_pack(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Build a compact, cited L1-style bundle from hybrid retrieval."""
    query = (args.query or "").strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    limit = max(1, int(args.limit))
    budget_tokens = max(1, int(args.budget_tokens))
    max_l2_items = 0
    nice_cap = 100

    started = time.perf_counter()

    graph_state = _pack_graph_preflight_optional(conn, query=query, args=args)

    retrieval_args = argparse.Namespace(
        query=query,
        query_en=getattr(args, "query_en", None),
        limit=limit,
        k=60,
        model=defaults.embed_model(),
        base_url=defaults.openai_base_url(),
        rerank_provider="none",
        rerank_topn=limit,
        rerank_model=defaults.rerank_model(),
        rerank_api_key=None,
        rerank_base_url=None,
        rerank_timeout_sec=15,
    )

    try:
        state = _hybrid_retrieve(
            conn,
            retrieval_args,
            candidate_limit_override=max(limit * 3, limit + 8),
        )
    except RuntimeError as e:
        _emit({"error": str(e)}, True)
        sys.exit(1)

    ordered_ids = state["ordered_ids"]
    obs_map = state["obs_map"]

    detail_map: Dict[int, Dict[str, Any]] = {}
    if ordered_ids:
        q_detail = f"SELECT id, detail_json FROM observations WHERE id IN ({','.join(['?']*len(ordered_ids))})"
        detail_rows = conn.execute(q_detail, ordered_ids).fetchall()
        detail_map = {int(r["id"]): _pack_parse_detail_json(r["detail_json"]) for r in detail_rows}

    selected_items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    candidate_trace: List[pack_trace_v1.PackTraceV1Candidate] = []

    used_tokens = 0
    for rid in ordered_ids:
        row = obs_map.get(rid)
        detail_obj = detail_map.get(rid, {})
        importance_label = _pack_importance_label(detail_obj)
        trust_tier = _pack_trust_tier(detail_obj)

        record_ref = f"obs:{rid}"
        text = _pack_item_text(row or {})
        token_estimate = _estimate_tokens(text) if text else 0

        include = False
        reasons: List[str] = []

        if row is None:
            reasons.append("missing_row")
        elif not text:
            reasons.append("missing_summary")
        elif len(selected_items) >= limit:
            reasons.append("max_items_reached")
        elif used_tokens + token_estimate > budget_tokens:
            reasons.append("budget_tokens_exceeded")
        else:
            include = True
            used_tokens += token_estimate
            reasons.extend(["within_item_limit", "within_budget"])
            if rid in state["fts_ids"]:
                reasons.append("matched_fts")
            if rid in state["vec_ids"] or rid in state["vec_en_ids"]:
                reasons.append("matched_vector")

            selected_items.append(
                {
                    "recordRef": record_ref,
                    "layer": "L1",
                    "id": rid,
                    "summary": text,
                    "kind": row.get("kind"),
                    "lang": row.get("lang"),
                }
            )
            citations.append({"recordRef": record_ref, "url": None})

        candidate_trace.append(
            pack_trace_v1.PackTraceV1Candidate(
                id=record_ref,
                layer="L1",
                importance=importance_label,
                trust=trust_tier,
                scores=pack_trace_v1.PackTraceV1CandidateScores(
                    rrf=float(state["rrf_scores"].get(rid, 0.0)),
                    fts=float(1.0 if rid in state["fts_ids"] else 0.0),
                    semantic=float(1.0 if (rid in state["vec_ids"] or rid in state["vec_en_ids"]) else 0.0),
                ),
                decision=pack_trace_v1.PackTraceV1Decision(
                    included=include,
                    reason=list(reasons),
                    rationale=list(reasons),
                    caps=pack_trace_v1.PackTraceV1DecisionCaps(
                        niceCapHit=False,
                        l2CapHit=False,
                    ),
                ),
                citations=pack_trace_v1.PackTraceV1CandidateCitations(
                    url=None,
                    recordRef=record_ref,
                ),
            )
        )

    bundle_lines = [f"- [{item['recordRef']}] {item['summary']}" for item in selected_items]
    bundle_text = "\n".join(bundle_lines)

    payload: Dict[str, Any] = {
        "bundle_text": bundle_text,
        "items": selected_items,
        "citations": citations,
    }

    # Optional graph output (kept separate for safety; consumer may choose to inject).
    if (graph_state or {}).get("use_graph") != "off":
        payload["graph"] = {
            "use_graph": graph_state.get("use_graph"),
            "triggered": bool(graph_state.get("triggered")),
            "trigger_reason": graph_state.get("trigger_reason"),
            "fail_open": bool(graph_state.get("fail_open")),
            "error_first_line": graph_state.get("error_first_line"),
            "stage0": graph_state.get("stage0"),
            "stage1": graph_state.get("stage1"),
            "probe": graph_state.get("probe"),
            "probe_decision": graph_state.get("probe_decision"),
            "selection_count": int(graph_state.get("selection_count") or 0),
            "budget_tokens": int(graph_state.get("budget_tokens") or 0),
            "take": int(graph_state.get("take") or 0),
            "scope": graph_state.get("scope"),
            "preflight": graph_state.get("payload"),
        }

        graph_bundle = ((graph_state.get("payload") or {}).get("bundle_text") or "").strip()
        if graph_bundle:
            combined = (graph_bundle + "\n" + bundle_text).strip() + "\n"
            max_chars = max(0, int(budget_tokens + int(graph_state.get("budget_tokens") or 0)) * 4 - 3)
            if max_chars and len(combined) > max_chars:
                combined = combined[:max_chars].rstrip() + "\n"
            payload["bundle_text_with_graph"] = combined

    if bool(args.trace):
        duration_ms = int((time.perf_counter() - started) * 1000)
        included_refs = [item["recordRef"] for item in selected_items]
        included_candidates = [c for c in candidate_trace if bool(getattr(c.decision, "included", False))]
        rationale_missing_count = sum(1 for c in included_candidates if not list(getattr(c.decision, "reason", []) or []))
        citation_missing_count = sum(1 for c in included_candidates if not str(getattr(c.citations, "recordRef", "") or "").strip())
        all_included_have_rationale = rationale_missing_count == 0
        all_included_have_citations = citation_missing_count == 0
        trace = pack_trace_v1.PackTraceV1(
            kind=pack_trace_v1.PACK_TRACE_V1_KIND,
            ts=_utcnow_iso(),
            version=pack_trace_v1.PackTraceV1Version(openclaw_mem=__version__),
            query=pack_trace_v1.PackTraceV1Query(
                text=query,
                scope=None,
                intent=None,
            ),
            budgets=pack_trace_v1.PackTraceV1Budgets(
                budgetTokens=budget_tokens,
                maxItems=limit,
                maxL2Items=max_l2_items,
                niceCap=nice_cap,
            ),
            lanes=[
                pack_trace_v1.PackTraceV1Lane(
                    name="hot",
                    source="session/recent",
                    searched=False,
                    retrievers=[],
                ),
                pack_trace_v1.PackTraceV1Lane(
                    name="warm",
                    source="sqlite-observations",
                    searched=True,
                    retrievers=[
                        pack_trace_v1.PackTraceV1Retriever(kind="fts5", topK=int(state["candidate_limit"])),
                        pack_trace_v1.PackTraceV1Retriever(kind="vector", topK=int(state["candidate_limit"])),
                        pack_trace_v1.PackTraceV1Retriever(kind="rrf", k=60),
                    ],
                ),
                pack_trace_v1.PackTraceV1Lane(
                    name="cold",
                    source="curated/durable",
                    searched=False,
                    retrievers=[],
                ),
            ],
            candidates=candidate_trace,
            output=pack_trace_v1.PackTraceV1Output(
                includedCount=len(selected_items),
                excludedCount=max(0, len(candidate_trace) - len(selected_items)),
                l2IncludedCount=0,
                citationsCount=len(citations),
                refreshedRecordRefs=included_refs,
                coverage=pack_trace_v1.PackTraceV1Coverage(
                    rationaleMissingCount=rationale_missing_count,
                    citationMissingCount=citation_missing_count,
                    allIncludedHaveRationale=all_included_have_rationale,
                    allIncludedHaveCitations=all_included_have_citations,
                ),
            ),
            timing=pack_trace_v1.PackTraceV1Timing(durationMs=duration_ms),
            extensions={"graph": _pack_graph_trace_extension(graph_state)} if (graph_state or {}).get("use_graph") != "off" else {},
        )
        payload["trace"] = pack_trace_v1.to_dict(trace)

    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print((payload.get("bundle_text_with_graph") or bundle_text))



def _atomic_write(path_: Path, content: str) -> None:
    path_.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".txt",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path_)


def _format_index_line(row: sqlite3.Row) -> str:
    rid = int(row["id"])
    ts = (row["ts"] or "").strip()
    tool = (row["tool_name"] or "").strip()
    kind = (row["kind"] or "").strip()
    summary = (row["summary"] or "").replace("\n", " ").strip()
    return f"- obs#{rid} {ts} [{kind}] {tool} :: {summary}\n"


def _build_index(conn: sqlite3.Connection, out_path: Path, limit: int) -> int:
    rows = conn.execute(
        "SELECT id, ts, kind, tool_name, summary FROM observations ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    rows = list(reversed(rows))

    header = (
        "# openclaw-mem observations index\n\n"
        "This file is auto-generated. It is safe to embed and search via OpenClaw memorySearch.\n\n"
    )
    body = "".join(_format_index_line(r) for r in rows)
    _atomic_write(out_path, header + body)
    return len(rows)


def cmd_index(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Build a Markdown index file that OpenClaw memorySearch can embed (Route A)."""
    out_path = Path(args.to or DEFAULT_INDEX_PATH)
    limit = int(args.limit)

    n = _build_index(conn, out_path, limit)
    _emit({"ok": True, "to": str(out_path), "rows": n}, args.json)


def _extract_obs_ids(text: str) -> List[int]:
    import re

    ids = set()
    for m in re.finditer(r"\bobs#(\d+)\b", text or ""):
        try:
            ids.add(int(m.group(1)))
        except Exception:
            continue
    return sorted(ids)


def _tokenize_query(q: str) -> List[str]:
    import re

    q = (q or "").lower().strip()
    if not q:
        return []
    parts = re.split(r"[^a-z0-9_#]+", q)
    toks = [p for p in parts if len(p) >= 3 or p.startswith("obs#")]
    return toks[:20]


def _rank_obs_ids_from_snippet(snippet: str, query: str, base_score: float = 0.0) -> List[tuple[int, float]]:
    """Heuristically map a memory_search snippet back to obs IDs.

    memory_search returns chunk-level matches; a snippet may contain multiple obs lines.
    We score each obs line by simple token overlap with the query.
    """
    import re

    toks = _tokenize_query(query)
    if not snippet:
        return []

    ranked: List[tuple[int, float]] = []
    for line in str(snippet).splitlines():
        m = re.search(r"\bobs#(\d+)\b", line)
        if not m:
            continue
        try:
            oid = int(m.group(1))
        except Exception:
            continue

        line_l = line.lower()
        overlap = sum(1 for t in toks if t in line_l)
        # Strongly prefer exact obs# queries
        exact = 5 if f"obs#{oid}" in (query or "").lower() else 0
        score = overlap + exact + (base_score * 2.0)
        ranked.append((oid, float(score)))

    # Highest score first
    ranked.sort(key=lambda x: (-x[1], x[0]))
    return ranked


def cmd_semantic(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Semantic recall via OpenClaw memory_search (black-box embeddings).

    Steps:
      1) Call Gateway /tools/invoke for memory_search
      2) Parse obs#IDs from snippets
      3) Resolve IDs back into openclaw-mem SQLite observations
    """
    query = args.query.strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    # Call OpenClaw's built-in memory_search tool
    tool_args = {
        "query": query,
        "maxResults": int(args.max_results),
        "minScore": float(args.min_score),
    }
    try:
        result = _gateway_tools_invoke(args, tool="memory_search", tool_args=tool_args, session_key=args.session_key)
    except Exception as e:
        _emit({"error": str(e)}, args.json)
        sys.exit(1)

    # Parse results
    results: Any = None
    if isinstance(result, dict):
        # /tools/invoke wraps tool details
        details = result.get("details")
        if isinstance(details, dict) and isinstance(details.get("results"), list):
            results = details.get("results")
        elif isinstance(result.get("results"), list):
            results = result.get("results")
    elif isinstance(result, list):
        results = result

    if not isinstance(results, list):
        _emit({"error": f"unexpected memory_search result shape: {type(result).__name__}"}, args.json)
        sys.exit(1)

    scores: Dict[int, float] = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        snippet = str(r.get("snippet") or "")
        base = float(r.get("score") or 0.0)
        for oid, sc in _rank_obs_ids_from_snippet(snippet, query, base_score=base):
            scores[oid] = max(scores.get(oid, 0.0), sc)

    if not scores:
        _emit({"ok": True, "query": query, "matches": [], "raw": results[: int(args.raw_limit)]}, args.json)
        return

    ids_ranked = [oid for oid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]

    # Resolve observations
    q = f"SELECT id, ts, kind, tool_name, summary FROM observations WHERE id IN ({','.join(['?']*len(ids_ranked))})"
    rows = conn.execute(q, ids_ranked).fetchall()
    obs_map = {int(r["id"]): dict(r) for r in rows}

    out = []
    for oid in ids_ranked[: int(args.limit)]:
        r = obs_map.get(oid)
        if not r:
            continue
        out.append(r)

    _emit(
        {
            "ok": True,
            "query": query,
            "ids": ids_ranked[: int(args.limit)],
            "matches": out,
            "raw": results[: int(args.raw_limit)],
        },
        args.json,
    )


def _triage_observations(conn: sqlite3.Connection, since_ts: str, keywords: List[str], limit: int) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = [since_ts]
    for k in keywords:
        like = f"%{k}%"
        clauses.append("(lower(coalesce(summary,'')) LIKE ? OR lower(coalesce(tool_name,'')) LIKE ? OR lower(coalesce(detail_json,'')) LIKE ?)")
        params.extend([like, like, like])

    where_kw = " OR ".join(clauses) if clauses else "1=0"
    q = f"""
        SELECT id, ts, kind, tool_name, summary
        FROM observations
        WHERE ts >= ? AND ({where_kw})
        ORDER BY ts DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]




def _triage_cron_errors(*, since_ms: int, cron_jobs_path: str, limit: int) -> List[Dict[str, Any]]:
    """Detect cron jobs whose lastStatus != ok.

    Reads OpenClaw cron store (jobs.json). Deterministic and no LLM calls.

    Notes:
    - Coerces numeric timestamps/durations that may be stored as strings.
    - Emits a bounded `lastErrorLine` when available (best-effort).
    """

    p = Path(os.path.expanduser(cron_jobs_path))
    if not p.exists():
        return []

    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception:
        return []

    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []

    def _as_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            try:
                return int(value)
            except Exception:
                return None
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                try:
                    return int(s)
                except Exception:
                    return None
            try:
                f = float(s)
            except Exception:
                return None
            if f != f or f in (float("inf"), float("-inf")):
                return None
            try:
                return int(f)
            except Exception:
                return None
        return None

    def _first_line(value: Any, *, max_chars: int = 400) -> str | None:
        if not isinstance(value, str):
            return None
        s = value.strip("\n")
        if not s:
            return None
        line = s.splitlines()[0].strip()
        if not line:
            return None
        if len(line) > max_chars:
            return line[: max_chars - 1] + "…"
        return line

    bad: List[Dict[str, Any]] = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        state = j.get("state") if isinstance(j.get("state"), dict) else {}

        last_status_raw = state.get("lastStatus")
        last_status = (str(last_status_raw).strip() if last_status_raw is not None else None)

        last_run = _as_int(state.get("lastRunAtMs"))
        if last_status is None or last_status.lower() == "ok":
            continue
        if last_run is not None and int(last_run) < int(since_ms):
            continue

        bad.append(
            {
                "id": j.get("id"),
                "name": j.get("name"),
                "enabled": j.get("enabled"),
                "lastStatus": last_status,
                "lastRunAtMs": last_run,
                "lastDurationMs": _as_int(state.get("lastDurationMs")),
                "nextRunAtMs": _as_int(state.get("nextRunAtMs")),
                "lastErrorLine": _first_line(
                    state.get("lastError")
                    or state.get("lastErrorLine")
                    or state.get("lastErrorMessage")
                    or state.get("error")
                ),
            }
        )

    bad.sort(key=lambda x: (-(int(x.get("lastRunAtMs") or 0)), str(x.get("name") or "")))
    return bad[:limit]



def _summary_has_task_marker(summary: str) -> bool:
    """Return True when summary begins with a task marker."""

    return _summary_has_task_marker_impl(summary)


def _triage_tasks(conn: sqlite3.Connection, *, since_ts: str, importance_min: float, limit: int) -> List[Dict[str, Any]]:
    """Scan proactively stored items (tool_name=memory_store) for tasks.

    Deterministic: all logic is local.

    Matching rules:
    - kind == 'task' OR
    - summary starts with TODO/TASK/REMINDER marker
      (case-insensitive; width-normalized via NFKC; supports plain or
      bracketed forms like `[TODO]`/`(TASK)`/`【TODO】`/`〔TODO〕`/`「TODO」`/`『TODO』`/`〖TODO〗`/`〘TODO〙`/`<TODO>`/`＜TODO＞` (including compact no-space forms like `[TODO]buy milk`/`【TODO】buy milk`/`〔TODO〕buy milk`/`「TODO」buy milk`/`『TODO』buy milk`/`〖TODO〗buy milk`/`〘TODO〙buy milk`/`<TODO>buy milk`/`＜TODO＞buy milk`), plus optional leading
      markdown wrappers like `>` blockquotes, list/checklist prefixes
      (`-`/`*`/`+`/`•`/`▪`/`‣`/`∙`/`·`/`●`/`○`/`◦`/`・`/`–`/`—`/`−`, `[ ]`/`[x]`/`[✓]`/`[✔]`/`[☐]`/`[☑]`/`[☒]`), and ordered-list prefixes like
      `1.`/`1)`/`1-`/`（1）`/`(1)`/`a.`/`a)`/`(a)`/`iv.`/`iv)`/`(iv)`; whitespace is optional
      between wrappers and the next wrapper/marker;
      accepts ':', whitespace, ';', '；', '-', '－', '–', '—', '−', or marker-only)

    Importance is best-effort parsed from detail_json.importance.
    """
    rows = conn.execute(
        """
        SELECT id, ts, kind, tool_name, summary, detail_json
        FROM observations
        WHERE ts >= ? AND tool_name = 'memory_store'
        ORDER BY id DESC
        LIMIT ?
        """,
        (since_ts, max(50, limit * 20)),
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        kind = (r["kind"] or "").strip().lower()
        summary = (r["summary"] or "").strip()
        if not summary:
            continue

        is_task = kind == "task" or _summary_has_task_marker(summary)
        if not is_task:
            continue

        imp = 0.0
        try:
            dj = json.loads(r["detail_json"] or "{}")
            from openclaw_mem.importance import parse_importance_score

            imp = parse_importance_score(dj.get("importance"))
        except Exception:
            imp = 0.0

        if imp < float(importance_min):
            continue

        out.append({"id": int(r["id"]), "ts": r["ts"], "kind": r["kind"], "tool_name": r["tool_name"], "summary": summary, "importance": imp})
        if len(out) >= limit:
            break

    return out


def _load_triage_state(path_: Path) -> Dict[str, Any]:
    try:
        if not path_.exists():
            return {}
        return json.loads(path_.read_text("utf-8"))
    except Exception:
        return {}


def _atomic_write_json(path_: Path, data: Dict[str, Any]) -> None:
    path_.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path_.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path_.suffix or ".json",
    ) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path_)


def cmd_triage(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Deterministic local triage.

    Modes:
    - heartbeat (default): observations + cron-errors + tasks (new-only)
    - observations: observations only
    - cron-errors: cron store only
    - tasks: tasks only (new-only)

    Exit codes:
      0 = no new issues
      10 = needs attention (new matches found)
      2 = invalid args / error
    """
    try:
        since_minutes = int(getattr(args, "since_minutes", 60))
        limit = int(getattr(args, "limit", 10))
    except Exception:
        _emit({"error": "invalid since/limit"}, True)
        sys.exit(2)

    mode = str(getattr(args, "mode", "heartbeat") or "heartbeat").strip().lower()
    if mode not in {"heartbeat", "observations", "cron-errors", "tasks"}:
        _emit({"error": f"invalid mode: {mode}"}, True)
        sys.exit(2)

    since_minutes = max(0, since_minutes)
    limit = max(1, min(200, limit))

    dedupe = bool(getattr(args, "dedupe", True))

    kw_raw = getattr(args, "keywords", None)
    if kw_raw:
        keywords = [k.strip().lower() for k in str(kw_raw).split(",") if k.strip()]
    else:
        keywords = [
            "error",
            "failed",
            "exception",
            "traceback",
            "timeout",
            "rate_limit",
            "unauthorized",
            "forbidden",
            "not allowed",
            "db locked",
        ]

    cron_jobs_path = getattr(args, "cron_jobs_path", None) or "~/.openclaw/cron/jobs.json"

    # Tasks scan is typically longer-lived than a 30m error window.
    tasks_since_minutes = int(getattr(args, "tasks_since_minutes", 24 * 60))
    importance_min = float(getattr(args, "importance_min", 0.7))

    state_path = Path(os.path.expanduser(getattr(args, "state_path", None) or "~/.openclaw/memory/openclaw-mem/triage-state.json"))
    state = _load_triage_state(state_path) if dedupe else {}

    last_obs_id = int(((state.get("observations") or {}).get("last_alerted_id") or 0))
    last_task_id = int(((state.get("tasks") or {}).get("last_alerted_id") or 0))
    last_cron_ms = int(((state.get("cron") or {}).get("last_alerted_bad_run_at_ms") or 0))

    from datetime import timezone

    since_dt = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    since_utc = since_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    since_ms = int(since_dt.timestamp() * 1000)

    tasks_since_dt = datetime.now(timezone.utc) - timedelta(minutes=max(0, tasks_since_minutes))
    tasks_since_utc = tasks_since_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    obs_all: List[Dict[str, Any]] = []
    cron_all: List[Dict[str, Any]] = []
    tasks_all: List[Dict[str, Any]] = []

    if mode in {"heartbeat", "observations"}:
        obs_all = _triage_observations(conn, since_utc, keywords, limit)

    if mode in {"heartbeat", "cron-errors"}:
        cron_all = _triage_cron_errors(since_ms=since_ms, cron_jobs_path=str(cron_jobs_path), limit=limit)

    if mode in {"heartbeat", "tasks"}:
        tasks_all = _triage_tasks(conn, since_ts=tasks_since_utc, importance_min=importance_min, limit=limit)

    if dedupe:
        # Dedupe: only alert on *new* items
        obs_new = [m for m in obs_all if int(m.get("id") or 0) > last_obs_id]
        tasks_new = [m for m in tasks_all if int(m.get("id") or 0) > last_task_id]
        cron_new = [m for m in cron_all if int(m.get("lastRunAtMs") or 0) > last_cron_ms]
    else:
        obs_new = list(obs_all)
        tasks_new = list(tasks_all)
        cron_new = list(cron_all)

    needs_attention = (len(obs_new) > 0) or (len(cron_new) > 0) or (len(tasks_new) > 0)

    out = {
        "kind": "openclaw-mem.triage.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "mode": mode,
        "dedupe": dedupe,
        "since_minutes": since_minutes,
        "since_utc": since_utc,
        "keywords": keywords,
        "cron_jobs_path": os.path.expanduser(str(cron_jobs_path)),
        "tasks_since_minutes": tasks_since_minutes,
        "tasks_since_utc": tasks_since_utc,
        "importance_min": importance_min,
        "state_path": str(state_path),
        "needs_attention": needs_attention,
        "observations": {
            "found_total": len(obs_all),
            "found_new": len(obs_new),
            "matches": obs_new,
        },
        "cron": {
            "found_total": len(cron_all),
            "found_new": len(cron_new),
            "matches": cron_new,
        },
        "tasks": {
            "found_total": len(tasks_all),
            "found_new": len(tasks_new),
            "matches": tasks_new,
        },
    }

    if needs_attention and dedupe:
        # Update state maxima
        if obs_new:
            last_obs_id = max(last_obs_id, max(int(m.get("id") or 0) for m in obs_new))
        if tasks_new:
            last_task_id = max(last_task_id, max(int(m.get("id") or 0) for m in tasks_new))
        if cron_new:
            last_cron_ms = max(last_cron_ms, max(int(m.get("lastRunAtMs") or 0) for m in cron_new))

        new_state = dict(state) if isinstance(state, dict) else {}
        new_state["observations"] = {"last_alerted_id": last_obs_id}
        new_state["tasks"] = {"last_alerted_id": last_task_id}
        new_state["cron"] = {"last_alerted_bad_run_at_ms": last_cron_ms}
        _atomic_write_json(state_path, new_state)

    _emit(out, True)

    if needs_attention:
        sys.exit(10)
    sys.exit(0)


def cmd_harvest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Auto-ingest and embed observations from log file.

    Hardening goals:
    - Recover orphaned `*.processing` files after crashes.
    - Emit exactly ONE JSON payload when `--json` is used.
    - Keep fail-open semantics: missing API key should not block ingest/archival.
    """

    _apply_importance_scorer_override(args)

    default_source = os.path.expanduser("~/.openclaw/memory/openclaw-mem-observations.jsonl")
    source = Path(args.source or default_source)
    summary = IngestRunSummary()

    # 1) Collect any orphaned processing files first (crash recovery).
    processing_files = sorted(source.parent.glob(f"{source.name}.*.processing"))
    recovered = bool(processing_files)

    # 2) Rotate current source (if present) into a new processing file.
    rotated = False
    if source.exists() and source.stat().st_size > 0:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        processing = source.with_suffix(f".jsonl.{ts}.processing")
        try:
            source.rename(processing)
            processing_files.append(processing)
            processing_files.sort()
            rotated = True
        except OSError as e:
            _emit({"error": f"Failed to rotate log: {e}"}, args.json)
            sys.exit(1)

    if not processing_files:
        _emit(
            {
                "kind": "openclaw-mem.harvest.v0",
                "ts": _utcnow_iso(),
                "version": {"openclaw_mem": __version__, "schema": "v0"},
                "ok": True,
                "processed_files": 0,
                "ingested": 0,
                "reason": "source empty/missing",
                "total_seen": summary.total_seen,
                "graded_filled": summary.graded_filled,
                "skipped_existing": summary.skipped_existing,
                "skipped_disabled": summary.skipped_disabled,
                "scorer_errors": summary.scorer_errors,
                "label_counts": summary.normalized_label_counts(),
            },
            args.json,
        )
        return

    # 3) Ingest all processing files (oldest first).
    inserted_ids: List[int] = []
    for processing in processing_files:
        try:
            with open(processing, "r", encoding="utf-8") as fp:
                for obs in _iter_jsonl(fp):
                    inserted_ids.append(_insert_observation(conn, obs, summary))
            conn.commit()
        except Exception as e:
            _emit({"error": f"Ingest failed: {e}", "file": str(processing)}, args.json)
            sys.exit(1)

    # 4) Update index (Route A) (best-effort).
    if getattr(args, "update_index", True):
        try:
            out_path = Path(getattr(args, "index_to", None) or DEFAULT_INDEX_PATH)
            _build_index(conn, out_path, int(getattr(args, "index_limit", 5000)))
        except Exception as e:
            print(f"Warning: failed to update index: {e}", file=sys.stderr)

    # 5) Embed (Optional, best-effort, quiet).
    embedded = 0
    embed_error: Optional[str] = None
    if args.embed:
        api_key = _get_api_key()
        if not api_key:
            embed_error = "missing_api_key"
        else:
            try:
                client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
                model = args.model
                limit = max(1, int(getattr(args, "embed_limit", 1000)))
                batch = 64
                now = _utcnow_iso()

                target = _embed_targets("original")[0]
                _warn_embedding_model_mismatch(
                    conn,
                    table=target["table"],
                    requested_model=model,
                    label=target["name"],
                )

                rows = conn.execute(
                    f"""
                    SELECT id, tool_name, {target['text_col']} AS text_value
                    FROM observations
                    WHERE id NOT IN (
                        SELECT observation_id FROM {target['table']} WHERE model = ?
                    )
                    AND trim(coalesce({target['text_col']}, '')) <> ''
                    ORDER BY id
                    LIMIT ?
                    """,
                    (model, limit),
                ).fetchall()

                todo = [dict(r) for r in rows]
                for i in range(0, len(todo), batch):
                    chunk = todo[i : i + batch]
                    texts = []
                    chunk_ids = []
                    for r in chunk:
                        tid = int(r["id"])
                        tool = (r.get("tool_name") or "").strip()
                        summary_text = (r.get("text_value") or "").strip()
                        text = f"{tool}: {summary_text}".strip(": ")
                        texts.append(text)
                        chunk_ids.append(tid)

                    vecs = client.embed(texts, model=model)
                    for tid, vec in zip(chunk_ids, vecs):
                        blob = pack_f32(vec)
                        norm = l2_norm(vec)
                        dim = len(vec)
                        conn.execute(
                            f"""
                            INSERT OR REPLACE INTO {target['table']}
                            (observation_id, model, dim, vector, norm, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (tid, model, dim, blob, norm, now),
                        )
                        embedded += 1

                    conn.commit()
            except Exception as e:
                embed_error = str(e)

    # 6) Archive or delete processed files.
    try:
        if args.archive_dir:
            archive_dir = Path(args.archive_dir)
            archive_dir.mkdir(parents=True, exist_ok=True)
            for processing in processing_files:
                dest = archive_dir / processing.name
                processing.rename(dest)
        else:
            for processing in processing_files:
                processing.unlink()
    except Exception as e:
        _emit({"error": f"Failed to archive/delete processing files: {e}"}, args.json)
        sys.exit(1)

    # Emit ONE harvest result payload.
    out: Dict[str, Any] = {
        "kind": "openclaw-mem.harvest.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "ingested": len(inserted_ids),
        "processed_files": len(processing_files),
        "files": [p.name for p in processing_files[:20]],
        "recovered": recovered,
        "rotated": rotated,
        "source": str(source),
        "archive": str(args.archive_dir) if args.archive_dir else "deleted",
        "total_seen": summary.total_seen,
        "graded_filled": summary.graded_filled,
        "skipped_existing": summary.skipped_existing,
        "skipped_disabled": summary.skipped_disabled,
        "scorer_errors": summary.scorer_errors,
        "label_counts": summary.normalized_label_counts(),
        "embedded": embedded,
    }
    if embed_error:
        out["embed_error"] = embed_error

    _emit(out, args.json)


# Regex patterns for writeback extraction.
_LANCEDB_ID_RE = re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")
_LANCEDB_FORCE_FIELDS = (
    "importance",
    "importance_label",
    "scope",
    "trust_tier",
    "category",
)
_LANCEDB_FORCE_FIELDS_SET = set(_LANCEDB_FORCE_FIELDS)
_LANCEDB_FORCE_FIELDS_DEFAULT = (
    "importance",
    "importance_label",
    "scope",
    "category",
)

_LANCEDB_WRITEBACK_NODE_SCRIPT = r"""import { readFile } from 'node:fs/promises';
import { connect } from '@lancedb/lancedb';

const ALLOWED_IMPORTANCE_LABELS = new Set(['must_remember', 'nice_to_have', 'ignore', 'unknown']);
const ALLOWED_TRUST_TIERS = new Set(['trusted', 'untrusted', 'quarantined']);
const ALLOWED_FORCE_FIELDS = new Set(['importance', 'importance_label', 'scope', 'category', 'trust_tier']);

function normalizeForceFieldList(rawValue) {
  if (typeof rawValue === 'string') {
    return rawValue
      .split(',')
      .map((value) => String(value ?? '').trim().toLowerCase())
      .filter((value) => ALLOWED_FORCE_FIELDS.has(value));
  }

  if (!Array.isArray(rawValue)) {
    return [];
  }

  return rawValue
    .map((value) => String(value ?? '').trim().toLowerCase())
    .filter((value) => ALLOWED_FORCE_FIELDS.has(value));
}

function normalizeFieldSet(values) {
  const unique = [];
  const seen = new Set();
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    unique.push(value);
  }
  return new Set(unique);
}

function hasMeaningfulValue(value) {
  if (value === null || value === undefined) {
    return false;
  }

  if (typeof value === 'number') {
    return Number.isFinite(value);
  }

  if (typeof value === 'string') {
    return value.trim().length > 0;
  }

  return true;
}

function hasColumn(columns, name) {
  return columns.has(name);
}

function clamp01(value) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized)) return undefined;
  if (normalized < 0) return 0;
  if (normalized > 1) return 1;
  return normalized;
}

function safeIdentifier(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  return raw.replace(/'/g, "''");
}

function allowedLabel(value) {
  const normalized = String(value ?? '').trim();
  return ALLOWED_IMPORTANCE_LABELS.has(normalized) ? normalized : null;
}

function allowedTrust(value) {
  const normalized = String(value ?? '').trim();
  return ALLOWED_TRUST_TIERS.has(normalized) ? normalized : null;
}

const payloadPath = process.argv[2];
if (!payloadPath) {
  console.error('missing payload path');
  process.exit(1);
}

(async () => {
  const rawPayload = await readFile(payloadPath, 'utf8');
  const payload = JSON.parse(rawPayload);

  const dbPath = String(payload.dbPath || '').trim();
  const tableName = String(payload.tableName || '').trim();
  const dryRun = Boolean(payload.dryRun);
  const forceOverwrite = Boolean(payload.forceOverwrite);
  const requestedForceFields = normalizeForceFieldList(payload.forceFields);
  const overwriteFields = forceOverwrite ? normalizeFieldSet(requestedForceFields) : new Set();
  const updates = Array.isArray(payload.updates) ? payload.updates : [];

  const summary = {
    checked: 0,
    updated: 0,
    overwritten: 0,
    overwrittenFields: 0,
    skipped: 0,
    missingIds: [],
    errors: 0,
    errorIds: [],
  };

  function canOverwriteField(name) {
    return forceOverwrite && overwriteFields.has(name);
  }

  if (!dbPath) {
    throw new Error('missing dbPath');
  }

  const db = await connect(dbPath);
  const table = await db.openTable(tableName);
  const schema = await table.schema();
  const columns = new Set((schema?.fields || []).map((field) => String(field?.name || '').trim()));

  for (const item of updates) {
    const candidateId = String(item?.id || '').trim();
    const incoming = item?.updates || {};

    if (!candidateId) {
      summary.skipped += 1;
      continue;
    }

    const where = `id = '${safeIdentifier(candidateId)}'`;
    const rows = await table.query().where(where).limit(1).toArray();
    if (!rows || rows.length === 0) {
      summary.missingIds.push(candidateId);
      continue;
    }

    const row = rows[0] || {};
    const current = {
      importance: row.importance,
      importance_label: row.importance_label,
      scope: row.scope,
      trust_tier: row.trust_tier,
      category: row.category,
    };

    const patch = {};
    let overwrittenFields = 0;
    let rowOverwritten = false;

    const incomingImportance = clamp01(incoming.importance);
    const hasCurrentImportance = hasMeaningfulValue(current.importance);
    if (incomingImportance !== undefined && hasColumn(columns, 'importance') && (!hasCurrentImportance || canOverwriteField('importance'))) {
      const currentImportance = clamp01(current.importance);
      if (currentImportance !== incomingImportance) {
        patch.importance = incomingImportance;
        if (canOverwriteField('importance') && hasMeaningfulValue(current.importance)) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!hasCurrentImportance) {
        patch.importance = incomingImportance;
      }
    }

    const incomingLabel = allowedLabel(incoming.importance_label);
    const currentLabel = String(current.importance_label || '').trim();
    if (incomingLabel && hasColumn(columns, 'importance_label') && (!hasMeaningfulValue(currentLabel) || canOverwriteField('importance_label'))) {
      if (currentLabel !== incomingLabel) {
        patch.importance_label = incomingLabel;
        if (canOverwriteField('importance_label') && currentLabel) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentLabel) {
        patch.importance_label = incomingLabel;
      }
    }

    const incomingScope = String(incoming.scope || '').trim();
    if (incomingScope && hasColumn(columns, 'scope') && (!hasMeaningfulValue(current.scope) || canOverwriteField('scope'))) {
      const currentScope = String(current.scope || '').trim();
      if (currentScope !== incomingScope) {
        patch.scope = incomingScope;
        if (canOverwriteField('scope') && currentScope) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentScope) {
        patch.scope = incomingScope;
      }
    }

    const incomingTrust = allowedTrust(incoming.trust_tier);
    const currentTrust = String(current.trust_tier || '').trim();
    if (incomingTrust && hasColumn(columns, 'trust_tier') && (!hasMeaningfulValue(currentTrust) || canOverwriteField('trust_tier'))) {
      if (currentTrust !== incomingTrust) {
        patch.trust_tier = incomingTrust;
        if (canOverwriteField('trust_tier') && currentTrust) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentTrust) {
        patch.trust_tier = incomingTrust;
      }
    }

    const incomingCategory = String(incoming.category || '').trim();
    if (incomingCategory && hasColumn(columns, 'category') && (!hasMeaningfulValue(current.category) || canOverwriteField('category'))) {
      const currentCategory = String(current.category || '').trim();
      if (currentCategory !== incomingCategory) {
        patch.category = incomingCategory;
        if (canOverwriteField('category') && currentCategory) {
          rowOverwritten = true;
          overwrittenFields += 1;
        }
      } else if (!currentCategory) {
        patch.category = incomingCategory;
      }
    }

    summary.checked += 1;
    if (Object.keys(patch).length === 0) {
      summary.skipped += 1;
      continue;
    }

    if (!dryRun) {
      try {
        await table.update({ where, values: patch });
      } catch (err) {
        summary.errors += 1;
        summary.errorIds.push(candidateId);
        continue;
      }
    }

    summary.updated += 1;
    if (rowOverwritten) {
      summary.overwritten += 1;
      summary.overwrittenFields += overwrittenFields;
    }
  }

  console.log(JSON.stringify({ success: true, summary }));
  await db.close?.();
})().catch((error) => {
  console.error(String(error?.stack || error));
  process.exit(1);
});
"""

def _coerce_lancedb_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None

    m = _LANCEDB_ID_RE.search(value)
    if not m:
        return None

    return m.group(0).strip()


def _extract_lancedb_id_from_obj(value: Any, *, hint_keys: Optional[Tuple[str, ...]] = None) -> Optional[str]:
    keys = set(k.lower() for k in (hint_keys or ("memory_id", "memoryid", "memory_uuid", "memoryuuid", "lancedb_id", "lancedbid", "lancedb", "lance_id")))

    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                continue

            if key.lower() in keys:
                candidate = _coerce_lancedb_id(nested)
                if candidate:
                    return candidate

            if isinstance(nested, (dict, list)):
                candidate = _extract_lancedb_id_from_obj(nested, hint_keys=hint_keys)
                if candidate:
                    return candidate

        return None

    if isinstance(value, list):
        for item in value:
            candidate = _extract_lancedb_id_from_obj(item, hint_keys=hint_keys)
            if candidate:
                return candidate

    return _coerce_lancedb_id(value)


def _extract_lancedb_id(row: sqlite3.Row, detail_obj: Dict[str, Any]) -> Optional[str]:
    for src in (
        detail_obj,
        detail_obj.get("result"),
        detail_obj.get("response"),
        detail_obj.get("output"),
        detail_obj.get("payload"),
        detail_obj.get("memory"),
        detail_obj.get("data"),
    ):
        if not isinstance(src, dict):
            continue

        direct = _extract_lancedb_id_from_obj(src)
        if direct:
            return direct

    summary = str(row["summary"] or "").strip()
    summary_en = str(row["summary_en"] or "").strip()

    for raw in (summary, summary_en):
        if not raw:
            continue

        m = _LANCEDB_ID_RE.search(raw)
        if m:
            return m.group(0).strip()

    return None


def _extract_importance_from_detail(detail_obj: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    from openclaw_mem.importance import label_from_score

    if not isinstance(detail_obj, dict):
        return (None, None)

    raw = detail_obj.get("importance")
    score: Optional[float] = None
    label: Optional[str] = None

    if isinstance(raw, dict):
        label = _normalize_importance_label(raw.get("label"))
        candidate = raw.get("score")
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            score = max(0.0, min(1.0, float(candidate)))
        elif isinstance(candidate, str):
            try:
                candidate_score = float(candidate.strip())
            except ValueError:
                candidate_score = None
            if candidate_score is not None:
                score = max(0.0, min(1.0, float(candidate_score)))

    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        score = max(0.0, min(1.0, float(raw)))
    elif isinstance(raw, str):
        if raw.strip():
            try:
                score = max(0.0, min(1.0, float(raw.strip())))
            except ValueError:
                score = None

    if score is None and label is None:
        return (None, None)

    if label not in {"must_remember", "nice_to_have", "ignore", "unknown"}:
        label = None

    if score is None:
        score_map = {
            "must_remember": 0.9,
            "nice_to_have": 0.7,
            "ignore": 0.2,
            "unknown": 0.0,
        }
        if not label:
            return (None, None)
        score = score_map.get(label, 0.0)
    elif not label:
        label = _normalize_importance_label(label_from_score(score))

    return (score, label)


def _extract_writeback_updates(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    detail_obj = _pack_parse_detail_json(row["detail_json"])

    lancedb_id = _extract_lancedb_id(row, detail_obj)
    if not lancedb_id:
        return None

    updates: Dict[str, Any] = {}

    score, label = _extract_importance_from_detail(detail_obj)
    if score is not None:
        updates["importance"] = score

    if label:
        updates["importance_label"] = label

    scope = _normalize_scope_token(detail_obj.get("scope") or row["kind"])
    if scope:
        updates["scope"] = scope

    trust = _pack_trust_tier(detail_obj)
    if trust != "unknown":
        updates["trust_tier"] = trust

    if isinstance(detail_obj.get("category"), str):
        updates["category"] = (detail_obj.get("category") or "").strip()
    elif isinstance(row["kind"], str):
        updates["category"] = str(row["kind"]).strip()

    return {"id": lancedb_id, "updates": updates}


def cmd_writeback_lancedb(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Write governance metadata from SQLite ledger rows back to LanceDB."""

    dry_run = bool(args.dry_run)
    limit = max(1, int(args.limit))
    batch = max(1, int(getattr(args, "batch", 50)))
    force_overwrite = bool(getattr(args, "force", False))

    force_fields: List[str] = []
    if force_overwrite:
        raw_force_fields = str(getattr(args, "force_fields", "")).strip() if getattr(args, "force_fields", None) is not None else ""
        if raw_force_fields:
            requested = [f.strip().lower() for f in raw_force_fields.split(",") if f.strip()]
            bad_fields = [f for f in requested if f not in _LANCEDB_FORCE_FIELDS_SET]
            if bad_fields:
                _emit(
                    {
                        "error": "invalid --force-fields value(s)",
                        "invalidFields": sorted(set(bad_fields)),
                        "allowedFields": sorted(_LANCEDB_FORCE_FIELDS_SET),
                    },
                    args.json,
                )
                sys.exit(1)

            # Preserve order, de-dupe
            force_fields = list(dict.fromkeys([f for f in requested if f in _LANCEDB_FORCE_FIELDS_SET]))
        else:
            force_fields = list(_LANCEDB_FORCE_FIELDS_DEFAULT)

    lancedb_path = os.path.expanduser(str(getattr(args, "lancedb", "")).strip())
    table = (getattr(args, "table", "") or "").strip()
    if not lancedb_path:
        _emit({"error": "missing --lancedb"}, args.json)
        sys.exit(1)

    if not table:
        _emit({"error": "missing --table"}, args.json)
        sys.exit(1)

    engine_path = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine"
    if not engine_path.exists():
        _emit({"error": f"openclaw-mem-engine path not found: {engine_path}"}, args.json)
        sys.exit(1)

    rows = conn.execute(
        """
        SELECT id, kind, summary, summary_en, detail_json
        FROM observations
        WHERE tool_name = 'memory_store'
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    prepared: List[Dict[str, Any]] = []
    skipped_no_id = 0

    for row in rows:
        payload = _extract_writeback_updates(row)
        if not payload:
            skipped_no_id += 1
            continue

        prepared.append(payload)

    if not prepared:
        _emit(
            {
                "ok": True,
                "dryRun": dry_run,
                "db": lancedb_path,
                "table": table,
                "limit": limit,
                "batch": batch,
                "forceOverwrite": force_overwrite,
                "forceFields": force_fields,
                "checked": skipped_no_id,
                "updated": 0,
                "overwritten": 0,
                "overwrittenFields": 0,
                "skipped": skipped_no_id,
                "missing": 0,
                "missingIds": [],
            },
            args.json,
        )
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False, dir=str(engine_path)) as script_file:
        script_file.write(_LANCEDB_WRITEBACK_NODE_SCRIPT)

    total_updated = 0
    total_overwritten = 0
    total_overwritten_fields = 0
    total_skipped = skipped_no_id
    total_checked = skipped_no_id
    missing_ids: List[str] = []
    total_errors = 0
    error_ids: List[str] = []

    try:
        for i in range(0, len(prepared), batch):
            chunk = prepared[i : i + batch]
            payload = {
                "dbPath": lancedb_path,
                "tableName": table,
                "dryRun": dry_run,
                "forceOverwrite": force_overwrite,
                "forceFields": force_fields,
                "updates": chunk,
            }

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as payload_file:
                json.dump(payload, payload_file, ensure_ascii=False)
                payload_path = payload_file.name

            proc = subprocess.run(
                ["node", script_file.name, payload_path],
                capture_output=True,
                text=True,
                cwd=str(engine_path),
                check=False,
            )
            os.unlink(payload_path)

            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                _emit({"error": "lancedb writeback execution failed", "detail": detail}, args.json)
                sys.exit(1)

            try:
                parsed = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                _emit({"error": "lancedb writeback returned invalid JSON"}, args.json)
                sys.exit(1)

            summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
            if not isinstance(summary, dict):
                _emit({"error": "lancedb writeback returned malformed summary"}, args.json)
                sys.exit(1)

            total_checked += int(summary.get("checked", 0))
            total_updated += int(summary.get("updated", 0))
            total_overwritten += int(summary.get("overwritten", 0))
            total_overwritten_fields += int(summary.get("overwrittenFields", 0))
            total_skipped += int(summary.get("skipped", 0))
            missing_ids.extend(summary.get("missingIds", []))

            chunk_errors = int(summary.get("errors", 0))
            total_errors += chunk_errors
            for error_id in summary.get("errorIds", []):
                if isinstance(error_id, str):
                    error_ids.append(error_id)

    finally:
        os.unlink(script_file.name)

    out = {
        "ok": total_errors == 0,
        "dryRun": dry_run,
        "db": lancedb_path,
        "table": table,
        "limit": limit,
        "batch": batch,
        "forceOverwrite": force_overwrite,
        "forceFields": force_fields,
        "checked": total_checked,
        "updated": total_updated,
        "overwritten": total_overwritten,
        "overwrittenFields": total_overwritten_fields,
        "skipped": total_skipped,
        "missing": len(missing_ids),
        "missingIds": missing_ids,
    }

    if total_errors:
        out["error_count"] = total_errors
        out["errorIds"] = error_ids

    _emit(out, args.json)

    if total_errors:
        sys.exit(1)

def cmd_store(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Proactive memory storage (SQLite + Vector + Markdown)."""
    text = args.text.strip()
    if not text:
        _emit({"error": "empty text"}, args.json)
        sys.exit(1)

    text_en = (getattr(args, "text_en", None) or "").strip() or None
    lang = (getattr(args, "lang", None) or "").strip() or None

    from openclaw_mem.importance import make_importance

    importance_obj = make_importance(
        float(args.importance),
        method="manual-via-cli",
        rationale="Provided via openclaw-mem store --importance.",
        version=1,
    )

    # 1. Insert into SQLite
    obs = {
        "kind": args.category,  # e.g., 'fact', 'preference'
        "summary": text,
        "summary_en": text_en,
        "lang": lang,
        "tool_name": "memory_store",
        "detail": {"importance": importance_obj},
    }
    rowid = _insert_observation(conn, obs)

    # 2. Embed and store vector
    api_key = _get_api_key()
    if api_key:
        try:
            client = OpenAIEmbeddingsClient(api_key=api_key, base_url=args.base_url)
            created_at = _utcnow_iso()

            vec = client.embed([text], model=args.model)[0]
            blob = pack_f32(vec)
            norm = l2_norm(vec)
            conn.execute(
                """
                INSERT OR REPLACE INTO observation_embeddings
                (observation_id, model, dim, vector, norm, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rowid, args.model, len(vec), blob, norm, created_at),
            )

            if text_en:
                vec_en = client.embed([text_en], model=args.model)[0]
                blob_en = pack_f32(vec_en)
                norm_en = l2_norm(vec_en)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO observation_embeddings_en
                    (observation_id, model, dim, vector, norm, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (rowid, args.model, len(vec_en), blob_en, norm_en, created_at),
                )

            conn.commit()
        except Exception as e:
            # Non-fatal: storage succeeded, vector failed
            print(f"Warning: Failed to embed memory: {e}", file=sys.stderr)
    else:
        conn.commit()
        print("Warning: No API key, skipping embedding", file=sys.stderr)

    # 3. Append to memory/YYYY-MM-DD.md
    workspace = Path(args.workspace) if hasattr(args, "workspace") and args.workspace else DEFAULT_WORKSPACE

    # Fallback logic for workspace memory dir
    memory_dir = workspace / "memory"
    if not memory_dir.exists():
         alt = Path(os.path.expanduser("~/.openclaw/memory"))
         if alt.exists():
             memory_dir = alt

    date_str = datetime.now().strftime("%Y-%m-%d")
    md_file = memory_dir / f"{date_str}.md"

    md_entry = f"- [{args.category.upper()}] {text} (importance: {importance_obj['score']:.2f}, {importance_obj['label']})\n"

    try:
        _atomic_append_file(md_file, md_entry)
        stored_path = str(md_file)
    except Exception as e:
        stored_path = f"failed ({e})"

    _emit({"ok": True, "id": rowid, "file": stored_path, "embedded": bool(api_key)}, args.json)


def cmd_artifact_stash(_conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    if getattr(args, "from_path", None):
        data = Path(str(args.from_path)).expanduser().read_bytes()
    else:
        data = sys.stdin.buffer.read()

    meta_obj: Dict[str, Any] = {}
    raw_meta_json = (getattr(args, "meta_json", None) or "").strip()
    if raw_meta_json:
        try:
            parsed = json.loads(raw_meta_json)
        except json.JSONDecodeError as e:
            _emit({"error": f"invalid --meta-json: {e}"}, True)
            sys.exit(2)
        if not isinstance(parsed, dict):
            _emit({"error": "--meta-json must be a JSON object"}, True)
            sys.exit(2)
        meta_obj = parsed

    receipt = stash_artifact(
        data,
        kind=str(getattr(args, "kind", "tool_output") or "tool_output"),
        meta=meta_obj,
        compress=bool(getattr(args, "gzip", False)),
    )
    _emit(receipt, bool(args.json))


def cmd_artifact_fetch(_conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    handle = str(getattr(args, "handle", "") or "").strip()
    try:
        parse_artifact_handle(handle)
    except ValueError as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    try:
        receipt = fetch_artifact(
            handle,
            mode=str(getattr(args, "mode", "headtail") or "headtail"),
            max_chars=max(1, int(getattr(args, "max_chars", 8000) or 8000)),
        )
    except FileNotFoundError as e:
        _emit({"error": str(e)}, True)
        sys.exit(1)
    except ValueError as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    if bool(args.json):
        _emit(receipt, True)
        return

    sys.stdout.write(str(receipt.get("text") or ""))


def cmd_artifact_peek(_conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    handle = str(getattr(args, "handle", "") or "").strip()
    try:
        parse_artifact_handle(handle)
    except ValueError as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    try:
        receipt = peek_artifact(
            handle,
            preview_chars=max(1, int(getattr(args, "preview_chars", 240) or 240)),
        )
    except FileNotFoundError as e:
        _emit({"error": str(e)}, True)
        sys.exit(1)

    _emit(receipt, bool(args.json))


# --- Graphic memory (GraphRAG-lite) — v0 skeleton (index-first + progressive disclosure) ---
#
# v0 design goals:
# - deterministic and local-only
# - safe-by-default (summary/snippet only; no detail_json dumps)
# - budgeted injection payloads (IndexPack / ContextPack)
#
# v0 implementation note:
# - this is NOT a full entity/KG system. It is a minimal link-graph using
#   timeline adjacency as the neighborhood expansion primitive.


def _graph_record_ref(obs_id: int) -> str:
    return f"obs:{int(obs_id)}"


def _graph_parse_record_ref(token: str) -> int:
    t = (token or "").strip()
    if not t:
        raise ValueError("empty record ref")
    if t.startswith("obs:"):
        t = t.split(":", 1)[1]
    return int(t)


def _graph_fts_sanitize_query(q: str) -> str:
    """Make ad-hoc keyword queries safer for SQLite FTS.

    Why:
    - FTS query syntax treats '-' specially. A query like `auto-capture` or
      `capture-md` can throw `sqlite3.OperationalError: no such column: capture`.
    - For "search bar" usage, we prefer a best-effort match over crashing.

    Strategy:
    - Quote tokens that contain '-' (turn them into phrase queries).
    - Preserve common boolean operators (OR/AND/NOT) and parentheses.
    """

    parts = []
    for raw in (q or "").split():
        if not raw:
            continue

        upper = raw.upper()
        if upper in {"OR", "AND", "NOT"}:
            parts.append(upper)
            continue

        # Peel parentheses + lightweight trailing punctuation.
        tok = raw
        prefix = ""
        while tok.startswith("("):
            prefix += "("
            tok = tok[1:]

        suffix = ""
        while tok.endswith(")"):
            suffix = ")" + suffix
            tok = tok[:-1]

        trail = ""
        while tok and tok[-1] in ",.;:":
            trail = tok[-1] + trail
            tok = tok[:-1]

        if tok and "-" in tok and not (tok.startswith('"') and tok.endswith('"')):
            tok = f'"{tok}"'

        parts.append(prefix + tok + trail + suffix)

    return " ".join(parts).strip()


def _graph_search_rows(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    scope: Optional[str] = None,
) -> List[sqlite3.Row]:
    q = (query or "").strip()
    if not q:
        return []

    limit_n = max(1, int(limit))
    scope_norm = _normalize_scope_token(scope)
    fetch_limit = limit_n if not scope_norm else max(limit_n, limit_n * 8, limit_n + 40)

    def _run(match_q: str, fetch_n: int) -> List[sqlite3.Row]:
        return conn.execute(
            """
            SELECT o.id, o.ts, o.kind, o.tool_name, o.summary, o.summary_en, o.lang,
                   snippet(observations_fts, 0, '[', ']', '…', 12) AS snippet,
                   snippet(observations_fts, 1, '[', ']', '…', 12) AS snippet_en,
                   bm25(observations_fts) AS score,
                   o.detail_json AS detail_json
            FROM observations_fts
            JOIN observations o ON o.id = observations_fts.rowid
            WHERE observations_fts MATCH ?
            ORDER BY score ASC
            LIMIT ?;
            """,
            (match_q, int(fetch_n)),
        ).fetchall()

    def _apply_scope(rows_in: List[sqlite3.Row]) -> List[sqlite3.Row]:
        if not scope_norm:
            return rows_in[:limit_n]

        out: List[sqlite3.Row] = []
        for r in rows_in:
            detail = _pack_parse_detail_json(r["detail_json"])
            row_scope = _normalize_scope_token(detail.get("scope"))
            if row_scope == scope_norm:
                out.append(r)
            if len(out) >= limit_n:
                break
        return out

    try:
        rows = _run(q, fetch_limit)
    except sqlite3.OperationalError:
        # Common failure mode: hyphenated terms in a "search bar" style query.
        q2 = _graph_fts_sanitize_query(q)
        if q2 and q2 != q:
            try:
                rows = _run(q2, fetch_limit)
            except sqlite3.OperationalError:
                rows = []
        else:
            rows = []

    rows = _apply_scope(rows)

    # Fallback for CJK keyword queries when FTS5 tokenizer cannot split terms well.
    if not rows and _has_cjk(q):
        rows = _search_cjk_fallback(conn, q, int(fetch_limit), scope=scope_norm)
        rows = rows[:limit_n]

    return rows


def _graph_row_title(r: sqlite3.Row) -> str:
    # Prefer human-friendly summary; fallback to snippet.
    summary = (r["summary"] or "").replace("\n", " ").strip()
    if summary:
        s = summary
    else:
        s = (r["snippet"] or "").replace("\n", " ").strip()

    if not s:
        kind = (r["kind"] or "obs").strip()
        tool = (r["tool_name"] or "").strip()
        s = f"{kind}:{tool}".strip(":")

    # Hard cap for safety in index packs.
    if len(s) > 180:
        s = s[:177] + "…"
    return s


def _graph_index_payload(
    conn: sqlite3.Connection,
    *,
    query: str,
    scope: Optional[str],
    limit: int,
    window: int,
    suggest_limit: int,
    budget_tokens: int,
) -> Dict[str, Any]:
    rows = _graph_search_rows(conn, query, limit, scope=scope)

    # Candidate list (L0)
    candidates: List[Dict[str, Any]] = []
    cand_ids: List[int] = []
    for r in rows:
        oid = int(r["id"])
        cand_ids.append(oid)
        candidates.append(
            {
                "recordRef": _graph_record_ref(oid),
                "id": oid,
                "ts": r["ts"],
                "kind": r["kind"],
                "tool_name": r["tool_name"],
                "score": float(r["score"]) if r["score"] is not None else None,
                "title": _graph_row_title(r),
                "why_relevant": "fts_match",
            }
        )

    # Neighborhood suggestions (simple deterministic link-graph): timeline adjacency.
    scope_norm = _normalize_scope_token(scope)
    neighbor_support: Dict[int, List[int]] = {}
    if window and cand_ids:
        seen = set(cand_ids)
        for oid in cand_ids:
            lo, hi = oid - window, oid + window
            nrows = conn.execute(
                "SELECT id, detail_json FROM observations WHERE id BETWEEN ? AND ? ORDER BY id",
                (lo, hi),
            ).fetchall()
            for nr in nrows:
                nid = int(nr["id"])
                if nid in seen:
                    continue
                if scope_norm:
                    detail = _pack_parse_detail_json(nr["detail_json"])
                    row_scope = _normalize_scope_token(detail.get("scope"))
                    if row_scope != scope_norm:
                        continue
                neighbor_support.setdefault(nid, []).append(oid)

    suggested_next: List[Dict[str, Any]] = []
    if suggest_limit and neighbor_support:
        for nid, supports in sorted(neighbor_support.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:suggest_limit]:
            suggested_next.append(
                {
                    "recordRef": _graph_record_ref(nid),
                    "id": nid,
                    "reason": "timeline_adjacent",
                    "support": {
                        "from": [_graph_record_ref(x) for x in supports[:5]],
                        "count": len(supports),
                    },
                }
            )

    # Build index_text (the injection payload) and enforce budget.
    lines: List[str] = []
    lines.append("[GRAPH_INDEX v0]")
    lines.append(f"Query: {query}")
    if scope:
        lines.append(f"Scope: {scope}")
    lines.append("")
    lines.append("Top candidates:")

    included: List[Dict[str, Any]] = []
    for c in candidates:
        line = f"- {c['recordRef']} [{c.get('kind')}] {c.get('tool_name') or ''} :: {c.get('title') or ''}".strip()
        new_est = _estimate_tokens("\n".join(lines + [line]))
        if new_est > budget_tokens and included:
            break
        lines.append(line)
        included.append(c)

    # Suggested expansions section (best-effort under budget)
    if suggested_next:
        lines.append("")
        lines.append("Suggested next expansions:")
        for s in suggested_next:
            line = f"- {s['recordRef']} reason={s['reason']} from={','.join(s['support']['from'])}".strip()
            new_est = _estimate_tokens("\n".join(lines + [line]))
            if new_est > budget_tokens:
                break
            lines.append(line)

    index_text = "\n".join(lines).strip() + "\n"

    # Defensive hard truncation to satisfy strict budgets (even for tiny budgets).
    max_chars = max(0, int(budget_tokens) * 4 - 3)
    if len(index_text) > max_chars:
        index_text = index_text[:max_chars].rstrip() + "\n"

    return {
        "kind": "openclaw-mem.graph.index.v0",
        "ts": _utcnow_iso(),
        "query": {"text": query, "scope": scope},
        "budget": {
            "budgetTokens": budget_tokens,
            "estimatedTokens": _estimate_tokens(index_text),
            "window": window,
        },
        "top_candidates": included,
        "suggested_next_expansions": suggested_next,
        "index_text": index_text,
    }


def cmd_graph_index(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (args.query or "").strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    payload = _graph_index_payload(
        conn,
        query=query,
        scope=(getattr(args, "scope", None) or "").strip() or None,
        limit=max(1, int(getattr(args, "limit", 12))),
        window=max(0, int(getattr(args, "window", 2))),
        suggest_limit=max(0, int(getattr(args, "suggest_limit", 6))),
        budget_tokens=max(1, int(getattr(args, "budget_tokens", 900))),
    )

    if bool(args.json):
        _emit(payload, True)
        return
    print(payload["index_text"], end="")


def _graph_pack_payload(
    conn: sqlite3.Connection,
    *,
    raw_ids: List[str],
    budget_tokens: int,
    max_items: int,
    allow_empty: bool = False,
    prefer_synthesis: bool = True,
) -> Dict[str, Any]:
    if not raw_ids:
        if allow_empty:
            return {
                "kind": "openclaw-mem.graph.pack.v0",
                "ts": _utcnow_iso(),
                "budget": {
                    "budgetTokens": budget_tokens,
                    "estimatedTokens": 0,
                },
                "selection": {
                    "inputRecordRefs": [],
                    "recordRefs": [],
                    "selectedCount": 0,
                    "preferredCardRefs": [],
                    "coveredRawRefs": [],
                },
                "items": [],
                "bundle_text": "",
            }
        raise ValueError("no ids")

    input_refs = _graph_collect_ref_tokens(raw_ids)
    selected_refs = list(input_refs)
    synth_preference = {
        "preferredCardRefs": [],
        "coveredRawRefs": [],
    }
    if prefer_synthesis:
        selected_refs, synth_preference = _graph_preflight_prefer_synthesis_cards(
            conn,
            selected_refs=input_refs,
            scope=None,
        )

    ids: List[int] = []
    for t in selected_refs:
        try:
            ids.append(_graph_parse_record_ref(t))
        except Exception as e:
            raise ValueError(f"bad id: {t}") from e

    # Dedupe while preserving order
    uniq: List[int] = []
    seen: set[int] = set()
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        uniq.append(i)
    uniq = uniq[:max_items]

    rows = conn.execute(
        f"SELECT id, ts, kind, tool_name, summary, detail_json FROM observations WHERE id IN ({','.join(['?']*len(uniq))})",
        uniq,
    ).fetchall()

    row_map = {int(r["id"]): r for r in rows}
    items: List[Dict[str, Any]] = []
    for oid in uniq:
        r = row_map.get(int(oid))
        if r is None:
            continue
        detail = _pack_parse_detail_json(r["detail_json"])
        synth = detail.get("graph_synthesis") if isinstance(detail.get("graph_synthesis"), dict) else None
        items.append(
            {
                "recordRef": _graph_record_ref(oid),
                "id": oid,
                "ts": r["ts"],
                "kind": r["kind"],
                "tool_name": r["tool_name"],
                "summary": (r["summary"] or "").replace("\n", " ").strip(),
                "synthesis": {
                    "title": synth.get("title"),
                    "why_it_matters": synth.get("why_it_matters"),
                    "source_count": synth.get("source_count"),
                    "status": synth.get("status"),
                } if synth else None,
            }
        )

    lines: List[str] = []
    lines.append("[GRAPH_CONTEXT v0]")
    lines.append(f"Items: {len(items)}")
    lines.append("")

    included_items: List[Dict[str, Any]] = []
    for idx, it in enumerate(items, 1):
        extra = ""
        synth = it.get("synthesis") if isinstance(it.get("synthesis"), dict) else None
        if synth:
            parts = []
            if synth.get("status"):
                parts.append(f"status={synth.get('status')}")
            if synth.get("source_count") is not None:
                parts.append(f"sources={int(synth.get('source_count') or 0)}")
            if synth.get("why_it_matters"):
                why = str(synth.get("why_it_matters") or "").replace("\n", " ").strip()
                if len(why) > 120:
                    why = why[:117] + "…"
                if why:
                    parts.append(f"why={why}")
            if parts:
                extra = " [" + ", ".join(parts) + "]"
        line = f"{idx}) {it['recordRef']} ts={it.get('ts')} [{it.get('kind')}] {it.get('tool_name') or ''} :: {it.get('summary') or ''}{extra}".strip()
        new_est = _estimate_tokens("\n".join(lines + [line]))
        if new_est > budget_tokens and included_items:
            break
        lines.append(line)
        included_items.append(it)

    bundle_text = "\n".join(lines).strip() + "\n"

    # Defensive hard truncation to satisfy strict budgets (even for tiny budgets).
    max_chars = max(0, int(budget_tokens) * 4 - 3)
    if len(bundle_text) > max_chars:
        bundle_text = bundle_text[:max_chars].rstrip() + "\n"

    return {
        "kind": "openclaw-mem.graph.pack.v0",
        "ts": _utcnow_iso(),
        "budget": {
            "budgetTokens": budget_tokens,
            "estimatedTokens": _estimate_tokens(bundle_text),
        },
        "selection": {
            "inputRecordRefs": input_refs,
            "recordRefs": [_graph_record_ref(x) for x in uniq],
            "selectedCount": len(uniq),
            "preferredCardRefs": list(synth_preference.get("preferredCardRefs") or []),
            "coveredRawRefs": list(synth_preference.get("coveredRawRefs") or []),
        },
        "items": included_items,
        "bundle_text": bundle_text,
    }


def cmd_graph_pack(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    raw_ids = list(getattr(args, "ids", []) or [])
    budget_tokens = max(1, int(getattr(args, "budget_tokens", 1500)))
    max_items = max(1, int(getattr(args, "max_items", 20)))

    try:
        payload = _graph_pack_payload(
            conn,
            raw_ids=raw_ids,
            budget_tokens=budget_tokens,
            max_items=max_items,
        )
    except ValueError as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    if bool(args.json):
        _emit(payload, True)
        return
    print(payload["bundle_text"], end="")


def _graph_preflight_selection(index_payload: Dict[str, Any], take: int) -> List[str]:
    refs: List[str] = []
    for c in list(index_payload.get("top_candidates") or []):
        ref = (c or {}).get("recordRef")
        if isinstance(ref, str) and ref.strip():
            refs.append(ref.strip())

    for s in list(index_payload.get("suggested_next_expansions") or []):
        ref = (s or {}).get("recordRef")
        if isinstance(ref, str) and ref.strip():
            refs.append(ref.strip())

    deduped: List[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        deduped.append(ref)
        if len(deduped) >= take:
            break

    return deduped


def cmd_graph_preflight(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (args.query or "").strip()
    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)

    scope = (getattr(args, "scope", None) or "").strip() or None
    limit = max(1, int(getattr(args, "limit", 12)))
    window = max(0, int(getattr(args, "window", 2)))
    suggest_limit = max(0, int(getattr(args, "suggest_limit", 6)))
    budget_tokens = max(1, int(getattr(args, "budget_tokens", 1200)))
    take = max(1, int(getattr(args, "take", 12)))

    index_payload = _graph_index_payload(
        conn,
        query=query,
        scope=scope,
        limit=limit,
        window=window,
        suggest_limit=suggest_limit,
        budget_tokens=budget_tokens,
    )

    selected_refs = _graph_preflight_selection(index_payload, take=take)
    preferred_refs, synth_preference = _graph_preflight_prefer_synthesis_cards(
        conn,
        selected_refs=selected_refs,
        scope=scope,
    )

    pack_payload = _graph_pack_payload(
        conn,
        raw_ids=preferred_refs,
        budget_tokens=budget_tokens,
        max_items=max(1, take),
        allow_empty=True,
    )

    payload = {
        "kind": "openclaw-mem.graph.preflight.v0",
        "ts": _utcnow_iso(),
        "query": {"text": query, "scope": scope},
        "selection": {
            "take": take,
            "recordRefs": preferred_refs,
            "selectedCount": len(preferred_refs),
            "rawRecordRefs": selected_refs,
            "preferredCardRefs": synth_preference.get("preferredCardRefs", []),
            "coveredRawRefs": synth_preference.get("coveredRawRefs", []),
        },
        "budget": {
            "budgetTokens": budget_tokens,
            "estimatedTokens": _estimate_tokens(pack_payload["bundle_text"]),
        },
        "index": {
            "kind": index_payload.get("kind"),
            "budget": index_payload.get("budget"),
            "top_candidates": index_payload.get("top_candidates", []),
            "suggested_next_expansions": index_payload.get("suggested_next_expansions", []),
        },
        "pack": pack_payload,
        "items": pack_payload.get("items", []),
        "bundle_text": pack_payload.get("bundle_text", ""),
    }

    if bool(args.json):
        _emit(payload, True)
        return
    print(pack_payload.get("bundle_text", ""), end="")


def _graph_collect_ref_tokens(raw_refs: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in list(raw_refs or []):
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _graph_fetch_rows_by_ids(conn: sqlite3.Connection, ids: List[int]) -> Dict[int, sqlite3.Row]:
    uniq: List[int] = []
    seen: set[int] = set()
    for item in ids:
        oid = int(item)
        if oid in seen:
            continue
        seen.add(oid)
        uniq.append(oid)
    if not uniq:
        return {}
    rows = conn.execute(
        f"SELECT id, ts, kind, tool_name, summary, detail_json FROM observations WHERE id IN ({','.join(['?']*len(uniq))})",
        uniq,
    ).fetchall()
    return {int(r['id']): r for r in rows}


def _graph_source_snapshot(row: sqlite3.Row) -> Dict[str, Any]:
    oid = int(row['id'])
    detail = _pack_parse_detail_json(row['detail_json'])
    return {
        'recordRef': _graph_record_ref(oid),
        'id': oid,
        'ts': row['ts'],
        'kind': row['kind'],
        'tool_name': row['tool_name'],
        'summary': (row['summary'] or '').replace('\n', ' ').strip(),
        'scope': _normalize_scope_token(detail.get('scope')) or None,
    }


def _graph_source_digest_from_snapshots(items: List[Dict[str, Any]]) -> str:
    payload = [
        {
            'recordRef': str(it.get('recordRef') or ''),
            'ts': str(it.get('ts') or ''),
            'kind': str(it.get('kind') or ''),
            'tool_name': str(it.get('tool_name') or ''),
            'summary': str(it.get('summary') or ''),
            'scope': str(it.get('scope') or ''),
        }
        for it in items
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


_GRAPH_CONTRADICTION_KEYWORDS: Tuple[str, ...] = (
    'contradict', 'contradiction', 'conflict', 'mismatch', 'incompatible', '矛盾', '衝突',
)

_GRAPH_REVIEW_KEYWORDS: Tuple[str, ...] = (
    'deprecated', 'deprecate', 'obsolete', 'outdated', 'stale', 'supersede', 'superseded',
    'replace', 'replaced', 'rename', 'renamed', 'rollback', 'rolled back', 'revert', 'reverted',
    '棄用', '過時', '取代', '改名', '回滾',
)


def _graph_review_signals_from_rows(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    for row in rows:
        summary = str(row['summary'] or '').replace('\n', ' ').strip()
        hay = summary.lower()
        kinds: List[Tuple[str, str]] = []
        for kw in _GRAPH_CONTRADICTION_KEYWORDS:
            if kw in hay or kw in summary:
                kinds.append(('contradiction_keyword', kw))
                break
        for kw in _GRAPH_REVIEW_KEYWORDS:
            if kw in hay or kw in summary:
                kinds.append(('review_keyword', kw))
                break
        for kind, keyword in kinds:
            signals.append(
                {
                    'kind': kind,
                    'keyword': keyword,
                    'recordRef': _graph_record_ref(int(row['id'])),
                    'summary': summary,
                }
            )
    return signals


def _graph_build_synth_markdown(
    *,
    title: str,
    summary_text: str,
    why_it_matters: Optional[str],
    scope: Optional[str],
    source_refs: List[str],
    source_digest: str,
    compiled_at: str,
    selection: Dict[str, Any],
) -> str:
    lines: List[str] = ['---']
    lines.append('kind: synthesis_card')
    lines.append(f'title: {json.dumps(title, ensure_ascii=False)}')
    if summary_text:
        lines.append(f'summary: {json.dumps(summary_text, ensure_ascii=False)}')
    if scope:
        lines.append(f'scope: {json.dumps(scope, ensure_ascii=False)}')
    lines.append(f'compiled_at: {json.dumps(compiled_at, ensure_ascii=False)}')
    lines.append(f'source_digest: {json.dumps(source_digest, ensure_ascii=False)}')
    lines.append('source_refs:')
    for ref in source_refs:
        lines.append(f'  - {json.dumps(ref, ensure_ascii=False)}')
    lines.append(f'selection: {json.dumps(selection, ensure_ascii=False, sort_keys=True)}')
    lines.append('---')
    lines.append('')
    lines.append(f'# {title}')
    lines.append('')
    if summary_text:
        lines.append(summary_text)
        lines.append('')
    if why_it_matters:
        lines.append('## Why it matters')
        lines.append('')
        lines.append(why_it_matters)
        lines.append('')
    lines.append('## Source refs')
    lines.append('')
    for ref in source_refs:
        lines.append(f'- {ref}')
    lines.append('')
    lines.append('## Notes')
    lines.append('')
    lines.append('<!-- Add the durable synthesis here. Keep it bounded and provenance-first. -->')
    lines.append('')
    return '\n'.join(lines)


def _graph_compile_selection(
    conn: sqlite3.Connection,
    *,
    explicit_refs: List[str],
    query_text: Optional[str],
    scope: Optional[str],
    limit: int,
    window: int,
    suggest_limit: int,
    take: int,
    budget_tokens: int,
) -> Tuple[List[str], Dict[str, Any]]:
    refs = _graph_collect_ref_tokens(explicit_refs)
    query_value = (query_text or '').strip()
    if refs and query_value:
        raise ValueError('choose explicit refs or --query, not both')
    if not refs and not query_value:
        raise ValueError('missing source refs or --query')

    if refs:
        return refs, {
            'mode': 'explicit_refs',
            'recordRefs': refs,
        }

    index_payload = _graph_index_payload(
        conn,
        query=query_value,
        scope=scope,
        limit=limit,
        window=window,
        suggest_limit=suggest_limit,
        budget_tokens=budget_tokens,
    )
    selected_refs = _graph_preflight_selection(index_payload, take=take)
    return selected_refs, {
        'mode': 'query_preflight',
        'query': {
            'text': query_value,
            'scope': scope,
            'limit': int(limit),
            'window': int(window),
            'suggestLimit': int(suggest_limit),
            'take': int(take),
            'budgetTokens': int(budget_tokens),
        },
        'index': {
            'topCandidates': len(index_payload.get('top_candidates') or []),
            'suggestedNextExpansions': len(index_payload.get('suggested_next_expansions') or []),
        },
        'recordRefs': selected_refs,
    }


def _graph_eval_synthesis_card(conn: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
    detail = _pack_parse_detail_json(row['detail_json'])
    synth = detail.get('graph_synthesis') if isinstance(detail.get('graph_synthesis'), dict) else {}
    record_ref = _graph_record_ref(int(row['id']))
    source_refs_raw = list(synth.get('source_refs') or [])
    source_refs = _graph_collect_ref_tokens(source_refs_raw)
    source_ids: List[int] = []
    for ref in source_refs:
        try:
            source_ids.append(_graph_parse_record_ref(ref))
        except Exception:
            continue
    source_rows = _graph_fetch_rows_by_ids(conn, source_ids)
    snapshots = [_graph_source_snapshot(source_rows[oid]) for oid in source_ids if oid in source_rows]
    current_digest = _graph_source_digest_from_snapshots(snapshots) if snapshots else ''

    reasons: List[str] = []
    missing_refs = [ref for ref in source_refs if _graph_parse_record_ref(ref) not in source_rows] if source_refs else []
    if not source_refs:
        reasons.append('missing_source_refs')
    if synth.get('source_digest') and current_digest and current_digest != str(synth.get('source_digest')):
        reasons.append('source_digest_mismatch')
    if missing_refs:
        reasons.append('missing_source_rows')

    selection = synth.get('selection') if isinstance(synth.get('selection'), dict) else {}
    selection_mode = str(selection.get('mode') or '').strip()
    current_selection: List[str] = []
    if selection_mode == 'query_preflight':
        query_meta = selection.get('query') if isinstance(selection.get('query'), dict) else {}
        query_text = str(query_meta.get('text') or '').strip()
        if query_text:
            index_payload = _graph_index_payload(
                conn,
                query=query_text,
                scope=(query_meta.get('scope') or None),
                limit=max(1, int(query_meta.get('limit') or 12)),
                window=max(0, int(query_meta.get('window') or 2)),
                suggest_limit=max(0, int(query_meta.get('suggestLimit') or 6)),
                budget_tokens=max(1, int(query_meta.get('budgetTokens') or 1200)),
            )
            current_selection = _graph_preflight_selection(index_payload, take=max(1, int(query_meta.get('take') or 12)))
            if current_selection != source_refs:
                reasons.append('selection_drift')

    new_selection_refs = [ref for ref in current_selection if ref not in set(source_refs)]
    new_selection_ids: List[int] = []
    for ref in new_selection_refs:
        try:
            new_selection_ids.append(_graph_parse_record_ref(ref))
        except Exception:
            continue
    new_selection_rows_map = _graph_fetch_rows_by_ids(conn, new_selection_ids)
    new_selection_rows = [new_selection_rows_map[oid] for oid in new_selection_ids if oid in new_selection_rows_map]
    review_signals = _graph_review_signals_from_rows(new_selection_rows)
    contradiction_signals = [sig for sig in review_signals if sig.get('kind') == 'contradiction_keyword']

    if reasons:
        status = 'stale'
    elif review_signals:
        status = 'review'
    else:
        status = 'fresh'
    return {
        'ok': True,
        'recordRef': record_ref,
        'title': str(synth.get('title') or row['summary'] or record_ref),
        'status': status,
        'reasonCount': len(reasons),
        'reasons': reasons,
        'compiledAt': synth.get('compiled_at') or row['ts'],
        'sourceRefs': source_refs,
        'sourceCount': len(source_refs),
        'missingSourceRefs': missing_refs,
        'storedSourceDigest': synth.get('source_digest') or None,
        'currentSourceDigest': current_digest or None,
        'selectionMode': selection_mode or None,
        'currentSelection': current_selection,
        'newSelectionRefs': new_selection_refs,
        'reviewSignals': review_signals,
        'reviewSignalCount': len(review_signals),
        'contradictionSignalCount': len(contradiction_signals),
        'scope': synth.get('scope') or detail.get('scope') or None,
    }


def _graph_preflight_prefer_synthesis_cards(
    conn: sqlite3.Connection,
    *,
    selected_refs: List[str],
    scope: Optional[str],
) -> Tuple[List[str], Dict[str, Any]]:
    refs = _graph_collect_ref_tokens(selected_refs)
    if not refs:
        return refs, {
            'enabled': True,
            'preferredCardRefs': [],
            'coveredRawRefs': [],
        }

    synth_rows = conn.execute(
        "SELECT id, ts, kind, tool_name, summary, detail_json FROM observations WHERE tool_name = 'graph.synth-compile' ORDER BY id DESC"
    ).fetchall()

    scope_norm = _normalize_scope_token(scope)
    candidates: List[Dict[str, Any]] = []
    for row in synth_rows:
        item = _graph_eval_synthesis_card(conn, row)
        if item.get('status') != 'fresh':
            continue
        item_scope = _normalize_scope_token(item.get('scope'))
        if scope_norm and item_scope and item_scope != scope_norm:
            continue
        source_refs = _graph_collect_ref_tokens(item.get('sourceRefs') or [])
        covered = [ref for ref in refs if ref in set(source_refs)]
        if len(covered) < 2:
            continue
        candidates.append(
            {
                'recordRef': item.get('recordRef'),
                'covered': covered,
                'coveredCount': len(covered),
                'sourceCount': len(source_refs),
            }
        )

    candidates.sort(key=lambda x: (-int(x.get('coveredCount') or 0), int(x.get('sourceCount') or 0), str(x.get('recordRef') or '')))

    remaining = list(refs)
    preferred_card_refs: List[str] = []
    covered_raw_refs: List[str] = []
    for cand in candidates:
        covered_now = [ref for ref in remaining if ref in set(cand.get('covered') or [])]
        if len(covered_now) < 2:
            continue
        preferred_card_refs.append(str(cand.get('recordRef') or ''))
        covered_raw_refs.extend(covered_now)
        remaining = [ref for ref in remaining if ref not in set(covered_now)]

    final_refs = _graph_collect_ref_tokens(preferred_card_refs + remaining)
    return final_refs, {
        'enabled': True,
        'preferredCardRefs': preferred_card_refs,
        'coveredRawRefs': covered_raw_refs,
    }


def cmd_graph_synth(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    synth_cmd = str(getattr(args, 'graph_synth_cmd', '') or '').strip().lower()

    if synth_cmd == 'compile':
        explicit_refs = _graph_collect_ref_tokens(getattr(args, 'record_ref', None))
        query_text = (getattr(args, 'query', None) or '').strip() or None
        scope = (getattr(args, 'scope', None) or '').strip() or None
        limit = max(1, int(getattr(args, 'limit', 12) or 12))
        window = max(0, int(getattr(args, 'window', 2) or 2))
        suggest_limit = max(0, int(getattr(args, 'suggest_limit', 6) or 6))
        take = max(1, int(getattr(args, 'take', 12) or 12))
        budget_tokens = max(1, int(getattr(args, 'budget_tokens', 1200) or 1200))

        try:
            selected_refs, selection = _graph_compile_selection(
                conn,
                explicit_refs=explicit_refs,
                query_text=query_text,
                scope=scope,
                limit=limit,
                window=window,
                suggest_limit=suggest_limit,
                take=take,
                budget_tokens=budget_tokens,
            )
        except ValueError as e:
            _emit({'error': str(e)}, True)
            sys.exit(2)

        source_ids = [_graph_parse_record_ref(ref) for ref in selected_refs]
        source_rows = _graph_fetch_rows_by_ids(conn, source_ids)
        missing = [ref for ref in selected_refs if _graph_parse_record_ref(ref) not in source_rows]
        if missing:
            _emit({'error': 'missing source refs', 'missing': missing}, True)
            sys.exit(2)

        snapshots = [_graph_source_snapshot(source_rows[oid]) for oid in source_ids if oid in source_rows]
        source_digest = _graph_source_digest_from_snapshots(snapshots)
        compiled_at = _utcnow_iso()

        title = (getattr(args, 'title', None) or '').strip()
        if not title:
            if query_text:
                title = f'Graph synthesis: {query_text}'
            elif len(selected_refs) == 1:
                title = f'Graph synthesis: {selected_refs[0]}'
            else:
                title = f'Graph synthesis ({len(selected_refs)} refs)'

        summary_text = (getattr(args, 'summary_text', None) or '').strip() or title
        why_it_matters = (getattr(args, 'why_it_matters', None) or '').strip() or None

        detail = {
            'scope': scope,
            'graph_synthesis': {
                'version': 'v0',
                'title': title,
                'summary': summary_text,
                'why_it_matters': why_it_matters,
                'source_refs': selected_refs,
                'source_count': len(selected_refs),
                'source_digest': source_digest,
                'compiled_at': compiled_at,
                'selection': selection,
                'status': 'fresh',
                'trust_tier': 'derived',
            },
        }

        obs = {
            'ts': compiled_at,
            'kind': 'note',
            'summary': summary_text,
            'tool_name': 'graph.synth-compile',
            'detail': detail,
        }
        rowid = _insert_observation(conn, obs)
        card_ref = _graph_record_ref(rowid)

        markdown_path = (getattr(args, 'write_md', None) or '').strip()
        markdown_written = None
        markdown_text = _graph_build_synth_markdown(
            title=title,
            summary_text=summary_text,
            why_it_matters=why_it_matters,
            scope=scope,
            source_refs=selected_refs,
            source_digest=source_digest,
            compiled_at=compiled_at,
            selection=selection,
        )
        if markdown_path:
            md_path = Path(markdown_path)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(markdown_text, encoding='utf-8')
            markdown_written = str(md_path)

        payload = {
            'kind': 'openclaw-mem.graph.synth.compile.v0',
            'ts': compiled_at,
            'cardRef': card_ref,
            'selection': selection,
            'result': {
                'ok': True,
                'recordRef': card_ref,
                'title': title,
                'summary': summary_text,
                'whyItMatters': why_it_matters,
                'sourceRefs': selected_refs,
                'sourceCount': len(selected_refs),
                'sourceDigest': source_digest,
                'markdownPath': markdown_written,
            },
            'bundle_text': markdown_text,
        }

        if bool(args.json):
            _emit(payload, True)
            return
        print(markdown_text, end='')
        return

    if synth_cmd == 'stale':
        refs = _graph_collect_ref_tokens(getattr(args, 'record_ref', None))
        if not refs:
            _emit({'error': 'missing record refs'}, True)
            sys.exit(2)

        ids = [_graph_parse_record_ref(ref) for ref in refs]
        row_map = _graph_fetch_rows_by_ids(conn, ids)
        items: List[Dict[str, Any]] = []
        missing_cards: List[str] = []
        for ref in refs:
            oid = _graph_parse_record_ref(ref)
            row = row_map.get(oid)
            if row is None:
                missing_cards.append(ref)
                continue
            items.append(_graph_eval_synthesis_card(conn, row))

        payload = {
            'kind': 'openclaw-mem.graph.synth.stale.v0',
            'ts': _utcnow_iso(),
            'count': len(items),
            'missing': missing_cards,
            'items': items,
        }
        if bool(args.json):
            _emit(payload, True)
            return
        for item in items:
            print(
                ' '.join(
                    [
                        f"recordRef={item.get('recordRef')}",
                        f"status={item.get('status')}",
                        f"reasons={','.join(item.get('reasons') or []) or '-'}",
                    ]
                )
            )
        for ref in missing_cards:
            print(f'recordRef={ref} status=missing reasons=missing_card')
        return

    _emit({'error': f'unknown graph synth command: {synth_cmd}'}, True)
    sys.exit(2)


def cmd_graph_lint(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _ = args
    synth_rows = conn.execute(
        "SELECT id, ts, kind, tool_name, summary, detail_json FROM observations WHERE tool_name = 'graph.synth-compile' ORDER BY id"
    ).fetchall()
    capture_rows = conn.execute(
        "SELECT id, ts, tool_name, summary FROM observations WHERE tool_name IN ('graph.capture-git', 'graph.capture-md') ORDER BY id"
    ).fetchall()

    synth_items: List[Dict[str, Any]] = []
    referenced_sources: set[str] = set()
    stale_items: List[Dict[str, Any]] = []
    review_items: List[Dict[str, Any]] = []
    contradiction_items: List[Dict[str, Any]] = []
    missing_source_ref_items: List[Dict[str, Any]] = []
    missing_digest_items: List[Dict[str, Any]] = []

    for row in synth_rows:
        item = _graph_eval_synthesis_card(conn, row)
        synth_items.append(item)
        for ref in list(item.get('sourceRefs') or []):
            referenced_sources.add(str(ref))
        if item.get('status') == 'stale':
            stale_items.append(item)
        if item.get('reviewSignalCount'):
            review_items.append(item)
        if int(item.get('contradictionSignalCount') or 0) > 0:
            contradiction_items.append(item)
        if not item.get('sourceRefs'):
            missing_source_ref_items.append(item)
        if not item.get('storedSourceDigest'):
            missing_digest_items.append(item)

    unreferenced_capture: List[Dict[str, Any]] = []
    for row in capture_rows:
        ref = _graph_record_ref(int(row['id']))
        if ref in referenced_sources:
            continue
        unreferenced_capture.append(
            {
                'recordRef': ref,
                'ts': row['ts'],
                'tool_name': row['tool_name'],
                'summary': (row['summary'] or '').replace('\n', ' ').strip(),
            }
        )

    payload = {
        'kind': 'openclaw-mem.graph.lint.v0',
        'ts': _utcnow_iso(),
        'counts': {
            'synthesisCards': len(synth_items),
            'staleCards': len(stale_items),
            'reviewCards': len(review_items),
            'contradictionSignalCards': len(contradiction_items),
            'cardsMissingSourceRefs': len(missing_source_ref_items),
            'cardsMissingSourceDigest': len(missing_digest_items),
            'captureRows': len(capture_rows),
            'unreferencedCaptureRows': len(unreferenced_capture),
        },
        'samples': {
            'staleCards': stale_items[:10],
            'reviewCards': review_items[:10],
            'contradictionSignalCards': contradiction_items[:10],
            'cardsMissingSourceRefs': missing_source_ref_items[:10],
            'cardsMissingSourceDigest': missing_digest_items[:10],
            'unreferencedCaptureRows': unreferenced_capture[:10],
        },
    }

    if bool(args.json):
        _emit(payload, True)
        return

    counts = payload['counts']
    print(
        ' '.join(
            [
                f"synthesis_cards={int(counts.get('synthesisCards') or 0)}",
                f"stale_cards={int(counts.get('staleCards') or 0)}",
                f"review_cards={int(counts.get('reviewCards') or 0)}",
                f"contradiction_signal_cards={int(counts.get('contradictionSignalCards') or 0)}",
                f"missing_source_refs={int(counts.get('cardsMissingSourceRefs') or 0)}",
                f"missing_source_digest={int(counts.get('cardsMissingSourceDigest') or 0)}",
                f"unreferenced_capture_rows={int(counts.get('unreferencedCaptureRows') or 0)}",
            ]
        )
    )


def _graph_env_bool_status(name: str, *, default: bool = False) -> Dict[str, Any]:
    raw = os.getenv(name)
    if raw is None:
        return {
            "present": False,
            "raw": None,
            "normalized": None,
            "enabled": bool(default),
            "valid": True,
            "default": bool(default),
            "reason": "unset_default",
        }

    normalized = str(raw).strip().lower()
    truthy = {"1", "true", "on", "yes", "y", "t"}
    falsy = {"0", "false", "off", "no", "n", "f", ""}

    if normalized in truthy:
        enabled = True
        valid = True
    elif normalized in falsy:
        enabled = False
        valid = True
    else:
        enabled = bool(default)
        valid = False

    reason = "invalid_fallback_default"
    if valid and enabled:
        reason = "parsed_truthy"
    elif valid and not enabled:
        reason = "parsed_falsy"

    return {
        "present": True,
        "raw": str(raw),
        "normalized": normalized,
        "enabled": enabled,
        "valid": valid,
        "default": bool(default),
        "reason": reason,
    }


def cmd_graph_auto_status(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _ = conn
    flags = {
        "OPENCLAW_MEM_GRAPH_AUTO_RECALL": _graph_env_bool_status("OPENCLAW_MEM_GRAPH_AUTO_RECALL", default=False),
        "OPENCLAW_MEM_GRAPH_AUTO_CAPTURE": _graph_env_bool_status("OPENCLAW_MEM_GRAPH_AUTO_CAPTURE", default=False),
        "OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD": _graph_env_bool_status("OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD", default=False),
    }

    payload = {
        "kind": "openclaw-mem.graph.auto-status.v0",
        "ts": _utcnow_iso(),
        "flags": flags,
    }

    if bool(args.json):
        _emit(payload, True)
        return

    for name, st in flags.items():
        raw = st.get("raw")
        raw_show = raw if isinstance(raw, str) else "(unset)"
        print(
            f"{name}: enabled={str(bool(st.get('enabled'))).lower()} "
            f"valid={str(bool(st.get('valid'))).lower()} raw={raw_show}"
        )


def cmd_graph_topology_refresh(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Deterministically refresh the topology graph (nodes/edges) from a curated file.

    This is the maintenance entrypoint for L3 topology knowledge.
    """

    _ = conn
    topology_path = str(getattr(args, "file", "") or "").strip()
    if not topology_path:
        _emit({"error": "missing --file"}, True)
        sys.exit(2)

    try:
        from openclaw_mem.graph.refresh import refresh_topology_file

        result = refresh_topology_file(topology_path=topology_path, db_path=str(args.db))
    except Exception as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    payload = {
        "kind": "openclaw-mem.graph.topology-refresh.v0",
        "ts": _utcnow_iso(),
        "file": topology_path,
        "result": result,
    }

    if bool(args.json):
        _emit(payload, True)
        return

    # text-only mode
    print(
        " ".join(
            [
                f"ok={str(bool(result.get('ok'))).lower()}",
                f"nodes={int(result.get('node_count') or 0)}",
                f"edges={int(result.get('edge_count') or 0)}",
                f"digest={result.get('topology_digest')}",
            ]
        )
    )


def cmd_graph_topology_extract(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Extract a deterministic topology seed from workspace + cron registry + cron specs."""

    _ = conn
    workspace = str(getattr(args, "workspace", "") or "").strip() or str(DEFAULT_WORKSPACE)
    cron_jobs = str(getattr(args, "cron_jobs", "") or "").strip() or DEFAULT_CRON_JOBS_JSON
    spec_dir = str(getattr(args, "spec_dir", "") or "").strip()
    if not spec_dir:
        spec_dir = str(Path(workspace) / "openclaw-async-coding-playbook" / "cron" / "jobs")

    out_path = str(getattr(args, "out", "") or "").strip()
    if not out_path:
        _emit({"error": "missing --out"}, True)
        sys.exit(2)

    try:
        seed = extract_topology_seed(
            workspace=workspace,
            cron_jobs_path=cron_jobs,
            spec_dir=spec_dir,
        )
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(seed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    counts = seed.get("counts") if isinstance(seed.get("counts"), dict) else {}
    payload = {
        "kind": "openclaw-mem.graph.topology-extract.v0",
        "ts": _utcnow_iso(),
        "workspace": str(Path(workspace).resolve()),
        "cron_jobs": str(Path(cron_jobs).resolve()),
        "spec_dir": str(Path(spec_dir).resolve()),
        "out": str(Path(out_path).resolve()),
        "result": {
            "ok": True,
            "node_count": int(counts.get("nodes") or 0),
            "edge_count": int(counts.get("edges") or 0),
            "repo_count": int(counts.get("repos") or 0),
            "cron_job_count": int(counts.get("cron_jobs") or 0),
            "spec_count": int(counts.get("spec_files") or 0),
            "node_types": counts.get("node_types") if isinstance(counts.get("node_types"), dict) else {},
            "edge_types": counts.get("edge_types") if isinstance(counts.get("edge_types"), dict) else {},
            "provenance_groups": counts.get("provenance_groups")
            if isinstance(counts.get("provenance_groups"), dict)
            else {},
        },
    }

    if bool(args.json):
        _emit(payload, True)
        return

    result = payload["result"]
    print(
        " ".join(
            [
                f"ok={str(bool(result.get('ok'))).lower()}",
                f"repos={int(result.get('repo_count') or 0)}",
                f"cron_jobs={int(result.get('cron_job_count') or 0)}",
                f"specs={int(result.get('spec_count') or 0)}",
                f"nodes={int(result.get('node_count') or 0)}",
                f"edges={int(result.get('edge_count') or 0)}",
                f"out={payload.get('out')}",
            ]
        )
    )


def cmd_graph_topology_diff(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Compare extracted seed topology against a curated topology file (suggest-only)."""

    _ = conn
    seed_path = str(getattr(args, "seed", "") or "").strip()
    curated_path = str(getattr(args, "curated", "") or "").strip()
    if not seed_path:
        _emit({"error": "missing --seed"}, True)
        sys.exit(2)
    if not curated_path:
        _emit({"error": "missing --curated"}, True)
        sys.exit(2)

    limit_raw = int(getattr(args, "limit", 50) or 50)
    limit = max(0, limit_raw)

    try:
        result = compare_topology_files(seed_path=seed_path, curated_path=curated_path, limit=limit)
    except Exception as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)

    payload = {
        "kind": "openclaw-mem.graph.topology-diff.v0",
        "ts": _utcnow_iso(),
        "seed": str(Path(seed_path).resolve()),
        "curated": str(Path(curated_path).resolve()),
        "result": result,
    }

    if bool(args.json):
        _emit(payload, True)
        return

    diff = result.get("diff") if isinstance(result.get("diff"), dict) else {}
    counts = diff.get("counts") if isinstance(diff.get("counts"), dict) else {}
    print(
        " ".join(
            [
                f"ok={str(bool(result.get('ok'))).lower()}",
                f"missing_nodes={int(counts.get('missing_nodes') or 0)}",
                f"stale_nodes={int(counts.get('stale_nodes') or 0)}",
                f"node_contract_mismatches={int(counts.get('node_contract_mismatches') or 0)}",
                f"missing_edges={int(counts.get('missing_edges') or 0)}",
                f"stale_edges={int(counts.get('stale_edges') or 0)}",
                f"edge_contract_mismatches={int(counts.get('edge_contract_mismatches') or 0)}",
                f"limit={int(diff.get('limit') or 0)}",
            ]
        )
    )


def _graph_capture_md_norm_ext(ext: str) -> str:
    v = str(ext or "").strip().lower()
    if not v:
        return ""
    if not v.startswith("."):
        v = "." + v
    return v


def _graph_capture_md_includes(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for raw in list(values or []):
        ext = _graph_capture_md_norm_ext(raw)
        if not ext or ext in out:
            continue
        out.append(ext)
    if out:
        return out
    return [*DEFAULT_GRAPH_CAPTURE_MD_INCLUDES]


def _graph_capture_md_excludes(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for raw in list(values or []):
        pat = str(raw or "").strip()
        if not pat or pat in out:
            continue
        out.append(pat)
    if out:
        return out
    return [*DEFAULT_GRAPH_CAPTURE_MD_EXCLUDES]


def _graph_capture_md_is_excluded(path: Path, patterns: List[str]) -> bool:
    raw = path.as_posix()
    for pat in patterns:
        if fnmatch.fnmatch(raw, pat):
            return True
    return False


def _graph_capture_md_collect_files(
    raw_paths: List[str],
    *,
    includes: List[str],
    excludes: List[str],
    max_files: int,
) -> Tuple[List[Path], int]:
    selected: List[Path] = []
    seen: set[str] = set()
    errors = 0

    for raw in raw_paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            errors += 1
            continue

        candidates: List[Path] = []
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            candidates = [x for x in p.rglob("*") if x.is_file()]
        else:
            errors += 1
            continue

        for fp in sorted(candidates):
            if len(selected) >= max_files:
                return selected, errors

            abs_key = str(fp)
            if abs_key in seen:
                continue

            ext = fp.suffix.lower()
            if ext not in includes:
                continue

            if _graph_capture_md_is_excluded(fp, excludes):
                continue

            seen.add(abs_key)
            selected.append(fp)

    return selected, errors


def _graph_capture_md_parse_sections(
    text: str,
    *,
    min_heading_level: int,
    max_sections: int,
) -> List[Dict[str, Any]]:
    if max_sections <= 0:
        return []

    heading_re = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
    fence_re = re.compile(r"^\s{0,3}(```+|~~~+)")

    lines = text.splitlines()
    sections: List[Dict[str, Any]] = []
    active: Optional[Dict[str, Any]] = None
    in_code = False

    for idx, line in enumerate(lines, 1):
        if fence_re.match(line):
            in_code = not in_code
            continue

        if in_code:
            continue

        m = heading_re.match(line)
        if not m:
            continue

        if active is not None:
            active["end_line"] = idx - 1
            sections.append(active)
            active = None

        level = len(m.group(1))
        heading = re.sub(r"\s+#+\s*$", "", (m.group(2) or "").strip()).strip() or "(untitled)"

        if level >= min_heading_level:
            active = {
                "heading": heading,
                "heading_level": level,
                "start_line": idx,
                "end_line": len(lines),
            }

    if active is not None:
        active["end_line"] = len(lines)
        sections.append(active)

    return sections[:max_sections]


def _graph_capture_md_first_lines_for_fingerprint(
    lines: List[str],
    *,
    start_line: int,
    end_line: int,
) -> List[str]:
    fence_re = re.compile(r"^\s{0,3}(```+|~~~+)")
    out: List[str] = []
    in_code = False

    begin = max(start_line + 1, 1)
    end = min(end_line, len(lines))
    for i in range(begin, end + 1):
        raw = lines[i - 1]
        if fence_re.match(raw):
            in_code = not in_code
            continue
        if in_code:
            continue

        v = raw.strip()
        if not v:
            continue

        out.append(v)
        if len(out) >= 5:
            break

    return out


def _graph_capture_md_summary(path: Path, heading: str) -> str:
    heading_text = re.sub(r"\s+", " ", (heading or "").replace("\n", " ")).strip() or "(untitled)"
    summary = f"[MD] {path.name}#{heading_text}"
    if len(summary) > 180:
        return summary[:177] + "…"
    return summary


def _graph_capture_md_git_root(file_path: Path, cache: Dict[str, Optional[Path]]) -> Optional[Path]:
    dir_key = str(file_path.parent.resolve())
    if dir_key in cache:
        return cache[dir_key]

    p = subprocess.run(
        ["git", "-C", str(file_path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        cache[dir_key] = None
        return None

    raw = (p.stdout or "").strip()
    if not raw:
        cache[dir_key] = None
        return None

    root = Path(raw).expanduser().resolve()
    cache[dir_key] = root
    return root


def _graph_capture_md_seen(conn: sqlite3.Connection, fingerprint: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM graph_capture_md_seen WHERE fingerprint = ? LIMIT 1",
        (fingerprint,),
    ).fetchone()
    return row is not None


def _graph_capture_md_mark_seen(
    conn: sqlite3.Connection,
    *,
    fingerprint: str,
    source_path: str,
    mtime: float,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO graph_capture_md_seen (fingerprint, source_path, mtime) VALUES (?, ?, ?)",
        (fingerprint, source_path, float(mtime)),
    )


def cmd_graph_capture_md(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    raw_paths = list(getattr(args, "path", []) or [])
    if not raw_paths:
        _emit({"error": "missing --path"}, True)
        sys.exit(2)

    includes = _graph_capture_md_includes(getattr(args, "include", None))
    excludes = _graph_capture_md_excludes(getattr(args, "exclude_glob", None))
    max_files = max(1, int(getattr(args, "max_files", 200) or 200))
    max_sections_per_file = max(1, int(getattr(args, "max_sections_per_file", 50) or 50))
    min_heading_level = max(1, int(getattr(args, "min_heading_level", 2) or 2))
    since_hours = max(0.0, float(getattr(args, "since_hours", 24) or 24))

    state_path = Path(
        os.path.expanduser(
            getattr(args, "state", None) or DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH
        )
    )

    state = _load_triage_state(state_path)
    if not isinstance(state, dict):
        state = {}
    files_state = state.get("files") if isinstance(state.get("files"), dict) else {}

    since_ts = datetime.now(timezone.utc).timestamp() - (since_hours * 3600.0)

    files, collect_errors = _graph_capture_md_collect_files(
        raw_paths,
        includes=includes,
        excludes=excludes,
        max_files=max_files,
    )

    totals = {
        "scanned_files": 0,
        "changed_files": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "errors": int(collect_errors),
    }

    per_path: List[Dict[str, Any]] = []
    for raw in raw_paths:
        p = Path(raw).expanduser().resolve()
        per_path.append(
            {
                "path": str(p),
                "scanned_files": 0,
                "changed_files": 0,
                "inserted": 0,
                "skipped_existing": 0,
                "errors": 0 if p.exists() else 1,
            }
        )

    git_root_cache: Dict[str, Optional[Path]] = {}
    file_to_group_idx: Dict[str, int] = {}
    for idx, item in enumerate(per_path):
        group_path = Path(item["path"])
        for fp in files:
            try:
                if fp == group_path or fp.is_relative_to(group_path):
                    file_to_group_idx[str(fp)] = idx
            except Exception:
                continue

    for fp in files:
        abs_path = str(fp.resolve())
        totals["scanned_files"] += 1

        group_idx = file_to_group_idx.get(abs_path)
        if group_idx is not None:
            per_path[group_idx]["scanned_files"] += 1

        try:
            st = fp.stat()
            mtime = float(st.st_mtime)
        except Exception:
            totals["errors"] += 1
            if group_idx is not None:
                per_path[group_idx]["errors"] += 1
            continue

        prev = files_state.get(abs_path) if isinstance(files_state.get(abs_path), dict) else None
        prev_mtime = None
        if isinstance(prev, dict) and isinstance(prev.get("mtime"), (int, float)):
            prev_mtime = float(prev.get("mtime"))

        if prev_mtime is None:
            should_scan = mtime >= since_ts
        else:
            should_scan = mtime > prev_mtime

        if not should_scan:
            continue

        totals["changed_files"] += 1
        if group_idx is not None:
            per_path[group_idx]["changed_files"] += 1

        try:
            text = fp.read_text(encoding="utf-8")
            raw_bytes = text.encode("utf-8")
            lines = text.splitlines()
            file_hash = hashlib.sha1(raw_bytes).hexdigest()

            sections = _graph_capture_md_parse_sections(
                text,
                min_heading_level=min_heading_level,
                max_sections=max_sections_per_file,
            )

            for sec in sections:
                heading = str(sec.get("heading") or "(untitled)")
                first_lines = _graph_capture_md_first_lines_for_fingerprint(
                    lines,
                    start_line=int(sec.get("start_line") or 1),
                    end_line=int(sec.get("end_line") or len(lines)),
                )
                material = "\n".join([heading, *first_lines])
                fingerprint = hashlib.sha1(material.encode("utf-8")).hexdigest()

                if _graph_capture_md_seen(conn, fingerprint):
                    totals["skipped_existing"] += 1
                    if group_idx is not None:
                        per_path[group_idx]["skipped_existing"] += 1
                    continue

                git_root = _graph_capture_md_git_root(fp, git_root_cache)
                rel_path = None
                if git_root is not None:
                    try:
                        rel_path = fp.resolve().relative_to(git_root).as_posix()
                    except Exception:
                        rel_path = None

                obs = {
                    "kind": "note",
                    "tool_name": "graph.capture-md",
                    "summary": _graph_capture_md_summary(fp, heading),
                    "detail": {
                        "source_path": abs_path,
                        "rel_path": rel_path,
                        "heading": heading,
                        "heading_level": int(sec.get("heading_level") or 0),
                        "start_line": int(sec.get("start_line") or 1),
                        "end_line": int(sec.get("end_line") or len(lines)),
                        "mtime": mtime,
                        "file_hash": file_hash,
                        "section_fingerprint": fingerprint,
                    },
                }
                _insert_observation(conn, obs)
                _graph_capture_md_mark_seen(
                    conn,
                    fingerprint=fingerprint,
                    source_path=abs_path,
                    mtime=mtime,
                )

                totals["inserted"] += 1
                if group_idx is not None:
                    per_path[group_idx]["inserted"] += 1

            files_state[abs_path] = {
                "mtime": mtime,
                "updated_at": _utcnow_iso(),
            }
        except Exception:
            totals["errors"] += 1
            if group_idx is not None:
                per_path[group_idx]["errors"] += 1

    conn.commit()

    state["files"] = files_state
    _atomic_write_json(state_path, state)

    payload = {
        "kind": "openclaw-mem.graph.capture-md.v0",
        "ts": _utcnow_iso(),
        "state_path": str(state_path),
        "since_hours": since_hours,
        "scanned_files": totals["scanned_files"],
        "changed_files": totals["changed_files"],
        "inserted": totals["inserted"],
        "skipped_existing": totals["skipped_existing"],
        "errors": totals["errors"],
    }

    if bool(args.json):
        payload["paths"] = per_path
        _emit(payload, True)
    else:
        print(
            " ".join(
                [
                    f"scanned_files={payload['scanned_files']}",
                    f"changed_files={payload['changed_files']}",
                    f"inserted={payload['inserted']}",
                    f"skipped_existing={payload['skipped_existing']}",
                    f"errors={payload['errors']}",
                ]
            )
        )

    if int(totals["errors"]) > 0:
        sys.exit(1)



def _graph_capture_git_default_since_iso(hours: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=max(0.0, float(hours)))
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _graph_capture_git_run_log(repo_path: Path, *, since_iso: str, max_commits: int) -> List[Dict[str, Any]]:
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "log",
        f"--since={since_iso}",
        f"--max-count={max(1, int(max_commits))}",
        "--date=iso-strict",
        "--pretty=format:%H%x1f%aI%x1f%s%x1e",
        "--name-only",
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "git log failed").strip())

    out: List[Dict[str, Any]] = []
    raw = p.stdout or ""
    for chunk in raw.split("\x1e"):
        part = chunk.strip("\n")
        if not part.strip():
            continue
        lines = part.splitlines()
        if not lines:
            continue
        header = lines[0]
        cols = header.split("\x1f", 2)
        if len(cols) < 3:
            continue
        sha, author_ts, subject = cols

        files: List[str] = []
        seen_files: set[str] = set()
        for f in lines[1:]:
            ff = f.strip()
            if not ff or ff in seen_files:
                continue
            seen_files.add(ff)
            files.append(ff)

        out.append(
            {
                "sha": sha.strip(),
                "author_ts": author_ts.strip(),
                "subject": subject.strip(),
                "files": files,
            }
        )

    return out

def _graph_capture_git_is_repo(path: Path) -> bool:
    p = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return p.returncode == 0 and (p.stdout or "").strip() == "true"


def _graph_capture_git_seen(conn: sqlite3.Connection, repo: str, sha: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM graph_capture_git_seen WHERE repo = ? AND sha = ? LIMIT 1",
        (repo, sha),
    ).fetchone()
    return row is not None


def _graph_capture_git_mark_seen(conn: sqlite3.Connection, repo: str, sha: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO graph_capture_git_seen (repo, sha, captured_at) VALUES (?, ?, ?)",
        (repo, sha, _utcnow_iso()),
    )


def _graph_capture_git_observation_exists(conn: sqlite3.Connection, repo: str, sha: str) -> bool:
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM observations
            WHERE tool_name = 'graph.capture-git'
              AND json_extract(detail_json, '$.repo') = ?
              AND json_extract(detail_json, '$.sha') = ?
            LIMIT 1
            """,
            (repo, sha),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT detail_json FROM observations WHERE tool_name = 'graph.capture-git'"
        ).fetchall()
        for r in rows:
            try:
                obj = json.loads(r["detail_json"] or "{}")
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            if str(obj.get("repo") or "") == repo and str(obj.get("sha") or "") == sha:
                return True
        return False


def cmd_graph_capture_git(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    repos = list(getattr(args, "repo", []) or [])
    if not repos:
        _emit({"error": "missing --repo"}, True)
        sys.exit(2)

    since_hours = max(0.0, float(getattr(args, "since", 24) or 24))
    max_commits = max(1, int(getattr(args, "max_commits", 50) or 50))
    state_path = Path(
        os.path.expanduser(
            getattr(args, "state", None) or DEFAULT_GRAPH_CAPTURE_STATE_PATH
        )
    )

    state = _load_triage_state(state_path)
    if not isinstance(state, dict):
        state = {}
    repos_state = state.get("repos") if isinstance(state.get("repos"), dict) else {}

    results: List[Dict[str, Any]] = []
    had_errors = False

    for repo_raw in repos:
        repo_path = Path(repo_raw).expanduser().resolve()
        repo_key = str(repo_path)
        repo_label = repo_path.name or repo_key

        summary = {
            "repo": repo_key,
            "inserted": 0,
            "skipped_existing": 0,
            "errors": 0,
        }

        if not repo_path.exists():
            summary["errors"] = 1
            had_errors = True
            results.append(summary)
            continue

        if not _graph_capture_git_is_repo(repo_path):
            summary["errors"] = 1
            had_errors = True
            results.append(summary)
            continue

        repo_prev = repos_state.get(repo_key) if isinstance(repos_state.get(repo_key), dict) else {}
        since_iso = str(repo_prev.get("last_author_ts") or _graph_capture_git_default_since_iso(since_hours))

        try:
            commits = _graph_capture_git_run_log(
                repo_path,
                since_iso=since_iso,
                max_commits=max_commits,
            )
        except Exception:
            summary["errors"] = 1
            had_errors = True
            results.append(summary)
            continue

        newest_author_ts = str(repo_prev.get("last_author_ts") or "")
        newest_sha = str(repo_prev.get("last_sha") or "")

        # Process old->new for deterministic accumulation.
        for c in reversed(commits):
            sha = str(c.get("sha") or "").strip()
            if not sha:
                continue
            author_ts = str(c.get("author_ts") or "").strip() or _utcnow_iso()
            subject = str(c.get("subject") or "").strip() or "(no subject)"
            files = list(c.get("files") or [])

            already_seen = _graph_capture_git_seen(conn, repo_key, sha)
            if not already_seen and _graph_capture_git_observation_exists(conn, repo_key, sha):
                _graph_capture_git_mark_seen(conn, repo_key, sha)
                already_seen = True

            if already_seen:
                summary["skipped_existing"] += 1
            else:
                obs = {
                    "ts": author_ts,
                    "kind": "note",
                    "tool_name": "graph.capture-git",
                    "summary": f"[GIT] {repo_label} {sha[:7]} {subject}",
                    "detail": {
                        "repo": repo_key,
                        "sha": sha,
                        "author_ts": author_ts,
                        "files": files,
                    },
                }
                _insert_observation(conn, obs)
                _graph_capture_git_mark_seen(conn, repo_key, sha)
                summary["inserted"] += 1

            if author_ts > newest_author_ts:
                newest_author_ts = author_ts
                newest_sha = sha

        repos_state[repo_key] = {
            "last_author_ts": newest_author_ts or since_iso,
            "last_sha": newest_sha,
            "updated_at": _utcnow_iso(),
        }

        conn.commit()
        results.append(summary)

    state["repos"] = repos_state
    _atomic_write_json(state_path, state)

    totals = {
        "inserted": sum(int(r["inserted"]) for r in results),
        "skipped_existing": sum(int(r["skipped_existing"]) for r in results),
        "errors": sum(int(r["errors"]) for r in results),
    }

    payload = {
        "kind": "openclaw-mem.graph.capture-git.v0",
        "ts": _utcnow_iso(),
        "state_path": str(state_path),
        "since_hours": since_hours,
        "max_commits": max_commits,
        "repos": results,
        "totals": totals,
    }

    if bool(args.json):
        _emit(payload, True)
    else:
        for r in results:
            print(
                f"{r['repo']}: inserted={r['inserted']} skipped_existing={r['skipped_existing']} errors={r['errors']}"
            )

    if had_errors:
        sys.exit(1)


def cmd_graph_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = (args.query or "").strip()
    to_path = (args.to or "").strip()
    scope = (getattr(args, "scope", None) or "").strip() or None

    if not query:
        _emit({"error": "empty query"}, True)
        sys.exit(2)
    if not to_path:
        _emit({"error": "missing --to"}, True)
        sys.exit(2)

    limit = max(1, int(getattr(args, "limit", 12)))
    window = max(0, int(getattr(args, "window", 2)))

    rows = _graph_search_rows(conn, query, limit, scope=scope)
    cand_ids = [int(r["id"]) for r in rows]
    scope_norm = _normalize_scope_token(scope)

    nodes: Dict[int, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def add_node(oid: int) -> None:
        if oid in nodes:
            return
        r = conn.execute(
            "SELECT id, ts, kind, tool_name, summary FROM observations WHERE id=?",
            (oid,),
        ).fetchone()
        if not r:
            return
        nodes[oid] = {
            "id": _graph_record_ref(oid),
            "type": "observation",
            "project": scope,
            "title": (r["summary"] or "").replace("\n", " ").strip()[:180],
            "provenance": {"ts": r["ts"], "kind": r["kind"], "tool_name": r["tool_name"]},
        }

    for oid in cand_ids:
        add_node(oid)

    if window and cand_ids:
        for oid in cand_ids:
            lo, hi = oid - window, oid + window
            nrows = conn.execute(
                "SELECT id, detail_json FROM observations WHERE id BETWEEN ? AND ? ORDER BY id",
                (lo, hi),
            ).fetchall()
            for nr in nrows:
                nid = int(nr["id"])
                if scope_norm:
                    detail = _pack_parse_detail_json(nr["detail_json"])
                    row_scope = _normalize_scope_token(detail.get("scope"))
                    if row_scope != scope_norm:
                        continue
                add_node(nid)
                if nid == oid:
                    continue
                edges.append(
                    {
                        "src": _graph_record_ref(oid),
                        "dst": _graph_record_ref(nid),
                        "type": "timeline_adjacent",
                        "provenance": {"window": window},
                    }
                )

    graph = {
        "kind": "openclaw-mem.graph.export.v0",
        "ts": _utcnow_iso(),
        "query": {"text": query, "scope": scope},
        "nodes": list(nodes.values()),
        "edges": edges,
    }

    out_path = Path(to_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload = {"ok": True, "to": str(out_path), "nodes": len(graph["nodes"]), "edges": len(edges)}
    _emit(payload, bool(args.json))


def cmd_graph_query(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    _ = conn
    query_cmd = str(getattr(args, "graph_query_cmd", "") or "").strip().lower()
    db_path = str(getattr(args, "db", "") or "").strip()

    if not db_path:
        _emit({"error": "missing --db"}, True)
        sys.exit(2)

    try:
        if query_cmd == "upstream":
            result = query_upstream(db_path=db_path, node_id=getattr(args, "node_id", None))
        elif query_cmd == "downstream":
            result = query_downstream(db_path=db_path, node_id=getattr(args, "node_id", None))
        elif query_cmd == "lineage":
            result = query_lineage(
                db_path=db_path,
                node_id=getattr(args, "node_id", None),
                max_depth=getattr(args, "max_depth", 1),
            )
        elif query_cmd == "writers":
            result = query_writers(db_path=db_path, artifact_id=getattr(args, "artifact_id", None))
        elif query_cmd == "filter":
            result = query_filter_nodes(
                db_path=db_path,
                tag=getattr(args, "tag", None),
                not_tag=getattr(args, "not_tag", None),
                node_type=getattr(args, "node_type", None),
            )
        elif query_cmd == "receipts":
            result = query_refresh_receipts(
                db_path=db_path,
                limit=getattr(args, "limit", 10),
                source_path=getattr(args, "source_path", None),
                topology_digest=getattr(args, "topology_digest", None),
            )
        elif query_cmd == "provenance":
            result = query_provenance(
                db_path=db_path,
                node_id=getattr(args, "node_id", None),
                edge_type=getattr(args, "edge_type", None),
                source_path=getattr(args, "source_path", None),
                source_path_prefix=getattr(args, "source_path_prefix", None),
                limit=getattr(args, "limit", 20),
                min_edge_count=getattr(args, "min_edge_count", 1),
                group_by_source=bool(getattr(args, "group_by_source", False)),
            )
        elif query_cmd == "subgraph":
            result = query_subgraph(
                db_path=db_path,
                node_id=getattr(args, "node_id", None),
                hops=getattr(args, "hops", 2),
                direction=getattr(args, "direction", "both"),
                max_nodes=getattr(args, "max_nodes", 40),
                max_edges=getattr(args, "max_edges", 80),
                edge_types=getattr(args, "edge_type", None),
                include_node_types=getattr(args, "include_node_type", None),
            )
        elif query_cmd == "drift":
            result = query_drift(
                db_path=db_path,
                live_json_path=getattr(args, "live_json", None),
                limit=getattr(args, "limit", 50),
            )
        else:
            raise ValueError(f"unsupported graph query command: {query_cmd}")
    except ValueError as e:
        _emit({"error": str(e)}, True)
        sys.exit(2)
    except sqlite3.OperationalError as e:
        _emit({"error": str(e)}, True)
        sys.exit(1)

    payload = {
        "kind": "openclaw-mem.graph.query.v0",
        "ts": _utcnow_iso(),
        "query_cmd": query_cmd,
        "result": result,
    }

    if bool(args.json):
        _emit(payload, True)
        return

    if query_cmd == "subgraph":
        text = str(result.get("bundle_text") or "").rstrip()
        if text:
            print(text)
        else:
            print(f"nodes={int(result.get('node_count', 0))} edges={int(result.get('edge_count', 0))}")
        return

    if query_cmd == "filter":
        print(f"count={int(result.get('count', 0))}")
        for node in list(result.get("nodes") or []):
            print(f"{node.get('id')} type={node.get('type')} tags={','.join(node.get('tags') or [])}")
        return

    if query_cmd == "receipts":
        receipts = list(result.get("receipts") or [])
        print(
            f"count={int(result.get('count', 0))} "
            f"total_count={int(result.get('total_count', 0))}"
        )
        for receipt in receipts:
            print(
                f"id={receipt.get('id')} refreshed_at={receipt.get('refreshed_at')} "
                f"nodes={receipt.get('node_count')} edges={receipt.get('edge_count')} "
                f"source={receipt.get('source_path')}"
            )
        return

    if query_cmd == "provenance":
        print(
            f"count={int(result.get('count', 0))} "
            f"total_distinct={int(result.get('total_distinct', 0))}"
        )
        for item in list(result.get("items") or []):
            edge_types = list(item.get("edge_types") or [])
            if edge_types:
                edge_types_summary = ",".join(
                    f"{str(edge.get('edge_type'))}:{int(edge.get('edge_count', 0))}"
                    for edge in edge_types
                )
            else:
                edge_types_summary = ""
            line = f"{item.get('provenance')} edges={item.get('edge_count')}"
            if edge_types_summary:
                line += f" edge_types={edge_types_summary}"
            print(line)
        return

    if query_cmd == "drift":
        print(
            f"topology_nodes={int(result.get('topology_node_count', 0))} "
            f"runtime_nodes={int(result.get('runtime_node_count', 0))}"
        )
        missing = result.get("missing_in_runtime") or {}
        runtime_only = result.get("runtime_only") or {}
        non_ok = result.get("non_ok_nodes") or {}
        print(f"missing_in_runtime={int(missing.get('count', 0))}")
        print(f"runtime_only={int(runtime_only.get('count', 0))}")
        print(f"non_ok_nodes={int(non_ok.get('count', 0))}")
        for item in list(non_ok.get("items") or []):
            print(f"non_ok:{item.get('node_id')} status={item.get('status')}")
        return

    edges = list(result.get("edges") or [])
    if query_cmd == "lineage":
        upstream = list(result.get("upstream") or [])
        downstream = list(result.get("downstream") or [])
        print(f"upstream_count={len(upstream)} downstream_count={len(downstream)}")
        for edge in upstream:
            print(f"UP {edge.get('src')} --{edge.get('type')}--> {edge.get('dst')}")
        for edge in downstream:
            print(f"DOWN {edge.get('src')} --{edge.get('type')}--> {edge.get('dst')}")
        return

    print(f"count={int(result.get('count', 0))}")
    for edge in edges:
        print(f"{edge.get('src')} --{edge.get('type')}--> {edge.get('dst')}")


def cmd_episodes_append(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    try:
        event_type = _normalize_episodic_type(getattr(args, "type", None))
        scope = _normalize_episodic_scope(getattr(args, "scope", None))
        ts_ms = _parse_ts_ms(getattr(args, "ts_ms", None))

        session_id = str(getattr(args, "session_id", "") or "").strip()
        agent_id = str(getattr(args, "agent_id", "") or "").strip()
        summary = _sanitize_str_surrogates(str(getattr(args, "summary", "") or "").strip())
        if not session_id:
            raise ValueError("session_id is required")
        if not agent_id:
            raise ValueError("agent_id is required")
        if not summary:
            raise ValueError("summary is required")

        payload_cap = int(getattr(args, "payload_cap_bytes", EPISODIC_DEFAULT_PAYLOAD_CAP_BYTES))
        refs_cap = int(getattr(args, "refs_cap_bytes", EPISODIC_DEFAULT_REFS_CAP_BYTES))
        if payload_cap <= 0 or refs_cap <= 0:
            raise ValueError("payload/refs caps must be > 0")

        payload_obj, payload_serialized, payload_size = _parse_optional_json_arg(
            getattr(args, "payload_json", None),
            getattr(args, "payload_file", None),
            "payload",
        )
        refs_obj, refs_serialized, refs_size = _parse_optional_json_arg(
            getattr(args, "refs_json", None),
            getattr(args, "refs_file", None),
            "refs",
        )

        if payload_size > payload_cap:
            raise ValueError(f"payload exceeds cap ({payload_size} > {payload_cap} bytes)")
        if refs_size > refs_cap:
            raise ValueError(f"refs exceeds cap ({refs_size} > {refs_cap} bytes)")

        _episodic_guard_text_fragments(
            summary,
            payload_serialized,
            refs_serialized,
            bool(getattr(args, "allow_tool_output", False)),
        )

        event_id_raw = str(getattr(args, "event_id", "") or "").strip()
        event_id = event_id_raw or str(uuid.uuid4())

        created_at = _utcnow_iso()
        conn.execute(
            """
            INSERT INTO episodic_events (
                event_id, ts_ms, scope, session_id, agent_id, type, summary,
                payload_json, refs_json, redacted, schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                event_id,
                ts_ms,
                scope,
                session_id,
                agent_id,
                event_type,
                summary,
                payload_serialized,
                refs_serialized,
                EPISODIC_SCHEMA_VERSION,
                created_at,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        _emit({
            "kind": "openclaw-mem.episodes.append.v0",
            "ok": False,
            "error": "event_id already exists",
            "detail": str(e),
        }, True)
        sys.exit(1)
    except ValueError as e:
        _emit({
            "kind": "openclaw-mem.episodes.append.v0",
            "ok": False,
            "error": str(e),
        }, True)
        sys.exit(2)

    out = {
        "kind": "openclaw-mem.episodes.append.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "event": {
            "event_id": event_id,
            "ts_ms": ts_ms,
            "scope": scope,
            "session_id": session_id,
            "agent_id": agent_id,
            "type": event_type,
            "summary": summary,
            "payload_bytes": payload_size,
            "refs_bytes": refs_size,
            "schema_version": EPISODIC_SCHEMA_VERSION,
            "redacted": False,
            "payload_present": payload_obj is not None,
            "refs_present": refs_obj is not None,
        },
        "caps": {
            "payload_cap_bytes": payload_cap,
            "refs_cap_bytes": refs_cap,
        },
    }
    _emit(out, args.json)


def _episodes_query_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    session_id: Optional[str],
    from_ts_ms: Optional[int],
    to_ts_ms: Optional[int],
    types_filter: Optional[List[str]],
    limit: int,
) -> List[sqlite3.Row]:
    clauses = ["scope = ?"]
    params: List[Any] = [scope]

    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if from_ts_ms is not None:
        clauses.append("ts_ms >= ?")
        params.append(int(from_ts_ms))
    if to_ts_ms is not None:
        clauses.append("ts_ms <= ?")
        params.append(int(to_ts_ms))
    if types_filter:
        placeholders = ",".join(["?"] * len(types_filter))
        clauses.append(f"type IN ({placeholders})")
        params.extend(types_filter)

    sql = (
        "SELECT id, event_id, ts_ms, scope, session_id, agent_id, type, summary, payload_json, refs_json, redacted, schema_version, created_at "
        "FROM episodic_events "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY ts_ms ASC, id ASC "
        "LIMIT ?"
    )
    params.append(int(limit))
    return conn.execute(sql, params).fetchall()


def cmd_episodes_query(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    try:
        scope = _resolve_query_scope(getattr(args, "scope", None), bool(getattr(args, "global_scope", False)))
        session_id = str(getattr(args, "session_id", "") or "").strip() or None
        from_ts_ms = None
        to_ts_ms = None
        if getattr(args, "from_ts_ms", None) is not None:
            from_ts_ms = _parse_ts_ms(getattr(args, "from_ts_ms"))
        if getattr(args, "to_ts_ms", None) is not None:
            to_ts_ms = _parse_ts_ms(getattr(args, "to_ts_ms"))
        if from_ts_ms is not None and to_ts_ms is not None and from_ts_ms > to_ts_ms:
            raise ValueError("from_ts_ms cannot be greater than to_ts_ms")

        types_filter = _normalize_types_filter(getattr(args, "types", None))
        limit = int(getattr(args, "limit", 50))
        limit = max(1, min(EPISODIC_MAX_QUERY_LIMIT, limit))
        include_payload = bool(getattr(args, "include_payload", False))
    except ValueError as e:
        _emit(
            {
                "kind": "openclaw-mem.episodes.query.v0",
                "ok": False,
                "error": str(e),
            },
            True,
        )
        sys.exit(2)

    rows = _episodes_query_rows(
        conn,
        scope=scope,
        session_id=session_id,
        from_ts_ms=from_ts_ms,
        to_ts_ms=to_ts_ms,
        types_filter=types_filter,
        limit=limit,
    )

    items = [_episodes_row_to_item(r, include_payload=include_payload) for r in rows]
    out = {
        "kind": "openclaw-mem.episodes.query.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "scope": scope,
        "filters": {
            "session_id": session_id,
            "from_ts_ms": from_ts_ms,
            "to_ts_ms": to_ts_ms,
            "types": types_filter or [],
            "limit": limit,
            "include_payload": include_payload,
        },
        "count": len(items),
        "items": items,
    }
    _emit(out, args.json)


def cmd_episodes_replay(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    try:
        scope = _resolve_query_scope(getattr(args, "scope", None), bool(getattr(args, "global_scope", False)))
        session_id = str(getattr(args, "session_id", "") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")

        limit = int(getattr(args, "limit", 200))
        limit = max(1, min(EPISODIC_MAX_QUERY_LIMIT, limit))
        include_payload = bool(getattr(args, "include_payload", False))
    except ValueError as e:
        _emit(
            {
                "kind": "openclaw-mem.episodes.replay.v0",
                "ok": False,
                "error": str(e),
            },
            True,
        )
        sys.exit(2)

    rows = _episodes_query_rows(
        conn,
        scope=scope,
        session_id=session_id,
        from_ts_ms=None,
        to_ts_ms=None,
        types_filter=None,
        limit=limit,
    )
    items = [_episodes_row_to_item(r, include_payload=include_payload) for r in rows]

    out = {
        "kind": "openclaw-mem.episodes.replay.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "scope": scope,
        "session_id": session_id,
        "count": len(items),
        "limit": limit,
        "include_payload": include_payload,
        "items": items,
    }
    _emit(out, args.json)


def _extract_text_blocks(content: Any) -> List[str]:
    out: List[str] = []
    if isinstance(content, str):
        text = _sanitize_str_surrogates(content).strip()
        if text:
            out.append(text)
        return out

    if not isinstance(content, list):
        return out

    for block in content:
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "").strip().lower() != "text":
            continue
        text = _sanitize_str_surrogates(str(block.get("text") or "")).strip()
        if text:
            out.append(text)
    return out


def _extract_role_text_from_session_line(obj: Dict[str, Any]) -> Tuple[Optional[str], str]:
    candidates: List[Dict[str, Any]] = []
    if isinstance(obj.get("message"), dict):
        candidates.append(obj["message"])
    candidates.append(obj)

    for cand in candidates:
        role = str(cand.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue

        texts = _extract_text_blocks(cand.get("content"))
        if not texts and isinstance(cand.get("text"), str):
            raw = _sanitize_str_surrogates(str(cand.get("text") or "")).strip()
            if raw:
                texts = [raw]

        merged = "\n".join(t for t in texts if t.strip()).strip()
        if merged:
            return role, merged

    return None, ""


def cmd_episodes_extract_sessions(_conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    sessions_root = Path(
        str(getattr(args, "sessions_root", None) or DEFAULT_OPENCLAW_SESSIONS_ROOT)
    ).expanduser().resolve()
    spool_path = Path(str(getattr(args, "file", None) or DEFAULT_EPISODIC_SPOOL_PATH)).expanduser().resolve()
    state_path = Path(
        str(getattr(args, "state", None) or DEFAULT_EPISODIC_EXTRACT_STATE_PATH)
    ).expanduser().resolve()

    summary_max = max(40, min(400, int(getattr(args, "summary_max_chars", 220) or 220)))
    payload_cap = int(
        getattr(
            args,
            "payload_cap_bytes",
            EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES,
        )
        or EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES
    )
    payload_cap = min(max(256, payload_cap), EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES)

    if not sessions_root.exists() or not sessions_root.is_dir():
        _emit(
            {
                "kind": "openclaw-mem.episodes.extract-sessions.v0",
                "ok": False,
                "error": f"sessions root not found: {sessions_root}",
            },
            True,
        )
        sys.exit(2)

    try:
        state = _read_json_file(state_path)
    except ValueError as e:
        _emit({"kind": "openclaw-mem.episodes.extract-sessions.v0", "ok": False, "error": str(e)}, True)
        sys.exit(2)

    files_state = state.get("files") if isinstance(state.get("files"), dict) else {}
    files = sorted([p for p in sessions_root.rglob("*.jsonl") if p.is_file()], key=lambda p: str(p))

    spool_path.parent.mkdir(parents=True, exist_ok=True)
    new_files_state: Dict[str, Any] = dict(files_state)

    files_seen = 0
    files_with_updates = 0
    lines_total = 0
    invalid_json = 0
    unsupported_rows = 0
    emitted = 0
    payload_redacted = 0
    payload_truncated = 0
    trailing_partial_bytes = 0
    errors_sample: List[str] = []

    lock_path = _episodic_lock_path(spool_path)
    with _episodic_flock(lock_path, exclusive=False, timeout_s=30), spool_path.open("a", encoding="utf-8") as spool_fp:
        for fp in files:
            files_seen += 1
            key = str(fp)
            stat = fp.stat()

            file_state = files_state.get(key) if isinstance(files_state.get(key), dict) else {}
            prev_offset = int(file_state.get("offset") or 0)
            prev_inode = int(file_state.get("inode") or 0)

            if prev_offset < 0:
                prev_offset = 0

            if prev_inode and prev_inode != int(stat.st_ino):
                prev_offset = 0
            if prev_offset > int(stat.st_size):
                prev_offset = 0

            with fp.open("rb") as in_fp:
                in_fp.seek(prev_offset)
                blob = in_fp.read(max(0, int(stat.st_size) - prev_offset))

            if not blob:
                new_files_state[key] = {
                    "offset": prev_offset,
                    "inode": int(stat.st_ino),
                    "size": int(stat.st_size),
                    "updated_at": _utcnow_iso(),
                }
                continue

            last_newline = blob.rfind(b"\n")
            if last_newline < 0:
                processed_blob = b""
                next_offset = prev_offset
                trailing_partial_bytes += len(blob)
            else:
                processed_blob = blob[: last_newline + 1]
                trailing_partial_bytes += len(blob) - len(processed_blob)
                next_offset = prev_offset + len(processed_blob)

            if not processed_blob:
                new_files_state[key] = {
                    "offset": next_offset,
                    "inode": int(stat.st_ino),
                    "size": int(stat.st_size),
                    "updated_at": _utcnow_iso(),
                }
                continue

            files_with_updates += 1
            cursor = prev_offset

            for raw_line in processed_blob.splitlines(keepends=True):
                line_start = cursor
                cursor += len(raw_line)

                line = raw_line.rstrip(b"\r\n")
                if not line.strip():
                    continue

                lines_total += 1
                try:
                    obj = json.loads(line.decode("utf-8"))
                    if not isinstance(obj, dict):
                        raise ValueError("json_not_object")
                except Exception:
                    invalid_json += 1
                    if len(errors_sample) < 5:
                        errors_sample.append(f"{fp}:{line_start}:invalid_json")
                    continue

                role, text = _extract_role_text_from_session_line(obj)
                if role not in {"user", "assistant"} or not text:
                    unsupported_rows += 1
                    continue

                scope_from_tag, stripped = _split_scope_prefixed_text(text)
                scope = _normalize_episodic_scope(scope_from_tag or "global")

                original_text = stripped or text
                clean_text = _redact_pii_lite(original_text)
                secret_like = _looks_like_secret(clean_text)
                tool_dump_like = _looks_like_tool_output(clean_text)

                event_type = "conversation.user" if role == "user" else "conversation.assistant"

                summary_text = clean_text
                payload_obj = None
                event_redacted = False
                payload_was_truncated = False

                if secret_like:
                    summary_text = "[REDACTED_SECRET]"
                    event_redacted = True
                elif tool_dump_like:
                    summary_text = "[REDACTED_TOOL_DUMP]"
                    event_redacted = True
                else:
                    payload_json, _payload_bytes, payload_was_truncated = _episodic_bounded_json(
                        {"text": clean_text},
                        cap_bytes=payload_cap,
                        label="payload",
                        max_string_chars=payload_cap,
                    )
                    payload_obj = json.loads(payload_json) if payload_json else None

                if payload_was_truncated:
                    payload_truncated += 1

                short = summary_text.replace("\n", " ").strip()
                if len(short) > summary_max:
                    short = short[:summary_max] + "…"
                summary = f"{event_type}: {short}" if short else event_type

                raw_ts = obj.get("ts_ms") or obj.get("timestamp_ms") or obj.get("tsMs")
                if raw_ts is None:
                    raw_ts = obj.get("timestamp") or obj.get("ts")
                try:
                    ts_ms = _parse_ts_ms(raw_ts)
                except Exception:
                    try:
                        ts_ms = int(datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00")).timestamp() * 1000)
                    except Exception:
                        ts_ms = _utcnow_ts_ms()

                event_id = f"ep-{hashlib.sha256(f'{key}:{line_start}:{event_type}:{clean_text}'.encode('utf-8')).hexdigest()[:32]}"
                if event_redacted:
                    payload_redacted += 1

                spool_event = {
                    "schema": EPISODIC_SPOOL_SCHEMA,
                    "event_id": event_id,
                    "ts_ms": ts_ms,
                    "scope": scope,
                    "session_id": _sanitize_str_surrogates(str(obj.get("sessionKey") or obj.get("session_id") or obj.get("session") or fp.stem)),
                    "agent_id": _sanitize_str_surrogates(str(obj.get("agentId") or obj.get("agent_id") or "main")),
                    "type": event_type,
                    "summary": summary,
                    "payload": payload_obj,
                    "redacted": event_redacted,
                    "refs": {
                        "source": "session_jsonl_tail",
                        "path": key,
                        "offset": int(line_start),
                    },
                }
                spool_fp.write(json.dumps(spool_event, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
                emitted += 1

            new_files_state[key] = {
                "offset": int(next_offset),
                "inode": int(stat.st_ino),
                "size": int(stat.st_size),
                "updated_at": _utcnow_iso(),
            }

    out_state = {
        "schema": EPISODIC_EXTRACT_STATE_SCHEMA,
        "sessions_root": str(sessions_root),
        "files": new_files_state,
        "updated_at": _utcnow_iso(),
    }
    _write_json_file_atomic(state_path, out_state)

    out = {
        "kind": "openclaw-mem.episodes.extract-sessions.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "source": {
            "sessions_root": str(sessions_root),
            "state": str(state_path),
            "spool": str(spool_path),
        },
        "files_seen": files_seen,
        "files_with_updates": files_with_updates,
        "lines_total": lines_total,
        "invalid_json": invalid_json,
        "unsupported_rows": unsupported_rows,
        "emitted": emitted,
        "payload_redacted": payload_redacted,
        "payload_truncated": payload_truncated,
        "trailing_partial_bytes": trailing_partial_bytes,
        "payload_cap_bytes": payload_cap,
        "errors_sample": errors_sample,
    }
    _emit(out, args.json)


def _episodic_state_int(raw: Any) -> Optional[int]:
    try:
        if raw is None:
            return None
        return int(raw)
    except Exception:
        return None


def _episodes_ingest_once(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
    state_path: Path,
    payload_cap: int,
    conversation_payload_cap: int,
    refs_cap: int,
    truncate_after: bool,
    rotate_after: bool,
    allow_missing_source: bool = False,
) -> Optional[Dict[str, Any]]:
    if not source_path.exists() or not source_path.is_file():
        if allow_missing_source:
            return None
        raise FileNotFoundError(f"source file not found: {source_path}")

    try:
        source_stat = source_path.stat()
    except FileNotFoundError:
        if allow_missing_source:
            return None
        raise FileNotFoundError(f"source file not found: {source_path}")
    except Exception as e:
        raise RuntimeError(f"failed to stat source file: {source_path}: {str(e)}") from e

    state = _read_json_file(state_path)

    prev_offset = _episodic_state_int(state.get("offset")) or 0
    prev_offset = max(0, prev_offset)
    prev_dev = _episodic_state_int(state.get("dev"))
    prev_inode = _episodic_state_int(state.get("inode"))
    prev_size = _episodic_state_int(state.get("size"))

    offset_recovery = None
    current_dev = int(source_stat.st_dev)
    current_inode = int(source_stat.st_ino)
    current_size = int(source_stat.st_size)

    if prev_dev is not None and prev_inode is not None and (prev_dev != current_dev or prev_inode != current_inode):
        offset_recovery = "reset_to_zero_source_replaced"
        prev_offset = 0
    elif prev_size is not None and prev_size > current_size:
        offset_recovery = "reset_to_zero_source_shrunk"
        prev_offset = 0
    elif prev_offset > current_size:
        offset_recovery = "reset_to_zero_source_shrunk"
        prev_offset = 0

    try:
        with source_path.open("rb") as fp:
            fp.seek(prev_offset)
            unread = max(0, current_size - prev_offset)
            blob = fp.read(unread)
    except FileNotFoundError:
        if allow_missing_source:
            return None
        raise FileNotFoundError(f"source file not found: {source_path}")

    last_newline = blob.rfind(b"\n")
    if last_newline < 0:
        processed_blob = b""
        next_offset = prev_offset
        trailing_partial_bytes = len(blob)
    else:
        processed_blob = blob[: last_newline + 1]
        trailing_partial_bytes = len(blob) - len(processed_blob)
        next_offset = prev_offset + len(processed_blob)

    line_total = 0
    line_blank = 0
    line_invalid_json = 0
    line_invalid_event = 0
    duplicates = 0
    inserted = 0
    payload_truncated_count = 0
    refs_truncated_count = 0
    late_redacted_count = 0
    errors_sample: List[str] = []

    cursor = prev_offset
    now_iso = _utcnow_iso()

    for raw_line in processed_blob.splitlines(keepends=True):
        line_start = cursor
        cursor += len(raw_line)

        line = raw_line.rstrip(b"\r\n")
        if not line.strip():
            line_blank += 1
            continue

        line_total += 1

        try:
            line_text = line.decode("utf-8")
            line_obj = json.loads(line_text)
            if not isinstance(line_obj, dict):
                raise ValueError("line is not a JSON object")
        except Exception:
            line_invalid_json += 1
            if len(errors_sample) < 5:
                errors_sample.append(f"line@{line_start}: invalid_json")
            continue

        try:
            fallback_seed = f"{line_start}:".encode("utf-8") + line
            fallback_event_id = f"ep-{hashlib.sha256(fallback_seed).hexdigest()[:32]}"
            event = _normalize_episodic_spool_event(
                line_obj,
                fallback_event_id=fallback_event_id,
                payload_cap=payload_cap,
                conversation_payload_cap=conversation_payload_cap,
                refs_cap=refs_cap,
            )
        except ValueError as e:
            line_invalid_event += 1
            if len(errors_sample) < 5:
                errors_sample.append(f"line@{line_start}: {str(e)}")
            continue

        try:
            conn.execute(
                """
                INSERT INTO episodic_events (
                    event_id, ts_ms, scope, session_id, agent_id, type, summary,
                    payload_json, refs_json, redacted, schema_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["ts_ms"],
                    event["scope"],
                    event["session_id"],
                    event["agent_id"],
                    event["type"],
                    event["summary"],
                    event["payload_json"],
                    event["refs_json"],
                    1 if bool(event.get("redacted")) else 0,
                    EPISODIC_SCHEMA_VERSION,
                    now_iso,
                ),
            )
            inserted += 1
            if bool(event.get("payload_truncated")):
                payload_truncated_count += 1
            if bool(event.get("refs_truncated")):
                refs_truncated_count += 1
            if bool(event.get("redacted")):
                late_redacted_count += 1
        except sqlite3.IntegrityError:
            duplicates += 1

    conn.commit()

    maintenance: Dict[str, Any] = {
        "requested": "truncate" if truncate_after else "rotate" if rotate_after else "none",
        "applied": "none",
        "reason": None,
        "rotated_to": None,
    }

    if truncate_after or rotate_after:
        if next_offset != current_size:
            maintenance["reason"] = "pending_partial_line"
        else:
            try:
                latest_stat = source_path.stat()
            except FileNotFoundError:
                latest_stat = None
            if latest_stat is None or int(latest_stat.st_size) != current_size or int(latest_stat.st_ino) != current_inode:
                maintenance["reason"] = "source_changed_since_snapshot"
            else:
                if truncate_after:
                    source_path.parent.mkdir(parents=True, exist_ok=True)
                    with source_path.open("w", encoding="utf-8"):
                        pass
                    maintenance["applied"] = "truncated"
                    next_offset = 0
                elif rotate_after:
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    rotated_path = source_path.with_name(f"{source_path.name}.{stamp}.ingested")
                    suffix = 1
                    while rotated_path.exists():
                        suffix += 1
                        rotated_path = source_path.with_name(f"{source_path.name}.{stamp}.ingested.{suffix}")
                    source_path.rename(rotated_path)
                    source_path.touch()
                    maintenance["applied"] = "rotated"
                    maintenance["rotated_to"] = str(rotated_path)
                    next_offset = 0

    try:
        final_stat = source_path.stat()
    except FileNotFoundError:
        if not allow_missing_source:
            raise
        final_stat = source_stat
    state_payload = {
        "schema": EPISODIC_INGEST_STATE_SCHEMA,
        "file": str(source_path),
        "offset": int(next_offset),
        "dev": int(final_stat.st_dev),
        "inode": int(final_stat.st_ino),
        "size": int(final_stat.st_size),
        "updated_at": _utcnow_iso(),
    }
    _write_json_file_atomic(state_path, state_payload)

    out = {
        "kind": "openclaw-mem.episodes.ingest.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "source": {
            "file": str(source_path),
            "state": str(state_path),
            "start_offset": prev_offset,
            "next_offset": int(next_offset),
            "snapshot_size": current_size,
            "offset_recovery": offset_recovery,
            "trailing_partial_bytes": trailing_partial_bytes,
            "processed_sha256": hashlib.sha256(processed_blob).hexdigest() if processed_blob else None,
            "spool_schema": EPISODIC_SPOOL_SCHEMA,
        },
        "lines": {
            "total": line_total,
            "blank": line_blank,
            "invalid_json": line_invalid_json,
            "invalid_event": line_invalid_event,
            "duplicates": duplicates,
        },
        "inserted": inserted,
        "bounded": {
            "payload_cap_bytes": payload_cap,
            "conversation_payload_cap_bytes": conversation_payload_cap,
            "payload_hard_cap_bytes": EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES,
            "refs_cap_bytes": refs_cap,
            "payload_truncated": payload_truncated_count,
            "refs_truncated": refs_truncated_count,
            "redacted_late": late_redacted_count,
        },
        "maintenance": maintenance,
        "errors_sample": errors_sample,
    }
    return out


def cmd_episodes_ingest(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    source_path = Path(str(getattr(args, "file", "") or "")).expanduser().resolve()
    state_path = Path(
        str(getattr(args, "state", None) or DEFAULT_EPISODIC_INGEST_STATE_PATH)
    ).expanduser().resolve()

    truncate_after = bool(getattr(args, "truncate", False))
    rotate_after = bool(getattr(args, "rotate", False))
    follow = bool(getattr(args, "follow", False))

    try:
        payload_cap = int(getattr(args, "payload_cap_bytes", EPISODIC_DEFAULT_PAYLOAD_CAP_BYTES))
        conversation_payload_cap = int(
            getattr(
                args,
                "conversation_payload_cap_bytes",
                EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES,
            )
        )
        refs_cap = int(getattr(args, "refs_cap_bytes", EPISODIC_DEFAULT_REFS_CAP_BYTES))
        poll_interval_ms = int(
            getattr(args, "poll_interval_ms", EPISODIC_FOLLOW_DEFAULT_POLL_INTERVAL_MS)
        )
        idle_exit_seconds = float(getattr(args, "idle_exit_seconds", 0.0) or 0.0)
        rotate_on_idle_seconds = float(
            getattr(args, "rotate_on_idle_seconds", EPISODIC_FOLLOW_DEFAULT_ROTATE_ON_IDLE_SECONDS)
            or 0.0
        )
        rotate_min_bytes = int(
            getattr(args, "rotate_min_bytes", EPISODIC_FOLLOW_DEFAULT_ROTATE_MIN_BYTES)
            or EPISODIC_FOLLOW_DEFAULT_ROTATE_MIN_BYTES
        )

        if payload_cap <= 0 or conversation_payload_cap <= 0 or refs_cap <= 0:
            raise ValueError("payload/refs caps must be > 0")
        payload_cap = min(payload_cap, EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES)
        conversation_payload_cap = min(
            conversation_payload_cap,
            EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES,
        )
        if truncate_after and rotate_after:
            raise ValueError("--truncate and --rotate are mutually exclusive")
        if follow and (truncate_after or rotate_after):
            raise ValueError("--follow cannot be combined with --truncate or --rotate")
        if follow and poll_interval_ms < EPISODIC_FOLLOW_MIN_POLL_INTERVAL_MS:
            raise ValueError(
                f"--poll-interval-ms must be >= {EPISODIC_FOLLOW_MIN_POLL_INTERVAL_MS}"
            )
        if idle_exit_seconds < 0:
            raise ValueError("--idle-exit-seconds must be >= 0")
        if rotate_on_idle_seconds < 0:
            raise ValueError("--rotate-on-idle-seconds must be >= 0")
        if rotate_min_bytes <= 0:
            raise ValueError("--rotate-min-bytes must be > 0")
        if rotate_on_idle_seconds > 0 and not follow:
            raise ValueError("--rotate-on-idle-seconds requires --follow")
        if rotate_on_idle_seconds > 0:
            try:
                import fcntl  # noqa: F401
            except Exception:
                raise ValueError("--rotate-on-idle-seconds requires POSIX fcntl/flock")
    except ValueError as e:
        _emit({"kind": "openclaw-mem.episodes.ingest.v0", "ok": False, "error": str(e)}, True)
        sys.exit(2)

    if not follow:
        try:
            out = _episodes_ingest_once(
                conn,
                source_path=source_path,
                state_path=state_path,
                payload_cap=payload_cap,
                conversation_payload_cap=conversation_payload_cap,
                refs_cap=refs_cap,
                truncate_after=truncate_after,
                rotate_after=rotate_after,
                allow_missing_source=False,
            )
            assert out is not None
        except FileNotFoundError as e:
            _emit(
                {
                    "kind": "openclaw-mem.episodes.ingest.v0",
                    "ok": False,
                    "error": str(e),
                },
                True,
            )
            sys.exit(2)
        except ValueError as e:
            _emit({"kind": "openclaw-mem.episodes.ingest.v0", "ok": False, "error": str(e)}, True)
            sys.exit(2)
        except RuntimeError as e:
            _emit(
                {
                    "kind": "openclaw-mem.episodes.ingest.v0",
                    "ok": False,
                    "error": str(e),
                },
                True,
            )
            sys.exit(1)
        except Exception as e:
            _emit(
                {
                    "kind": "openclaw-mem.episodes.ingest.v0",
                    "ok": False,
                    "error": "unexpected ingest failure",
                    "detail": str(e),
                },
                True,
            )
            sys.exit(1)

        _emit(out, args.json)
        return

    stop_requested = False
    stop_signal_name = None
    stop_reason = None

    installed_handlers: List[Tuple[Any, Any]] = []

    def _request_stop(signum: int, _frame: Any) -> None:
        nonlocal stop_requested, stop_signal_name
        stop_requested = True
        try:
            stop_signal_name = signal.Signals(signum).name
        except Exception:
            stop_signal_name = str(signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous = signal.getsignal(sig)
            signal.signal(sig, _request_stop)
            installed_handlers.append((sig, previous))
        except Exception:
            continue

    started = time.monotonic()
    last_activity = started

    cycles = 0
    active_cycles = 0
    idle_cycles = 0
    source_missing_cycles = 0
    aggregate_inserted = 0
    aggregate_duplicates = 0
    aggregate_invalid_json = 0
    aggregate_invalid_event = 0
    aggregate_payload_truncated = 0
    aggregate_refs_truncated = 0
    aggregate_redacted_late = 0
    aggregate_lines_total = 0
    rotate_attempts = 0
    rotate_applied = 0
    rotate_errors = 0
    rotate_last_rotated_to: Optional[str] = None

    last_cycle: Optional[Dict[str, Any]] = None

    lock_path = _episodic_lock_path(source_path)

    def _try_rotate_on_idle() -> Optional[str]:
        if rotate_on_idle_seconds <= 0:
            return None
        try:
            st = source_path.stat()
        except FileNotFoundError:
            return None
        size = int(st.st_size)
        if size <= 0 or size < rotate_min_bytes:
            return None
        # Require writer-idle too (mtime wallclock)
        try:
            if (time.time() - float(st.st_mtime)) < rotate_on_idle_seconds:
                return None
        except Exception:
            return None
        state = _read_json_file(state_path)
        offset = _episodic_state_int(state.get("offset")) or 0
        # Only rotate when fully caught up on a newline boundary
        if offset != size:
            return None
        try:
            with _episodic_flock(lock_path, exclusive=True, timeout_s=1.0):
                st2 = source_path.stat()
                size2 = int(st2.st_size)
                if size2 <= 0 or size2 < rotate_min_bytes:
                    return None
                state2 = _read_json_file(state_path)
                offset2 = _episodic_state_int(state2.get("offset")) or 0
                if offset2 != size2:
                    return None
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                rotated_path = source_path.with_name(f"{source_path.name}.{stamp}.idle-rotated")
                suffix = 1
                while rotated_path.exists():
                    suffix += 1
                    rotated_path = source_path.with_name(f"{source_path.name}.{stamp}.idle-rotated.{suffix}")
                source_path.rename(rotated_path)
                try:
                    # New empty spool for writer
                    with source_path.open("w", encoding="utf-8"):
                        pass
                except Exception:
                    # Best-effort rollback: restore original spool path
                    try:
                        rotated_path.rename(source_path)
                    except Exception:
                        pass
                    raise
                st_new = source_path.stat()
                state_payload = {
                    "schema": EPISODIC_INGEST_STATE_SCHEMA,
                    "file": str(source_path),
                    "offset": 0,
                    "dev": int(st_new.st_dev),
                    "inode": int(st_new.st_ino),
                    "size": int(st_new.st_size),
                    "updated_at": _utcnow_iso(),
                }
                _write_json_file_atomic(state_path, state_payload)
                return str(rotated_path)
        except TimeoutError:
            return None

    try:
        while True:
            if stop_requested:
                stop_reason = "signal"
                break

            cycle_activity = False
            cycle = _episodes_ingest_once(
                conn,
                source_path=source_path,
                state_path=state_path,
                payload_cap=payload_cap,
                conversation_payload_cap=conversation_payload_cap,
                refs_cap=refs_cap,
                truncate_after=False,
                rotate_after=False,
                allow_missing_source=True,
            )
            cycles += 1

            if cycle is None:
                source_missing_cycles += 1
            else:
                last_cycle = cycle
                lines = cycle.get("lines") or {}
                bounded = cycle.get("bounded") or {}
                source = cycle.get("source") or {}

                aggregate_inserted += int(cycle.get("inserted") or 0)
                aggregate_lines_total += int(lines.get("total") or 0)
                aggregate_duplicates += int(lines.get("duplicates") or 0)
                aggregate_invalid_json += int(lines.get("invalid_json") or 0)
                aggregate_invalid_event += int(lines.get("invalid_event") or 0)
                aggregate_payload_truncated += int(bounded.get("payload_truncated") or 0)
                aggregate_refs_truncated += int(bounded.get("refs_truncated") or 0)
                aggregate_redacted_late += int(bounded.get("redacted_late") or 0)

                start_offset = int(source.get("start_offset") or 0)
                next_offset = int(source.get("next_offset") or 0)
                if (
                    int(lines.get("total") or 0) > 0
                    or int(cycle.get("inserted") or 0) > 0
                    or next_offset != start_offset
                    or bool(source.get("offset_recovery"))
                ):
                    cycle_activity = True

            now = time.monotonic()
            if cycle_activity:
                active_cycles += 1
                last_activity = now
            else:
                idle_cycles += 1

            if stop_requested:
                stop_reason = "signal"
                break

            if idle_exit_seconds > 0 and (now - last_activity) >= idle_exit_seconds:
                stop_reason = "idle_timeout"
                break

            if rotate_on_idle_seconds > 0 and (not cycle_activity) and (now - last_activity) >= rotate_on_idle_seconds:
                rotate_attempts += 1
                try:
                    rotated_to = _try_rotate_on_idle()
                except Exception:
                    rotate_errors += 1
                    rotated_to = None
                if rotated_to:
                    rotate_applied += 1
                    rotate_last_rotated_to = rotated_to
                    cycle_activity = True
                    last_activity = now

            if not cycle_activity:
                time.sleep(poll_interval_ms / 1000.0)
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
    except ValueError as e:
        _emit({"kind": "openclaw-mem.episodes.ingest.v0", "ok": False, "error": str(e)}, True)
        sys.exit(2)
    except Exception as e:
        _emit(
            {
                "kind": "openclaw-mem.episodes.ingest.v0",
                "ok": False,
                "error": "follow ingest failed",
                "detail": str(e),
            },
            True,
        )
        sys.exit(1)
    finally:
        for sig, previous in installed_handlers:
            try:
                signal.signal(sig, previous)
            except Exception:
                pass

    duration_ms = int((time.monotonic() - started) * 1000)
    out = {
        "kind": "openclaw-mem.episodes.ingest.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "follow": {
            "enabled": True,
            "poll_interval_ms": poll_interval_ms,
            "idle_exit_seconds": idle_exit_seconds,
            "cycles": cycles,
            "active_cycles": active_cycles,
            "idle_cycles": idle_cycles,
            "source_missing_cycles": source_missing_cycles,
            "duration_ms": duration_ms,
            "stop_reason": (stop_reason or "signal") if stop_requested else stop_reason,
            "signal": stop_signal_name,
        },
        "rotate_on_idle": {
            "enabled": rotate_on_idle_seconds > 0,
            "idle_seconds": rotate_on_idle_seconds,
            "min_bytes": rotate_min_bytes,
            "attempts": rotate_attempts,
            "rotated": rotate_applied,
            "errors": rotate_errors,
            "last_rotated_to": rotate_last_rotated_to,
        },
        "source": {
            "file": str(source_path),
            "state": str(state_path),
            "spool_schema": EPISODIC_SPOOL_SCHEMA,
        },
        "aggregate": {
            "inserted": aggregate_inserted,
            "lines_total": aggregate_lines_total,
            "duplicates": aggregate_duplicates,
            "invalid_json": aggregate_invalid_json,
            "invalid_event": aggregate_invalid_event,
            "payload_truncated": aggregate_payload_truncated,
            "refs_truncated": aggregate_refs_truncated,
            "redacted_late": aggregate_redacted_late,
        },
        "bounded": {
            "payload_cap_bytes": payload_cap,
            "conversation_payload_cap_bytes": conversation_payload_cap,
            "payload_hard_cap_bytes": EPISODIC_INGEST_HARD_PAYLOAD_CAP_BYTES,
            "refs_cap_bytes": refs_cap,
        },
        "last_cycle": last_cycle,
    }
    _emit(out, args.json)


def cmd_episodes_redact(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    event_id = str(getattr(args, "event_id", "") or "").strip() or None
    session_id = str(getattr(args, "session_id", "") or "").strip() or None

    if bool(event_id) == bool(session_id):
        _emit(
            {
                "kind": "openclaw-mem.episodes.redact.v0",
                "ok": False,
                "error": "provide exactly one of --event-id or --session-id",
            },
            True,
        )
        sys.exit(2)

    replacement = str(getattr(args, "replacement", "placeholder") or "placeholder").strip().lower()
    if replacement not in {"null", "placeholder"}:
        _emit(
            {
                "kind": "openclaw-mem.episodes.redact.v0",
                "ok": False,
                "error": "replacement must be 'null' or 'placeholder'",
            },
            True,
        )
        sys.exit(2)

    payload_value: Optional[str]
    refs_value: Optional[str]
    if replacement == "null":
        payload_value = None
        refs_value = None
    else:
        redacted_value = _json_compact_dumps(EPISODIC_REDACT_PLACEHOLDER)
        payload_value = redacted_value
        refs_value = redacted_value

    try:
        if event_id:
            cur = conn.execute(
                "UPDATE episodic_events SET payload_json = ?, refs_json = ?, redacted = 1 WHERE event_id = ?",
                (payload_value, refs_value, event_id),
            )
            redacted_count = int(cur.rowcount)
            scope = None
        else:
            scope = _resolve_query_scope(getattr(args, "scope", None), bool(getattr(args, "global_scope", False)))
            cur = conn.execute(
                "UPDATE episodic_events SET payload_json = ?, refs_json = ?, redacted = 1 WHERE session_id = ? AND scope = ?",
                (payload_value, refs_value, session_id, scope),
            )
            redacted_count = int(cur.rowcount)
        conn.commit()
    except ValueError as e:
        _emit(
            {
                "kind": "openclaw-mem.episodes.redact.v0",
                "ok": False,
                "error": str(e),
            },
            True,
        )
        sys.exit(2)

    out = {
        "kind": "openclaw-mem.episodes.redact.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "target": {
            "event_id": event_id,
            "session_id": session_id,
            "scope": scope,
        },
        "replacement": replacement,
        "redacted_count": redacted_count,
    }
    _emit(out, args.json)


def _parse_retention_policy(raw: Optional[List[str]]) -> Dict[str, Optional[int]]:
    policy: Dict[str, Optional[int]] = dict(EPISODIC_DEFAULT_RETENTION_DAYS)
    if not raw:
        return policy

    for entry in raw:
        text = str(entry or "").strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError(f"invalid --policy entry: {text}")
        type_raw, days_raw = text.split("=", 1)
        event_type = _normalize_episodic_type(type_raw)
        days_token = days_raw.strip().lower()
        if days_token in {"forever", "inf", "infinite", "none"}:
            policy[event_type] = None
            continue
        try:
            days = int(days_token)
        except Exception as e:
            raise ValueError(f"invalid retention days for {event_type}: {days_raw}") from e
        if days < 0:
            raise ValueError(f"retention days must be >= 0 for {event_type}")
        policy[event_type] = days

    return policy


def cmd_episodes_gc(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    try:
        scope = _resolve_query_scope(getattr(args, "scope", None), bool(getattr(args, "global_scope", False)))
        now_ts_ms = _parse_ts_ms(getattr(args, "now_ts_ms", None))
        policy = _parse_retention_policy(getattr(args, "policy", None))
    except ValueError as e:
        _emit(
            {
                "kind": "openclaw-mem.episodes.gc.v0",
                "ok": False,
                "error": str(e),
            },
            True,
        )
        sys.exit(2)

    deleted_by_type: Dict[str, int] = {}
    deleted_total = 0

    for event_type in sorted(EPISODIC_ALLOWED_TYPES):
        days = policy.get(event_type)
        if days is None:
            deleted_by_type[event_type] = 0
            continue

        cutoff = now_ts_ms - (int(days) * 24 * 60 * 60 * 1000)
        cur = conn.execute(
            "DELETE FROM episodic_events WHERE scope = ? AND type = ? AND ts_ms < ?",
            (scope, event_type, int(cutoff)),
        )
        deleted = int(cur.rowcount)
        deleted_by_type[event_type] = deleted
        deleted_total += deleted

    conn.commit()

    policy_days = {k: policy.get(k) for k in sorted(EPISODIC_ALLOWED_TYPES)}
    out = {
        "kind": "openclaw-mem.episodes.gc.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "ok": True,
        "scope": scope,
        "now_ts_ms": now_ts_ms,
        "deleted_total": deleted_total,
        "deleted_by_type": deleted_by_type,
        "policy_days": policy_days,
    }
    _emit(out, args.json)


def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Examples:\n"
        "  # Observation store\n"
        "  openclaw-mem status --json\n"
        "  openclaw-mem profile --json --recent-limit 15\n"
        "  openclaw-mem backend --json\n"
        "  openclaw-mem ingest --file observations.jsonl --json\n"
        "\n"
        "  # Progressive disclosure search\n"
        "  openclaw-mem search \"gateway timeout\" --limit 20 --json\n"
        "  openclaw-mem timeline 23 41 57 --window 4 --json\n"
        "  openclaw-mem get 23 41 57 --json\n"
        "\n"
        "  # Docs memory (hybrid FTS + vector)\n"
        "  openclaw-mem docs ingest --path ./docs --json\n"
        "  openclaw-mem docs search \"hybrid retrieval\" --trace --json\n"
        "\n"
        "  # Episodic events ledger (v0)\n"
        "  openclaw-mem episodes append --scope openclaw-mem --session-id s1 --agent-id lyria --type conversation.user --summary \"Asked for update\" --json\n"
        "  openclaw-mem episodes extract-sessions --sessions-root ~/.openclaw/sessions --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json --json\n"
        "  openclaw-mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --json\n"
        "  openclaw-mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --follow --poll-interval-ms 1000 --json\n"
        "  openclaw-mem episodes query --scope openclaw-mem --session-id s1 --limit 50 --json\n"
        "\n"
        "  # AI compression (requires API key via env or ~/.openclaw/openclaw.json)\n"
        "  export OPENAI_API_KEY=sk-...\n"
        "  openclaw-mem summarize --json  # yesterday's notes\n"
        "  openclaw-mem summarize 2026-02-04 --dry-run\n"
        "\n"
        "  # Export observations (Markdown)\n"
        "  openclaw-mem export --to /tmp/export.md --limit 20 --json\n"
        "  openclaw-mem export --to MEMORY.md --yes --limit 20\n"
        "\n"
        "  # Vector search (Phase 3)\n"
        "  export OPENAI_API_KEY=sk-...\n"
        "  openclaw-mem embed --limit 500 --json\n"
        "  openclaw-mem vsearch \"gateway timeout\" --limit 10 --json\n"
        "\n"
        "  # Recall/writeback (Phase 5)\n"
        "  openclaw-mem writeback-lancedb --db mem.sqlite --lancedb ~/.openclaw/memory/lancedb --table memories --limit 50 --dry-run\n"
        "\n"
        "  # Hybrid Search & Store (Phase 4)\n"
        "  openclaw-mem hybrid \"python error\" --limit 5 --json\n"
        "  openclaw-mem hybrid \"python error\" --rerank-provider jina --rerank-topn 20 --json\n"
        "  openclaw-mem store \"Prefer tabs over spaces\" --category preference --importance 0.9 --json\n"
        "\n"
        "Global flags also work before the command:\n"
        "  openclaw-mem --db /tmp/mem.sqlite --json status\n"
        "\n"
        "Input JSONL (one per line) for ingest:\n"
        "  {\"ts\":\"2026-02-04T13:00:00Z\", \"kind\":\"tool\", \"tool_name\":\"cron.list\", \"summary\":\"cron list called\", \"detail\":{...}}\n"
    )

    p = argparse.ArgumentParser(
        prog="openclaw-mem",
        description="OpenClaw memory CLI (M0 prototype).",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags (before the subcommand). These are merged with per-command flags.
    p.add_argument("--db", dest="db_global", default=None, help="SQLite DB path")
    p.add_argument("--json", dest="json_global", action="store_true", help="Structured JSON output")

    def add_common(sp: argparse.ArgumentParser) -> None:
        # Allow flags after the subcommand too.
        sp.add_argument("--db", default=None, help="SQLite DB path")
        sp.add_argument("--json", action="store_true", help="Structured JSON output")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="Show store stats")
    add_common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("profile", help="Show ops profile (counts/ranges/labels/recent)")
    add_common(sp)
    sp.add_argument("--recent-limit", type=int, default=10, help="Number of recent rows to include (default: 10)")
    sp.add_argument("--tool-limit", type=int, default=10, help="Max top tools to include (default: 10)")
    sp.add_argument("--kind-limit", type=int, default=10, help="Max top kinds to include (default: 10)")
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser("backend", help="Inspect active OpenClaw memory backend + fallback posture")
    add_common(sp)
    sp.set_defaults(func=cmd_backend)

    sp = sub.add_parser("optimize", help="Recommendation-first memory optimization helpers (zero-write)")
    add_common(sp)
    osub = sp.add_subparsers(dest="optimize_cmd", required=True)

    o = osub.add_parser("review", help="Review memory health signals and emit recommendations (no writes)")
    add_common(o)
    o.add_argument("--limit", type=int, default=1000, help="Max observation rows to scan (default: 1000)")
    o.add_argument("--stale-days", type=int, default=60, help="Staleness threshold in days (default: 60)")
    o.add_argument("--duplicate-min-count", dest="duplicate_min_count", type=int, default=2, help="Min rows per duplicate cluster (default: 2)")
    o.add_argument("--bloat-summary-chars", dest="bloat_summary_chars", type=int, default=240, help="Summary length threshold for bloat candidates (default: 240)")
    o.add_argument("--bloat-detail-bytes", dest="bloat_detail_bytes", type=int, default=4096, help="detail_json size threshold for bloat candidates in bytes (default: 4096)")
    o.add_argument("--orphan-min-tokens", dest="orphan_min_tokens", type=int, default=2, help="Minimum token count for weakly connected candidates (default: 2)")
    o.add_argument("--miss-min-count", dest="miss_min_count", type=int, default=2, help="Min repeated no-result memory_recall events per query/scope group (default: 2)")
    o.add_argument("--scope", default=None, help="Filter review to a normalized detail.scope token")
    o.add_argument("--top", type=int, default=10, help="Max candidate rows/groups per signal in output (default: 10)")
    o.set_defaults(func=cmd_optimize_review)

    sp = sub.add_parser("ingest", help="Ingest observations (JSONL via --file or stdin)")
    add_common(sp)
    sp.add_argument("--file", help="JSONL file path (default: stdin)")
    sp.add_argument(
        "--importance-scorer",
        dest="importance_scorer",
        default=None,
        help=(
            "Override importance autograde scorer for this run (env fallback: OPENCLAW_MEM_IMPORTANCE_SCORER). "
            "Use 'heuristic-v1' to enable, or 'off' to disable."
        ),
    )
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("search", help="FTS search over observations")
    add_common(sp)
    sp.add_argument("query", help="Search query (FTS5 syntax)")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("docs", help="Docs memory (operator-authored markdown ingest/search)")
    add_common(sp)
    dsub = sp.add_subparsers(dest="docs_cmd", required=True)

    d = dsub.add_parser("ingest", help="Ingest markdown docs into docs_chunks")
    add_common(d)
    d.add_argument("--path", action="append", required=True, help="Markdown file or directory path (repeatable)")
    d.add_argument("--max-chars", dest="max_chars", type=int, default=1400, help="Chunk size upper bound in characters (default: 1400)")
    d.add_argument("--embed", action="store_true", default=True, help="Generate embeddings for changed chunks when API key is available (default: true)")
    d.add_argument("--no-embed", dest="embed", action="store_false", help="Skip embeddings during ingest")
    d.add_argument("--batch", type=int, default=32, help="Embedding batch size (default: 32)")
    d.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    d.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    d.set_defaults(func=cmd_docs_ingest)

    d = dsub.add_parser("search", help="Hybrid docs retrieval (FTS + vector + deterministic RRF)")
    add_common(d)
    d.add_argument("query", help="Search query text")
    d.add_argument("--limit", type=int, default=10, help="Final selected chunks (default: 10)")
    d.add_argument("--fts-k", dest="fts_k", type=int, default=30, help="FTS candidate count before fusion (default: 30)")
    d.add_argument("--vec-k", dest="vec_k", type=int, default=30, help="Vector candidate count before fusion (default: 30)")
    d.add_argument("--k", type=int, default=60, help="RRF constant (default: 60)")
    d.add_argument("--trace", action="store_true", help="Include trace receipt: fts top-k, vec top-k, fused ranking, selected chunks")
    d.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    d.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    d.set_defaults(func=cmd_docs_search)

    sp = sub.add_parser("timeline", help="Windowed timeline around IDs")
    add_common(sp)
    sp.add_argument("ids", type=int, nargs="+", help="Observation IDs")
    sp.add_argument("--window", type=int, default=4, help="±N rows around each id")
    sp.set_defaults(func=cmd_timeline)

    sp = sub.add_parser("get", help="Get full observations by ID")
    add_common(sp)
    sp.add_argument("ids", type=int, nargs="+", help="Observation IDs")
    sp.set_defaults(func=cmd_get)

    sp = sub.add_parser("summarize", help="Run AI compression on daily notes (requires API key)")
    add_common(sp)
    sp.add_argument("date", nargs="?", help="Date to compress (YYYY-MM-DD, default: yesterday)")
    sp.add_argument("--workspace", type=Path, help="Workspace root (default: cwd)")
    sp.add_argument("--model", default=defaults.summary_model(), help="OpenAI model (env: OPENCLAW_MEM_SUMMARY_MODEL)")
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--max-tokens", type=int, default=700, help="Max output tokens")
    sp.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    sp.add_argument("--dry-run", action="store_true", help="Preview without writing")
    # Gateway options
    sp.add_argument("--gateway", action="store_true", help="Use OpenClaw Gateway for model routing")
    sp.add_argument("--gateway-url", help="OpenClaw Gateway base URL (auto-detected if unset)")
    sp.add_argument("--gateway-token", help="OpenClaw Gateway token (auto-detected from ~/.openclaw/openclaw.json)")
    sp.add_argument("--agent-id", default="main", help="Target agent ID for Gateway (default: main)")
    sp.set_defaults(func=cmd_summarize)

    sp = sub.add_parser("export", help="Export observations to a Markdown file")
    add_common(sp)
    sp.add_argument("--to", required=True, help="Target file (e.g., MEMORY.md)")
    sp.add_argument("--yes", action="store_true", help="Required when exporting to MEMORY.md")
    sp.add_argument("--ids", type=int, nargs="+", help="Specific observation IDs to export")
    sp.add_argument("--limit", type=int, default=50, help="Export last N observations (default: 50)")
    sp.add_argument("--include-detail", action="store_true", help="Include detail_json blocks")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("embed", help="Compute/store embeddings for observations (requires API key)")
    add_common(sp)
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--limit", type=int, default=500, help="Max observations to embed (default: 500)")
    sp.add_argument("--batch", type=int, default=64, help="Batch size per API call (default: 64)")
    sp.add_argument("--field", choices=["original", "english", "both"], default="original", help="Embedding source field (default: original)")
    sp.set_defaults(func=cmd_embed)

    sp = sub.add_parser("vsearch", help="Vector search over embeddings (cosine similarity)")
    add_common(sp)
    sp.add_argument("query", help="Query text")
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--query-vector-json", help="Provide query vector as JSON array (testing/offline)")
    sp.add_argument("--query-vector-file", help="Provide query vector from JSON file (testing/offline)")
    sp.set_defaults(func=cmd_vsearch)

    sp = sub.add_parser("hybrid", help="Hybrid search (Vector + FTS) using RRF")
    add_common(sp)
    sp.add_argument("query", help="Query text")
    sp.add_argument("--query-en", help="Optional English query for additional vector route")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--k", type=int, default=60, help="RRF constant (default: 60)")
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument(
        "--rerank-provider",
        choices=["none", "jina", "cohere"],
        default="none",
        help="Optional post-retrieval rerank provider (default: none)",
    )
    sp.add_argument(
        "--rerank-model",
        default=defaults.rerank_model(),
        help="Reranker model name (provider-specific) (env: OPENCLAW_MEM_RERANK_MODEL)",
    )
    sp.add_argument(
        "--rerank-topn",
        type=int,
        default=20,
        help="Top-N reranked items to prioritize before RRF fallback",
    )
    sp.add_argument("--rerank-api-key", help="Reranker API key (or env: JINA_API_KEY/COHERE_API_KEY)")
    sp.add_argument("--rerank-base-url", help="Optional reranker endpoint override")
    sp.add_argument("--rerank-timeout-sec", type=int, default=15, help="Reranker HTTP timeout in seconds")
    sp.set_defaults(func=cmd_hybrid)

    sp = sub.add_parser("pack", help="Build a compact, cited bundle from hybrid retrieval")
    sp.add_argument("--db", default=None, help="SQLite DB path")
    sp.add_argument(
        "--json",
        dest="json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Structured JSON output (default: true). Use --no-json for bundle_text only.",
    )
    sp.add_argument("--query", required=True, help="Pack query text")
    sp.add_argument("--query-en", help="Optional English query for bilingual retrieval")
    sp.add_argument("--limit", type=int, default=12, help="Max packed items (default: 12)")
    sp.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=1200, help="Token budget for bundle text (default: 1200)")

    # Optional: Graphic Memory preflight integration (default OFF; fail-open)
    sp.add_argument(
        "--use-graph",
        choices=["off", "auto", "on"],
        default="off",
        help="Graphic Memory integration: off (default) | auto (deterministic trigger+probe) | on (always run preflight).",
    )
    sp.add_argument("--graph-scope", default=None, help="Optional scope hint for graph preflight (default: unset)")
    sp.add_argument("--graph-budget-tokens", type=int, default=1200, help="Token budget for graph preflight bundle_text (default: 1200)")
    sp.add_argument("--graph-take", type=int, default=12, help="Max selected refs to pack for graph preflight (default: 12)")

    # Probe knobs (used in --use-graph=auto)
    sp.add_argument("--graph-probe", choices=["on", "off"], default=None, help="Enable index-probe stage in auto mode (default: on)")
    sp.add_argument("--graph-probe-limit", type=int, default=5, help="Max FTS rows to fetch in probe (default: 5)")
    sp.add_argument("--graph-probe-t-high", type=float, default=-5.0, help="Probe trigger threshold for best bm25() score (default: -5.0)")
    sp.add_argument("--graph-probe-t-marginal", type=float, default=-2.0, help="Probe marginal threshold (default: -2.0)")
    sp.add_argument("--graph-probe-n-min", type=int, default=3, help="Breadth minimum count for marginal probe hits (default: 3)")

    sp.add_argument("--trace", action="store_true", help="Include redaction-safe retrieval trace (`openclaw-mem.pack.trace.v1`) with include/exclude decisions")
    sp.set_defaults(func=cmd_pack)


    # Graphic memory (GraphRAG-lite) — v0 command group
    sp = sub.add_parser("graph", help="Graphic memory helpers (index-first graph recall + packing)")
    sp.add_argument("--db", default=None, help="SQLite DB path")
    sp.add_argument(
        "--json",
        dest="json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Structured JSON output (default: true). Use --no-json for text-only payload.",
    )
    gsub = sp.add_subparsers(dest="graph_cmd", required=True)

    g = gsub.add_parser("index", help="Build an L0 IndexPack for a query (budgeted, injection-ready)")
    g.add_argument("query", help="Query text")
    g.add_argument("--scope", help="Optional scope filter token (matches detail.scope after normalization)")
    g.add_argument("--limit", type=int, default=12, help="Max candidate hits to consider (default: 12)")
    g.add_argument("--window", type=int, default=2, help="Timeline window for neighborhood suggestions (default: 2)")
    g.add_argument("--suggest-limit", dest="suggest_limit", type=int, default=6, help="Max suggested expansions (default: 6)")
    g.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=900, help="Token budget for index_text (default: 900)")
    g.set_defaults(func=cmd_graph_index)

    g = gsub.add_parser("pack", help="Build an L1 ContextPack from selected recordRefs/ids (safe-by-default)")
    g.add_argument("ids", nargs="+", help="Record refs (e.g., obs:123) or numeric ids")
    g.add_argument("--max-items", dest="max_items", type=int, default=20, help="Max items to include (default: 20)")
    g.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=1500, help="Token budget for bundle_text (default: 1500)")
    g.set_defaults(func=cmd_graph_pack)

    g = gsub.add_parser("preflight", help="Run index+selection+pack in one deterministic step")
    g.add_argument("query", help="Query text")
    g.add_argument("--scope", help="Optional scope filter token (matches detail.scope after normalization)")
    g.add_argument("--limit", type=int, default=12, help="Max candidate hits to consider (default: 12)")
    g.add_argument("--window", type=int, default=2, help="Timeline window for neighborhood suggestions (default: 2)")
    g.add_argument("--suggest-limit", dest="suggest_limit", type=int, default=6, help="Max suggested expansions (default: 6)")
    g.add_argument("--take", type=int, default=12, help="Max selected refs to pack (default: 12)")
    g.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=1200, help="Token budget for bundle_text (default: 1200)")
    g.set_defaults(func=cmd_graph_preflight, json=False)

    g = gsub.add_parser("synth", help="Compile / check derived Graphic Memory synthesis cards")
    ssub = g.add_subparsers(dest="graph_synth_cmd", required=True)

    s = ssub.add_parser("compile", help="Compile a synthesis card from explicit refs or a query preflight")
    s.add_argument("--record-ref", dest="record_ref", action="append", default=None, help="Source record ref (repeatable, e.g. obs:123)")
    s.add_argument("--query", help="Optional query text; uses graph preflight selection when set")
    s.add_argument("--scope", help="Optional scope filter token when using --query")
    s.add_argument("--limit", type=int, default=12, help="Max candidate hits to consider for query mode (default: 12)")
    s.add_argument("--window", type=int, default=2, help="Timeline window for query mode (default: 2)")
    s.add_argument("--suggest-limit", dest="suggest_limit", type=int, default=6, help="Max suggested expansions for query mode (default: 6)")
    s.add_argument("--take", type=int, default=12, help="Max selected refs for query mode (default: 12)")
    s.add_argument("--budget-tokens", dest="budget_tokens", type=int, default=1200, help="Token budget for query-mode selection (default: 1200)")
    s.add_argument("--title", help="Optional synthesis title")
    s.add_argument("--summary", dest="summary_text", help="Stored synthesis summary text (defaults to title)")
    s.add_argument("--why-it-matters", dest="why_it_matters", help="Optional why-it-matters note")
    s.add_argument("--write-md", dest="write_md", help="Optional Markdown materialization path")
    s.set_defaults(func=cmd_graph_synth)

    s = ssub.add_parser("stale", help="Check whether synthesis cards are stale")
    s.add_argument("record_ref", nargs='+', help="Synthesis card refs (e.g. obs:123)")
    s.set_defaults(func=cmd_graph_synth)

    g = gsub.add_parser("lint", help="Run deterministic health checks for synthesis-card coverage / staleness")
    g.set_defaults(func=cmd_graph_lint)

    g = gsub.add_parser("auto-status", help="Show effective Graphic Memory automation env toggles")
    g.set_defaults(func=cmd_graph_auto_status)

    g = gsub.add_parser("topology-refresh", help="Refresh topology graph (nodes/edges) from a curated file")
    g.add_argument("--file", required=True, help="Topology file path (.json; .yaml requires PyYAML)")
    g.set_defaults(func=cmd_graph_topology_refresh)

    g = gsub.add_parser("topology-extract", help="Extract a deterministic topology seed from workspace + cron + specs")
    g.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Workspace root to scan for repo roots (default: cwd)")
    g.add_argument("--cron-jobs", dest="cron_jobs", default=DEFAULT_CRON_JOBS_JSON, help=f"Cron jobs registry JSON path (default: {DEFAULT_CRON_JOBS_JSON})")
    g.add_argument("--spec-dir", dest="spec_dir", help="Cron spec directory (default: <workspace>/openclaw-async-coding-playbook/cron/jobs)")
    g.add_argument("--out", required=True, help="Output topology seed JSON path")
    g.set_defaults(func=cmd_graph_topology_extract)

    g = gsub.add_parser("topology-diff", help="Compare extracted seed topology with curated topology (suggest-only)")
    g.add_argument("--seed", required=True, help="Extracted topology seed file (.json/.yaml)")
    g.add_argument("--curated", required=True, help="Curated topology file (.json/.yaml)")
    g.add_argument("--limit", type=int, default=50, help="Max rows per diff bucket in output (default: 50)")
    g.set_defaults(func=cmd_graph_topology_diff)

    g = gsub.add_parser("query", help="Deterministic graph topology queries (upstream/downstream/lineage/writers/subgraph/filter/receipts/provenance/drift)")
    qsub = g.add_subparsers(dest="graph_query_cmd", required=True)

    q = qsub.add_parser("upstream", help="List incoming edges into node_id")
    q.add_argument("node_id", help="Target node id")
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("downstream", help="List outgoing edges from node_id")
    q.add_argument("node_id", help="Source node id")
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("lineage", help="List both upstream and downstream edges for node_id")
    q.add_argument("node_id", help="Target node id")
    q.add_argument("--max-depth", dest="max_depth", type=int, default=1, help="Traversal depth in hops (default: 1; max: 8)")
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("writers", help="List writes edges that target artifact_id")
    q.add_argument("artifact_id", help="Artifact node id")
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("subgraph", help="Emit a bounded subgraph around node_id (pack-style, provenance-first)")
    q.add_argument("node_id", help="Center node id")
    q.add_argument("--hops", type=int, default=2, help="Neighborhood hops (default: 2)")
    q.add_argument(
        "--direction",
        choices=["upstream", "downstream", "both"],
        default="both",
        help="Edge expansion direction (default: both)",
    )
    q.add_argument("--max-nodes", dest="max_nodes", type=int, default=40, help="Max nodes to include (default: 40)")
    q.add_argument("--max-edges", dest="max_edges", type=int, default=80, help="Max edges to include (default: 80)")
    q.add_argument(
        "--edge-type",
        dest="edge_type",
        action="append",
        default=None,
        help="Only include edges with these types (repeatable; comma-separated ok)",
    )
    q.add_argument(
        "--include-node-type",
        dest="include_node_type",
        action="append",
        default=None,
        help="Only include nodes with these node types (repeatable; comma-separated ok). Center node is always included.",
    )
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("filter", help="Filter nodes by tags/type")
    q.add_argument("--tag", help="Require tag")
    q.add_argument("--not-tag", dest="not_tag", help="Exclude tag")
    q.add_argument("--node-type", dest="node_type", help="Require node type")
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("receipts", help="List recent deterministic refresh receipts")
    q.add_argument("--limit", type=int, default=10, help="Max receipts to return (default: 10)")
    q.add_argument("--source-path", dest="source_path", help="Optional exact source_path filter")
    q.add_argument("--topology-digest", dest="topology_digest", help="Optional exact topology_digest filter")
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("provenance", help="List provenance references with edge counts")
    q.add_argument("--node-id", dest="node_id", help="Optional node id filter (matches src or dst)")
    q.add_argument("--edge-type", dest="edge_type", help="Optional edge type filter")
    q.add_argument("--source-path", dest="source_path", help="Optional exact source path filter (before #anchor)")
    q.add_argument("--source-path-prefix", dest="source_path_prefix", help="Optional source path prefix filter (before #anchor)")
    q.add_argument("--group-by-source", dest="group_by_source", action="store_true", help="Group by provenance source path (drop #anchor suffixes)")
    q.add_argument("--min-edge-count", dest="min_edge_count", type=int, default=1, help="Only include provenance groups with at least this many edges (default: 1)")
    q.add_argument("--limit", type=int, default=20, help="Max provenance rows to return (default: 20)")
    q.set_defaults(func=cmd_graph_query)

    q = qsub.add_parser("drift", help="Compare topology graph nodes against runtime state JSON")
    q.add_argument("--live-json", dest="live_json", required=True, help="Runtime state JSON path (nodes/status_by_node)")
    q.add_argument("--limit", type=int, default=50, help="Max node ids to include per drift bucket (default: 50)")
    q.set_defaults(func=cmd_graph_query)

    g = gsub.add_parser("capture-git", help="Capture recent git commits as observations (idempotent)")
    g.add_argument("--repo", action="append", required=True, help="Git repository path (repeatable)")
    g.add_argument("--since", type=float, default=24, help="Fallback lookback window in hours (default: 24)")
    g.add_argument("--state", default=DEFAULT_GRAPH_CAPTURE_STATE_PATH, help=f"Capture state file (default: {DEFAULT_GRAPH_CAPTURE_STATE_PATH})")
    g.add_argument("--max-commits", dest="max_commits", type=int, default=50, help="Max commits per repo per run (default: 50)")
    g.set_defaults(func=cmd_graph_capture_git)

    g = gsub.add_parser("capture-md", help="Capture Markdown heading sections as index-only observations (idempotent)")
    g.add_argument("--path", action="append", required=True, help="Markdown file/directory path (repeatable)")
    g.add_argument("--include", action="append", default=None, help="File extension filter (repeatable, default: .md)")
    g.add_argument("--exclude-glob", dest="exclude_glob", action="append", default=None, help="Exclude glob pattern (repeatable)")
    g.add_argument("--max-files", dest="max_files", type=int, default=200, help="Max files to inspect per run (default: 200)")
    g.add_argument("--max-sections-per-file", dest="max_sections_per_file", type=int, default=50, help="Max heading sections captured per file (default: 50)")
    g.add_argument("--min-heading-level", dest="min_heading_level", type=int, default=2, help="Capture headings at this level or deeper (default: 2)")
    g.add_argument("--state", default=DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH, help=f"Capture state file (default: {DEFAULT_GRAPH_CAPTURE_MD_STATE_PATH})")
    g.add_argument("--since-hours", dest="since_hours", type=float, default=24, help="Fallback lookback window in hours for first scan (default: 24)")
    g.set_defaults(func=cmd_graph_capture_md)

    g = gsub.add_parser("export", help="Export a small graph.json artifact around query hits (portable artifact)")
    g.add_argument("--query", required=True, help="Query text")
    g.add_argument("--scope", help="Optional scope filter token (matches detail.scope after normalization)")
    g.add_argument("--to", required=True, help="Output path for graph.json")
    g.add_argument("--limit", type=int, default=12)
    g.add_argument("--window", type=int, default=2)
    g.set_defaults(func=cmd_graph_export)

    sp = sub.add_parser("artifact", help="Context Budget Sidecar artifact store (stash/fetch/peek)")
    sp.add_argument("--db", default=None, help="SQLite DB path")
    sp.add_argument("--json", action="store_true", help="Structured JSON output")
    asub = sp.add_subparsers(dest="artifact_cmd", required=True)

    a = asub.add_parser("stash", help="Store raw tool output from --from PATH or stdin")
    a.add_argument("--db", default=None, help="SQLite DB path")
    a.add_argument("--json", action="store_true", help="Structured JSON output")
    a.add_argument("--from", dest="from_path", help="Read raw payload bytes from file path (default: stdin)")
    a.add_argument("--kind", default="tool_output", help="Artifact kind label (default: tool_output)")
    a.add_argument("--meta-json", default=None, help="Optional metadata JSON object (small, non-raw)")
    a.add_argument("--gzip", action="store_true", help="Compress blob as .txt.gz")
    a.set_defaults(func=cmd_artifact_stash)

    a = asub.add_parser("fetch", help="Fetch bounded artifact text by handle")
    a.add_argument("--db", default=None, help="SQLite DB path")
    a.add_argument(
        "--json",
        dest="json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Structured JSON output (default: true). Use --no-json for raw bounded text only.",
    )
    a.add_argument("handle", help="Artifact handle: ocm_artifact:v1:sha256:<64hex>")
    a.add_argument("--mode", choices=["headtail", "head", "tail"], default="headtail", help="Bounded extraction mode (default: headtail)")
    a.add_argument("--max-chars", dest="max_chars", type=int, default=8000, help="Maximum characters to return (default: 8000)")
    a.set_defaults(func=cmd_artifact_fetch)

    a = asub.add_parser("peek", help="Show artifact metadata + tiny preview")
    a.add_argument("--db", default=None, help="SQLite DB path")
    a.add_argument("--json", action="store_true", help="Structured JSON output")
    a.add_argument("handle", help="Artifact handle: ocm_artifact:v1:sha256:<64hex>")
    a.add_argument("--preview-chars", dest="preview_chars", type=int, default=240, help="Preview character budget (default: 240)")
    a.set_defaults(func=cmd_artifact_peek)

    sp = sub.add_parser("episodes", help="Append/extract/ingest/query/replay/redact/gc for episodic session events")
    add_common(sp)
    esub = sp.add_subparsers(dest="episodes_cmd", required=True)

    e = esub.add_parser("append", help="Append one episodic event row")
    add_common(e)
    e.add_argument("--event-id", help="Stable event id (default: auto-generated UUIDv4)")
    e.add_argument("--ts-ms", type=int, help="Event timestamp in unix ms (default: now)")
    e.add_argument("--scope", required=True, help="Scope token (normalized; required)")
    e.add_argument("--session-id", required=True, help="Session/run id (required)")
    e.add_argument("--agent-id", required=True, help="Logical actor id (required)")
    e.add_argument("--type", required=True, help="Event type enum (e.g. tool.result)")
    e.add_argument("--summary", required=True, help="Short human-readable summary")
    e.add_argument("--payload-json", help="Optional payload JSON string")
    e.add_argument("--payload-file", help="Optional payload JSON file")
    e.add_argument("--refs-json", help="Optional refs JSON string")
    e.add_argument("--refs-file", help="Optional refs JSON file")
    e.add_argument("--payload-cap-bytes", type=int, default=EPISODIC_DEFAULT_PAYLOAD_CAP_BYTES, help="Payload size cap in bytes (default: 8192)")
    e.add_argument("--refs-cap-bytes", type=int, default=EPISODIC_DEFAULT_REFS_CAP_BYTES, help="Refs size cap in bytes (default: 4096)")
    e.add_argument("--allow-tool-output", action="store_true", help="Allow tool-output/secret-like content (default: reject)")
    e.set_defaults(func=cmd_episodes_append)

    e = esub.add_parser("extract-sessions", help="Tail OpenClaw session JSONL files into episodic spool (conversation fallback)")
    add_common(e)
    e.add_argument(
        "--sessions-root",
        default=DEFAULT_OPENCLAW_SESSIONS_ROOT,
        help=f"OpenClaw sessions root (default: {DEFAULT_OPENCLAW_SESSIONS_ROOT})",
    )
    e.add_argument("--file", default=DEFAULT_EPISODIC_SPOOL_PATH, help=f"Episodes spool JSONL output (default: {DEFAULT_EPISODIC_SPOOL_PATH})")
    e.add_argument(
        "--state",
        default=DEFAULT_EPISODIC_EXTRACT_STATE_PATH,
        help=f"Extractor offset state file (default: {DEFAULT_EPISODIC_EXTRACT_STATE_PATH})",
    )
    e.add_argument("--summary-max-chars", type=int, default=220, help="Summary max chars for extracted conversation events (default: 220)")
    e.add_argument("--payload-cap-bytes", type=int, default=EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES, help="Conversation payload cap in bytes (default: 4096, hard max: 8192)")
    e.set_defaults(func=cmd_episodes_extract_sessions)

    e = esub.add_parser("ingest", help="Ingest episodic events from JSONL spool using an offset state file")
    add_common(e)
    e.add_argument("--file", required=True, help=f"Episodes spool JSONL file (e.g., {DEFAULT_EPISODIC_SPOOL_PATH})")
    e.add_argument(
        "--state",
        default=DEFAULT_EPISODIC_INGEST_STATE_PATH,
        help=f"Offset state file (default: {DEFAULT_EPISODIC_INGEST_STATE_PATH})",
    )
    e.add_argument("--payload-cap-bytes", type=int, default=EPISODIC_DEFAULT_PAYLOAD_CAP_BYTES, help="Generic payload cap in bytes (default: 8192, hard max: 8192)")
    e.add_argument("--conversation-payload-cap-bytes", type=int, default=EPISODIC_DEFAULT_CONVERSATION_PAYLOAD_CAP_BYTES, help="Conversation payload cap in bytes (default: 4096, hard max: 8192)")
    e.add_argument("--refs-cap-bytes", type=int, default=EPISODIC_DEFAULT_REFS_CAP_BYTES, help="Refs size cap in bytes (default: 4096)")
    e.add_argument("--follow", action="store_true", help="Run as a tailer daemon (poll spool + ingest continuously until interrupted)")
    e.add_argument("--poll-interval-ms", type=int, default=EPISODIC_FOLLOW_DEFAULT_POLL_INTERVAL_MS, help="Follow mode poll interval in ms (default: 1000, min: 100)")
    e.add_argument("--idle-exit-seconds", type=float, default=0.0, help="Optional follow auto-exit after N idle seconds (default: 0 = never)")
    e.add_argument("--rotate-on-idle-seconds", type=float, default=EPISODIC_FOLLOW_DEFAULT_ROTATE_ON_IDLE_SECONDS, help="Follow mode: rotate spool when fully caught up and idle for N seconds (default: 0 = disabled)")
    e.add_argument("--rotate-min-bytes", type=int, default=EPISODIC_FOLLOW_DEFAULT_ROTATE_MIN_BYTES, help="Follow mode: only rotate when spool size >= N bytes (default: 1MB)")
    e.add_argument("--truncate", action="store_true", help="Truncate source spool after fully consuming current snapshot")
    e.add_argument("--rotate", action="store_true", help="Rotate source spool after fully consuming current snapshot")
    e.set_defaults(func=cmd_episodes_ingest)

    e = esub.add_parser("query", help="Query episodic events (summary-only by default)")
    add_common(e)
    e.add_argument("--scope", help="Scope token. Required unless --global")
    e.add_argument("--global", dest="global_scope", action="store_true", help="Explicitly query global scope")
    e.add_argument("--session-id", help="Optional session filter")
    e.add_argument("--from-ts-ms", type=int, help="Inclusive lower bound unix ms")
    e.add_argument("--to-ts-ms", type=int, help="Inclusive upper bound unix ms")
    e.add_argument("--type", dest="types", action="append", help="Event type filter (repeatable or comma-separated)")
    e.add_argument("--limit", type=int, default=50, help="Max rows (default: 50, max: 500)")
    e.add_argument("--include-payload", action="store_true", help="Include payload object in output")
    e.set_defaults(func=cmd_episodes_query)

    e = esub.add_parser("replay", help="Replay one session timeline")
    add_common(e)
    e.add_argument("session_id", help="Session id")
    e.add_argument("--scope", help="Scope token. Required unless --global")
    e.add_argument("--global", dest="global_scope", action="store_true", help="Explicitly query global scope")
    e.add_argument("--limit", type=int, default=200, help="Max rows (default: 200, max: 500)")
    e.add_argument("--include-payload", action="store_true", help="Include payload object in output")
    e.set_defaults(func=cmd_episodes_replay)

    e = esub.add_parser("redact", help="Redact payloads by event_id or session_id")
    add_common(e)
    e.add_argument("--event-id", help="Redact one event by event_id")
    e.add_argument("--session-id", help="Redact all events in a session (requires scope unless --global)")
    e.add_argument("--scope", help="Scope token for session redaction")
    e.add_argument("--global", dest="global_scope", action="store_true", help="Explicitly target global scope")
    e.add_argument("--replacement", choices=["null", "placeholder"], default="placeholder", help="Payload replacement strategy (default: placeholder)")
    e.set_defaults(func=cmd_episodes_redact)

    e = esub.add_parser("gc", help="Apply retention policy and delete old episodic events")
    add_common(e)
    e.add_argument("--scope", help="Scope token. Required unless --global")
    e.add_argument("--global", dest="global_scope", action="store_true", help="Explicitly target global scope")
    e.add_argument("--now-ts-ms", type=int, help="Retention reference time in unix ms (default: now)")
    e.add_argument("--policy", action="append", help="Override retention policy TYPE=DAYS or TYPE=forever (repeatable)")
    e.set_defaults(func=cmd_episodes_gc)

    sp = sub.add_parser("store", help="Proactively store a memory")
    add_common(sp)
    sp.add_argument("text", help="Memory content")
    sp.add_argument("--text-en", help="Optional English translation/summary")
    sp.add_argument("--lang", help="Original text language code (e.g., ko, ja, es)")
    sp.add_argument("--category", default="fact", choices=["fact", "preference", "decision", "entity", "task", "other"])
    sp.add_argument("--importance", type=float, default=0.7)
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--workspace", type=Path, help="Workspace root (default: cwd)")
    sp.set_defaults(func=cmd_store)

    sp = sub.add_parser("index", help="Build Markdown index for OpenClaw memory_search (Route A)")
    add_common(sp)
    sp.add_argument("--to", help=f"Output path (default: {DEFAULT_INDEX_PATH})")
    sp.add_argument("--limit", type=int, default=5000, help="Max observations to include")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("semantic", help="Semantic recall via OpenClaw memory_search (black-box embeddings)")
    add_common(sp)
    sp.add_argument("query", help="Search query")
    sp.add_argument("--limit", type=int, default=10, help="Max matched observation IDs to resolve")
    sp.add_argument("--max-results", type=int, default=8, help="memory_search maxResults")
    sp.add_argument("--min-score", type=float, default=0.0, help="memory_search minScore")
    sp.add_argument("--raw-limit", type=int, default=8, help="Include first N raw memory_search hits")
    sp.add_argument("--session-key", default="main", help="Gateway sessionKey for tools/invoke")
    sp.add_argument("--gateway-url", help="OpenClaw Gateway base URL (auto-detected if unset)")
    sp.add_argument("--gateway-token", help="OpenClaw Gateway token (auto-detected from ~/.openclaw/openclaw.json)")
    sp.add_argument("--agent-id", default="main", help="Target agent ID for Gateway (default: main)")
    sp.set_defaults(func=cmd_semantic)

    sp = sub.add_parser("triage", help="Deterministic local scan (heartbeat/cron)"
    )
    add_common(sp)
    sp.add_argument(
        "--mode",
        default="heartbeat",
        choices=["heartbeat", "observations", "cron-errors", "tasks"],
        help="Scan mode (default: heartbeat)",
    )
    sp.add_argument("--since-minutes", type=int, default=60, help="Look back window in minutes")
    sp.add_argument("--limit", type=int, default=10, help="Max matches to return")
    sp.add_argument("--keywords", help="Comma-separated keywords override (observations modes)")
    sp.add_argument(
        "--cron-jobs-path",
        dest="cron_jobs_path",
        help="Path to OpenClaw cron jobs store (default: ~/.openclaw/cron/jobs.json)",
    )
    sp.add_argument(
        "--tasks-since-minutes",
        dest="tasks_since_minutes",
        type=int,
        default=24 * 60,
        help="Tasks lookback window in minutes (default: 1440)",
    )
    sp.add_argument(
        "--importance-min",
        dest="importance_min",
        type=float,
        default=0.7,
        help="Min importance for tasks mode (default: 0.7)",
    )
    sp.add_argument(
        "--state-path",
        dest="state_path",
        help="State file for dedupe (default: ~/.openclaw/memory/openclaw-mem/triage-state.json)",
    )
    sp.add_argument(
        "--no-dedupe",
        dest="dedupe",
        action="store_false",
        default=True,
        help="Disable state dedupe; return all matches (manual debugging)",
    )
    sp.set_defaults(func=cmd_triage)

    sp = sub.add_parser("harvest", help="Auto-ingest and embed observations from log file")
    add_common(sp)
    sp.add_argument("--source", help="JSONL source file (default: ~/.openclaw/memory/openclaw-mem-observations.jsonl)")
    sp.add_argument(
        "--importance-scorer",
        dest="importance_scorer",
        default=None,
        help=(
            "Override importance autograde scorer for this run (env fallback: OPENCLAW_MEM_IMPORTANCE_SCORER). "
            "Use 'heuristic-v1' to enable, or 'off' to disable."
        ),
    )
    sp.add_argument("--archive-dir", help="Directory to move processed files (default: delete)")
    sp.add_argument("--embed", action="store_true", default=True, help="Run embedding after ingest (default: True)")
    sp.add_argument("--no-embed", dest="embed", action="store_false", help="Skip embedding")
    sp.add_argument(
        "--model",
        default=defaults.embed_model(),
        help="Embedding model (env: OPENCLAW_MEM_EMBED_MODEL)",
    )
    sp.add_argument(
        "--base-url",
        default=defaults.openai_base_url(),
        help="OpenAI API base URL (env: OPENCLAW_MEM_OPENAI_BASE_URL)",
    )
    sp.add_argument("--update-index", action="store_true", default=True, help="Update Route A index file after ingest (default: True)")
    sp.add_argument("--no-update-index", dest="update_index", action="store_false", help="Skip index update")
    sp.add_argument("--index-to", default=None, help=f"Index output path (default: {DEFAULT_INDEX_PATH})")
    sp.add_argument("--index-limit", type=int, default=5000, help="Index: max observations to include")
    sp.add_argument(
        "--embed-limit",
        type=int,
        default=1000,
        help="Max embeddings to compute during harvest (default: 1000)",
    )
    sp.set_defaults(func=cmd_harvest)

    sp = sub.add_parser("writeback-lancedb", help="Write graded metadata back into LanceDB rows")
    add_common(sp)
    sp.add_argument("--lancedb", required=True, help="LanceDB directory path")
    sp.add_argument("--table", required=True, help="LanceDB table name")
    sp.add_argument("--limit", type=int, default=50, help="Max SQLite rows to inspect (default: 50)")
    sp.add_argument(
        "--batch",
        type=int,
        default=25,
        help="Batch size for node writeback calls (default: 25)",
    )
    sp.add_argument(
        "--force",
        "--overwrite",
        dest="force",
        action="store_true",
        default=False,
        help="Overwrite existing metadata fields when incoming values are available",
    )
    sp.add_argument(
        "--force-fields",
        dest="force_fields",
        default=None,
        help=(
            "Comma-separated list of fields allowed to be overwritten when --force is set "
            "(importance, importance_label, scope, category, trust_tier)."
        ),
    )
    sp.add_argument("--dry-run", action="store_true", help="Dry-run mode: show receipts without writing")
    sp.set_defaults(func=cmd_writeback_lancedb)

    return p


def main() -> None:
    args = build_parser().parse_args()

    # Merge global flags (before subcommand) + per-command flags (after subcommand)
    base_db = os.environ.get("OPENCLAW_MEM_DB", DEFAULT_DB)
    args.db = getattr(args, "db", None) or getattr(args, "db_global", None) or base_db
    args.json = bool(getattr(args, "json", False) or getattr(args, "json_global", False))

    conn = _connect(args.db)
    args.func(conn, args)


if __name__ == "__main__":
    main()
