"""Deterministic source ingestion review helpers.

The reviewer turns public/source text into candidate memory records, entity hints,
and follow-up actions without writing to the durable store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "openclaw-mem.ingestion-review.v0"

DECISION_RE = re.compile(r"^(?:decision|decided|決策|決定)\s*[:：-]\s*(?P<text>.+)$", re.IGNORECASE)
TODO_RE = re.compile(r"^(?:todo|next|follow[- ]?up|action|下一步|待辦)\s*[:：-]\s*(?P<text>.+)$", re.IGNORECASE)
ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9_.-]{2,}(?:\s+[A-Z][A-Za-z0-9_.-]{2,}){0,3}\b")
INJECTION_TERMS = (
    "ignore previous instructions",
    "reveal your system prompt",
    "delete all",
    "exfiltrate",
    "api key",
    "password",
    "secret token",
)
PRIVATE_MARKERS = (
    "private-channel:",
    "private-user:",
    "operator-ledger",
    "local-only receipt",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _contains_any(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term in lowered]


def _snippet(text: str, *, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class SourceReviewPolicy:
    max_candidates: int = 12
    max_entity_hints: int = 16


def review_source(text: str, *, source_kind: str = "text", source_ref: str | None = None, policy: SourceReviewPolicy | None = None) -> dict[str, Any]:
    """Review one source and emit public-safe candidate records.

    This is intentionally deterministic and side-effect-free. It does not fetch
    URLs, call models, or write memory.
    """

    policy = policy or SourceReviewPolicy()
    lines = _split_lines(text)
    candidates: list[dict[str, Any]] = []
    follow_up_actions: list[dict[str, Any]] = []
    entity_seen: set[str] = set()
    entity_hints: list[dict[str, Any]] = []
    risk_terms = _contains_any(text, INJECTION_TERMS)
    private_markers = _contains_any(text, PRIVATE_MARKERS)

    if risk_terms:
        candidates.append(
            {
                "recordRef": "source:risk:1",
                "category": "risk",
                "trust": "untrusted",
                "importance": {"score": 0.8, "label": "must_remember", "method": "ingestion-review-v0"},
                "text": "Source contains prompt-injection or secret-seeking language; quarantine before use.",
                "reasons": ["source_risk_terms_detected"],
            }
        )

    for idx, line in enumerate(lines, start=1):
        if len(candidates) >= policy.max_candidates:
            break
        decision_match = DECISION_RE.match(line)
        todo_match = TODO_RE.match(line)
        if decision_match:
            candidates.append(
                {
                    "recordRef": f"source:line:{idx}",
                    "category": "decision",
                    "trust": "unknown",
                    "importance": {"score": 0.85, "label": "must_remember", "method": "ingestion-review-v0"},
                    "text": _snippet(decision_match.group("text")),
                    "source_kind": source_kind,
                    "source_ref": source_ref,
                    "reasons": ["explicit_decision_marker"],
                }
            )
        elif todo_match:
            action = {
                "source_line": idx,
                "action": _snippet(todo_match.group("text")),
                "status": "candidate",
                "source_kind": source_kind,
                "source_ref": source_ref,
            }
            follow_up_actions.append(action)
            candidates.append(
                {
                    "recordRef": f"source:line:{idx}",
                    "category": "todo",
                    "trust": "unknown",
                    "importance": {"score": 0.65, "label": "nice_to_have", "method": "ingestion-review-v0"},
                    "text": action["action"],
                    "source_kind": source_kind,
                    "source_ref": source_ref,
                    "reasons": ["explicit_follow_up_marker"],
                }
            )

        for match in ENTITY_RE.finditer(line):
            entity = match.group(0).strip()
            if entity.lower() in {"todo", "next", "decision"} or entity in entity_seen:
                continue
            entity_seen.add(entity)
            entity_hints.append({"name": entity, "source_line": idx, "source_kind": source_kind, "source_ref": source_ref})
            if len(entity_hints) >= policy.max_entity_hints:
                break

    return {
        "schema_version": SCHEMA_VERSION,
        "reviewed_at": _now_iso(),
        "source_kind": source_kind,
        "source_ref": source_ref,
        "summary": {
            "line_count": len(lines),
            "candidate_count": len(candidates),
            "entity_hint_count": len(entity_hints),
            "follow_up_count": len(follow_up_actions),
            "risk_term_count": len(risk_terms),
            "private_marker_count": len(private_markers),
        },
        "candidates": candidates,
        "entity_hints": entity_hints,
        "follow_up_actions": follow_up_actions,
        "risk_terms": risk_terms,
        "private_markers": private_markers,
        "writes_performed": False,
        "apply_allowed": False,
    }
