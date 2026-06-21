from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


MARKER_PREFIX = "<<ocm:artifact:v1:sha256:"
MARKER_RE = re.compile(r"^<<ocm:artifact:v1:sha256:([0-9A-Fa-f]{64})>>>$")
HASH_RE = re.compile(r"^sha256:([0-9A-Fa-f]{64})$")
PUT_RECEIPT_SCHEMA = "openclaw-mem.pack-artifact-put-receipt.v1"
RETRIEVE_RECEIPT_SCHEMA = "openclaw-mem.pack-retrieve-receipt.v1"
PACK_RECEIPT_SCHEMA = "openclaw-mem.pack-receipt.v1"
OBSERVE_SCHEMA = "openclaw-mem.pack-observe-report.v1"

DEFAULT_ADMISSION = {
    "minPackBytes": 4096,
    "minPackTokensEstimate": 1000,
    "maxArtifactBytes": 10 * 1024 * 1024,
    "maxStoreBytesPerSession": 100 * 1024 * 1024,
}
MAX_STRATEGY_FIELD_CHARS = 240
MAX_STRATEGY_PATH_CHARS = 160
TRUST_ORDER = {
    "unknown": 0,
    "low": 1,
    "tool-output": 2,
    "user-provided": 2,
    "trusted": 3,
    "high": 4,
    "global-imported": 4,
}


def default_store_path(state_root: Path | str) -> Path:
    return Path(state_root) / "memory" / "pack-artifacts" / "openclaw-mem-pack-artifacts.sqlite"


def artifact_hash(raw_bytes: bytes | bytearray) -> str:
    return f"sha256:{hashlib.sha256(bytes(raw_bytes)).hexdigest()}"


def parse_marker(marker: str) -> str:
    if not isinstance(marker, str):
        raise ValueError("marker must be a string")
    try:
        marker.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("marker must be ASCII") from exc
    match = MARKER_RE.fullmatch(marker)
    if not match:
        raise ValueError("invalid openclaw-mem artifact marker")
    return f"sha256:{match.group(1).lower()}"


