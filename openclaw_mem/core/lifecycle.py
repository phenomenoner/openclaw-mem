"""Upgrade-safe memory lifecycle state and retrieval gates.

Lifecycle is orthogonal to trust: quarantined records remain governed by the
trust policy and are intentionally not a lifecycle state.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


CAPTURED = "captured"
CATEGORIZED = "categorized"
ACTIVE = "active"
CONSOLIDATED = "consolidated"
STALE = "stale"
SOFT_ARCHIVED = "soft-archived"

STATES = frozenset(
    {CAPTURED, CATEGORIZED, ACTIVE, CONSOLIDATED, STALE, SOFT_ARCHIVED}
)
LEGAL_TRANSITIONS = {
    CAPTURED: frozenset({CATEGORIZED}),
    CATEGORIZED: frozenset({ACTIVE}),
    ACTIVE: frozenset({CONSOLIDATED, STALE}),
    CONSOLIDATED: frozenset({ACTIVE, STALE}),
    STALE: frozenset({ACTIVE, SOFT_ARCHIVED}),
    SOFT_ARCHIVED: frozenset({ACTIVE}),
}
TRANSITION_KIND = "openclaw-mem.lifecycle.transition.v1"
HISTORY_LIMIT = 20


class LifecycleTransitionError(ValueError):
    def __init__(self, from_state: str, to_state: str):
        allowed = sorted(LEGAL_TRANSITIONS.get(from_state, ()))
        super().__init__(f"illegal lifecycle transition: {from_state} -> {to_state}")
        self.from_state = from_state
        self.to_state = to_state
        self.hint = (
            f"allowed next states from {from_state}: {', '.join(allowed)}"
            if allowed
            else f"set a supported lifecycle state: {', '.join(sorted(STATES))}"
        )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_detail(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def state_from_detail(detail: Mapping[str, Any] | Any) -> str:
    value = dict(detail) if isinstance(detail, Mapping) else parse_detail(detail)
    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        return ACTIVE
    state = str(lifecycle.get("state") or "").strip().lower()
    if state in STATES:
        return state
    # Preserve the meaning of the pre-state-machine soft-archive marker.
    if str(lifecycle.get("archived_at") or "").strip():
        return SOFT_ARCHIVED
    return ACTIVE


def is_soft_archived(detail: Mapping[str, Any] | Any) -> bool:
    return state_from_detail(detail) == SOFT_ARCHIVED


def filter_retrieval_results(
    conn: sqlite3.Connection,
    results: Sequence[Mapping[str, Any]],
    *,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    items = [dict(item) for item in results]
    if include_archived or not items:
        return items
    ids = [int(item["id"]) for item in items if item.get("id") is not None]
    if not ids:
        return items
    rows = conn.execute(
        f"SELECT id, detail_json FROM observations WHERE id IN ({','.join('?' for _ in ids)})",
        ids,
    ).fetchall()
    archived = {
        int(row[0]) for row in rows if is_soft_archived(row[1])
    }
    return [item for item in items if int(item.get("id", -1)) not in archived]


def state_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {state: 0 for state in sorted(STATES)}
    for row in conn.execute("SELECT detail_json FROM observations"):
        state = state_from_detail(row[0])
        counts[state] = counts.get(state, 0) + 1
    return counts


def transition(
    conn: sqlite3.Connection,
    obs_id: int,
    to: str,
    reason_code: str,
    actor: str,
    *,
    at: str | None = None,
) -> dict[str, Any]:
    target = str(to or "").strip().lower()
    if target not in STATES:
        raise ValueError(f"unsupported lifecycle state: {target or '<empty>'}")
    reason = str(reason_code or "").strip()
    actor_name = str(actor or "").strip()
    if not reason:
        raise ValueError("lifecycle reason_code is required")
    if not actor_name:
        raise ValueError("lifecycle actor is required")

    row = conn.execute(
        "SELECT detail_json FROM observations WHERE id = ?", (int(obs_id),)
    ).fetchone()
    if row is None:
        raise ValueError(f"observation not found: {int(obs_id)}")
    detail = parse_detail(row[0])
    lifecycle_raw = detail.get("lifecycle")
    lifecycle = dict(lifecycle_raw) if isinstance(lifecycle_raw, Mapping) else {}
    current = state_from_detail(detail)
    changed = current != target
    if changed and target not in LEGAL_TRANSITIONS.get(current, frozenset()):
        raise LifecycleTransitionError(current, target)

    occurred_at = str(at or _utcnow_iso())
    history_raw = lifecycle.get("history")
    history = [dict(item) for item in history_raw if isinstance(item, Mapping)] if isinstance(history_raw, list) else []
    history.append(
        {
            "from": current,
            "to": target,
            "reason_code": reason,
            "actor": actor_name,
            "at": occurred_at,
            "changed": changed,
        }
    )
    lifecycle.update(
        {
            "state": target,
            "updated_at": occurred_at,
            "last_reason": reason,
            "history": history[-HISTORY_LIMIT:],
        }
    )
    if target == SOFT_ARCHIVED:
        lifecycle.setdefault("archived_at", occurred_at)
        lifecycle.setdefault("archive_reason_code", reason)
    detail["lifecycle"] = lifecycle
    conn.execute(
        "UPDATE observations SET detail_json = ? WHERE id = ?",
        (json.dumps(detail, ensure_ascii=False, sort_keys=True), int(obs_id)),
    )
    return {
        "kind": TRANSITION_KIND,
        "recordRef": f"obs:{int(obs_id)}",
        "observation_id": int(obs_id),
        "from": current,
        "to": target,
        "reason_code": reason,
        "actor": actor_name,
        "at": occurred_at,
        "changed": changed,
        "evidence_refs": [f"obs:{int(obs_id)}"],
    }
