"""Deterministic memory steward review helpers.

This module is intentionally review-only: it classifies candidate memory/context
records and emits suggested lifecycle actions, but never mutates storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from openclaw_mem.importance import parse_importance_score
from openclaw_mem.provenance_trust_schema import normalize_trust_tier

SCHEMA_VERSION = "openclaw-mem.steward-review.v0"

PROMOTE_CATEGORIES = {"decision", "preference", "fact", "constraint", "runbook", "todo"}
PROMOTE_TERMS = (
    "decision",
    "decided",
    "must remember",
    "do not forget",
    "rollback",
    "verifier",
    "success criteria",
    "authority",
)
LOW_SIGNAL_TERMS = (
    "same state",
    "no change",
    "still running",
    "routine heartbeat",
    "empty result",
)
UNTRUSTED_RISK_TERMS = (
    "ignore previous instructions",
    "reveal your system prompt",
    "delete all",
    "send this to",
    "exfiltrate",
    "api key",
    "password",
    "secret token",
)
PUBLIC_PRIVATE_MARKERS = (
    "/home/",
    "/users/",
    "private-channel:",
    "private-user:",
    "operator-ledger",
    "local-only receipt",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("text") or candidate.get("summary") or candidate.get("content") or ""
    return str(value)


def _contains_any(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term in lowered]


def public_safety_markers(text: str) -> list[str]:
    """Return public-repo leakage markers found in text.

    This is a conservative string scan, not a secret detector. It is intended as a
    cheap guard before writing public-facing roadmap/spec docs.
    """

    lowered = text.lower()
    return [marker for marker in PUBLIC_PRIVATE_MARKERS if marker.lower() in lowered]


@dataclass(frozen=True)
class StewardPolicy:
    promote_threshold: float = 0.80
    nice_threshold: float = 0.50


def review_candidate(candidate: Mapping[str, Any], *, policy: StewardPolicy | None = None) -> dict[str, Any]:
    """Build a deterministic, review-only lifecycle recommendation.

    The returned object is intentionally side-effect-free. Downstream apply paths
    must checkpoint and verify separately before mutating any durable store.
    """

    policy = policy or StewardPolicy()
    text = _text(candidate)
    category = str(candidate.get("category") or candidate.get("type") or "unknown").strip().lower()
    trust = normalize_trust_tier(candidate.get("trust") or candidate.get("trust_tier") or "unknown") or "unknown"
    importance_score = parse_importance_score(candidate.get("importance"))
    reasons: list[str] = []
    lanes: list[str] = []

    risky_terms = _contains_any(text, UNTRUSTED_RISK_TERMS)
    if trust in {"untrusted", "quarantined"} and risky_terms:
        action = "quarantine_candidate"
        reasons.append("untrusted_risky_content")
        lanes.append("trust_policy_review")
    else:
        promote_terms = _contains_any(text, PROMOTE_TERMS)
        low_signal_terms = _contains_any(text, LOW_SIGNAL_TERMS)
        if category in PROMOTE_CATEGORIES and importance_score >= policy.promote_threshold:
            action = "promote_to_memory_candidate"
            reasons.append("high_importance_promotable_category")
            lanes.append("store")
        elif promote_terms and importance_score >= policy.nice_threshold:
            action = "promote_to_memory_candidate"
            reasons.append("promotable_terms_with_nontrivial_importance")
            lanes.append("store")
        elif low_signal_terms and importance_score < policy.nice_threshold:
            action = "archive_or_ignore_candidate"
            reasons.append("low_signal_operational_chatter")
            lanes.append("observe")
        else:
            action = "keep_observed_candidate"
            reasons.append("insufficient_signal_for_mutation")
            lanes.append("observe")

    if candidate.get("selected_in_context") is True:
        lanes.append("pack")
        reasons.append("selected_into_context_pack")

    leakage_markers = public_safety_markers(text)
    if leakage_markers:
        reasons.append("public_safety_review_required")
        lanes.append("public_safety")

    return {
        "schema_version": SCHEMA_VERSION,
        "record_ref": candidate.get("recordRef") or candidate.get("record_ref") or candidate.get("id"),
        "action": action,
        "lanes": sorted(set(lanes)),
        "reasons": reasons,
        "importance_score": importance_score,
        "trust": trust,
        "category": category,
        "public_safety_markers": leakage_markers,
        "side_effects": [],
        "apply_allowed": False,
        "reviewed_at": _now_iso(),
    }


def review_candidates(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
    reviews = [review_candidate(candidate) for candidate in candidates]
    counts: dict[str, int] = {}
    for review in reviews:
        action = str(review["action"])
        counts[action] = counts.get(action, 0) + 1
    return {
        "schema_version": "openclaw-mem.steward-review-batch.v0",
        "reviewed_at": _now_iso(),
        "count": len(reviews),
        "action_counts": dict(sorted(counts.items())),
        "reviews": reviews,
        "side_effects": [],
        "apply_allowed": False,
    }
