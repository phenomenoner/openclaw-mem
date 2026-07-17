"""Read-only goal primitive helpers.

The first product slice intentionally exposes status only.  It normalizes a
controller/goal receipt into a small status object and validates that the result
is safe to use as a low-blast-radius goal readback.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "openclaw-mem.goal-status.v0"
ACTIVE_STATUSES = {"active", "in_progress", "blocked", "paused"}
CLOSED_STATUSES = {"complete", "completed", "closed", "cancelled"}
VALID_STATUSES = ACTIVE_STATUSES | CLOSED_STATUSES | {"unknown"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_goal_receipt(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("goal receipt must be a JSON object")
    return payload


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


def _goal_obj(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    goal = receipt.get("goal")
    return goal if isinstance(goal, Mapping) else receipt


def build_goal_status(receipt: Mapping[str, Any], *, source_ref: str | None = None) -> dict[str, Any]:
    goal = _goal_obj(receipt)
    goal_id = str(_pick(goal, "goal_id", "id") or _pick(receipt, "goal_id", "id") or "unknown-goal")
    objective = str(_pick(goal, "objective", "summary") or _pick(receipt, "objective", "summary") or "")
    status = str(_pick(goal, "status") or _pick(receipt, "status") or "unknown").strip().lower()
    updated_at = _pick(goal, "updated_at", "recorded_at") or _pick(receipt, "updated_at", "recorded_at")
    phase = _pick(goal, "phase", "phase_goal") or _pick(receipt, "phase", "phase_goal")
    next_gate = _pick(goal, "next_gate", "current_gate") or _pick(receipt, "next_gate", "current_gate")
    verifier = _pick(goal, "completion_verifier", "verifier_receipt") or _pick(receipt, "completion_verifier", "verifier_receipt")
    continuation = _pick(goal, "continuation_owner", "owner") or _pick(receipt, "continuation_owner", "owner")
    stop_loss = _pick(goal, "stop_loss", "stop_loss_state") or _pick(receipt, "stop_loss", "stop_loss_state")

    errors: list[str] = []
    warnings: list[str] = []
    if not objective:
        errors.append("goal objective/summary is required")
    if status not in VALID_STATUSES:
        errors.append(f"goal status must be one of {sorted(VALID_STATUSES)}")
    if status in ACTIVE_STATUSES and not next_gate:
        warnings.append("active goal has no next_gate/current_gate")
    if status in ACTIVE_STATUSES and not continuation:
        warnings.append("active goal has no continuation owner")

    active = status in ACTIVE_STATUSES
    closed = status in CLOSED_STATUSES
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not errors,
        "writes_performed": False,
        "source_ref": source_ref,
        "goal": {
            "goal_id": goal_id,
            "objective": objective,
            "status": status,
            "phase": phase,
            "updated_at": updated_at,
            "next_gate": next_gate,
            "has_verifier": verifier is not None,
            "continuation_owner": continuation,
            "stop_loss": stop_loss,
            "active": active,
            "closed": closed,
        },
        "errors": errors,
        "warnings": warnings,
        "checked_at": now_iso(),
    }


def render_goal_status(status: Mapping[str, Any]) -> str:
    goal = status.get("goal") if isinstance(status.get("goal"), Mapping) else {}
    lines = [
        f"goal_status goal_id={goal.get('goal_id')} status={goal.get('status')} writes_performed=false"
    ]
    if goal.get("next_gate"):
        lines.append(f"next_gate={goal.get('next_gate')}")
    if goal.get("continuation_owner"):
        lines.append(f"continuation_owner={goal.get('continuation_owner')}")
    if status.get("errors"):
        lines.append("errors=" + ",".join(str(x) for x in status.get("errors") or []))
    if status.get("warnings"):
        lines.append("warnings=" + ",".join(str(x) for x in status.get("warnings") or []))
    return " ".join(lines)
