"""Self Curator lifecycle engine.

The scanner is review-only. The apply lane may mutate whitelisted files only
through explicit plan -> checkpoint -> apply -> verify -> rollback receipts.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PACKET_KIND = "openclaw.curator.lifecycle-review.v0"
DEFAULT_OUT_ROOT = Path(".state/self-curator/runs")
_STUB_RE = re.compile(r"\b(todo|tbd|stub|placeholder|draft)\b", re.IGNORECASE)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class SkillScan:
    path: Path
    rel: str
    text: str


def utc_run_id(now: datetime | None = None) -> str:
    ts = now or datetime.now(timezone.utc)
    return ts.strftime("%Y%m%d-%H%M%S")


def _utc_iso(now: datetime | None = None) -> str:
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(target_ref: str, action: str, reason_code: str) -> str:
    digest = hashlib.sha256(f"{target_ref}\0{action}\0{reason_code}".encode("utf-8")).hexdigest()[:12]
    return f"curator-{digest}"


def validate_run_id(run_id: str) -> str:
    """Return a safe run id or raise ValueError.

    Run ids become directory names under the requested output root, so v0 accepts
    only a single slug component and rejects separators/traversal outright.
    """

    if not _RUN_ID_RE.match(run_id):
        raise ValueError("invalid_run_id")
    if run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError("invalid_run_id")
    return run_id


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    out: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip("\"'")
    return out


def iter_skill_files(skill_roots: Iterable[Path]) -> list[SkillScan]:
    scans: list[SkillScan] = []
    for root in skill_roots:
        root = Path(root).expanduser().resolve()
        if not root.exists():
            continue
        candidates = sorted(root.glob("*/SKILL.md"))
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="replace")
            try:
                rel = str(path.relative_to(Path.cwd()))
            except ValueError:
                rel = str(path)
            scans.append(SkillScan(path=path, rel=rel, text=text))
    return scans


def classify_skill(scan: SkillScan) -> dict[str, Any]:
    text = scan.text
    fm = _frontmatter(text)
    evidence: list[str] = []
    action = "keep"
    reason_code = "no_obvious_deterministic_issue"
    reason = "No obvious deterministic lifecycle issue found in v0 scan."

    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end >= 0:
            body = text[end + 4 :]

    if not fm.get("name"):
        action = "refresh"
        reason_code = "missing_frontmatter_name"
        reason = "Skill frontmatter is missing a name; refresh review recommended before lifecycle automation."
        evidence.append("frontmatter.name missing")
    elif not fm.get("description"):
        action = "refresh"
        reason_code = "missing_frontmatter_description"
        reason = "Skill frontmatter is missing a description; refresh review recommended before lifecycle automation."
        evidence.append("frontmatter.description missing")
    elif len(body.strip()) < 240:
        action = "refresh"
        reason_code = "very_short_skill_body"
        reason = "Skill body is very short; refresh review recommended before treating it as stable procedural memory."
        evidence.append(f"body_chars={len(body.strip())}")
    elif _STUB_RE.search(text):
        action = "refresh"
        reason_code = "stub_marker_present"
        reason = "Skill contains TODO/stub/draft markers; refresh review recommended."
        evidence.append("stub_marker_present")
    else:
        action = "promote_to_review"
        reason_code = "substantial_skill_review_before_future_automation"
        reason = "Skill appears substantial; consider pin/review posture before any future lifecycle automation."
        evidence.append("substantial_skill_detected")

    return {
        "candidate_id": _stable_id(scan.rel, action, reason_code),
        "target_ref": scan.rel,
        "lifecycle_action": action,
        "reason": reason,
        "reason_code": reason_code,
        "evidence_refs": evidence,
        "risk_class": "skill_surface",
        "apply_lane": "molt_gic_packet" if action != "keep" else "none",
        "checkpoint_required": action != "keep",
    }


def build_skill_review(
    *,
    skill_roots: Iterable[Path],
    run_id: str | None = None,
    now: datetime | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    run_id = validate_run_id(run_id or utc_run_id(now))
    ts = _utc_iso(now)
    roots = [Path(p).expanduser() for p in skill_roots]
    scans = iter_skill_files(roots)
    candidates = [classify_skill(scan) for scan in scans]
    if limit is not None and limit >= 0:
        candidates = candidates[:limit]

    counts_by_action: dict[str, int] = {}
    for c in candidates:
        action = str(c.get("lifecycle_action") or "unknown")
        counts_by_action[action] = counts_by_action.get(action, 0) + 1

    return {
        "kind": PACKET_KIND,
        "run_id": run_id,
        "ts": ts,
        "mode": "review_only",
        "scope": "skill",
        "source_refs": [str(p) for p in roots],
        "summary": {
            "skills_scanned": len(scans),
            "candidate_count": len(candidates),
            "counts_by_action": counts_by_action,
            "writes_performed": 0,
        },
        "candidates": candidates,
        "writes_performed": 0,
        "blocked_until": "human_review",
    }


def render_report(packet: dict[str, Any]) -> str:
    summary = packet.get("summary") if isinstance(packet.get("summary"), dict) else {}
    candidates = packet.get("candidates") if isinstance(packet.get("candidates"), list) else []
    counts = summary.get("counts_by_action") if isinstance(summary.get("counts_by_action"), dict) else {}
    lines = [
        "# Self Curator skill lifecycle review",
        "",
        f"- packet: `{packet.get('kind')}`",
        f"- run_id: `{packet.get('run_id')}`",
        f"- mode: `{packet.get('mode')}`",
        f"- scope: `{packet.get('scope')}`",
        f"- skills_scanned: {summary.get('skills_scanned', 0)}",
        f"- candidate_count: {summary.get('candidate_count', 0)}",
        f"- writes_performed: {packet.get('writes_performed', 0)}",
        f"- blocked_until: `{packet.get('blocked_until')}`",
        "- source_packet: `review.json`",
        "",
        "## Counts by action",
        "",
    ]
    if counts:
        for key in sorted(counts):
            lines.append(f"- {key}: {counts[key]}")
    else:
        lines.append("- none: 0")
    lines.extend(["", "## Candidates", ""])
    if not candidates:
        lines.append("No candidates emitted.")
    for c in candidates:
        lines.extend(
            [
                f"### {c.get('target_ref')}",
                "",
                f"- action: `{c.get('lifecycle_action')}`",
                f"- reason_code: `{c.get('reason_code')}`",
                f"- reason: {c.get('reason')}",
                f"- apply_lane: `{c.get('apply_lane')}`",
                f"- checkpoint_required: {str(bool(c.get('checkpoint_required'))).lower()}",
                "",
            ]
        )
    lines.extend(
        [
            "## Safety posture",
            "",
            "This v0 command is review-only. It writes this report and the matching JSON packet only; reviewed skills are not modified.",
            "",
        ]
    )
    return "\n".join(lines)


def write_review_artifacts(packet: dict[str, Any], out_root: Path) -> dict[str, str]:
    out_root = Path(out_root).expanduser()
    run_id = validate_run_id(str(packet.get("run_id") or utc_run_id()))
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    review_path = run_dir / "review.json"
    report_path = run_dir / "REPORT.md"
    review_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_report(packet), encoding="utf-8")
    return {"run_dir": str(run_dir), "review_json": str(review_path), "report_md": str(report_path)}

APPLY_PLAN_KIND = "openclaw.curator.apply-plan.v1"
CHECKPOINT_KIND = "openclaw.curator.checkpoint.v1"
APPLY_RECEIPT_KIND = "openclaw.curator.apply-receipt.v1"
VERIFY_RECEIPT_KIND = "openclaw.curator.verify-receipt.v1"
ROLLBACK_RECEIPT_KIND = "openclaw.curator.rollback-receipt.v1"
_ALLOWED_MUTATION_ACTIONS = {"replace_text", "write_file", "move_file", "archive_file", "set_frontmatter_field"}


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("target_is_not_file")
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(ref: str) -> Path:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("empty_target_ref")
    p = Path(ref)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("unsafe_target_ref")
    return p


def _resolve_under(root: Path, ref: str) -> Path:
    root = Path(root).expanduser().resolve()
    rel = _safe_rel(ref)
    out = (root / rel).resolve()
    if out != root and root not in out.parents:
        raise ValueError("target_outside_workspace")
    return out


def _unique_targets(plan: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for m in plan.get("mutations") or []:
        for key in ("target_ref", "dest_ref"):
            val = m.get(key)
            if isinstance(val, str) and val and val not in refs:
                refs.append(val)
    return refs


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_apply_plan(plan: dict[str, Any], *, workspace_root: Path) -> None:
    if plan.get("kind") != APPLY_PLAN_KIND:
        raise ValueError("invalid_apply_plan_kind")
    mutations = plan.get("mutations")
    if not isinstance(mutations, list):
        raise ValueError("missing_mutations")
    for m in mutations:
        action = m.get("action")
        if action not in _ALLOWED_MUTATION_ACTIONS:
            raise ValueError(f"unsupported_mutation_action:{action}")
        target = _resolve_under(workspace_root, str(m.get("target_ref") or ""))
        if target.exists() and not target.is_file():
            raise ValueError("target_is_not_file")
        if action in {"move_file", "archive_file"}:
            dest = _resolve_under(workspace_root, str(m.get("dest_ref") or ""))
            if dest.exists() and not dest.is_file():
                raise ValueError("dest_is_not_file")
        if action == "replace_text":
            patch = m.get("patch") if isinstance(m.get("patch"), dict) else None
            if not patch or not isinstance(patch.get("old_text"), str) or not isinstance(patch.get("new_text"), str):
                raise ValueError("invalid_replace_text_patch")
        if action == "write_file" and not isinstance(m.get("content"), str):
            raise ValueError("invalid_write_file_content")
        if action == "set_frontmatter_field":
            if not isinstance(m.get("field"), str) or not isinstance(m.get("value"), str):
                raise ValueError("invalid_frontmatter_mutation")
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", str(m.get("field") or "")):
                raise ValueError("invalid_frontmatter_field")


def build_apply_plan(
    *,
    mutations: list[dict[str, Any]],
    plan_id: str | None = None,
    source_review: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    plan_id = validate_run_id(plan_id or f"plan-{utc_run_id(now)}")
    plan = {
        "kind": APPLY_PLAN_KIND,
        "mode": "apply_plan",
        "plan_id": plan_id,
        "ts": _utc_iso(now),
        "source_review": source_review,
        "mutations": mutations,
        "requires_checkpoint": True,
    }
    return plan


def create_checkpoint(*, plan: dict[str, Any], workspace_root: Path, checkpoint_root: Path, checkpoint_id: str | None = None) -> dict[str, Any]:
    validate_apply_plan(plan, workspace_root=workspace_root)
    checkpoint_id = validate_run_id(checkpoint_id or f"checkpoint-{utc_run_id()}")
    checkpoint_dir = Path(checkpoint_root).expanduser() / checkpoint_id
    files_dir = checkpoint_dir / "files"
    files: list[dict[str, Any]] = []
    for ref in _unique_targets(plan):
        target = _resolve_under(workspace_root, ref)
        exists = target.exists()
        snap_rel = Path(ref)
        snap_path = files_dir / snap_rel
        if exists and not target.is_file():
            raise ValueError("target_is_not_file")
        if exists:
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, snap_path)
        files.append(
            {
                "target_ref": ref,
                "exists_before": exists,
                "before_sha256": sha256_file(target),
                "snapshot_path": str(snap_path),
            }
        )
    manifest = {
        "kind": CHECKPOINT_KIND,
        "checkpoint_id": checkpoint_id,
        "ts": _utc_iso(),
        "plan_id": plan.get("plan_id"),
        "workspace_root": str(Path(workspace_root).expanduser().resolve()),
        "files": files,
    }
    _write_json(checkpoint_dir / "checkpoint.json", manifest)
    return manifest


def _check_preconditions(mutation: dict[str, Any], target: Path) -> list[str]:
    failures: list[str] = []
    pre = mutation.get("preconditions") if isinstance(mutation.get("preconditions"), dict) else {}
    if "sha256" in pre and sha256_file(target) != pre.get("sha256"):
        failures.append("sha256_mismatch")
    if "exists" in pre and bool(target.exists()) is not bool(pre.get("exists")):
        failures.append("exists_mismatch")
    if "must_contain" in pre:
        text = target.read_text(encoding="utf-8") if target.exists() else ""
        if str(pre.get("must_contain")) not in text:
            failures.append("must_contain_missing")
    return failures


def _set_frontmatter_field(text: str, field: str, value: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", field):
        raise ValueError("invalid_frontmatter_field")
    line = f"{field}: {value}"
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end >= 0:
            head = text[4:end].splitlines()
            body = text[end:]
            replaced = False
            out_lines = []
            for existing in head:
                if existing.split(":", 1)[0].strip() == field and ":" in existing:
                    out_lines.append(line)
                    replaced = True
                else:
                    out_lines.append(existing)
            if not replaced:
                out_lines.append(line)
            return "---\n" + "\n".join(out_lines) + body
    return f"---\n{line}\n---\n\n" + text


def _apply_one_mutation(mutation: dict[str, Any], *, workspace_root: Path) -> dict[str, Any]:
    action = mutation.get("action")
    target_ref = str(mutation.get("target_ref") or "")
    target = _resolve_under(workspace_root, target_ref)
    if target.exists() and not target.is_file():
        raise ValueError("target_is_not_file")
    before = target.read_text(encoding="utf-8") if target.exists() and target.is_file() else ""
    before_sha = sha256_file(target)

    failures = _check_preconditions(mutation, target)
    if failures:
        return {"mutation_id": mutation.get("mutation_id"), "target_ref": target_ref, "action": action, "applied": False, "failures": failures}

    if action == "replace_text":
        patch = mutation.get("patch") if isinstance(mutation.get("patch"), dict) else {}
        old = str(patch.get("old_text") or "")
        new = str(patch.get("new_text") or "")
        if not old or before.count(old) != 1:
            return {"mutation_id": mutation.get("mutation_id"), "target_ref": target_ref, "action": action, "applied": False, "failures": ["old_text_not_unique"]}
        after = before.replace(old, new, 1)
        target.write_text(after, encoding="utf-8")
    elif action == "write_file":
        content = str(mutation.get("content") or "")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    elif action in {"move_file", "archive_file"}:
        dest_ref = str(mutation.get("dest_ref") or "")
        dest = _resolve_under(workspace_root, dest_ref)
        if not target.exists():
            return {"mutation_id": mutation.get("mutation_id"), "target_ref": target_ref, "action": action, "applied": False, "failures": ["target_missing"]}
        if dest.exists():
            return {"mutation_id": mutation.get("mutation_id"), "target_ref": target_ref, "action": action, "applied": False, "failures": ["dest_exists"]}
        if dest.parent.exists() and not dest.parent.is_dir():
            return {"mutation_id": mutation.get("mutation_id"), "target_ref": target_ref, "action": action, "applied": False, "failures": ["dest_parent_not_dir"]}
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(dest))
    elif action == "set_frontmatter_field":
        field = str(mutation.get("field") or "")
        value = str(mutation.get("value") or "")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_set_frontmatter_field(before, field, value), encoding="utf-8")
    else:
        raise ValueError(f"unsupported_mutation_action:{action}")

    result = {
        "mutation_id": mutation.get("mutation_id"),
        "target_ref": target_ref,
        "dest_ref": mutation.get("dest_ref"),
        "action": action,
        "applied": True,
        "before_sha256": before_sha,
        "after_sha256": sha256_file(target) if target.exists() else None,
    }
    if action in {"move_file", "archive_file"} and mutation.get("dest_ref"):
        dest = _resolve_under(workspace_root, str(mutation.get("dest_ref")))
        result["dest_after_sha256"] = sha256_file(dest) if dest.exists() else None
    return result


def _write_diff(*, workspace_root: Path, checkpoint: dict[str, Any], receipt_dir: Path) -> str:
    lines: list[str] = []
    for f in checkpoint.get("files") or []:
        ref = str(f.get("target_ref") or "")
        current = _resolve_under(workspace_root, ref)
        snap = Path(str(f.get("snapshot_path") or ""))
        before = snap.read_text(encoding="utf-8", errors="replace").splitlines(True) if snap.exists() else []
        after = current.read_text(encoding="utf-8", errors="replace").splitlines(True) if current.exists() else []
        lines.extend(difflib.unified_diff(before, after, fromfile=f"before/{ref}", tofile=f"after/{ref}"))
    diff_path = receipt_dir / "apply.diff"
    diff_path.write_text("".join(lines), encoding="utf-8")
    return str(diff_path)


def apply_plan(*, plan: dict[str, Any], workspace_root: Path, checkpoint_root: Path, receipt_root: Path, run_id: str | None = None) -> dict[str, Any]:
    validate_apply_plan(plan, workspace_root=workspace_root)
    run_id = validate_run_id(run_id or f"apply-{utc_run_id()}")
    receipt_dir = Path(receipt_root).expanduser() / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = create_checkpoint(plan=plan, workspace_root=workspace_root, checkpoint_root=checkpoint_root, checkpoint_id=f"{run_id}-checkpoint")
    mutations_applied: list[dict[str, Any]] = []
    mutations_skipped: list[dict[str, Any]] = []
    exception_info: dict[str, Any] | None = None
    try:
        for mutation in plan.get("mutations") or []:
            result = _apply_one_mutation(mutation, workspace_root=workspace_root)
            if result.get("applied"):
                mutations_applied.append(result)
            else:
                mutations_skipped.append(result)
                break
    except Exception as exc:  # fail closed and restore any earlier writes
        exception_info = {"type": exc.__class__.__name__, "message": str(exc)}
        mutations_skipped.append({"action": "exception", "applied": False, "failures": ["exception"], "exception": exception_info})

    # If any mutation failed, restore from checkpoint to keep apply atomic, including
    # exceptions raised after a mutation performed a partial write but before it returned.
    if mutations_skipped:
        restore = _restore_checkpoint(checkpoint)
        mutations_skipped.append({"action": "atomic_restore", "applied": True, "checkpoint_id": checkpoint.get("checkpoint_id"), "restored": restore})
        mutations_applied = []

    diff_path = _write_diff(workspace_root=workspace_root, checkpoint=checkpoint, receipt_dir=receipt_dir)
    receipt = {
        "kind": APPLY_RECEIPT_KIND,
        "mode": "applied" if mutations_applied and not mutations_skipped else "failed_closed" if mutations_skipped else "applied",
        "run_id": run_id,
        "ts": _utc_iso(),
        "plan_id": plan.get("plan_id"),
        "checkpoint": checkpoint,
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "writes_performed": len(mutations_applied),
        "mutations_applied": mutations_applied,
        "mutations_skipped": mutations_skipped,
        "exception": exception_info,
        "diff_path": diff_path,
        "verify": {
            "preconditions_passed": not mutations_skipped,
            "postconditions_passed": not mutations_skipped,
            "rollback_rehearsal_available": True,
        },
        "rollback_command": f"openclaw-mem self-curator rollback --receipt {receipt_dir / 'apply-receipt.json'} --json",
    }
    receipt_path = receipt_dir / "apply-receipt.json"
    _write_json(receipt_path, receipt)
    receipt["receipt_path"] = str(receipt_path)
    _write_json(receipt_path, receipt)
    return receipt


def _remove_path(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _restore_checkpoint(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    workspace_root = Path(str(checkpoint.get("workspace_root") or ".")).expanduser().resolve()
    restored: list[dict[str, Any]] = []
    # First remove paths that did not exist before (for write_file or move/archive destinations).
    for f in reversed(checkpoint.get("files") or []):
        ref = str(f.get("target_ref") or "")
        target = _resolve_under(workspace_root, ref)
        if not bool(f.get("exists_before")):
            _remove_path(target)
    # Then restore paths that existed before.
    for f in reversed(checkpoint.get("files") or []):
        ref = str(f.get("target_ref") or "")
        target = _resolve_under(workspace_root, ref)
        snap = Path(str(f.get("snapshot_path") or ""))
        existed = bool(f.get("exists_before"))
        before_sha = f.get("before_sha256")
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snap, target)
        current_sha = sha256_file(target) if target.exists() else None
        ok = current_sha == before_sha if existed else not target.exists()
        restored.append({"target_ref": ref, "restored": True, "after_sha256": current_sha, "expected_sha256": before_sha, "expected_exists": existed, "ok": ok})
    return restored


def rollback_apply_receipt(*, receipt: dict[str, Any], out_root: Path | None = None) -> dict[str, Any]:
    checkpoint = receipt.get("checkpoint") if isinstance(receipt.get("checkpoint"), dict) else None
    if not checkpoint:
        raise ValueError("missing_checkpoint")
    restored = _restore_checkpoint(checkpoint)
    payload = {
        "kind": ROLLBACK_RECEIPT_KIND,
        "ts": _utc_iso(),
        "source_apply_receipt": receipt.get("receipt_path"),
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "restored": restored,
        "writes_performed": len(restored),
        "ok": all(bool(r.get("ok")) for r in restored),
    }
    if out_root:
        run_id = validate_run_id(f"rollback-{utc_run_id()}")
        path = Path(out_root).expanduser() / run_id / "rollback-receipt.json"
        payload["receipt_path"] = str(path)
        _write_json(path, payload)
    return payload


def verify_apply_receipt(*, receipt: dict[str, Any]) -> dict[str, Any]:
    checkpoint = receipt.get("checkpoint") if isinstance(receipt.get("checkpoint"), dict) else {}
    workspace_root = Path(str(checkpoint.get("workspace_root") or ".")).expanduser().resolve()
    file_checks = []
    ok = True
    applied_by_ref = {m.get("target_ref"): m for m in receipt.get("mutations_applied") or [] if isinstance(m, dict)}
    applied_dest_by_ref = {m.get("dest_ref"): m for m in receipt.get("mutations_applied") or [] if isinstance(m, dict) and m.get("dest_ref")}
    for f in checkpoint.get("files") or []:
        ref = str(f.get("target_ref") or "")
        target = _resolve_under(workspace_root, ref)
        exists = target.exists()
        current_sha = sha256_file(target) if exists else None
        expected_sha = None
        expected_exists = exists
        if ref in applied_by_ref:
            m = applied_by_ref[ref]
            if m.get("action") in {"move_file", "archive_file"}:
                expected_exists = False
                expected_sha = None
            else:
                expected_exists = True
                expected_sha = m.get("after_sha256")
        elif ref in applied_dest_by_ref:
            expected_exists = True
            expected_sha = applied_dest_by_ref[ref].get("dest_after_sha256")
        elif receipt.get("mode") == "failed_closed":
            expected_exists = bool(f.get("exists_before"))
            expected_sha = f.get("before_sha256")
        check_ok = (exists is expected_exists) and (expected_sha is None or current_sha == expected_sha)
        ok = ok and check_ok
        file_checks.append({"target_ref": ref, "current_sha256": current_sha, "exists": exists, "expected_exists": expected_exists, "expected_sha256": expected_sha, "ok": check_ok})
    payload = {
        "kind": VERIFY_RECEIPT_KIND,
        "ts": _utc_iso(),
        "source_apply_receipt": receipt.get("receipt_path"),
        "mode": receipt.get("mode"),
        "writes_performed": receipt.get("writes_performed"),
        "diff_exists": Path(str(receipt.get("diff_path") or "")).exists(),
        "rollback_rehearsal_available": bool(receipt.get("rollback_command")) and bool(checkpoint),
        "file_checks": file_checks,
    }
    payload["ok"] = bool(ok and payload["diff_exists"] and payload["rollback_rehearsal_available"])
    return payload

CONTROLLER_RECEIPT_KIND = "openclaw.curator.controller-run.v1"
CONTROLLER_POLICY_KIND = "openclaw.curator.policy.v1"


def _candidate_to_unattended_mutation(candidate: dict[str, Any], *, workspace_root: Path) -> dict[str, Any] | None:
    """Build a deterministic unattended mutation for safe skill lifecycle hygiene.

    The scheduled controller mutates the skill body itself, not a sidecar: it
    appends a bounded `## Curator lifecycle` section. Very short or malformed
    skill files can be archived by policy, but normal substantial skills get an
    in-place lifecycle section only once.
    """

    target_ref = str(candidate.get("target_ref") or "")
    workspace_root = Path(workspace_root).expanduser().resolve()
    if Path(target_ref).is_absolute():
        try:
            target_ref = str(Path(target_ref).resolve().relative_to(workspace_root))
        except ValueError:
            return None
    if not target_ref.endswith("/SKILL.md"):
        return None
    skill_path = _resolve_under(workspace_root, target_ref)
    if not skill_path.exists() or not skill_path.is_file():
        return None
    text = skill_path.read_text(encoding="utf-8", errors="replace")
    reason_code = str(candidate.get("reason_code") or "")
    if reason_code in {"very_short_skill_body", "missing_frontmatter_name"}:
        archive_ref = str(Path("skills/.archive") / Path(target_ref).parts[-2] / "SKILL.md")
        return {
            "mutation_id": _stable_id(target_ref, "archive_file", str(candidate.get("candidate_id") or "candidate")),
            "target_ref": target_ref,
            "dest_ref": archive_ref,
            "action": "archive_file",
            "risk_class": "skill_surface",
            "preconditions": {"sha256": sha256_file(skill_path)},
        }
    if "## Curator lifecycle" in text:
        return None
    value = str(candidate.get("lifecycle_action") or "review")
    reason = reason_code or "review"
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end >= 0:
            insert_at = end + len("\n---")
            if len(text) > insert_at and text[insert_at] == "\n":
                insert_at += 1
            old_text = text[:insert_at]
        else:
            old_text = text[:1]
    else:
        old_text = text[:1]
    section = (
        "\n## Curator lifecycle\n\n"
        f"- Status: `{value}`\n"
        f"- Reason: `{reason}`\n"
        "- Rollback: use the apply receipt generated by `openclaw-mem self-curator`.\n"
    )
    return {
        "mutation_id": _stable_id(target_ref, "replace_text", str(candidate.get("candidate_id") or "candidate")),
        "target_ref": target_ref,
        "action": "replace_text",
        "risk_class": "skill_surface",
        "preconditions": {"sha256": sha256_file(skill_path)},
        "patch": {"old_text": old_text, "new_text": old_text + section},
    }


def build_controller_plan_from_review(*, review: dict[str, Any], workspace_root: Path, plan_id: str | None = None, max_mutations: int = 5) -> dict[str, Any]:
    mutations: list[dict[str, Any]] = []
    for candidate in review.get("candidates") or []:
        if len(mutations) >= max_mutations:
            break
        if not isinstance(candidate, dict):
            continue
        mutation = _candidate_to_unattended_mutation(candidate, workspace_root=workspace_root)
        if mutation:
            mutations.append(mutation)
    return build_apply_plan(
        mutations=mutations,
        plan_id=plan_id or f"controller-plan-{utc_run_id()}",
        source_review=str(review.get("run_id") or "review"),
    )


def build_policy_for_plan(*, plan: dict[str, Any], mode: str, unattended: bool) -> dict[str, Any]:
    allowed = True
    reasons: list[str] = []
    for m in plan.get("mutations") or []:
        action = m.get("action")
        target = str(m.get("target_ref") or "")
        risk = m.get("risk_class")
        if risk != "skill_surface":
            allowed = False
            reasons.append(f"unsupported_risk:{risk}")
        if action == "replace_text" and target.endswith("/SKILL.md"):
            patch = m.get("patch") if isinstance(m.get("patch"), dict) else {}
            old_text = str(patch.get("old_text") or "")
            new_text = str(patch.get("new_text") or "")
            delta = new_text[len(old_text):] if new_text.startswith(old_text) else ""
            lifecycle_re = re.compile(
                r"^\n## Curator lifecycle\n\n"
                r"- Status: `(?:promote_to_review|refresh|review)`\n"
                r"- Reason: `[A-Za-z0-9_-]+`\n"
                r"- Rollback: use the apply receipt generated by `openclaw-mem self-curator`\.\n$"
            )
            if delta and "## Curator lifecycle" not in old_text and lifecycle_re.fullmatch(delta):
                continue
        if action == "archive_file" and target.endswith("/SKILL.md") and str(m.get("dest_ref") or "").startswith("skills/.archive/"):
            continue
        allowed = False
        reasons.append(f"unsupported_unattended_mutation:{action}:{target}")
    if not plan.get("mutations"):
        allowed = False
        reasons.append("no_mutations")
    if mode == "dry_run":
        allowed = False
        reasons.append("dry_run_mode")
    return {
        "kind": CONTROLLER_POLICY_KIND,
        "mode": mode,
        "unattended": unattended,
        "decision": "apply" if allowed else "proposal_only",
        "reasons": reasons,
        "mutation_count": len(plan.get("mutations") or []),
    }


def run_controller(
    *,
    skill_roots: Iterable[Path],
    workspace_root: Path,
    out_root: Path,
    mode: str = "dry_run",
    unattended: bool = True,
    run_id: str | None = None,
    max_mutations: int = 5,
) -> dict[str, Any]:
    run_id = validate_run_id(run_id or f"controller-{utc_run_id()}")
    run_dir = Path(out_root).expanduser() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    review = build_skill_review(skill_roots=skill_roots, run_id=f"{run_id}-review", limit=None)
    _write_json(run_dir / "review.json", review)
    plan = build_controller_plan_from_review(review=review, workspace_root=workspace_root, plan_id=f"{run_id}-plan", max_mutations=max_mutations)
    _write_json(run_dir / "plan.json", plan)
    policy = build_policy_for_plan(plan=plan, mode=mode, unattended=unattended)
    _write_json(run_dir / "policy.json", policy)

    apply_receipt: dict[str, Any] | None = None
    verify_receipt: dict[str, Any] | None = None
    rollback_receipt: dict[str, Any] | None = None
    if policy.get("decision") == "apply" and plan.get("mutations"):
        apply_receipt = apply_plan(
            plan=plan,
            workspace_root=workspace_root,
            checkpoint_root=run_dir / "checkpoints",
            receipt_root=run_dir,
            run_id="apply",
        )
        verify_receipt = verify_apply_receipt(receipt=apply_receipt)
        _write_json(run_dir / "verify.json", verify_receipt)
        if not verify_receipt.get("ok"):
            rollback_receipt = rollback_apply_receipt(receipt=apply_receipt, out_root=run_dir)
            _write_json(run_dir / "rollback-receipt.json", rollback_receipt)
    report_lines = [
        "# Self Curator controller report",
        "",
        f"- run_id: `{run_id}`",
        f"- mode: `{mode}`",
        f"- unattended: {str(unattended).lower()}",
        f"- decision: `{policy.get('decision')}`",
        f"- reviewed candidates: {review.get('summary', {}).get('candidate_count', 0)}",
        f"- planned mutations: {len(plan.get('mutations') or [])}",
        f"- writes_performed: {apply_receipt.get('writes_performed') if apply_receipt else 0}",
        f"- verify_ok: {verify_receipt.get('ok') if verify_receipt else None}",
        "",
        "## Artifacts",
        "",
        "- review: `review.json`",
        "- plan: `plan.json`",
        "- policy: `policy.json`",
    ]
    if apply_receipt:
        report_lines.append("- apply receipt: `apply/apply-receipt.json`")
        report_lines.append("- diff: `apply/apply.diff`")
    if verify_receipt:
        report_lines.append("- verify: `verify.json`")
    if rollback_receipt:
        report_lines.append("- rollback: `rollback-receipt.json`")
    (run_dir / "REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    receipt = {
        "kind": CONTROLLER_RECEIPT_KIND,
        "run_id": run_id,
        "ts": _utc_iso(),
        "mode": mode,
        "unattended": unattended,
        "run_dir": str(run_dir),
        "review_path": str(run_dir / "review.json"),
        "plan_path": str(run_dir / "plan.json"),
        "policy_path": str(run_dir / "policy.json"),
        "report_path": str(run_dir / "REPORT.md"),
        "decision": policy.get("decision"),
        "writes_performed": apply_receipt.get("writes_performed") if apply_receipt else 0,
        "verify_ok": verify_receipt.get("ok") if verify_receipt else None,
        "rollback_performed": rollback_receipt is not None,
        "apply_receipt_path": apply_receipt.get("receipt_path") if apply_receipt else None,
    }
    _write_json(run_dir / "controller-receipt.json", receipt)
    return receipt
