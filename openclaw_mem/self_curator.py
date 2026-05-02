"""Review-only lifecycle curator sidecar.

The v0 sidecar is intentionally deterministic and zero-write with respect to the
surfaces it reviews. It may write only its own run artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
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
