"""Convert controller/goal receipts into packable active-line context.

This module has no dependency on a live controller. It reads an already-produced
receipt/status object and emits a small ContextPack-compatible item list.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "openclaw-mem.active-line-context.v0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_receipt(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("active-line receipt must be a JSON object")
    return data


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _goal_from_receipt(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    goal = receipt.get("goal")
    return goal if isinstance(goal, Mapping) else receipt


def build_active_line_context(receipt: Mapping[str, Any], *, source_ref: str | None = None) -> dict[str, Any]:
    """Return a bounded ContextPack-like active-line context object."""

    goal = _goal_from_receipt(receipt)
    goal_id = str(_pick(goal, "goal_id", "id") or _pick(receipt, "goal_id", "id") or "unknown-goal")
    objective = str(_pick(goal, "objective", "summary") or _pick(receipt, "objective", "summary") or "No objective supplied")
    status = str(_pick(goal, "status") or _pick(receipt, "status") or "unknown")
    updated_at = _pick(goal, "updated_at", "recorded_at") or _pick(receipt, "updated_at", "recorded_at")
    next_gate = _pick(goal, "next_gate", "current_gate") or _pick(receipt, "next_gate", "current_gate")
    stop_loss = _pick(goal, "stop_loss", "stop_loss_state") or _pick(receipt, "stop_loss", "stop_loss_state")
    verifier = _pick(goal, "completion_verifier", "verifier_receipt") or _pick(receipt, "completion_verifier", "verifier_receipt")

    lines = [f"Active line `{goal_id}` is {status}: {objective}"]
    if next_gate:
        lines.append(f"Current gate: {next_gate}")
    if stop_loss:
        lines.append(f"Stop-loss: {stop_loss}")
    if verifier:
        lines.append("Verifier receipt present.")

    item = {
        "recordRef": f"active-line:{goal_id}",
        "layer": "L0",
        "type": "active_line",
        "importance": "must_remember" if status == "active" else "nice_to_have",
        "trust": "trusted",
        "text": " ".join(lines),
        "citations": {"recordRef": f"active-line:{goal_id}", "source_ref": source_ref},
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "compiled_at": _now_iso(),
        "source_ref": source_ref,
        "active_line": {
            "goal_id": goal_id,
            "status": status,
            "objective": objective,
            "updated_at": updated_at,
            "next_gate": next_gate,
            "stop_loss": stop_loss,
            "has_verifier": verifier is not None,
        },
        "context_pack_fragment": {
            "schema": "openclaw-mem.context-pack.fragment.v0",
            "bundle_text": f"- [{item['recordRef']}] {item['text']}",
            "items": [item],
        },
        "writes_performed": False,
    }