def put_artifact(
    raw_bytes: bytes | bytearray,
    metadata: Mapping[str, Any],
    *,
    store_path: Path | str,
    admission: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    raw = bytes(raw_bytes)
    store = Path(store_path)
    conn = _connect_store(store)
    try:
        meta = _normalize_metadata(metadata, now=now)
        config = _admission(admission)
        digest = artifact_hash(raw)
        marker = _marker_for_hash(digest)

        duplicate = _find_record(conn, digest, meta["agentId"], meta["sessionKey"])
        if duplicate is not None:
            receipt = _put_receipt(
                meta,
                store,
                decision="stored",
                reason="duplicate-existing-artifact",
                digest=digest,
                marker=marker,
                record_id=int(duplicate["id"]),
                duplicate=True,
                bytes_stored=0,
                latency_ms=_latency_ms(started),
            )
            return {
                "decision": "stored",
                "reason": "duplicate-existing-artifact",
                "hash": digest,
                "marker": marker,
                "recordId": int(duplicate["id"]),
                "duplicate": True,
                "receipt": receipt,
            }

        denial = _admission_denial(raw, meta, config, conn)
        if denial:
            receipt = _put_receipt(
                meta,
                store,
                decision="blocked",
                reason="admission-denied",
                digest=digest,
                marker=marker,
                record_id=None,
                duplicate=False,
                bytes_stored=0,
                latency_ms=_latency_ms(started),
            )
            return {
                "decision": "blocked",
                "reason": "admission-denied",
                "hash": digest,
                "marker": marker,
                "recordId": None,
                "duplicate": False,
                "receipt": receipt,
            }

        cur = conn.execute(
            """
            INSERT INTO pack_artifacts (
              artifact_hash, agent_id, session_key, source_kind, source_id, trust_level, scope,
              created_at, expires_at, ttl_policy_json, content_type, producer, command_or_tool,
              receipt_id, byte_length, raw_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest,
                meta["agentId"],
                meta["sessionKey"],
                meta["sourceKind"],
                meta["sourceId"],
                meta["trustLevel"],
                meta["scope"],
                meta["createdAt"],
                meta.get("expiresAt"),
                json.dumps(meta["ttlPolicy"], sort_keys=True),
                meta["contentType"],
                meta["producer"],
                meta["commandOrTool"],
                meta["receiptId"],
                len(raw),
                raw,
            ),
        )
        conn.commit()
        record_id = int(cur.lastrowid)
        receipt = _put_receipt(
            meta,
            store,
            decision="stored",
            reason="stored",
            digest=digest,
            marker=marker,
            record_id=record_id,
            duplicate=False,
            bytes_stored=len(raw),
            latency_ms=_latency_ms(started),
        )
        return {
            "decision": "stored",
            "reason": "stored",
            "hash": digest,
            "marker": marker,
            "recordId": record_id,
            "duplicate": False,
            "receipt": receipt,
        }
    finally:
        conn.close()


def retrieve_artifact(
    marker_or_hash: str,
    requester_metadata: Mapping[str, Any],
    *,
    store_path: Path | str,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    digest = _parse_marker_or_hash(marker_or_hash)
    marker = _marker_for_hash(digest)
    store = Path(store_path)
    conn = _connect_store(store)
    try:
        requester = _normalize_metadata(requester_metadata, now=now)
        receipt = {
            "schema": RETRIEVE_RECEIPT_SCHEMA,
            "retrievedAt": _iso(now),
            "artifactHash": digest,
            "marker": marker,
            "agentId": requester["agentId"],
            "sessionKey": requester["sessionKey"],
            "requester": requester.get("producer", "operator"),
            "decision": "missing",
            "bytesReturned": 0,
            "latencyMs": 0,
            "scopeDecision": "not-evaluated",
            "trustDecision": "not-evaluated",
        }
        row = _select_record(conn, digest, requester)
        if row is None:
            receipt["latencyMs"] = _latency_ms(started)
            return {"decision": "missing", "receipt": receipt}

        expires_at = row["expires_at"]
        if expires_at and _parse_iso(expires_at) <= _now(now):
            receipt["decision"] = "expired"
            receipt["latencyMs"] = _latency_ms(started)
            return {"decision": "expired", "receipt": receipt}

        if not _scope_allowed(str(row["scope"]), requester["scope"]):
            receipt["decision"] = "scope-denied"
            receipt["scopeDecision"] = "denied"
            receipt["latencyMs"] = _latency_ms(started)
            return {"decision": "scope-denied", "receipt": receipt}
        receipt["scopeDecision"] = "allowed"

        if not _trust_allowed(str(row["trust_level"]), requester["trustLevel"]):
            receipt["decision"] = "trust-denied"
            receipt["trustDecision"] = "denied"
            receipt["latencyMs"] = _latency_ms(started)
            return {"decision": "trust-denied", "receipt": receipt}
        receipt["trustDecision"] = "allowed"

        raw = bytes(row["raw_bytes"])
        receipt["decision"] = "returned"
        receipt["bytesReturned"] = len(raw)
        receipt["latencyMs"] = _latency_ms(started)
        return {"decision": "returned", "rawBytes": raw, "receipt": receipt}
    finally:
        conn.close()


def pack_candidate(
    raw_bytes: bytes | bytearray,
    metadata: Mapping[str, Any],
    *,
    store_path: Path | str,
    admission: Optional[Mapping[str, Any]] = None,
    strategy_config: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    raw = bytes(raw_bytes)
    meta = _normalize_metadata(metadata, now=now)
    strategy = _select_strategy(raw, meta)
    disabled = _disabled_strategies(strategy_config)
    if strategy in disabled:
        return _pack_result(
            raw,
            meta,
            decision="pass-through",
            reason="strategy-disabled",
            strategy=strategy,
            content=raw,
            marker=None,
            digest=None,
            started=started,
        )

    config = _admission(admission)
    if len(raw) < int(config["minPackBytes"]) and _estimate_tokens(raw) < int(config["minPackTokensEstimate"]):
        return _pack_result(
            raw,
            meta,
            decision="blocked",
            reason="admission-denied",
            strategy=strategy,
            content=raw,
            marker=None,
            digest=None,
            started=started,
        )

    digest = artifact_hash(raw)
    marker = _marker_for_hash(digest)
    packed = _apply_strategy(raw, strategy, marker)
    if packed is None:
        return _pack_result(
            raw,
            meta,
            decision="blocked",
            reason="unsafe-type",
            strategy=strategy,
            content=raw,
            marker=None,
            digest=None,
            started=started,
        )
    packed_bytes = packed.encode("utf-8")
    if len(packed_bytes) >= len(raw) or _estimate_tokens(packed_bytes) >= _estimate_tokens(raw):
        return _pack_result(
            raw,
            meta,
            decision="blocked",
            reason="not-smaller",
            strategy=strategy,
            content=raw,
            marker=None,
            digest=None,
            started=started,
        )

    put = put_artifact(raw, meta, store_path=store_path, admission=config, now=now)
    if put["decision"] != "stored":
        return _pack_result(
            raw,
            meta,
            decision="blocked",
            reason="admission-denied",
            strategy=strategy,
            content=raw,
            marker=None,
            digest=put["hash"],
            started=started,
        )

    return _pack_result(
        raw,
        meta,
        decision="packed",
        reason="stored-and-packed",
        strategy=strategy,
        content=packed_bytes,
        marker=put["marker"],
        digest=put["hash"],
        started=started,
    )


def validate_canary_schema(canary: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if canary.get("schema") != "openclaw-mem.pack-canary.v1":
        errors.append("schema must be openclaw-mem.pack-canary.v1")
    for key in ("canaryId", "strategy", "artifactHash", "marker", "expectedRetrievalDecision", "createdAt"):
        if not str(canary.get(key) or "").strip():
            errors.append(f"{key} is required")
    try:
        if canary.get("marker"):
            marker_hash = parse_marker(str(canary.get("marker")))
            if canary.get("artifactHash") and marker_hash != _parse_marker_or_hash(str(canary.get("artifactHash"))):
                errors.append("marker does not match artifactHash")
    except ValueError:
        errors.append("marker must be a full artifact marker")
    try:
        if canary.get("artifactHash"):
            _parse_marker_or_hash(str(canary.get("artifactHash")))
    except ValueError:
        errors.append("artifactHash must be sha256:<64-hex>")
    return {"valid": not errors, "errors": errors}


def collect_observe_report(
    receipts_dir: Path | str,
    *,
    strategy_config: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    receipts = _read_receipts(Path(receipts_dir))
    per_strategy: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"packed": 0, "blocked": 0, "passThrough": 0, "estimatedTokensSaved": 0}
    )
    retrieval = Counter()
    disabled_observed = Counter()
    latency = Counter()
    for receipt in receipts:
        schema = receipt.get("schema")
        if schema == PACK_RECEIPT_SCHEMA:
            strategy = str(receipt.get("strategy") or "unknown")
            decision = str(receipt.get("decision") or "")
            if decision == "packed":
                per_strategy[strategy]["packed"] += 1
            elif decision == "blocked":
                per_strategy[strategy]["blocked"] += 1
            else:
                per_strategy[strategy]["passThrough"] += 1
            if receipt.get("reason") == "strategy-disabled":
                disabled_observed[strategy] += 1
            before = _safe_int(receipt.get("tokensBefore"))
            after = _safe_int(receipt.get("tokensAfter"))
            per_strategy[strategy]["estimatedTokensSaved"] += max(0, before - after)
        elif schema == RETRIEVE_RECEIPT_SCHEMA:
            retrieval[str(receipt.get("decision") or "unknown")] += 1
        elif schema == "openclaw-mem.pack-canary-receipt.v1":
            retrieval["_canary_total"] += 1
            if receipt.get("passed") is False or str(receipt.get("decision") or "").lower() in {"failed", "fail"}:
                retrieval["_canary_failed"] += 1
        if "latencyMs" in receipt:
            latency[_latency_bucket(_safe_int(receipt.get("latencyMs")))] += 1
    configured_disabled = sorted(_disabled_strategies(strategy_config))
    return {
        "schema": OBSERVE_SCHEMA,
        "disabledStrategies": {
            "configured": configured_disabled,
            "observed": dict(disabled_observed),
        },
        "perStrategy": dict(per_strategy),
        "retrieval": {
            "returned": int(retrieval["returned"]),
            "missing": int(retrieval["missing"]),
            "expired": int(retrieval["expired"]),
            "scope-denied": int(retrieval["scope-denied"]),
            "trust-denied": int(retrieval["trust-denied"]),
        },
        "latency": dict(latency),
        "canary": {
            "allGreen": int(retrieval["_canary_failed"]) == 0,
            "failed": int(retrieval["_canary_failed"]),
            "total": int(retrieval["_canary_total"]),
        },
    }


def _connect_store(store_path: Path) -> sqlite3.Connection:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(store_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pack_artifacts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          artifact_hash TEXT NOT NULL,
          agent_id TEXT NOT NULL,
          session_key TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_id TEXT NOT NULL,
          trust_level TEXT NOT NULL,
          scope TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          ttl_policy_json TEXT NOT NULL,
          content_type TEXT NOT NULL,
          producer TEXT NOT NULL,
          command_or_tool TEXT NOT NULL,
          receipt_id TEXT NOT NULL,
          byte_length INTEGER NOT NULL,
          raw_bytes BLOB NOT NULL,
          UNIQUE(artifact_hash, agent_id, session_key)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pack_artifacts_hash ON pack_artifacts(artifact_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pack_artifacts_session ON pack_artifacts(agent_id, session_key)")
    conn.commit()
    return conn


def _normalize_metadata(metadata: Mapping[str, Any], *, now: Optional[datetime]) -> dict[str, Any]:
    current = _now(now)
    ttl_policy = _normalize_ttl(metadata.get("ttlPolicy"), current)
    return {
        "agentId": str(metadata.get("agentId") or metadata.get("agent_id") or "main"),
        "sessionKey": str(metadata.get("sessionKey") or metadata.get("session_key") or "default"),
        "sourceKind": str(metadata.get("sourceKind") or metadata.get("source_kind") or "tool-output"),
        "sourceId": str(metadata.get("sourceId") or metadata.get("source_id") or "unknown"),
        "trustLevel": str(metadata.get("trustLevel") or metadata.get("trust_level") or "unknown"),
        "scope": str(metadata.get("scope") or "session"),
        "contentType": str(metadata.get("contentType") or metadata.get("content_type") or "text/plain"),
        "producer": str(metadata.get("producer") or "tool"),
        "commandOrTool": str(metadata.get("commandOrTool") or metadata.get("command_or_tool") or ""),
        "receiptId": str(metadata.get("receiptId") or metadata.get("receipt_id") or ""),
        "ttlPolicy": ttl_policy,
        "createdAt": _iso(current),
        "expiresAt": ttl_policy.get("expiresAt"),
    }


def _normalize_ttl(value: Any, now: datetime) -> dict[str, Any]:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or value.get("mode") or "session")
        seconds = value.get("seconds")
        expires_at = value.get("expiresAt") or value.get("expires_at")
        if seconds is not None:
            expires_at = _iso(now + timedelta(seconds=int(seconds)))
        return {
            "kind": kind,
            "expiresAt": expires_at,
            "maxArtifactBytes": int(value.get("maxArtifactBytes") or DEFAULT_ADMISSION["maxArtifactBytes"]),
            "maxStoreBytesPerSession": int(
                value.get("maxStoreBytesPerSession") or DEFAULT_ADMISSION["maxStoreBytesPerSession"]
            ),
        }
    return {
        "kind": str(value or "session"),
        "expiresAt": None,
        "maxArtifactBytes": DEFAULT_ADMISSION["maxArtifactBytes"],
        "maxStoreBytesPerSession": DEFAULT_ADMISSION["maxStoreBytesPerSession"],
    }


def _admission(admission: Optional[Mapping[str, Any]]) -> dict[str, int]:
    out = dict(DEFAULT_ADMISSION)
    if isinstance(admission, Mapping):
        for key in out:
            if key in admission:
                out[key] = int(admission[key])
    return out


def _admission_denial(raw: bytes, meta: Mapping[str, Any], config: Mapping[str, int], conn: sqlite3.Connection) -> bool:
    ttl = meta["ttlPolicy"]
    max_artifact = min(int(config["maxArtifactBytes"]), int(ttl["maxArtifactBytes"]))
    if len(raw) > max_artifact:
        return True
    max_session = min(int(config["maxStoreBytesPerSession"]), int(ttl["maxStoreBytesPerSession"]))
    row = conn.execute(
        "SELECT COALESCE(SUM(byte_length), 0) AS total FROM pack_artifacts WHERE agent_id=? AND session_key=?",
        (meta["agentId"], meta["sessionKey"]),
    ).fetchone()
    return int(row["total"] or 0) + len(raw) > max_session


def _find_record(conn: sqlite3.Connection, digest: str, agent_id: str, session_key: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pack_artifacts WHERE artifact_hash=? AND agent_id=? AND session_key=?",
        (digest, agent_id, session_key),
    ).fetchone()


def _select_record(conn: sqlite3.Connection, digest: str, requester: Mapping[str, Any]) -> Optional[sqlite3.Row]:
    rows = conn.execute("SELECT * FROM pack_artifacts WHERE artifact_hash=? ORDER BY id ASC", (digest,)).fetchall()
    if not rows:
        return None
    for row in rows:
        if row["agent_id"] == requester["agentId"] and row["session_key"] == requester["sessionKey"]:
            return row
    for row in rows:
        if row["session_key"] == requester["sessionKey"]:
            return row
    return rows[0]


def _parse_marker_or_hash(value: str) -> str:
    if value.startswith(MARKER_PREFIX):
        return parse_marker(value)
    match = HASH_RE.fullmatch(value)
    if not match:
        raise ValueError("artifact lookup requires marker or sha256:<64-hex>")
    return f"sha256:{match.group(1).lower()}"


def _marker_for_hash(digest: str) -> str:
    return f"{MARKER_PREFIX}{_parse_marker_or_hash(digest).split(':', 1)[1]}>>>"


def _scope_allowed(stored_scope: str, requester_scope: str) -> bool:
    if stored_scope in {"global-imported", "global", "public"}:
        return True
    return stored_scope == requester_scope


def _trust_allowed(stored_trust: str, requester_trust: str) -> bool:
    return TRUST_ORDER.get(str(requester_trust), 0) >= TRUST_ORDER.get(str(stored_trust), 0)


def _put_receipt(
    meta: Mapping[str, Any],
    store: Path,
    *,
    decision: str,
    reason: str,
    digest: str,
    marker: str,
    record_id: Optional[int],
    duplicate: bool,
    bytes_stored: int,
    latency_ms: int,
) -> dict[str, Any]:
    return {
        "schema": PUT_RECEIPT_SCHEMA,
        "storePath": str(store),
        "decision": decision,
        "reason": reason,
        "artifactHash": digest,
        "marker": marker,
        "recordId": record_id,
        "duplicate": duplicate,
        "bytesStored": bytes_stored,
        "latencyMs": latency_ms,
        "metadata": _receipt_metadata(meta),
    }


def _receipt_metadata(meta: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "agentId": meta["agentId"],
        "sessionKey": meta["sessionKey"],
        "sourceKind": meta["sourceKind"],
        "sourceId": meta["sourceId"],
        "trustLevel": meta["trustLevel"],
        "scope": meta["scope"],
        "contentType": meta["contentType"],
        "producer": meta["producer"],
        "commandOrTool": meta["commandOrTool"],
        "receiptId": meta["receiptId"],
        "ttlPolicy": meta["ttlPolicy"],
    }


def _pack_result(
    raw: bytes,
    meta: Mapping[str, Any],
    *,
    decision: str,
    reason: str,
    strategy: str,
    content: bytes,
    marker: Optional[str],
    digest: Optional[str],
    started: float,
) -> dict[str, Any]:
    receipt = {
        "schema": PACK_RECEIPT_SCHEMA,
        "decision": decision,
        "reason": reason,
        "strategy": strategy,
        "lossMode": "structure-preserving" if decision == "packed" else "pass-through",
        "artifactHash": digest,
        "marker": marker,
        "tokensBefore": _estimate_tokens(raw),
        "tokensAfter": _estimate_tokens(content),
        "bytesBefore": len(raw),
        "bytesAfter": len(content),
        "latencyMs": _latency_ms(started),
        "metadata": _receipt_metadata(meta),
    }
    result = {
        "decision": decision,
        "reason": reason,
        "strategy": strategy,
        "content": content,
        "receipt": receipt,
    }
    if marker:
        result["marker"] = marker
    if digest:
        result["hash"] = digest
    return result


def _select_strategy(raw: bytes, meta: Mapping[str, Any]) -> str:
    source = str(meta.get("sourceKind") or "")
    content_type = str(meta.get("contentType") or "")
    if source == "search-results":
        return "search-results-v1"
    if source == "log":
        return "log-anomaly-v1"
    if "json" in content_type:
        return "json-shape-v1"
    return "log-anomaly-v1"


def _disabled_strategies(config: Optional[Mapping[str, Any]]) -> set[str]:
    if not isinstance(config, Mapping):
        return set()
    strategies = config.get("strategies")
    disabled = set()
    if isinstance(strategies, Mapping):
        for name, value in strategies.items():
            if isinstance(value, Mapping) and value.get("enabled") is False:
                disabled.add(str(name))
    for name in config.get("disabledStrategies") or []:
        disabled.add(str(name))
    return disabled


def _apply_strategy(raw: bytes, strategy: str, marker: str) -> Optional[str]:
    text = raw.decode("utf-8", errors="replace")
    if strategy == "json-shape-v1":
        return _json_shape(text, marker)
    if strategy == "log-anomaly-v1":
        return _log_anomaly(text, marker)
    if strategy == "search-results-v1":
        return _search_results(text, marker)
    return None


def _json_shape(text: str, marker: str) -> Optional[str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("items") if isinstance(payload, dict) else [payload]
    if not isinstance(rows, list):
        rows = [payload]
    fields: list[str] = []
    anomalies: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            for key in row:
                field = _bounded_text(str(key), MAX_STRATEGY_PATH_CHARS)
                if field not in fields:
                    fields.append(field)
            row_text = json.dumps(row, sort_keys=True)
            lower = row_text.lower()
            if any(word in lower for word in ("error", "failed", "exception", "panic")):
                anomalies.append(_bounded_text(row_text, MAX_STRATEGY_FIELD_CHARS))
    first = [_bounded_json(row) for row in rows[:3]]
    last = [_bounded_json(row) for row in rows[-3:]]
    omitted = max(0, len(rows) - len(first) - len(last) - len(anomalies))
    parts = [
        "openclaw-mem packed artifact strategy: json-shape-v1",
        f"rowCount: {len(rows)}",
        f"fields: {', '.join(fields)}",
        f"anomalies: {' | '.join(anomalies[:8])}",
        f"firstRows: {' | '.join(first)}",
        f"lastRows: {' | '.join(last)}",
        f"omittedRows: {omitted}",
        f"artifactMarker: {marker}",
    ]
    return "\n".join(parts) + "\n"


def _log_anomaly(text: str, marker: str) -> str:
    lines = text.splitlines()
    anomalies = []
    for idx, line in enumerate(lines, start=1):
        lower = line.lower()
        if any(word in lower for word in ("error", "warn", "fail", "panic", "exception", "traceback")):
            anomalies.append(f"{idx}: {_bounded_text(line)}")
    first = [_bounded_text(line) for line in lines[:5]]
    last = [_bounded_text(line) for line in lines[-5:]]
    omitted = max(0, len(lines) - len(first) - len(last) - len(anomalies))
    return "\n".join(
        [
            "openclaw-mem packed artifact strategy: log-anomaly-v1",
            f"lineCount: {len(lines)}",
            f"firstLines: {' | '.join(first)}",
            f"lastLines: {' | '.join(last)}",
            f"anomalies: {' | '.join(anomalies[:20])}",
            f"omittedLines: {omitted}",
            f"artifactMarker: {marker}",
        ]
    ) + "\n"


def _search_results(text: str, marker: str) -> Optional[str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    matches = payload.get("matches") or payload.get("results") or []
    if not isinstance(matches, list):
        return None
    query = str(payload.get("query") or "")
    histogram = Counter(_bounded_text(str(item.get("path") or item.get("file") or "-"), MAX_STRATEGY_PATH_CHARS) for item in matches if isinstance(item, Mapping))
    first = []
    for item in matches[:8]:
        if not isinstance(item, Mapping):
            continue
        first.append(
            f"{_bounded_text(str(item.get('path') or item.get('file') or '-'), MAX_STRATEGY_PATH_CHARS)}:{item.get('line') or 0} {_bounded_text(str(item.get('snippet') or item.get('text') or ''))}"
        )
    top_paths = [path for path, _count in histogram.most_common(8)]
    return "\n".join(
        [
            "openclaw-mem packed artifact strategy: search-results-v1",
            f"query: {_bounded_text(query)}",
            f"totalMatches: {_safe_int(payload.get('totalMatches'), len(matches))}",
            f"topPaths: {', '.join(top_paths)}",
            f"pathHistogram: {dict(histogram)}",
            f"firstMatches: {' | '.join(first)}",
            f"omittedMatches: {max(0, len(matches) - len(first))}",
            f"artifactMarker: {marker}",
        ]
    ) + "\n"


def _escape_marker_like(text: str) -> str:
    return text.replace("<<ocm:artifact:", "[escaped ocm artifact marker:")


def _bounded_json(value: Any, max_chars: int = MAX_STRATEGY_FIELD_CHARS) -> str:
    try:
        text = json.dumps(value, sort_keys=True)
    except TypeError:
        text = str(value)
    return _bounded_text(text, max_chars)


def _bounded_text(text: str, max_chars: int = MAX_STRATEGY_FIELD_CHARS) -> str:
    escaped = _escape_marker_like(str(text)).replace("\r", "\\r").replace("\n", "\\n")
    if len(escaped) <= max_chars:
        return escaped
    return escaped[: max(0, max_chars - 14)] + "...<truncated>"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _estimate_tokens(data: bytes) -> int:
    return max(1, (len(data) + 3) // 4)


def _latency_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _latency_bucket(ms: int) -> str:
    if ms <= 10:
        return "0-10ms"
    if ms <= 100:
        return "11-100ms"
    if ms <= 1000:
        return "101-1000ms"
    return "1000ms+"


def _now(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: Optional[datetime]) -> str:
    return _now(value).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _read_receipts(receipts_dir: Path) -> list[dict[str, Any]]:
    out = []
    if not receipts_dir.exists():
        return out
    for path in receipts_dir.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out
