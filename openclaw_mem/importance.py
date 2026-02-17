from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict


def _clamp01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


_LABEL_TO_SCORE = {
    # Conservative representative scores aligned to MVP v1 thresholds.
    # This mapping is only used when the canonical `score` field is missing.
    "ignore": 0.0,
    "nice_to_have": 0.5,
    "must_remember": 0.8,
}

# Backward-compatible aliases used by older/inconsistently-normalized payloads.
_LABEL_ALIAS_TO_CANONICAL = {
    "must remember": "must_remember",
    "must-remember": "must_remember",
    "nice to have": "nice_to_have",
    "nice-to-have": "nice_to_have",
    "low": "ignore",
    "medium": "nice_to_have",
    "high": "must_remember",
}


def label_from_score(score: float) -> str:
    s = _clamp01(float(score))
    if s >= 0.80:
        return "must_remember"
    if s >= 0.50:
        return "nice_to_have"
    return "ignore"


def _normalize_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    key = _LABEL_ALIAS_TO_CANONICAL.get(key, key)
    if key in _LABEL_TO_SCORE:
        return key
    return None


def is_parseable_importance(value: Any) -> bool:
    """Return whether `detail_json.importance` carries parseable signal."""
    if isinstance(value, bool):
        return False

    if isinstance(value, (int, float)):
        return math.isfinite(float(value))

    if isinstance(value, dict):
        score = value.get("score")
        if isinstance(score, bool):
            score = None
        if isinstance(score, (int, float)):
            return math.isfinite(float(score))

        return _normalize_label(value.get("label")) is not None

    return False


def make_importance(
    score: float,
    *,
    method: str,
    rationale: str,
    version: int = 1,
    graded_at: str | None = None,
    label: str | None = None,
) -> Dict[str, Any]:
    """Build a canonical `detail_json.importance` object.

    Canonical schema lives in the playbook project docs; this helper keeps
    CLI/tooling writes consistent and reversible.
    """
    s = _clamp01(float(score))
    lab = (label or label_from_score(s)).strip().lower()

    ts = graded_at
    if not ts:
        ts = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    return {
        "score": s,
        "label": lab,
        "rationale": rationale,
        "method": method,
        "version": int(version),
        "graded_at": ts,
    }


def parse_importance_score(value: Any) -> float:
    """Best-effort parse of an importance score from detail_json.importance.

    Compatibility:
    - canonical: object form {"score": 0.86, ...}
    - legacy: numeric form 0.86

    Returns:
      float score clamped to [0,1]. Missing/invalid returns 0.0.
    """
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return _clamp01(float(value))

    if isinstance(value, dict):
        score = value.get("score")
        if isinstance(score, bool):
            score = None
        if isinstance(score, (int, float)):
            return _clamp01(float(score))

        key = _normalize_label(value.get("label"))
        if key is not None:
            return _LABEL_TO_SCORE[key]

    return 0.0
