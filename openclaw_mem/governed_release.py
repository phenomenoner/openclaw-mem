"""Governed apply and release-hardening checks for Slice 7.

This module deliberately does not apply mutations or publish releases. It emits
review/gate receipts that make approval boundaries explicit before any future
higher-risk automation can be considered.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from openclaw_mem.mutation_framework import PLAN_SCHEMA, validate_plan
from openclaw_mem.steward_review import public_safety_markers

APPLY_REVIEW_SCHEMA = "openclaw-mem.governed.apply-review.v0"
RELEASE_CHECK_SCHEMA = "openclaw-mem.governed.release-check.v0"
ADVISORY_DOSSIER_SCHEMA = "openclaw-mem.governed.advisory-dossier.v0"
RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _risk(plan: Mapping[str, Any]) -> str:
    max_rank = 0
    for m in plan.get("mutations") or []:
        if isinstance(m, Mapping):
            max_rank = max(max_rank, RISK_ORDER.get(str(m.get("risk_class") or "L1"), 99))
    for label, rank in RISK_ORDER.items():
        if rank == max_rank:
            return label
    return "unknown"


def review_apply_plan(
    plan: Mapping[str, Any],
    *,
    allowed_root: str | Path,
    l2_enabled: bool = False,
    human_approved: bool = False,
    ck_approved: bool = False,
) -> dict[str, Any]:
    validation = validate_plan(plan, allowed_root=allowed_root, allow_apply=True)
    highest = _risk(plan)
    reasons: list[str] = []
    if plan.get("schema_version") != PLAN_SCHEMA:
        reasons.append("invalid_plan_schema")
    if not validation.get("ok"):
        reasons.append("plan_validation_failed")
    if highest == "L2" and not l2_enabled:
        reasons.append("l2_requires_config_gate")
    if highest == "L3" and not human_approved:
        reasons.append("l3_requires_human_approval")
    if highest == "L4" and not ck_approved:
        reasons.append("l4_requires_ck_approval")
    # Slice 7 still does not approve L3/L4 auto apply. Approval only records who
    # must be present for a future separate lane.
    if highest in {"L3", "L4"}:
        reasons.append("l3_l4_not_auto_applyable")
    decision = "advisory_allow_local_apply" if not reasons and highest in {"L0", "L1"} else "advisory_allow_l2_local_apply" if not reasons and highest == "L2" else "blocked"
    return {
        "schema_version": APPLY_REVIEW_SCHEMA,
        "ok": decision != "blocked",
        "decision": decision,
        "highest_risk_class": highest,
        "writes_performed": False,
        "topology_changed": False,
        "l2_enabled": bool(l2_enabled),
        "human_approved": bool(human_approved),
        "ck_approved": bool(ck_approved),
        "reasons": reasons,
        "validation": validation,
        "reviewed_at": now_iso(),
    }


def _affected_surfaces(plan: Mapping[str, Any]) -> list[str]:
    surfaces: list[str] = []
    seen: set[str] = set()
    for m in plan.get("mutations") or []:
        if not isinstance(m, Mapping):
            continue
        path = str(m.get("path") or "").strip() or "<missing-path>"
        if path not in seen:
            surfaces.append(path)
            seen.add(path)
    return surfaces


def _proposed_changes(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for m in plan.get("mutations") or []:
        if not isinstance(m, Mapping):
            continue
        action = str(m.get("action") or "")
        path = str(m.get("path") or "")
        item: dict[str, Any] = {
            "mutation_id": m.get("mutation_id"),
            "action": action,
            "path": path,
            "risk_class": str(m.get("risk_class") or "L1"),
            "protected": bool(m.get("protected", False)),
            "requires_approval": bool(m.get("requires_approval", False)),
        }
        if "rationale" in m:
            item["rationale"] = m.get("rationale")
        if action == "replace_text":
            item["old_preview"] = str(m.get("old") or "")[:240]
            item["new_preview"] = str(m.get("new") or "")[:240]
        elif action == "write_file":
            item["content_preview"] = str(m.get("content") or "")[:240]
        changes.append(item)
    return changes


def build_advisory_dossier(
    plan: Mapping[str, Any],
    *,
    allowed_root: str | Path,
    title: str | None = None,
    why_now: str | None = None,
    recommendation: str | None = None,
    do_nothing_cost: str | None = None,
    operator_target: str | None = None,
    l2_enabled: bool = False,
    human_approved: bool = False,
    ck_approved: bool = False,
) -> dict[str, Any]:
    """Build an operator-facing advisory dossier without applying anything."""

    apply_review = review_apply_plan(
        plan,
        allowed_root=allowed_root,
        l2_enabled=l2_enabled,
        human_approved=human_approved,
        ck_approved=ck_approved,
    )
    highest = str(apply_review.get("highest_risk_class") or _risk(plan))
    if highest == "L4":
        approval_needed = "CK explicit approval required before any separate execution line"
    elif highest == "L3":
        approval_needed = "human operator approval required before any separate execution line"
    elif highest == "L2":
        approval_needed = "L2 config gate required before local advisory apply"
    else:
        approval_needed = "no high-risk approval required by dossier policy"
    approval_status = "approval_required" if highest in {"L3", "L4"} else "not_high_risk"
    return {
        "schema_version": ADVISORY_DOSSIER_SCHEMA,
        "ok": True,
        "writes_performed": False,
        "topology_changed": False,
        "title": title or f"Governed advisory dossier for {highest} mutation plan",
        "verdict": "approval_required_before_execution" if highest in {"L3", "L4"} else "not_l3_l4_review_only",
        "recommendation": recommendation or "Review the dossier; approve only by opening a separate execution line with explicit scope.",
        "risk_class": highest,
        "why_now": why_now or "Not provided.",
        "do_nothing_cost": do_nothing_cost or "Not provided.",
        "operator_target": operator_target or "CK/operator",
        "affected_surfaces": _affected_surfaces(plan),
        "proposed_changes": _proposed_changes(plan),
        "approval": {
            "status": approval_status,
            "needed": approval_needed,
            "message_delivery_is_not_approval": True,
            "execution_requires_separate_line": True,
        },
        "rollback_plan": [
            "Do not execute this dossier directly.",
            "If approved later, require a separate execution receipt with before/after diff and rollback command/path.",
            "For file mutations, rollback must restore original content or revert the execution commit.",
        ],
        "verifier_plan": [
            "Validate the plan against the intended allowed root before execution.",
            "Run counterfactual authority checks showing the same L3/L4 candidate remains blocked without explicit execution approval.",
            "Run the smallest targeted tests or smoke checks for affected surfaces.",
            "Capture a closure receipt and topology readback after any approved execution line.",
        ],
        "apply_review": apply_review,
        "created_at": now_iso(),
    }


def render_advisory_dossier_markdown(dossier: Mapping[str, Any]) -> str:
    changes = dossier.get("proposed_changes") or []
    surfaces = dossier.get("affected_surfaces") or []
    approval = dossier.get("approval") or {}
    apply_review = dossier.get("apply_review") or {}
    lines = [
        "# L3/L4 Advisory Dossier",
        "",
        f"Verdict: {dossier.get('verdict')}",
        f"Recommendation: {dossier.get('recommendation')}",
        f"Risk class: {dossier.get('risk_class')}",
        f"Why now: {dossier.get('why_now')}",
        f"Operator target: {dossier.get('operator_target')}",
        "",
        "## Approval needed",
        "",
        f"- Status: {approval.get('status')}",
        f"- Needed: {approval.get('needed')}",
        f"- Message delivery is not approval: {approval.get('message_delivery_is_not_approval')}",
        f"- Separate execution line required: {approval.get('execution_requires_separate_line')}",
        "",
        "## Affected surfaces",
        "",
    ]
    lines.extend([f"- `{s}`" for s in surfaces] or ["- none"])
    lines.extend(["", "## Proposed changes", ""])
    if changes:
        for c in changes:
            lines.append(f"- `{c.get('action')}` `{c.get('path')}` risk={c.get('risk_class')} protected={c.get('protected')} requires_approval={c.get('requires_approval')}")
            if c.get("rationale"):
                lines.append(f"  - rationale: {c.get('rationale')}")
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Rollback",
        "",
        *[f"- {x}" for x in dossier.get("rollback_plan") or []],
        "",
        "## Verifier",
        "",
        *[f"- {x}" for x in dossier.get("verifier_plan") or []],
        "",
        "## Apply-review receipt",
        "",
        f"- decision: {apply_review.get('decision')}",
        f"- ok: {apply_review.get('ok')}",
        f"- reasons: {', '.join(apply_review.get('reasons') or [])}",
        f"- writes_performed: {apply_review.get('writes_performed')}",
        f"- topology_changed: {apply_review.get('topology_changed')}",
        "",
        "## Do nothing cost",
        "",
        str(dossier.get("do_nothing_cost") or "Not provided."),
        "",
    ])
    return "\n".join(lines)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _version_from_pyproject(text: str) -> str | None:
    m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return m.group(1) if m else None


def _version_from_init(text: str) -> str | None:
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else None


def _lockfile_project_version_present(lock_text: str, expected: str) -> bool:
    pattern = (
        r'(?ms)^\[\[package\]\]\s*\n'
        r'name\s*=\s*"openclaw-context-pack"\s*\n'
        rf'version\s*=\s*"{re.escape(expected)}"\s*\n'
    )
    return bool(re.search(pattern, lock_text))


def release_check(
    *,
    repo_root: str | Path,
    expected_version: str | None = None,
    require_receipt: bool = True,
    docs_glob: str = "docs/self-improvement*.md",
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    pyproject = _read(root / "pyproject.toml")
    init = _read(root / "openclaw_mem" / "__init__.py")
    lock = _read(root / "uv.lock")
    changelog = _read(root / "CHANGELOG.md")
    version = _version_from_pyproject(pyproject)
    init_version = _version_from_init(init)
    expected = expected_version or version
    errors: list[str] = []
    warnings: list[str] = []
    if not version:
        errors.append("missing_pyproject_version")
    if init_version != version:
        errors.append("init_version_mismatch")
    if expected and version != expected:
        errors.append("expected_version_mismatch")
    lock_has_project_version = bool(expected and _lockfile_project_version_present(lock, expected))
    if expected and not lock_has_project_version:
        errors.append("uv_lock_version_missing")
    if expected and f"## [{expected}]" not in changelog:
        errors.append("changelog_entry_missing")
    receipts = sorted((root / "docs").glob("2026-*_self-improvement*receipt.md"))
    if require_receipt and not receipts:
        if not receipts:
            errors.append("release_receipt_missing")
    public_markers: dict[str, list[str]] = {}
    docs_paths = set(root.glob(docs_glob)) | set(root.glob("docs/2026-*_self-improvement*.md"))
    for path in sorted(docs_paths):
        markers = public_safety_markers(_read(path))
        if markers:
            public_markers[str(path.relative_to(root))] = markers
    if public_markers:
        errors.append("public_safety_markers_found")
    return {
        "schema_version": RELEASE_CHECK_SCHEMA,
        "ok": not errors,
        "writes_performed": False,
        "topology_changed": False,
        "repo_root": str(root),
        "expected_version": expected,
        "versions": {"pyproject": version, "init": init_version},
        "checks": {
            "version_consistent": bool(version and init_version == version),
            "lockfile_mentions_version": lock_has_project_version,
            "changelog_entry_present": bool(expected and f"## [{expected}]" in changelog),
            "receipt_present": bool(receipts),
            "public_safety_clean": not public_markers,
        },
        "public_safety_markers": public_markers,
        "errors": errors,
        "warnings": warnings,
        "checked_at": now_iso(),
    }
