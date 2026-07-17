"""Canonical memory taxonomy and deterministic bilingual classification."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import Counter
from typing import Any, Mapping


CANONICAL_KINDS = frozenset(
    {"fact", "preference", "decision", "entity", "event", "plan", "learning", "note"}
)
CLASSIFIABLE_KINDS = frozenset({"", "note", "tool"})

_LEARNING_PROBLEM_EN = re.compile(r"\b(error|failed|failure|bug|broken|issue|problem)\b", re.I)
_LEARNING_SOLUTION_EN = re.compile(r"\b(fix(?:ed)?|solution|resolved?|workaround|repair(?:ed)?)\b", re.I)
_DECISION_EN = re.compile(r"\b(decided|decision|we chose|we choose|chosen)\b", re.I)
_PREFERENCE_EN = re.compile(r"\b(prefer(?:red|s)?|preference|always use|i like)\b", re.I)
_PLAN_EN = re.compile(r"\b(plan(?:ned)? to|planning to|intend to|will|todo)\b", re.I)


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def classify(
    text: Any,
    tool_name: Any = None,
    explicit: Any = None,
) -> tuple[str, float, str]:
    """Return ``(kind, confidence, method)`` without models or network access.

    Explicit kinds other than the legacy capture aliases are authoritative.
    ``note``, ``tool``, and an empty kind enter the deterministic classifier.
    """

    explicit_value = str(explicit or "").strip()
    if explicit_value.lower() not in CLASSIFIABLE_KINDS:
        return explicit_value, 1.0, "explicit"

    normalized = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    tool = unicodedata.normalize("NFKC", str(tool_name or "")).strip().lower()

    problem_zh = _contains_any(normalized, ("錯誤", "报错", "報錯", "失敗", "故障", "問題"))
    solution_zh = _contains_any(normalized, ("解法", "修正", "修復", "解决", "解決", "繞過", "绕过"))
    if (problem_zh and solution_zh) or (
        bool(_LEARNING_PROBLEM_EN.search(normalized))
        and bool(_LEARNING_SOLUTION_EN.search(normalized))
    ):
        return "learning", 0.95, "rule:problem-solution"

    if _contains_any(normalized, ("決定", "决定", "決議", "决议", "採用", "采用")) or _DECISION_EN.search(normalized):
        return "decision", 0.95, "rule:decision"
    if _contains_any(normalized, ("偏好", "總是使用", "总是使用", "喜歡", "喜欢")) or _PREFERENCE_EN.search(normalized):
        return "preference", 0.95, "rule:preference"
    if _contains_any(normalized, ("計畫", "计划", "打算", "預計", "预计", "將會", "将会", "待辦", "待办")) or _PLAN_EN.search(normalized):
        return "plan", 0.90, "rule:plan"

    method = "fallback:memory-store" if tool in {"memory_store", "memory.store"} else "fallback:note"
    return "note", 0.25, method


def _detail(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _distribution(rows: list[tuple[int, str, str, str, str]]) -> dict[str, int]:
    counts = Counter((str(row[1] or "").strip() or "<empty>") for row in rows)
    return dict(sorted(counts.items()))


def backfill_kinds(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    batch_size: int = 500,
) -> dict[str, Any]:
    """Classify eligible legacy rows once and return before/after distributions."""

    bounded_batch = max(1, min(10_000, int(batch_size)))
    raw_rows = conn.execute(
        "SELECT id, kind, summary, tool_name, detail_json FROM observations ORDER BY id"
    ).fetchall()
    rows = [tuple(row) for row in raw_rows]
    before = _distribution(rows)
    updates: list[tuple[str, str, int]] = []
    predicted = Counter(before)

    for row_id, kind, summary, tool_name, detail_json in rows:
        explicit = str(kind or "").strip()
        if explicit.lower() not in CLASSIFIABLE_KINDS:
            continue
        detail = _detail(detail_json)
        if isinstance(detail.get("classification"), Mapping):
            continue
        classified, confidence, method = classify(summary, tool_name, explicit)
        detail["classification"] = {
            "method": method,
            "confidence": confidence,
        }
        old_label = explicit or "<empty>"
        if old_label != classified:
            predicted[old_label] -= 1
            predicted[classified] += 1
        updates.append(
            (
                classified,
                json.dumps(detail, ensure_ascii=False, sort_keys=True),
                int(row_id),
            )
        )

    if not dry_run:
        for offset in range(0, len(updates), bounded_batch):
            conn.executemany(
                "UPDATE observations SET kind = ?, detail_json = ? WHERE id = ?",
                updates[offset : offset + bounded_batch],
            )

    after = {
        key: int(value)
        for key, value in sorted(predicted.items())
        if int(value) > 0
    }
    return {
        "kind": "openclaw-mem.db.backfill.kind.v1",
        "field": "kind",
        "dry_run": bool(dry_run),
        "eligible": len(updates),
        "updated": 0 if dry_run else len(updates),
        "would_update": len(updates),
        "batch_size": bounded_batch,
        "distribution_before": before,
        "distribution_after": after,
        "idempotent": len(updates) == 0,
    }
