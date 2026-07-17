"""Opt-in composite retrieval scoring with per-factor evidence."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from openclaw_mem.core.lifecycle import state_from_detail
from openclaw_mem.importance import label_from_score, normalize_label, parse_importance_score


HALF_LIFE_DAYS = {
    "preference": 365.0,
    "decision": 180.0,
    "fact": 120.0,
    "entity": 120.0,
    "plan": 60.0,
    "learning": 180.0,
    "event": 14.0,
    "note": 30.0,
    "tool": 30.0,
}
IMPORTANCE_WEIGHTS = {
    "must_remember": 1.2,
    "nice_to_have": 1.0,
    "unknown": 1.0,
    "ignore": 0.8,
}
STATE_GATES = {
    "active": 1.0,
    "captured": 1.0,
    "categorized": 1.0,
    "consolidated": 0.9,
    "stale": 0.5,
    "soft-archived": 0.0,
    "archived": 0.0,
}


def scoring_kwargs(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize resolved config or an argparse-shaped mapping for core calls."""

    scoring = value.get("scoring") if isinstance(value.get("scoring"), Mapping) else value

    def enabled(name: str) -> bool:
        nested = scoring.get(name) if isinstance(scoring, Mapping) else None
        if isinstance(nested, Mapping):
            return bool(nested.get("enabled", True))
        return bool(scoring.get(f"{name}_enabled", True)) if isinstance(scoring, Mapping) else True

    return {
        "scoring_profile": str(scoring.get("profile", "relevance") if isinstance(scoring, Mapping) else "relevance"),
        "scoring_relevance_enabled": enabled("relevance"),
        "scoring_importance_enabled": enabled("importance"),
        "scoring_recency_enabled": enabled("recency"),
        "scoring_use_enabled": enabled("use"),
        "scoring_state_enabled": enabled("state"),
    }


def _parse_detail(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_time(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _importance_label(detail: Mapping[str, Any]) -> str:
    value = detail.get("importance")
    if isinstance(value, Mapping):
        normalized = normalize_label(value.get("label"))
        if normalized:
            return normalized
    elif isinstance(value, str):
        normalized = normalize_label(value)
        if normalized:
            return normalized
    if value is None:
        return "unknown"
    return label_from_score(parse_importance_score(value))


def score_components(
    *,
    relevance: float,
    kind: str,
    ts: Any,
    detail: Mapping[str, Any],
    now: datetime,
    relevance_enabled: bool = True,
    importance_enabled: bool = True,
    recency_enabled: bool = True,
    use_enabled: bool = True,
    state_enabled: bool = True,
) -> dict[str, Any]:
    lifecycle = detail.get("lifecycle") if isinstance(detail.get("lifecycle"), Mapping) else {}
    importance_label = _importance_label(detail)
    importance_weight = IMPORTANCE_WEIGHTS.get(importance_label, 1.0) if importance_enabled else 1.0

    observed_at = _parse_time(ts)
    age_days = max(0.0, (now - observed_at).total_seconds() / 86400.0) if observed_at else 0.0
    half_life = HALF_LIFE_DAYS.get(str(kind or "note").strip().lower(), HALF_LIFE_DAYS["note"])
    recency_decay = math.pow(0.5, age_days / half_life) if recency_enabled else 1.0

    try:
        used_count = max(0, int(lifecycle.get("used_count") or 0))
    except (TypeError, ValueError):
        used_count = 0
    use_boost = min(1.3, 1.0 + 0.1 * math.log1p(used_count)) if use_enabled else 1.0
    state = state_from_detail(detail)
    state_gate = STATE_GATES.get(state, 1.0) if state_enabled else 1.0
    relevance_factor = max(0.0, float(relevance)) if relevance_enabled else 1.0
    final = relevance_factor * importance_weight * recency_decay * use_boost * state_gate
    return {
        "relevance": relevance_factor,
        "importance_weight": importance_weight,
        "importance_label": importance_label,
        "recency_decay": recency_decay,
        "age_days": age_days,
        "half_life_days": half_life,
        "use_boost": use_boost,
        "used_count": used_count,
        "state_gate": state_gate,
        "state": state,
        "final": final,
        "enabled": {
            "relevance": bool(relevance_enabled),
            "importance": bool(importance_enabled),
            "recency": bool(recency_enabled),
            "use": bool(use_enabled),
            "state": bool(state_enabled),
        },
    }


def score_results(
    conn: sqlite3.Connection,
    results: Sequence[Mapping[str, Any]],
    *,
    profile: str = "relevance",
    relevance_enabled: bool = True,
    importance_enabled: bool = True,
    recency_enabled: bool = True,
    use_enabled: bool = True,
    state_enabled: bool = True,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return the input order/shape unchanged for the relevance profile."""

    items = [dict(item) for item in results]
    if str(profile or "relevance").strip().lower() != "composite" or not items:
        return items
    ids = [int(item["id"]) for item in items if item.get("id") is not None]
    rows = conn.execute(
        f"SELECT id, ts, kind, detail_json FROM observations WHERE id IN ({','.join('?' for _ in ids)})",
        ids,
    ).fetchall() if ids else []
    metadata = {
        int(row[0]): {
            "ts": row[1],
            "kind": row[2],
            "detail": _parse_detail(row[3]),
        }
        for row in rows
    }
    # Recency half-lives are measured in days.  A UTC-day reference keeps
    # receipts deterministic across equivalent CLI/MCP calls without changing
    # any meaningful decay boundary.
    reference_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reference_time = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        row_id = int(item.get("id") or -1)
        meta = metadata.get(row_id, {})
        raw_relevance = item.get("rrf_score", item.get("score"))
        relevance = (
            float(raw_relevance)
            if isinstance(raw_relevance, (int, float)) and float(raw_relevance) > 0.0
            else 1.0 / (60.0 + index + 1.0)
        )
        components = score_components(
            relevance=relevance,
            kind=str(meta.get("kind") or item.get("kind") or "note"),
            ts=meta.get("ts", item.get("ts")),
            detail=meta.get("detail") if isinstance(meta.get("detail"), Mapping) else {},
            now=reference_time,
            relevance_enabled=relevance_enabled,
            importance_enabled=importance_enabled,
            recency_enabled=recency_enabled,
            use_enabled=use_enabled,
            state_enabled=state_enabled,
        )
        item["score_components"] = components
        item["final_score"] = float(components["final"])
        scored.append((float(components["final"]), index, item))
    scored.sort(key=lambda value: (-value[0], value[1]))
    return [item for _score, _index, item in scored]
