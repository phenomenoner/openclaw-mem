"""Citation-only use tracking and protected-tier decay candidates."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from openclaw_mem.core.lifecycle import is_soft_archived, state_from_detail


P1_KINDS = frozenset({"preference", "decision", "fact", "learning", "plan", "entity"})
P2_KINDS = frozenset({"event", "note", "tool"})
PRIORITIES = frozenset({"P0", "P1", "P2"})


def _parse_detail(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_time(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def priority_for(kind: Any, detail: Mapping[str, Any]) -> str:
    lifecycle = detail.get("lifecycle") if isinstance(detail.get("lifecycle"), Mapping) else {}
    explicit = str(lifecycle.get("priority") or "").strip().upper()
    if explicit in PRIORITIES:
        return explicit
    normalized_kind = str(kind or "note").strip().lower()
    return "P1" if normalized_kind in P1_KINDS else "P2"


def use_tracking_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    raw = str(os.getenv("OPENCLAW_MEM_USE_TRACKING", "1") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _selection_signature(refs: Sequence[str]) -> str:
    canonical = json.dumps(list(refs), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def refresh_selected_records(
    conn: sqlite3.Connection,
    *,
    selected_refs: Sequence[Any],
    ts: str,
    enabled: bool | None = None,
    max_refs: int = 64,
) -> dict[str, Any]:
    refs: list[str] = []
    seen: set[str] = set()
    for raw in selected_refs:
        ref = str(raw or "").strip()
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
        if len(refs) >= max(1, int(max_refs)):
            break
    ref_to_id: dict[str, int] = {}
    skipped: list[str] = []
    for ref in refs:
        prefix, separator, raw_id = ref.partition(":")
        if prefix != "obs" or not separator or not raw_id.isdigit() or int(raw_id) <= 0:
            skipped.append(ref)
            continue
        ref_to_id[ref] = int(raw_id)

    def receipt(*, status: str, refreshed: list[str], missing: list[str], before: dict[str, int], after: dict[str, int], error: str | None = None) -> dict[str, Any]:
        return {
            "kind": "openclaw-mem.pack.lifecycle-write.v1",
            "mode": "selected_pack_records_only",
            "status": status,
            "ts": ts,
            "selection": {
                "pack_selected_refs": refs,
                "refreshed_record_refs": refreshed,
                "skipped_record_refs": skipped,
                "missing_record_refs": missing,
                "selection_signature": _selection_signature(refs),
            },
            "mutation": {
                "memory_mutation": (
                    "detail_json.lifecycle_refresh"
                    if refreshed
                    else "failed_open"
                    if status == "failed_open"
                    else "none"
                ),
                "writes_observations": len(refreshed),
                "writes_embeddings": 0,
                "auto_archive_applied": 0,
                "auto_mutation_applied": len(refreshed),
                "hard_delete_applied": 0,
            },
            "lifecycle": {
                "last_used_at": ts,
                "used_count_before": before,
                "used_count_after": after,
                "archived_at_preserved": True,
            },
            "storage": {"field": "observations.detail_json.lifecycle", "error_code": error},
        }

    if not use_tracking_enabled(enabled):
        return receipt(status="disabled", refreshed=[], missing=[], before={}, after={})
    if bool(conn.execute("PRAGMA query_only").fetchone()[0]):
        return receipt(status="readonly", refreshed=[], missing=[], before={}, after={})
    ids = list(dict.fromkeys(ref_to_id.values()))
    if not ids:
        return receipt(status="no_observation_refs", refreshed=[], missing=[], before={}, after={})
    rows = conn.execute(
        f"SELECT id, detail_json FROM observations WHERE id IN ({','.join('?' for _ in ids)})",
        ids,
    ).fetchall()
    detail_by_id = {int(row[0]): _parse_detail(row[1]) for row in rows}
    missing = [ref for ref, obs_id in ref_to_id.items() if obs_id not in detail_by_id]
    refreshed: list[str] = []
    before_counts: dict[str, int] = {}
    after_counts: dict[str, int] = {}
    try:
        with conn:
            for ref, obs_id in ref_to_id.items():
                detail = detail_by_id.get(obs_id)
                if detail is None:
                    continue
                lifecycle = dict(detail.get("lifecycle") or {}) if isinstance(detail.get("lifecycle"), Mapping) else {}
                try:
                    before_count = max(0, int(lifecycle.get("used_count") or 0))
                except (TypeError, ValueError):
                    before_count = 0
                lifecycle["last_used_at"] = ts
                lifecycle["used_count"] = before_count + 1
                detail["lifecycle"] = lifecycle
                conn.execute(
                    "UPDATE observations SET detail_json = ? WHERE id = ?",
                    (json.dumps(detail, ensure_ascii=False, sort_keys=True), obs_id),
                )
                refreshed.append(ref)
                before_counts[ref] = before_count
                after_counts[ref] = before_count + 1
    except (sqlite3.OperationalError, sqlite3.IntegrityError) as exc:
        conn.rollback()
        return receipt(
            status="readonly" if isinstance(exc, sqlite3.OperationalError) and "readonly" in str(exc).lower() else "failed_open",
            refreshed=[],
            missing=missing,
            before={},
            after={},
            error=type(exc).__name__,
        )
    return receipt(status="updated", refreshed=refreshed, missing=missing, before=before_counts, after=after_counts)


def decay_candidates(
    conn: sqlite3.Connection,
    *,
    p1_unused_days: int = 90,
    p2_unused_days: int = 30,
    limit: int = 1000,
    scope: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    reference_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rows = conn.execute(
        "SELECT id, ts, kind, tool_name, summary, detail_json FROM observations ORDER BY id DESC LIMIT ?",
        (max(1, int(limit)),),
    ).fetchall()
    items: list[dict[str, Any]] = []
    protected_p0 = 0
    for row in rows:
        detail = _parse_detail(row["detail_json"])
        if scope and str(detail.get("scope") or "").strip() != str(scope).strip():
            continue
        if is_soft_archived(detail):
            continue
        if state_from_detail(detail) not in {"active", "consolidated", "stale"}:
            continue
        priority = priority_for(row["kind"], detail)
        if priority == "P0":
            protected_p0 += 1
            continue
        lifecycle = detail.get("lifecycle") if isinstance(detail.get("lifecycle"), Mapping) else {}
        last_used_at = _parse_time(lifecycle.get("last_used_at"))
        observed_at = _parse_time(row["ts"])
        reference = last_used_at or observed_at
        if reference is None:
            continue
        unused_days = max(0, int((reference_time - reference).total_seconds() // 86400))
        threshold = max(1, int(p1_unused_days if priority == "P1" else p2_unused_days))
        if unused_days < threshold:
            continue
        trust = str(detail.get("trust") or detail.get("trust_tier") or "unknown")
        items.append(
            {
                "id": int(row["id"]),
                "recordRef": f"obs:{int(row['id'])}",
                "priority": priority,
                "kind": str(row["kind"] or "note"),
                "trust": trust,
                "unused_days": unused_days,
                "threshold_days": threshold,
                "last_used_at": last_used_at.isoformat() if last_used_at else None,
                "summary_preview": str(row["summary"] or "")[:160],
            }
        )
    items.sort(key=lambda item: (-int(item["unused_days"]), int(item["id"])))
    return {
        "kind": "openclaw-mem.use-decay.candidates.v1",
        "thresholds": {"P1": max(1, int(p1_unused_days)), "P2": max(1, int(p2_unused_days))},
        "protected_p0": protected_p0,
        "count": len(items),
        "items": items,
    }
