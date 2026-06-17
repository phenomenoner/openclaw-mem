"""Local staged mutation framework for self-improvement Slice 6.

This framework is deliberately narrow.  It supports plan -> stage -> synthetic
apply -> rollback for local fixture files only, so higher-risk governed apply
work can be built later without changing OpenClaw core/runtime topology.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PLAN_SCHEMA = "openclaw-mem.mutation.plan.v0"
STAGE_SCHEMA = "openclaw-mem.mutation.stage.v0"
APPLY_SCHEMA = "openclaw-mem.mutation.apply.v0"
ROLLBACK_SCHEMA = "openclaw-mem.mutation.rollback.v0"
VALID_RISK = {"L0", "L1", "L2", "L3", "L4"}
APPLY_ALLOWED_RISK = {"L0", "L1", "L2"}
VALID_ACTIONS = {"write_file", "replace_text"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def stable_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _mutation_id(m: Mapping[str, Any]) -> str:
    raw = "\0".join([str(m.get("action") or ""), str(m.get("path") or ""), str(m.get("content") or ""), str(m.get("old") or ""), str(m.get("new") or "")])
    return "mut-" + stable_id(raw)


def _normalize_mutation(raw: Mapping[str, Any]) -> dict[str, Any]:
    action = str(raw.get("action") or "").strip()
    path = str(raw.get("path") or "").strip()
    risk = str(raw.get("risk_class") or "L1").strip()
    mutation = {
        "mutation_id": str(raw.get("mutation_id") or _mutation_id(raw)),
        "action": action,
        "path": path,
        "risk_class": risk,
        "protected": bool(raw.get("protected", False)),
        "requires_approval": bool(raw.get("requires_approval", False)),
    }
    for key in ("content", "old", "new", "rationale"):
        if key in raw:
            mutation[key] = raw.get(key)
    return mutation


def build_plan(*, mutations: list[Mapping[str, Any]], plan_id: str | None = None, source_ref: str | None = None) -> dict[str, Any]:
    normalized = [_normalize_mutation(m) for m in mutations]
    seed = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return {
        "schema_version": PLAN_SCHEMA,
        "plan_id": plan_id or "mutation-plan-" + stable_id(seed),
        "mode": "plan",
        "source_ref": source_ref,
        "writes_performed": False,
        "mutations": normalized,
        "created_at": now_iso(),
    }


def _safe_target(path: str, *, allowed_root: Path) -> Path:
    if not path:
        raise ValueError("path_required")
    p = Path(path)
    if p.is_absolute() or p.drive or p.root:
        raise ValueError("absolute_paths_forbidden")
    if any(part in {"..", ""} for part in p.parts):
        raise ValueError("path_traversal_forbidden")
    root = allowed_root.expanduser().resolve()
    target = (root / p).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("target_outside_allowed_root") from exc
    return target


def validate_plan(plan: Mapping[str, Any], *, allowed_root: str | Path, allow_apply: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    mutations = plan.get("mutations")
    if plan.get("schema_version") != PLAN_SCHEMA:
        errors.append("invalid_plan_schema")
    if not isinstance(mutations, list):
        errors.append("mutations must be a list")
        mutations = []
    root = Path(allowed_root)
    for idx, item in enumerate(mutations):
        if not isinstance(item, Mapping):
            errors.append(f"mutations[{idx}] must be an object")
            continue
        action = str(item.get("action") or "")
        risk = str(item.get("risk_class") or "")
        if action not in VALID_ACTIONS:
            errors.append(f"mutations[{idx}].action unsupported: {action}")
        if risk not in VALID_RISK:
            errors.append(f"mutations[{idx}].risk_class invalid: {risk}")
        if bool(item.get("protected")):
            errors.append(f"mutations[{idx}] touches protected surface")
        if risk in {"L3", "L4"} or bool(item.get("requires_approval")):
            errors.append(f"mutations[{idx}] requires manual approval; slice6 apply is L0-L2 synthetic only")
        if allow_apply and risk not in APPLY_ALLOWED_RISK:
            errors.append(f"mutations[{idx}].risk_class not apply-allowed: {risk}")
        try:
            _safe_target(str(item.get("path") or ""), allowed_root=root)
        except ValueError as exc:
            errors.append(f"mutations[{idx}].path {exc}")
        if action == "write_file" and "content" not in item:
            errors.append(f"mutations[{idx}].content required for write_file")
        if action == "replace_text":
            if "old" not in item or "new" not in item:
                errors.append(f"mutations[{idx}].old/new required for replace_text")
    return {
        "schema_version": "openclaw-mem.mutation.validation.v0",
        "ok": not errors,
        "writes_performed": False,
        "allowed_root": str(Path(allowed_root).expanduser()),
        "mutation_count": len(mutations),
        "errors": errors,
        "warnings": warnings,
        "validated_at": now_iso(),
    }


def stage_plan(plan: Mapping[str, Any], *, stage_root: str | Path, allowed_root: str | Path) -> dict[str, Any]:
    validation = validate_plan(plan, allowed_root=allowed_root, allow_apply=False)
    stage_id = "stage-" + stable_id(json.dumps(plan, ensure_ascii=False, sort_keys=True) + str(allowed_root))
    stage_dir = Path(stage_root) / stage_id
    payload = {
        "schema_version": STAGE_SCHEMA,
        "ok": bool(validation["ok"]),
        "stage_id": stage_id,
        "plan_id": plan.get("plan_id"),
        "writes_performed": True,
        "write_scope": "staged_mutation_artifact",
        "allowed_root": str(Path(allowed_root).expanduser()),
        "validation": validation,
        "created_at": now_iso(),
    }
    stage_dir.mkdir(parents=True, exist_ok=True)
    write_json(stage_dir / "plan.json", plan)
    write_json(stage_dir / "stage-receipt.json", payload)
    payload["stage_dir"] = str(stage_dir)
    return payload


def _snapshot_target(target: Path, backup_dir: Path, rel: str) -> dict[str, Any]:
    backup_path = backup_dir / rel
    if target.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
        before = target.read_text(encoding="utf-8")
        existed = True
    else:
        before = None
        existed = False
    return {"path": rel, "existed": existed, "backup_path": str(backup_path) if existed else None, "before_sha256": hashlib.sha256((before or "").encode("utf-8")).hexdigest() if existed else None}


def apply_plan(plan: Mapping[str, Any], *, allowed_root: str | Path, receipt_root: str | Path) -> dict[str, Any]:
    validation = validate_plan(plan, allowed_root=allowed_root, allow_apply=True)
    run_id = "apply-" + stable_id(json.dumps(plan, ensure_ascii=False, sort_keys=True) + now_iso())
    run_dir = Path(receipt_root) / run_id
    backup_dir = run_dir / "backups"
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    root = Path(allowed_root).expanduser().resolve()
    if not validation["ok"]:
        payload = {
            "schema_version": APPLY_SCHEMA,
            "ok": False,
            "mode": "failed_closed",
            "run_id": run_id,
            "writes_performed": False,
            "validation": validation,
            "mutations_applied": applied,
            "mutations_skipped": [],
            "rollback_available": False,
            "created_at": now_iso(),
        }
        write_json(run_dir / "apply-receipt.json", payload)
        return payload
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        for item in plan.get("mutations") or []:
            m = dict(item)
            rel = str(m["path"])
            target = _safe_target(rel, allowed_root=root)
            snapshot = _snapshot_target(target, backup_dir, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            if m["action"] == "write_file":
                target.write_text(str(m.get("content") or ""), encoding="utf-8")
            elif m["action"] == "replace_text":
                if not target.exists():
                    skipped.append({"mutation_id": m.get("mutation_id"), "path": rel, "reason": "target_missing"})
                    break
                text = target.read_text(encoding="utf-8")
                old = str(m.get("old"))
                if text.count(old) != 1:
                    skipped.append({"mutation_id": m.get("mutation_id"), "path": rel, "reason": "old_text_not_unique"})
                    break
                target.write_text(text.replace(old, str(m.get("new")), 1), encoding="utf-8")
            after = target.read_text(encoding="utf-8")
            applied.append({"mutation_id": m.get("mutation_id"), "action": m.get("action"), "path": rel, "snapshot": snapshot, "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest()})
    except Exception as exc:  # fail closed and let rollback receipt explain what happened
        skipped.append({"reason": "exception", "exception": repr(exc)})

    if skipped:
        rollback = rollback_apply_receipt({"schema_version": APPLY_SCHEMA, "run_id": run_id, "allowed_root": str(root), "mutations_applied": applied}, out_root=run_dir)
        applied = []
        mode = "failed_closed"
    else:
        rollback = None
        mode = "applied" if applied else "noop"
    payload = {
        "schema_version": APPLY_SCHEMA,
        "ok": not skipped,
        "mode": mode,
        "run_id": run_id,
        "plan_id": plan.get("plan_id"),
        "allowed_root": str(root),
        "writes_performed": bool(applied),
        "mutations_applied": applied,
        "mutations_skipped": skipped,
        "rollback_available": bool(applied),
        "rollback_receipt": rollback,
        "created_at": now_iso(),
    }
    write_json(run_dir / "apply-receipt.json", payload)
    payload["receipt_path"] = str(run_dir / "apply-receipt.json")
    return payload


def rollback_apply_receipt(receipt: Mapping[str, Any], *, out_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(str(receipt.get("allowed_root") or ".")).expanduser().resolve()
    restored: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in reversed(receipt.get("mutations_applied") or []):
        if not isinstance(item, Mapping):
            continue
        snap = item.get("snapshot") if isinstance(item.get("snapshot"), Mapping) else {}
        rel = str(item.get("path") or snap.get("path") or "")
        try:
            target = _safe_target(rel, allowed_root=root)
        except ValueError as exc:
            errors.append(f"{rel}:{exc}")
            continue
        if snap.get("existed"):
            backup = Path(str(snap.get("backup_path") or ""))
            if not backup.exists():
                errors.append(f"missing_backup:{rel}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
            action = "restored"
        else:
            if target.exists():
                target.unlink()
            action = "deleted_created_file"
        restored.append({"path": rel, "action": action})
    payload = {
        "schema_version": ROLLBACK_SCHEMA,
        "ok": not errors,
        "run_id": "rollback-" + stable_id(str(receipt.get("run_id")) + now_iso()),
        "source_apply_run_id": receipt.get("run_id"),
        "writes_performed": bool(restored),
        "restored": restored,
        "errors": errors,
        "created_at": now_iso(),
    }
    if out_root:
        write_json(Path(out_root) / "rollback-receipt.json", payload)
    return payload
