"""Shared governance substrate for self-improvement surfaces.

This module is intentionally deterministic and local-only.  It validates the
small receipt/inventory contract used by read-only consolidation pilots before
any curator or goal runtime is allowed to mutate durable state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "openclaw-mem.self-improvement-surface.v0"
RECEIPT_SCHEMA_VERSION = "openclaw-mem.self-improvement-receipt.v0"

VALID_STATES = {"stable", "lab", "shadow", "retired"}
VALID_WRITE_AUTHORITIES = {"none", "suggest", "stage", "apply-local", "apply-publish"}
VALID_RISK_CLASSES = {"L0", "L1", "L2", "L3", "L4"}

AUTHORITY_RANK = {
    "none": 0,
    "suggest": 1,
    "stage": 2,
    "apply-local": 3,
    "apply-publish": 4,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_object(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _as_list(value: Any, *, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _surface_items(inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = inventory.get("surfaces", [])
    if not isinstance(raw, list):
        raise ValueError("surfaces must be a list")
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"surfaces[{idx}] must be an object")
        out.append(dict(item))
    return out


def validate_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a self-improvement surface inventory and return a receipt."""

    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    surfaces = []

    try:
        items = _surface_items(inventory)
    except ValueError as exc:
        items = []
        errors.append(str(exc))

    for idx, item in enumerate(items):
        sid = str(item.get("surface_id") or "").strip()
        if not sid:
            errors.append(f"surfaces[{idx}].surface_id is required")
        elif sid in seen:
            errors.append(f"duplicate surface_id: {sid}")
        else:
            seen.add(sid)

        state = str(item.get("state") or "").strip()
        if state not in VALID_STATES:
            errors.append(f"{sid or f'surfaces[{idx}]'}.state must be one of {sorted(VALID_STATES)}")

        write_authority = str(item.get("write_authority") or "").strip()
        if write_authority not in VALID_WRITE_AUTHORITIES:
            errors.append(
                f"{sid or f'surfaces[{idx}]'}.write_authority must be one of {sorted(VALID_WRITE_AUTHORITIES)}"
            )

        risk_class = str(item.get("risk_class") or "").strip()
        if risk_class not in VALID_RISK_CLASSES:
            errors.append(f"{sid or f'surfaces[{idx}]'}.risk_class must be one of {sorted(VALID_RISK_CLASSES)}")

        if "protected" in item and not isinstance(item.get("protected"), bool):
            errors.append(f"{sid or f'surfaces[{idx}]'}.protected must be boolean")

        if state == "retired" and not item.get("rollback"):
            warnings.append(f"{sid or f'surfaces[{idx}]'} is retired without rollback/readback reference")

        surfaces.append(
            {
                "surface_id": sid,
                "state": state,
                "write_authority": write_authority,
                "risk_class": risk_class,
                "protected": bool(item.get("protected", False)),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "inventory-validation",
        "ok": not errors,
        "writes_performed": False,
        "surface_count": len(items),
        "protected_count": sum(1 for s in surfaces if s.get("protected")),
        "states": {state: sum(1 for s in surfaces if s.get("state") == state) for state in sorted(VALID_STATES)},
        "errors": errors,
        "warnings": warnings,
        "validated_at": now_iso(),
    }


def _inventory_by_id(inventory: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("surface_id")): item for item in _surface_items(inventory) if item.get("surface_id")}


def _min_required_authority(surface: Mapping[str, Any]) -> str:
    risk = str(surface.get("risk_class") or "").strip()
    configured = str(surface.get("write_authority") or "none").strip()
    if bool(surface.get("protected", False)) or risk in {"L3", "L4"}:
        floor = "apply-publish" if risk == "L4" else "apply-local"
        return floor if AUTHORITY_RANK[floor] >= AUTHORITY_RANK.get(configured, 0) else configured
    return configured if configured in AUTHORITY_RANK else "none"


def validate_receipt(receipt: Mapping[str, Any], *, inventory: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate a self-improvement receipt against optional inventory policy."""

    errors: list[str] = []
    warnings: list[str] = []

    mode = str(receipt.get("mode") or "none").strip()
    if mode not in VALID_WRITE_AUTHORITIES:
        errors.append(f"mode must be one of {sorted(VALID_WRITE_AUTHORITIES)}")

    risk_class = str(receipt.get("risk_class") or "").strip()
    if risk_class and risk_class not in VALID_RISK_CLASSES:
        errors.append(f"risk_class must be one of {sorted(VALID_RISK_CLASSES)}")

    writes_performed = receipt.get("writes_performed", False)
    if not isinstance(writes_performed, bool):
        errors.append("writes_performed must be boolean")

    try:
        applied = _as_list(receipt.get("applied"), field="applied")
    except ValueError as exc:
        applied = []
        errors.append(str(exc))

    if applied and AUTHORITY_RANK.get(mode, 0) < AUTHORITY_RANK["suggest"]:
        errors.append("non-empty applied[] requires mode >= suggest")
    if writes_performed and AUTHORITY_RANK.get(mode, 0) < AUTHORITY_RANK["apply-local"]:
        errors.append("writes_performed=true requires mode >= apply-local")

    inv = _inventory_by_id(inventory) if inventory else {}
    protected_touched = False
    for idx, item in enumerate(applied):
        if not isinstance(item, dict):
            errors.append(f"applied[{idx}] must be an object")
            continue
        sid = str(item.get("surface_id") or receipt.get("surface_id") or "").strip()
        if not sid:
            errors.append(f"applied[{idx}].surface_id is required")
            continue
        surface = inv.get(sid)
        if not surface:
            warnings.append(f"applied[{idx}] references unknown surface_id: {sid}")
            continue
        if bool(surface.get("protected", False)):
            protected_touched = True
        required = _min_required_authority(surface)
        if AUTHORITY_RANK.get(mode, 0) < AUTHORITY_RANK.get(required, 0):
            errors.append(
                f"applied[{idx}] touches {sid} requiring {required}; receipt mode is {mode}"
            )

    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "kind": "receipt-validation",
        "ok": not errors,
        "writes_performed": False,
        "mode": mode,
        "applied_count": len(applied),
        "protected_touched": protected_touched,
        "errors": errors,
        "warnings": warnings,
        "validated_at": now_iso(),
    }


def validate_bundle(*, inventory: Mapping[str, Any] | None = None, receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    inventory_result = validate_inventory(inventory or {"surfaces": []}) if inventory is not None else None
    receipt_result = validate_receipt(receipt or {}, inventory=inventory) if receipt is not None else None
    ok = True
    if inventory_result is not None:
        ok = ok and bool(inventory_result.get("ok"))
    if receipt_result is not None:
        ok = ok and bool(receipt_result.get("ok"))
    return {
        "schema_version": "openclaw-mem.self-improvement-validation-bundle.v0",
        "ok": ok,
        "writes_performed": False,
        "inventory": inventory_result,
        "receipt": receipt_result,
        "validated_at": now_iso(),
    }
