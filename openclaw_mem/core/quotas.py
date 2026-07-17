"""Deterministic soft category quotas for pack candidate selection."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


def candidate_kind(candidate: Mapping[str, Any]) -> str:
    direct = str(candidate.get("kind") or "").strip().lower()
    if direct:
        return direct
    row = candidate.get("row")
    return str(row.get("kind") or "").strip().lower() if isinstance(row, Mapping) else ""


def candidate_ref(candidate: Mapping[str, Any]) -> str:
    direct = str(candidate.get("recordRef") or "").strip()
    if direct:
        return direct
    row_id = candidate.get("id", candidate.get("rid"))
    return f"obs:{int(row_id)}" if row_id is not None else ""


def _eligible(candidate: Mapping[str, Any]) -> bool:
    return bool(candidate.get("_quota_eligible", True))


def apply_soft_quotas(
    candidates: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    enabled: bool,
    preference_min: int = 1,
    decision_min: int = 1,
    event_max_ratio: float = 0.4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Promote required kinds and mark excess events without mutating inputs."""

    items = [dict(candidate) for candidate in candidates]
    if not enabled or not items:
        return items, []

    bounded_limit = max(0, int(limit))
    reserved: list[dict[str, Any]] = []
    reserved_indexes: set[int] = set()
    hits: list[dict[str, Any]] = []
    remaining_slots = bounded_limit

    for kind, minimum in (
        ("preference", max(0, int(preference_min))),
        ("decision", max(0, int(decision_min))),
    ):
        wanted = min(minimum, remaining_slots)
        indexes = [
            index
            for index, item in enumerate(items)
            if index not in reserved_indexes
            and _eligible(item)
            and candidate_kind(item) == kind
        ][:wanted]
        if indexes:
            refs = [candidate_ref(items[index]) for index in indexes]
            hits.append({"kind": kind, "action": "reserved", "refs": refs})
            reserved.extend(items[index] for index in indexes)
            reserved_indexes.update(indexes)
            remaining_slots -= len(indexes)

    ordered = reserved + [
        item for index, item in enumerate(items) if index not in reserved_indexes
    ]
    ratio = min(1.0, max(0.0, float(event_max_ratio)))
    event_limit = int(math.floor(bounded_limit * ratio))
    event_seen = 0
    capped_refs: list[str] = []
    for item in ordered:
        if not _eligible(item) or candidate_kind(item) != "event":
            continue
        if event_seen >= event_limit:
            item["quota_capped"] = True
            capped_refs.append(candidate_ref(item))
        else:
            event_seen += 1
    if capped_refs:
        hits.append({"kind": "event", "action": "capped", "refs": capped_refs})
    return ordered, hits


def finalize_quota_hits(
    hits: Sequence[Mapping[str, Any]],
    *,
    selected_refs: Sequence[str],
) -> list[dict[str, Any]]:
    """Report reservations only when they survived all downstream pack gates."""

    selected = set(selected_refs)
    finalized: list[dict[str, Any]] = []
    for raw in hits:
        hit = dict(raw)
        refs = [str(ref) for ref in hit.get("refs") or []]
        if str(hit.get("action")) == "reserved":
            refs = [ref for ref in refs if ref in selected]
        if refs:
            hit["refs"] = refs
            finalized.append(hit)
    return finalized
