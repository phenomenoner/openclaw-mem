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
