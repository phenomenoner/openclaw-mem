"""Staged skill-capture proposal helpers.

This is intentionally not a live skill mutation system.  It lets an agent mark a
bounded learning candidate during a turn and write an L1 proposal artifact for a
later curator/reviewer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "openclaw-mem.skill-capture.proposal.v0"
MAX_TEXT_CHARS = 4000
MAX_CANDIDATES_PER_TURN = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_candidate_id(text: str, *, target_skill: str | None = None, source_ref: str | None = None) -> str:
    seed = "\0".join([target_skill or "", source_ref or "", text])
    return "skill-capture-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def build_proposal(
    *,
    text: str,
    source_ref: str | None = None,
    target_skill: str | None = None,
    rationale: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    body = str(text or "").strip()
    errors: list[str] = []
    warnings: list[str] = []
    if not body:
        errors.append("text is required")
    if len(body) > MAX_TEXT_CHARS:
        errors.append(f"text exceeds {MAX_TEXT_CHARS} chars")
    if target_skill and any(part in target_skill for part in ("..", "/", "\\")):
        errors.append("target_skill must be a skill name, not a path")
    if not rationale:
        warnings.append("rationale is recommended for curator review")

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not errors,
        "mode": "stage",
        "risk_class": "L1",
        "writes_performed": False,
        "candidate_id": stable_candidate_id(body, target_skill=target_skill, source_ref=source_ref),
        "run_id": run_id,
        "source_ref": source_ref,
        "target_skill": target_skill,
        "proposal": {
            "text": body,
            "rationale": rationale,
            "action": "propose_skill_update",
        },
        "limits": {
            "max_text_chars": MAX_TEXT_CHARS,
            "max_candidates_per_turn": MAX_CANDIDATES_PER_TURN,
        },
        "errors": errors,
        "warnings": warnings,
        "created_at": now_iso(),
    }


def write_proposal(proposal: dict[str, Any], *, out: str | Path | None = None, out_dir: str | Path | None = None) -> Path:
    if out and out_dir:
        raise ValueError("provide only one of out or out_dir")
    if out:
        path = Path(out)
    else:
        root = Path(out_dir or ".state/skill-capture/proposals")
        path = root / f"{proposal.get('candidate_id')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = dict(proposal)
    stored["writes_performed"] = True
    stored["write_scope"] = "staged_proposal_artifact"
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
