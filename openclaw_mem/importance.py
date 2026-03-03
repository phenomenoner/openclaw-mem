from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict
import unicodedata


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

    # Width-normalize first so full-width variants like
    # `ＭＵＳＴ＿ＲＥＭＥＭＢＥＲ` / `ＮＩＣＥ－ＴＯ－ＨＡＶＥ` are accepted.
    key = unicodedata.normalize("NFKC", value).strip().lower()
    key = _LABEL_ALIAS_TO_CANONICAL.get(key, key)
    if key in _LABEL_TO_SCORE:
        return key
    return None


def normalize_label(value: Any) -> str | None:
    """Public wrapper for label normalization.

    Keeps CLI receipts and any external callers aligned with the
    same backward-compatible aliases used by the importance parser.
    """

    return _normalize_label(value)


def _parse_score_like(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        score = float(value)
        if math.isfinite(score):
            return score
        return None

    if isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized:
            return None

        # Explicit percent form: '86%' -> 0.86
        if normalized.endswith('%'):
            raw = normalized[:-1].strip()
            if not raw:
                return None
            try:
                score = float(raw) / 100.0
            except Exception:
                return None
            if math.isfinite(score):
                return score
            return None

        # Explicit ratio form: '86/100' -> 0.86
        if '/' in normalized:
            left, right = normalized.split('/', 1)
            left = left.strip()
            right = right.strip()
            if not left or not right:
                return None
            try:
                num = float(left)
                den = float(right)
            except Exception:
                return None
            if not math.isfinite(num) or not math.isfinite(den) or den == 0.0:
                return None
            score = num / den
            if math.isfinite(score):
                return score
            return None

        try:
            score = float(normalized)
        except Exception:
            return None
        if math.isfinite(score):
            return score
        return None

    return None


def is_parseable_importance(value: Any) -> bool:
    """Return whether `detail_json.importance` carries parseable signal."""
    if _parse_score_like(value) is not None:
        return True

    if isinstance(value, dict):
        if _parse_score_like(value.get("score")) is not None:
            return True

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
    normalized = _normalize_label(label)
    lab = normalized if normalized is not None else label_from_score(s)

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


def _coerce_percent_if_intlike(score: float) -> float:
    """Coerce common integer-ish 0-100 scores into 0-1 percent form."""

    s = float(score)
    if s > 1.0 and s <= 100.0 and s.is_integer():
        return s / 100.0
    return s


def parse_importance_score(value: Any) -> float:
    """Best-effort parse of an importance score from detail_json.importance.

    Compatibility:
    - canonical: object form {"score": 0.86, ...}
    - legacy: numeric form 0.86

    Returns:
      float score clamped to [0,1]. Missing/invalid returns 0.0.
    """
    score = _parse_score_like(value)
    if score is not None:
        return _clamp01(_coerce_percent_if_intlike(score))

    if isinstance(value, dict):
        score = _parse_score_like(value.get("score"))
        if score is not None:
            return _clamp01(_coerce_percent_if_intlike(score))

        key = _normalize_label(value.get("label"))
        if key is not None:
            return _LABEL_TO_SCORE[key]

    return 0.0
