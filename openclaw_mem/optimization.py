from __future__ import annotations

import json
import math
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from openclaw_mem import __version__
from openclaw_mem.importance import is_parseable_importance, label_from_score, normalize_label, parse_importance_score
from openclaw_mem.scope import normalize_scope_token as _normalize_scope_token


_STOPWORDS: Set[str] = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "via",
    "with",
}

_WORD_TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

_IMPORTANCE_HIGH_RISK_UNDERLABEL_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"\bapi[\s_\-]*key\b", re.IGNORECASE)),
    ("private_key", re.compile(r"\b(private|secret|ssh)[\s_\-]*key\b", re.IGNORECASE)),
    ("password", re.compile(r"\b(password|passphrase)\b", re.IGNORECASE)),
    ("seed_phrase", re.compile(r"\b(seed[\s_\-]*phrase|mnemonic)\b", re.IGNORECASE)),
    ("access_token", re.compile(r"\b(access|refresh)[\s_\-]*token\b", re.IGNORECASE)),
    ("zh_password", re.compile(r"密碼")),
    ("zh_private_key", re.compile(r"私鑰|金鑰")),
    ("zh_seed_phrase", re.compile(r"助記詞|種子詞")),
    ("zh_token", re.compile(r"存取權杖|刷新權杖")),
]

_IMPORTANCE_DRIFT_THRESHOLD_PROFILES: Dict[str, Dict[str, float]] = {
    "strict": {
        "score_label_mismatch_count_lte": 1.0,
        "score_label_mismatch_rate_pct_lte": 2.0,
        "missing_or_unparseable_count_lte": 0.0,
        "missing_or_unparseable_rate_pct_lte": 0.0,
        "high_risk_underlabel_count_lte": 0.0,
        "high_risk_underlabel_rate_pct_lte": 0.0,
    },
    "balanced": {
        "score_label_mismatch_count_lte": 3.0,
        "score_label_mismatch_rate_pct_lte": 5.0,
        "missing_or_unparseable_count_lte": 1.0,
        "missing_or_unparseable_rate_pct_lte": 2.0,
        "high_risk_underlabel_count_lte": 0.0,
        "high_risk_underlabel_rate_pct_lte": 0.0,
    },
    "lenient": {
        "score_label_mismatch_count_lte": 5.0,
        "score_label_mismatch_rate_pct_lte": 10.0,
        "missing_or_unparseable_count_lte": 2.0,
        "missing_or_unparseable_rate_pct_lte": 5.0,
        "high_risk_underlabel_count_lte": 1.0,
        "high_risk_underlabel_rate_pct_lte": 1.0,
    },
}

_DEFAULT_IMPORTANCE_DRIFT_PROFILE = "strict"

_SOFT_ARCHIVE_LOW_IMPORTANCE_LABELS: Set[str] = {
    "ignore",
    "nice_to_have",
}


_EPISODIC_RETENTION_DAYS: Dict[str, Optional[int]] = {
    "conversation.user": 60,
    "conversation.assistant": 90,
    "tool.call": 30,
    "tool.result": 30,
    "ops.alert": 90,
    "ops.decision": None,
}

_PACK_LIFECYCLE_SHADOW_TABLE = "pack_lifecycle_shadow_log"
_OBS_REF_RE = re.compile(r"^obs:(\d+)$")
_CO_SELECTION_RECENCY_HALF_LIFE_DAYS = 30.0

_LINK_CONFIDENCE_MODEL_V0: Dict[str, Dict[str, Any]] = {
    "receipt_co_selection": {
        "base": 0.62,
        "cap": 0.95,
        "weights": {
            "co_selection_events": 0.16,
            "shared_selected_count": 0.12,
            "co_selection_recency": 0.08,
            "lexical_score": 0.07,
            "shared_token_count": 0.05,
        },
    },
    "lexical_backfill_low_confidence": {
        "base": 0.30,
        "cap": 0.55,
        "weights": {
            "co_selection_events": 0.00,
            "shared_selected_count": 0.00,
            "co_selection_recency": 0.00,
            "lexical_score": 0.18,
            "shared_token_count": 0.10,
        },
    },
    "lexical_fallback": {
        "base": 0.46,
        "cap": 0.78,
        "weights": {
            "co_selection_events": 0.00,
            "shared_selected_count": 0.00,
            "co_selection_recency": 0.00,
            "lexical_score": 0.20,
            "shared_token_count": 0.11,
        },
    },
}


def _parse_iso_utc(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts.strip():
        return None
    value = ts.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_summary(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    t = unicodedata.normalize("NFKC", text).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _fingerprint_summary(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokenize(text: str) -> Set[str]:
    if not text:
        return set()
    out: Set[str] = set()
    for tok in _WORD_TOKEN_RE.findall(text):
        if tok not in _STOPWORDS:
            out.add(tok)
    for tok in _CJK_TOKEN_RE.findall(text):
        out.add(tok)
    return out


def _parse_detail(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _importance_label(detail_obj: Dict[str, Any]) -> str:
    importance = detail_obj.get("importance")
    if importance is None:
        return "unknown"
    if not is_parseable_importance(importance):
        return "unknown"
    return label_from_score(parse_importance_score(importance))


def _importance_stored_label(importance_value: Any) -> Optional[str]:
    if not isinstance(importance_value, dict):
        return None
    return normalize_label(importance_value.get("label"))


def _importance_high_risk_underlabel_hits(summary: str) -> List[str]:
    if not summary:
        return []

    hits: List[str] = []
    for code, pattern in _IMPORTANCE_HIGH_RISK_UNDERLABEL_PATTERNS:
        if pattern.search(summary):
            hits.append(code)
    return hits


def _importance_drift_rate_pct(count: int, rows_scanned: int) -> float:
    total = max(1, int(rows_scanned))
    return round((max(0, int(count)) / total) * 100.0, 2)


def importance_drift_profile_names() -> List[str]:
    return list(_IMPORTANCE_DRIFT_THRESHOLD_PROFILES.keys())


def normalize_importance_drift_profile(profile: Optional[str]) -> str:
    raw = str(profile or "").strip().lower()
    if raw in _IMPORTANCE_DRIFT_THRESHOLD_PROFILES:
        return raw
    return _DEFAULT_IMPORTANCE_DRIFT_PROFILE


def importance_drift_thresholds_for_profile(profile: Optional[str]) -> Dict[str, float]:
    profile_name = normalize_importance_drift_profile(profile)
    return dict(_IMPORTANCE_DRIFT_THRESHOLD_PROFILES.get(profile_name) or _IMPORTANCE_DRIFT_THRESHOLD_PROFILES[_DEFAULT_IMPORTANCE_DRIFT_PROFILE])


def build_importance_drift_policy_card(
    *,
    rows_scanned: int,
    score_label_mismatch_count: int,
    missing_or_unparseable_count: int,
    high_risk_underlabel_count: int,
    profile: Optional[str] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    checked_rows = max(1, int(rows_scanned))
    profile_name = normalize_importance_drift_profile(profile)
    active_thresholds = importance_drift_thresholds_for_profile(profile_name)
    if isinstance(thresholds, dict):
        for key, value in thresholds.items():
            if key in active_thresholds:
                try:
                    active_thresholds[key] = float(value)
                except Exception:
                    continue

    metrics = {
        "rows_scanned": checked_rows,
        "score_label_mismatch_count": max(0, int(score_label_mismatch_count)),
        "score_label_mismatch_rate_pct": _importance_drift_rate_pct(score_label_mismatch_count, checked_rows),
        "missing_or_unparseable_count": max(0, int(missing_or_unparseable_count)),
        "missing_or_unparseable_rate_pct": _importance_drift_rate_pct(missing_or_unparseable_count, checked_rows),
        "high_risk_underlabel_count": max(0, int(high_risk_underlabel_count)),
        "high_risk_underlabel_rate_pct": _importance_drift_rate_pct(high_risk_underlabel_count, checked_rows),
    }

    checks = {
        "score_label_mismatch_count_within_threshold": metrics["score_label_mismatch_count"] <= active_thresholds["score_label_mismatch_count_lte"],
        "score_label_mismatch_rate_within_threshold": metrics["score_label_mismatch_rate_pct"] <= active_thresholds["score_label_mismatch_rate_pct_lte"],
        "missing_or_unparseable_count_within_threshold": metrics["missing_or_unparseable_count"] <= active_thresholds["missing_or_unparseable_count_lte"],
        "missing_or_unparseable_rate_within_threshold": metrics["missing_or_unparseable_rate_pct"] <= active_thresholds["missing_or_unparseable_rate_pct_lte"],
        "high_risk_underlabel_count_within_threshold": metrics["high_risk_underlabel_count"] <= active_thresholds["high_risk_underlabel_count_lte"],
        "high_risk_underlabel_rate_within_threshold": metrics["high_risk_underlabel_rate_pct"] <= active_thresholds["high_risk_underlabel_rate_pct_lte"],
    }

    reasons: List[str] = []
    if not checks["score_label_mismatch_count_within_threshold"]:
        reasons.append("score_label_mismatch_count_exceeded")
    if not checks["score_label_mismatch_rate_within_threshold"]:
        reasons.append("score_label_mismatch_rate_exceeded")
    if not checks["missing_or_unparseable_count_within_threshold"]:
        reasons.append("missing_or_unparseable_count_exceeded")
    if not checks["missing_or_unparseable_rate_within_threshold"]:
        reasons.append("missing_or_unparseable_rate_exceeded")
    if not checks["high_risk_underlabel_count_within_threshold"]:
        reasons.append("high_risk_underlabel_count_exceeded")
    if not checks["high_risk_underlabel_rate_within_threshold"]:
        reasons.append("high_risk_underlabel_rate_exceeded")

    acceptable_for_promotion = len(reasons) == 0
    status = "accept" if acceptable_for_promotion else "hold"
    severity = "none" if acceptable_for_promotion else ("high" if metrics["high_risk_underlabel_count"] > 0 else "medium")

    return {
        "kind": "openclaw-mem.optimize.importance-drift-policy-card.v0",
        "mode": "proposal_only_read_only",
        "query_only_enforced": True,
        "writes_performed": 0,
        "memory_mutation": "none",
        "status": status,
        "severity": severity,
        "acceptable_for_promotion_apply": acceptable_for_promotion,
        "threshold_profile": profile_name,
        "profile": {
            "name": profile_name,
        },
        "metrics": metrics,
        "thresholds": active_thresholds,
        "checks": checks,
        "reasons": reasons,
    }


def _preview(text: str, limit: int = 120) -> str:
    t = text.replace("\n", " ").strip()
    if len(t) <= limit:
        return t
    return t[: max(16, limit - 1)].rstrip() + "…"


def _to_nonnegative_int(raw: Any) -> Optional[int]:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if isinstance(raw, float) and raw.is_integer():
        iv = int(raw)
        return iv if iv >= 0 else None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if re.fullmatch(r"\d+", s):
            return int(s)
    return None


def _sum_nonnegative_int_values(raw: Any) -> Optional[int]:
    if not isinstance(raw, dict):
        return None
    total = 0
    seen = 0
    for v in raw.values():
        iv = _to_nonnegative_int(v)
        if iv is None:
            continue
        total += iv
        seen += 1
    if seen == 0:
        return None
    return total


def _extract_recall_result_count(detail_obj: Dict[str, Any]) -> Optional[int]:
    for key in ("result_count", "results_count"):
        iv = _to_nonnegative_int(detail_obj.get(key))
        if iv is not None:
            return iv

    direct_results = detail_obj.get("results")
    if isinstance(direct_results, list):
        return len(direct_results)
    iv = _to_nonnegative_int(direct_results)
    if iv is not None:
        return iv

    details_obj = detail_obj.get("details")
    if isinstance(details_obj, dict):
        nested_results = details_obj.get("results")
        if isinstance(nested_results, list):
            return len(nested_results)
        iv = _to_nonnegative_int(nested_results)
        if iv is not None:
            return iv

    receipt = detail_obj.get("receipt")
    if isinstance(receipt, dict):
        lifecycle = receipt.get("lifecycle")
        if isinstance(lifecycle, dict):
            for key in ("selected_total", "selectedTotal", "result_count", "results_count"):
                iv = _to_nonnegative_int(lifecycle.get(key))
                if iv is not None:
                    return iv

            selected_counts = lifecycle.get("selected_counts")
            iv = _sum_nonnegative_int_values(selected_counts)
            if iv is not None:
                return iv

            selected_counts = lifecycle.get("selectedCounts")
            iv = _sum_nonnegative_int_values(selected_counts)
            if iv is not None:
                return iv

    return None


def _extract_recall_query(detail_obj: Dict[str, Any]) -> Optional[str]:
    candidates: List[Any] = [
        detail_obj.get("query"),
        (detail_obj.get("args") or {}).get("query") if isinstance(detail_obj.get("args"), dict) else None,
        (detail_obj.get("input") or {}).get("query") if isinstance(detail_obj.get("input"), dict) else None,
        (detail_obj.get("request") or {}).get("query") if isinstance(detail_obj.get("request"), dict) else None,
    ]

    for c in candidates:
        q = _normalize_summary(c)
        if len(q) >= 3:
            return q
    return None


def _build_recommendations(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []

    stale = report["signals"]["staleness"]
    if stale["count"] > 0:
        recs.append(
            {
                "type": "mark_stale_candidate",
                "priority": "low",
                "confidence": 0.74,
                "why": f"{stale['count']} rows are older than {stale['threshold_days']} days without recent-use protection",
                "evidence": {
                    "count": stale["count"],
                    "protected_recent_use": stale.get("protected_recent_use", 0),
                    "sample_ids": [it["id"] for it in stale["items"][:5]],
                },
                "suggested_action": "Review candidates for archive/summary tagging (manual approval).",
                "safe_for_auto_apply": False,
            }
        )

    archive = report["signals"].get("soft_archive_candidates", {})
    if archive.get("count", 0) > 0:
        recs.append(
            {
                "type": "stage_soft_archive_candidates",
                "priority": "low",
                "confidence": 0.76,
                "why": (
                    f"{archive['count']} stale low-importance rows are eligible for reversible soft-archive proposals"
                ),
                "evidence": {
                    "count": archive["count"],
                    "protected_recent_use": archive.get("protected_recent_use", 0),
                    "excluded_must_remember": archive.get("excluded_must_remember", 0),
                    "excluded_already_archived": archive.get("excluded_already_archived", 0),
                    "sample_ids": [it["id"] for it in archive.get("items", [])[:5]],
                },
                "suggested_action": "Keep proposal-only by default; review soft-archive candidates with governance before any write lane.",
                "safe_for_auto_apply": False,
            }
        )

    dup = report["signals"]["duplication"]
    if dup["groups"] > 0:
        recs.append(
            {
                "type": "merge_candidates",
                "priority": "medium",
                "confidence": 0.82,
                "why": f"{dup['groups']} duplicate clusters found",
                "evidence": {
                    "groups": dup["groups"],
                    "duplicate_rows": dup["duplicate_rows"],
                    "sample_groups": [it["ids"] for it in dup["items"][:3]],
                },
                "suggested_action": "Pick canonical rows and merge/alias duplicates manually.",
                "safe_for_auto_apply": False,
            }
        )

    bloat = report["signals"]["bloat"]
    if bloat["count"] > 0:
        recs.append(
            {
                "type": "summarize_bloat_candidates",
                "priority": "medium",
                "confidence": 0.71,
                "why": f"{bloat['count']} rows exceed summary/detail size thresholds",
                "evidence": {
                    "count": bloat["count"],
                    "summary_chars_threshold": bloat["summary_chars_threshold"],
                    "detail_bytes_threshold": bloat["detail_bytes_threshold"],
                    "sample_ids": [it["id"] for it in bloat["items"][:5]],
                },
                "suggested_action": "Create concise summaries and keep originals as cold references.",
                "safe_for_auto_apply": False,
            }
        )

    weak = report["signals"]["weakly_connected"]
    if weak["count"] > 0:
        recs.append(
            {
                "type": "strengthen_edge_candidates",
                "priority": "low",
                "confidence": 0.63,
                "why": f"{weak['count']} rows have no lexical neighbors in the current sample",
                "evidence": {
                    "count": weak["count"],
                    "sample_ids": [it["id"] for it in weak["items"][:5]],
                },
                "suggested_action": "Link to nearby decisions/tasks or add scope tags for future recall.",
                "safe_for_auto_apply": False,
            }
        )

    misses = report["signals"].get("repeated_misses", {})
    if misses.get("groups", 0) > 0:
        recs.append(
            {
                "type": "widen_scope_candidate",
                "priority": "medium",
                "confidence": 0.67,
                "why": (
                    f"{misses['groups']} repeated no-result memory_recall query patterns detected"
                ),
                "evidence": {
                    "groups": misses["groups"],
                    "miss_events": misses["miss_events"],
                    "sample_queries": [it["query"] for it in misses["items"][:3]],
                    "sample_ids": [it["latest_id"] for it in misses["items"][:5]],
                },
                "suggested_action": "Review scope/query constraints and capture missing canonical memory for high-repeat misses.",
                "safe_for_auto_apply": False,
            }
        )

    return recs


def _episodic_retention_days(event_type: str) -> Optional[int]:
    return _EPISODIC_RETENTION_DAYS.get(str(event_type or "").strip().lower())


def _parse_json_obj(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _extract_obs_ids_from_refs(raw: Any) -> Set[int]:
    out: Set[int] = set()

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            m = _OBS_REF_RE.fullmatch(value.strip())
            if m:
                out.add(int(m.group(1)))
            return
        if isinstance(value, list):
            for item in value:
                _walk(item)
            return
        if isinstance(value, dict):
            for v in value.values():
                _walk(v)

    _walk(raw)
    return out


def _recent_use_from_lifecycle(
    conn: sqlite3.Connection,
    *,
    lifecycle_limit: int,
) -> Dict[str, Any]:
    rows = conn.execute(
        f"""
        SELECT id, ts, selection_signature, receipt_json
        FROM {_PACK_LIFECYCLE_SHADOW_TABLE}
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, int(lifecycle_limit)),),
    ).fetchall()

    by_obs_id: Dict[int, Dict[str, Any]] = {}
    co_selected_pairs: Dict[tuple[int, int], Dict[str, Any]] = {}
    selection_events = 0

    for row in rows:
        receipt_obj = _parse_json_obj(row["receipt_json"])
        selection_obj = receipt_obj.get("selection") if isinstance(receipt_obj, dict) else {}
        if not isinstance(selection_obj, dict):
            selection_obj = {}

        refs = selection_obj.get("pack_selected_refs")
        if not isinstance(refs, list):
            refs = []

        ts = str(row["ts"] or "").strip() or None
        sig = str(row["selection_signature"] or "").strip() or str(selection_obj.get("selection_signature") or "").strip() or None

        selected_obs_ids: Set[int] = set()
        for ref in refs:
            if not isinstance(ref, str):
                continue
            m = _OBS_REF_RE.fullmatch(ref.strip())
            if not m:
                continue
            obs_id = int(m.group(1))
            selected_obs_ids.add(obs_id)
            slot = by_obs_id.setdefault(
                obs_id,
                {"count": 0, "last_selected_ts": None, "recent_ref": ref},
            )
            slot["count"] += 1
            selection_events += 1
            current_ts = slot.get("last_selected_ts")
            if ts and (not current_ts or str(ts) > str(current_ts)):
                slot["last_selected_ts"] = ts

        ordered = sorted(selected_obs_ids)
        for idx, left_obs_id in enumerate(ordered):
            for right_obs_id in ordered[idx + 1 :]:
                key = (left_obs_id, right_obs_id)
                slot = co_selected_pairs.setdefault(
                    key,
                    {
                        "count": 0,
                        "last_selected_ts": None,
                        "selection_signatures": [],
                    },
                )
                slot["count"] += 1
                current_ts = slot.get("last_selected_ts")
                if ts and (not current_ts or str(ts) > str(current_ts)):
                    slot["last_selected_ts"] = ts
                if sig and sig not in slot["selection_signatures"] and len(slot["selection_signatures"]) < 5:
                    slot["selection_signatures"].append(sig)

    return {
        "lifecycle_rows_scanned": len(rows),
        "selection_events": selection_events,
        "by_obs_id": by_obs_id,
        "co_selected_pairs": co_selected_pairs,
    }


def _recent_use_item(obs_id: int, recent_use_index: Dict[int, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    slot = recent_use_index.get(int(obs_id))
    if not slot:
        return None
    return {
        "id": int(obs_id),
        "count": int(slot.get("count") or 0),
        "last_selected_ts": slot.get("last_selected_ts"),
        "record_ref": slot.get("recent_ref") or f"obs:{int(obs_id)}",
    }


def _receipt_link_evidence(
    left_obs_ids: Set[int],
    right_obs_ids: Set[int],
    *,
    recent_use_index: Dict[int, Dict[str, Any]],
    co_selected_pairs: Dict[tuple[int, int], Dict[str, Any]],
    now_utc: datetime,
) -> Dict[str, Any]:
    shared_selected_obs_ids = sorted(obs_id for obs_id in (left_obs_ids & right_obs_ids) if obs_id in recent_use_index)

    co_selected_pairs_items: List[Dict[str, Any]] = []
    selection_signatures: List[str] = []
    co_selection_events = 0
    co_selection_last_dt: Optional[datetime] = None
    co_selection_last_ts: Optional[str] = None

    for left_obs_id in sorted(left_obs_ids):
        for right_obs_id in sorted(right_obs_ids):
            if left_obs_id == right_obs_id:
                continue
            key = (left_obs_id, right_obs_id) if left_obs_id < right_obs_id else (right_obs_id, left_obs_id)
            slot = co_selected_pairs.get(key)
            if not slot:
                continue
            count = int(slot.get("count") or 0)
            if count <= 0:
                continue
            co_selection_events += count
            slot_last_ts = str(slot.get("last_selected_ts") or "").strip() or None
            slot_last_dt = _parse_iso_utc(slot_last_ts) if slot_last_ts else None
            if slot_last_dt is not None and (co_selection_last_dt is None or slot_last_dt > co_selection_last_dt):
                co_selection_last_dt = slot_last_dt
                co_selection_last_ts = slot_last_ts
            co_selected_pairs_items.append(
                {
                    "left_record_ref": f"obs:{left_obs_id}",
                    "right_record_ref": f"obs:{right_obs_id}",
                    "count": count,
                    "last_selected_ts": slot_last_ts,
                }
            )
            for sig in slot.get("selection_signatures") or []:
                if not isinstance(sig, str) or not sig.strip() or sig in selection_signatures:
                    continue
                selection_signatures.append(sig)
                if len(selection_signatures) >= 5:
                    break

    co_selected_pairs_items.sort(
        key=lambda x: (x["count"], x["left_record_ref"], x["right_record_ref"]),
        reverse=True,
    )

    shared_selected_refs = [f"obs:{obs_id}" for obs_id in shared_selected_obs_ids]
    co_selection_recency_days = None
    co_selection_recency_score = 0.0
    if co_selection_last_dt is not None:
        now_anchor = now_utc.astimezone(timezone.utc)
        age_days = max(0.0, (now_anchor - co_selection_last_dt).total_seconds() / 86400.0)
        co_selection_recency_days = round(age_days, 3)
        co_selection_recency_score = round(
            _clip_unit(math.pow(2.0, -age_days / _CO_SELECTION_RECENCY_HALF_LIFE_DAYS)),
            3,
        )

    return {
        "shared_selected_refs": shared_selected_refs,
        "shared_selected_count": len(shared_selected_refs),
        "co_selection_events": co_selection_events,
        "co_selection_last_ts": co_selection_last_ts,
        "co_selection_recency_days": co_selection_recency_days,
        "co_selection_recency_score": co_selection_recency_score,
        "co_selected_pair_count": len(co_selected_pairs_items),
        "co_selected_pairs": co_selected_pairs_items[:5],
        "selection_signatures": selection_signatures[:5],
    }


def _clip_unit(raw: Any) -> float:
    try:
        value = float(raw)
    except Exception:
        return 0.0
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value


def _link_confidence_from_evidence(
    *,
    evidence_mode: str,
    receipt_evidence: Dict[str, Any],
    lexical_score: float,
    shared_token_count: int,
) -> Dict[str, Any]:
    mode = str(evidence_mode or "").strip() or "lexical_fallback"
    model = _LINK_CONFIDENCE_MODEL_V0.get(mode) or _LINK_CONFIDENCE_MODEL_V0["lexical_fallback"]
    weights = model.get("weights") or {}

    co_selection_events = max(0, int((receipt_evidence or {}).get("co_selection_events") or 0))
    shared_selected_count = max(0, int((receipt_evidence or {}).get("shared_selected_count") or 0))
    co_selection_recency_norm = _clip_unit((receipt_evidence or {}).get("co_selection_recency_score"))
    lexical_norm = _clip_unit(lexical_score)
    token_norm = _clip_unit(max(0, int(shared_token_count)) / 4.0)
    co_selection_events_norm = _clip_unit(co_selection_events / 3.0)
    shared_selected_norm = _clip_unit(shared_selected_count / 2.0)

    contributions = {
        "co_selection_events": round(float(weights.get("co_selection_events", 0.0)) * co_selection_events_norm, 3),
        "shared_selected_count": round(float(weights.get("shared_selected_count", 0.0)) * shared_selected_norm, 3),
        "co_selection_recency": round(float(weights.get("co_selection_recency", 0.0)) * co_selection_recency_norm, 3),
        "lexical_score": round(float(weights.get("lexical_score", 0.0)) * lexical_norm, 3),
        "shared_token_count": round(float(weights.get("shared_token_count", 0.0)) * token_norm, 3),
    }
    base = round(float(model.get("base", 0.0)), 3)
    cap = round(float(model.get("cap", 1.0)), 3)
    raw_confidence = round(base + sum(contributions.values()), 3)
    confidence = round(min(cap, raw_confidence), 3)

    return {
        "confidence": confidence,
        "confidence_components": {
            "model": "evidence_weighted_v0",
            "mode": mode,
            "base": base,
            "inputs": {
                "co_selection_events": co_selection_events,
                "shared_selected_count": shared_selected_count,
                "co_selection_last_ts": (receipt_evidence or {}).get("co_selection_last_ts"),
                "co_selection_recency_days": (receipt_evidence or {}).get("co_selection_recency_days"),
                "co_selection_recency_score": round(co_selection_recency_norm, 3),
                "lexical_score": round(lexical_norm, 3),
                "shared_token_count": max(0, int(shared_token_count)),
            },
            "weights": {
                "co_selection_events": round(float(weights.get("co_selection_events", 0.0)), 3),
                "shared_selected_count": round(float(weights.get("shared_selected_count", 0.0)), 3),
                "co_selection_recency": round(float(weights.get("co_selection_recency", 0.0)), 3),
                "lexical_score": round(float(weights.get("lexical_score", 0.0)), 3),
                "shared_token_count": round(float(weights.get("shared_token_count", 0.0)), 3),
            },
            "contributions": contributions,
            "raw": raw_confidence,
            "cap": cap,
        },
    }


def _event_ref(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": item["id"],
        "event_id": item["event_id"],
        "type": item["type"],
        "scope": item["scope"],
        "session_id": item["session_id"],
        "ts_ms": item["ts_ms"],
        "summary_preview": item["summary_preview"],
    }


def _cluster_draft_summary(cluster_items: List[Dict[str, Any]], shared_tokens: List[str]) -> str:
    if not cluster_items:
        return ""
    scope = cluster_items[0].get("scope") or "global"
    session_id = cluster_items[0].get("session_id") or "session"
    type_counts: Dict[str, int] = {}
    for item in cluster_items:
        type_counts[str(item.get("type") or "unknown")] = type_counts.get(str(item.get("type") or "unknown"), 0) + 1
    type_bits = [f"{k}:{v}" for k, v in sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    token_bits = shared_tokens[:3]
    token_part = ", ".join(token_bits) if token_bits else "related context"
    type_part = " | ".join(type_bits) if type_bits else "mixed events"
    return (
        f"{len(cluster_items)} episodic events in {scope}/{session_id} repeatedly touch {token_part}; "
        f"candidate consolidation over {type_part}."
    )


def _build_consolidation_recommendations(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    candidates = report.get("candidates", {})

    summary = candidates.get("summary", {})
    if summary.get("groups", 0) > 0:
        recs.append(
            {
                "type": "review_summary_candidates",
                "priority": "medium",
                "confidence": 0.79,
                "why": f"{summary['groups']} episodic clusters look compressible into summary candidates",
                "evidence": {
                    "groups": summary["groups"],
                    "sample_event_ids": [
                        (it.get("event_ids") or [])[:3] for it in summary.get("items", [])[:3]
                    ],
                },
                "suggested_action": "Review draft summaries and decide whether to keep as proposals, archive sources, or discard.",
                "safe_for_auto_apply": False,
            }
        )

    archive = candidates.get("archive", {})
    if archive.get("count", 0) > 0:
        recs.append(
            {
                "type": "stage_archive_candidates",
                "priority": "low",
                "confidence": 0.72,
                "why": f"{archive['count']} episodic rows are nearing retention horizon with low-signal traits",
                "evidence": {
                    "count": archive["count"],
                    "sample_ids": [it.get("id") for it in archive.get("items", [])[:5]],
                },
                "suggested_action": "Stage low-signal episodes for archive or deletion review before GC windows close.",
                "safe_for_auto_apply": False,
            }
        )

    links = candidates.get("links", {})
    if links.get("pairs", 0) > 0:
        recs.append(
            {
                "type": "review_link_candidates",
                "priority": "low",
                "confidence": 0.68,
                "why": f"{links['pairs']} cross-session link candidates were found (receipt-derived when lifecycle evidence exists)",
                "evidence": {
                    "pairs": links["pairs"],
                    "sample_shared_tokens": [it.get("shared_tokens", [])[:3] for it in links.get("items", [])[:3]],
                    "sample_evidence_mode": [it.get("evidence_mode") for it in links.get("items", [])[:3]],
                },
                "suggested_action": "Review whether repeated cross-session motifs deserve explicit graph or note linkage.",
                "safe_for_auto_apply": False,
            }
        )

    return recs


def build_consolidation_review(
    conn: sqlite3.Connection,
    *,
    limit: int = 500,
    scope: Optional[str] = None,
    session_id: Optional[str] = None,
    summary_min_group_size: int = 2,
    summary_min_shared_tokens: int = 2,
    archive_lookahead_days: int = 7,
    archive_min_signal_reasons: int = 2,
    link_min_shared_tokens: int = 2,
    link_lexical_backfill_max: int = 1,
    lifecycle_limit: int = 200,
    top: int = 10,
) -> Dict[str, Any]:
    row_limit = max(1, int(limit))
    summary_min_group_size = max(2, int(summary_min_group_size))
    summary_min_shared_tokens = max(1, int(summary_min_shared_tokens))
    archive_lookahead_days = max(1, int(archive_lookahead_days))
    archive_min_signal_reasons = max(1, int(archive_min_signal_reasons))
    link_min_shared_tokens = max(1, int(link_min_shared_tokens))
    link_lexical_backfill_max = max(0, int(link_lexical_backfill_max))
    lifecycle_limit = max(1, int(lifecycle_limit))
    top = max(1, int(top))
    scope_norm = _normalize_scope_token(scope)
    session_norm = str(session_id or "").strip() or None

    prev_query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
    if not prev_query_only:
        conn.execute("PRAGMA query_only = ON")

    try:
        where_parts: List[str] = []
        params_total: List[Any] = []
        params_rows: List[Any] = []
        if scope_norm:
            where_parts.append("scope = ?")
            params_total.append(scope_norm)
            params_rows.append(scope_norm)
        if session_norm:
            where_parts.append("session_id = ?")
            params_total.append(session_norm)
            params_rows.append(session_norm)
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        total_rows = int(conn.execute(f"SELECT COUNT(*) FROM episodic_events{where_sql}", params_total).fetchone()[0])
        rows = conn.execute(
            f"""
            SELECT id, event_id, ts_ms, scope, session_id, agent_id, type, summary, payload_json, refs_json, redacted
            FROM episodic_events{where_sql}
            ORDER BY id DESC
            LIMIT ?
            """,
            params_rows + [row_limit],
        ).fetchall()
        recent_use_meta = _recent_use_from_lifecycle(conn, lifecycle_limit=lifecycle_limit)
    finally:
        if not prev_query_only:
            conn.execute("PRAGMA query_only = OFF")

    now = datetime.now(timezone.utc)
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        summary_raw = str(row["summary"] or "")
        summary_norm = _normalize_summary(summary_raw)
        dt = datetime.fromtimestamp(int(row["ts_ms"]) / 1000.0, tz=timezone.utc)
        age_days = max(0, int((now - dt).total_seconds() // 86400))
        refs_obj = _parse_json_obj(row["refs_json"])
        refs_obs_ids = _extract_obs_ids_from_refs(refs_obj)
        payload_present = bool(str(row["payload_json"] or "").strip())
        retention_days = _episodic_retention_days(str(row["type"] or ""))
        days_until_gc = None if retention_days is None else max(0, int(retention_days - age_days))
        prepared.append(
            {
                "id": int(row["id"]),
                "event_id": str(row["event_id"]),
                "ts_ms": int(row["ts_ms"]),
                "scope": str(row["scope"]),
                "session_id": str(row["session_id"]),
                "agent_id": str(row["agent_id"]),
                "type": str(row["type"]),
                "summary": summary_norm,
                "summary_preview": _preview(summary_raw),
                "tokens": _tokenize(summary_norm),
                "token_count": 0,
                "summary_chars": len(summary_raw),
                "refs": refs_obj,
                "refs_obs_ids": refs_obs_ids,
                "has_refs": bool(refs_obj),
                "payload_present": payload_present,
                "redacted": bool(int(row["redacted"] or 0)),
                "retention_days": retention_days,
                "age_days": age_days,
                "days_until_gc": days_until_gc,
            }
        )
    for item in prepared:
        item["token_count"] = len(item["tokens"])

    global_token_to_ids: Dict[str, Set[int]] = {}
    for item in prepared:
        for tok in item["tokens"]:
            global_token_to_ids.setdefault(tok, set()).add(item["id"])
    max_common_freq = max(3, int(len(prepared) * 0.80))

    summary_items: List[Dict[str, Any]] = []
    groups: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for item in prepared:
        groups.setdefault((item["scope"], item["session_id"]), []).append(item)

    for (scope_key, session_key), group in groups.items():
        if len(group) < summary_min_group_size:
            continue
        group_sorted = sorted(group, key=lambda x: x["id"])
        adjacency: Dict[int, Set[int]] = {it["id"]: set() for it in group_sorted}
        by_id = {it["id"]: it for it in group_sorted}
        for idx, left in enumerate(group_sorted):
            for right in group_sorted[idx + 1 :]:
                shared = sorted(tok for tok in (left["tokens"] & right["tokens"]) if len(global_token_to_ids.get(tok, ())) <= max_common_freq)
                if len(shared) < summary_min_shared_tokens:
                    continue
                adjacency[left["id"]].add(right["id"])
                adjacency[right["id"]].add(left["id"])

        seen: Set[int] = set()
        for start in [it["id"] for it in group_sorted]:
            if start in seen or not adjacency[start]:
                continue
            stack = [start]
            component: List[int] = []
            seen.add(start)
            while stack:
                cur = stack.pop()
                component.append(cur)
                for nxt in adjacency[cur]:
                    if nxt in seen:
                        continue
                    seen.add(nxt)
                    stack.append(nxt)
            if len(component) < summary_min_group_size:
                continue
            cluster = [by_id[i] for i in sorted(component)]
            token_counts: Dict[str, int] = {}
            for item in cluster:
                for tok in item["tokens"]:
                    if len(global_token_to_ids.get(tok, ())) <= max_common_freq:
                        token_counts[tok] = token_counts.get(tok, 0) + 1
            shared_tokens = [tok for tok, count in sorted(token_counts.items(), key=lambda kv: (-kv[1], kv[0])) if count >= 2]
            if len(shared_tokens) < summary_min_shared_tokens:
                continue
            type_counts: Dict[str, int] = {}
            for item in cluster:
                type_counts[item["type"]] = type_counts.get(item["type"], 0) + 1
            summary_items.append(
                {
                    "scope": scope_key,
                    "session_id": session_key,
                    "count": len(cluster),
                    "ids": [it["id"] for it in cluster],
                    "event_ids": [it["event_id"] for it in cluster],
                    "shared_tokens": shared_tokens[:5],
                    "type_counts": type_counts,
                    "time_range": {
                        "start_ts_ms": min(it["ts_ms"] for it in cluster),
                        "end_ts_ms": max(it["ts_ms"] for it in cluster),
                    },
                    "draft_summary": _cluster_draft_summary(cluster, shared_tokens),
                    "source_event_refs": [_event_ref(it) for it in cluster[: min(len(cluster), 8)]],
                }
            )
    summary_items.sort(key=lambda x: (x["count"], len(x["shared_tokens"]), x["ids"][-1]), reverse=True)

    recent_use_index = recent_use_meta.get("by_obs_id", {}) if isinstance(recent_use_meta, dict) else {}
    archive_items: List[Dict[str, Any]] = []
    archive_protected_recent_use = 0
    recent_use_refs_seen: Set[int] = set()
    for item in prepared:
        retention_days = item["retention_days"]
        if retention_days is None or item["days_until_gc"] is None:
            continue
        if item["days_until_gc"] > archive_lookahead_days:
            continue
        reasons: List[str] = []
        if not item["has_refs"]:
            reasons.append("no_refs")
        if item["token_count"] <= 4:
            reasons.append("low_token_count")
        if item["summary_chars"] <= 80:
            reasons.append("short_summary")
        if not item["payload_present"]:
            reasons.append("no_payload")
        if item["redacted"]:
            reasons.append("redacted")
        if len(reasons) < archive_min_signal_reasons:
            continue
        recent_use_evidence = [
            _recent_use_item(obs_id, recent_use_index)
            for obs_id in sorted(item.get("refs_obs_ids") or set())
            if _recent_use_item(obs_id, recent_use_index) is not None
        ]
        if recent_use_evidence:
            archive_protected_recent_use += 1
            for ev in recent_use_evidence:
                recent_use_refs_seen.add(int(ev["id"]))
            continue
        archive_items.append(
            {
                "id": item["id"],
                "event_id": item["event_id"],
                "scope": item["scope"],
                "session_id": item["session_id"],
                "type": item["type"],
                "age_days": item["age_days"],
                "retention_days": retention_days,
                "days_until_gc": item["days_until_gc"],
                "low_signal_reasons": reasons,
                "summary_preview": item["summary_preview"],
                "source_event_ref": _event_ref(item),
            }
        )
    archive_items.sort(key=lambda x: (x["days_until_gc"], -x["age_days"], x["id"]))

    lifecycle_rows_scanned = int(recent_use_meta.get("lifecycle_rows_scanned") or 0)
    co_selected_pairs = recent_use_meta.get("co_selected_pairs", {}) if isinstance(recent_use_meta, dict) else {}

    link_items: List[Dict[str, Any]] = []
    lexical_backfill_candidates: List[Dict[str, Any]] = []
    scope_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in prepared:
        scope_groups.setdefault(item["scope"], []).append(item)
    seen_pairs: Set[tuple[int, int]] = set()
    for scope_key, group in scope_groups.items():
        ordered = sorted(group, key=lambda x: x["id"])
        for idx, left in enumerate(ordered):
            for right in ordered[idx + 1 :]:
                if left["session_id"] == right["session_id"]:
                    continue
                pair_key = (left["id"], right["id"])
                if pair_key in seen_pairs:
                    continue

                shared = sorted(tok for tok in (left["tokens"] & right["tokens"]) if len(global_token_to_ids.get(tok, ())) <= max_common_freq)
                union_size = max(1, len(left["tokens"] | right["tokens"]))
                lexical_score = round(len(shared) / union_size, 3)

                evidence = _receipt_link_evidence(
                    set(left.get("refs_obs_ids") or set()),
                    set(right.get("refs_obs_ids") or set()),
                    recent_use_index=recent_use_index,
                    co_selected_pairs=co_selected_pairs,
                    now_utc=now,
                )
                has_receipt_evidence = bool(
                    evidence.get("shared_selected_count")
                    or evidence.get("co_selection_events")
                )

                link_candidate = {
                    "scope": scope_key,
                    "shared_tokens": shared[:5],
                    "shared_token_count": len(shared),
                    "score": lexical_score,
                    "receipt_evidence": evidence,
                    "left": _event_ref(left),
                    "right": _event_ref(right),
                }

                if lifecycle_rows_scanned > 0:
                    if has_receipt_evidence:
                        link_items.append(
                            {
                                **link_candidate,
                                "evidence_mode": "receipt_co_selection",
                                **_link_confidence_from_evidence(
                                    evidence_mode="receipt_co_selection",
                                    receipt_evidence=evidence,
                                    lexical_score=lexical_score,
                                    shared_token_count=len(shared),
                                ),
                            }
                        )
                    elif len(shared) >= link_min_shared_tokens:
                        lexical_backfill_candidates.append(
                            {
                                **link_candidate,
                                "evidence_mode": "lexical_backfill_low_confidence",
                                **_link_confidence_from_evidence(
                                    evidence_mode="lexical_backfill_low_confidence",
                                    receipt_evidence=evidence,
                                    lexical_score=lexical_score,
                                    shared_token_count=len(shared),
                                ),
                            }
                        )
                    else:
                        continue
                else:
                    if len(shared) < link_min_shared_tokens:
                        continue
                    link_items.append(
                        {
                            **link_candidate,
                            "evidence_mode": "lexical_fallback",
                            **_link_confidence_from_evidence(
                                evidence_mode="lexical_fallback",
                                receipt_evidence=evidence,
                                lexical_score=lexical_score,
                                shared_token_count=len(shared),
                            ),
                        }
                    )
                seen_pairs.add(pair_key)

    lexical_backfill_candidate_pairs = len(lexical_backfill_candidates)
    lexical_backfill_pairs = 0
    lexical_backfill_suppressed_pairs = 0
    if lifecycle_rows_scanned > 0 and link_lexical_backfill_max > 0 and lexical_backfill_candidates:
        lexical_backfill_candidates.sort(
            key=lambda x: (
                x.get("confidence", 0),
                x.get("shared_token_count", 0),
                x.get("score", 0),
                (x.get("right") or {}).get("id", 0),
            ),
            reverse=True,
        )
        selected_backfill = lexical_backfill_candidates[:link_lexical_backfill_max]
        lexical_backfill_pairs = len(selected_backfill)
        lexical_backfill_suppressed_pairs = max(0, lexical_backfill_candidate_pairs - lexical_backfill_pairs)
        link_items.extend(selected_backfill)

    link_items.sort(
        key=lambda x: (
            x.get("confidence", 0),
            int(((x.get("receipt_evidence") or {}).get("co_selection_events") or 0)),
            int(((x.get("receipt_evidence") or {}).get("shared_selected_count") or 0)),
            x.get("shared_token_count", 0),
            x.get("score", 0),
            (x.get("right") or {}).get("id", 0),
        ),
        reverse=True,
    )
    receipt_link_pairs = sum(1 for item in link_items if item.get("evidence_mode") == "receipt_co_selection")
    lexical_fallback_link_pairs = sum(1 for item in link_items if item.get("evidence_mode") == "lexical_fallback")

    rows_scanned = len(prepared)
    coverage_pct = round((rows_scanned / total_rows) * 100, 1) if total_rows > 0 else 100.0
    warnings: List[Dict[str, Any]] = []
    if total_rows > rows_scanned:
        warnings.append(
            {
                "code": "sample_is_recent_window",
                "message": "Review scans the most recent episodic rows only; older consolidation/archive candidates may exist outside the current sample window.",
                "sample_order": "id_desc_recent_window",
            }
        )

    report: Dict[str, Any] = {
        "kind": "openclaw-mem.optimize.consolidation-review.v0",
        "ts": now.isoformat(),
        "version": {"openclaw_mem": __version__, "schema": "v0"},
        "source": {
            "table": "episodic_events",
            "row_limit": row_limit,
            "rows_scanned": rows_scanned,
            "total_rows": total_rows,
            "scope": scope_norm,
            "session_id": session_norm,
            "coverage_pct": coverage_pct,
            "sample_order": "id_desc_recent_window",
        },
        "policy": {
            "mode": "recommendation-first",
            "writes_performed": 0,
            "memory_mutation": "none",
            "query_only_enforced": True,
            "canonical_rewrite": "forbidden",
        },
        "thresholds": {
            "summary_min_group_size": summary_min_group_size,
            "summary_min_shared_tokens": summary_min_shared_tokens,
            "archive_lookahead_days": archive_lookahead_days,
            "archive_min_signal_reasons": archive_min_signal_reasons,
            "link_min_shared_tokens": link_min_shared_tokens,
            "link_lexical_backfill_max": link_lexical_backfill_max,
            "lifecycle_limit": lifecycle_limit,
            "rare_token_max_freq": max_common_freq,
        },
        "signals": {
            "recent_use": {
                "lifecycle_rows_scanned": int(recent_use_meta.get("lifecycle_rows_scanned") or 0),
                "selection_events": int(recent_use_meta.get("selection_events") or 0),
                "protected_archive_candidates": archive_protected_recent_use,
                "linked_observation_rows": len(recent_use_refs_seen),
                "items": [
                    _recent_use_item(obs_id, recent_use_index)
                    for obs_id in sorted(recent_use_refs_seen, key=lambda x: (recent_use_index.get(x, {}).get("count", 0), x), reverse=True)[:top]
                    if _recent_use_item(obs_id, recent_use_index) is not None
                ],
            },
            "link_evidence": {
                "lifecycle_rows_scanned": lifecycle_rows_scanned,
                "mode": "receipt_first_with_bounded_lexical_backfill_when_lifecycle_exists",
                "receipt_supported_pairs": receipt_link_pairs,
                "lexical_fallback_pairs": lexical_fallback_link_pairs,
                "lexical_backfill_pairs": lexical_backfill_pairs,
                "lexical_backfill_candidate_pairs": lexical_backfill_candidate_pairs,
                "lexical_backfill_suppressed_pairs": lexical_backfill_suppressed_pairs,
                "hybrid_gate": {
                    "active": bool(lifecycle_rows_scanned > 0),
                    "lexical_backfill_max": link_lexical_backfill_max,
                },
                "confidence_model": {
                    "name": "evidence_weighted_v0",
                    "modes": {
                        mode: {
                            "base": round(float(cfg.get("base", 0.0)), 3),
                            "cap": round(float(cfg.get("cap", 1.0)), 3),
                            "weights": {
                                key: round(float(value), 3)
                                for key, value in (cfg.get("weights") or {}).items()
                            },
                        }
                        for mode, cfg in _LINK_CONFIDENCE_MODEL_V0.items()
                    },
                    "normalization": {
                        "co_selection_events_saturation": 3,
                        "shared_selected_count_saturation": 2,
                        "shared_token_count_saturation": 4,
                        "co_selection_recency_half_life_days": _CO_SELECTION_RECENCY_HALF_LIFE_DAYS,
                    },
                },
            },
        },
        "candidates": {
            "summary": {"groups": len(summary_items), "items": summary_items[:top]},
            "archive": {"count": len(archive_items), "protected_by_recent_use": archive_protected_recent_use, "items": archive_items[:top]},
            "links": {"pairs": len(link_items), "items": link_items[:top]},
        },
        "warnings": warnings,
    }
    report["recommendations"] = _build_consolidation_recommendations(report)
    return report


def render_consolidation_review(report: Dict[str, Any]) -> str:
    src = report.get("source", {})
    candidates = report.get("candidates", {})
    summary = candidates.get("summary", {})
    archive = candidates.get("archive", {})
    links = candidates.get("links", {})
    recent_use = (report.get("signals") or {}).get("recent_use", {})

    lines = [
        "openclaw-mem optimize consolidation-review (recommendation-only)",
        (
            "rows scanned: "
            f"{src.get('rows_scanned', 0)}/{src.get('row_limit', 0)} "
            f"(total_rows={src.get('total_rows', 0)}, coverage={src.get('coverage_pct', 0)}%, sample_order={src.get('sample_order', 'unknown')})"
        ),
        (
            "candidates: "
            f"summary={summary.get('groups', 0)} groups | "
            f"archive={archive.get('count', 0)} (protected_by_recent_use={archive.get('protected_by_recent_use', 0)}) | "
            f"links={links.get('pairs', 0)} pairs | "
            f"recent_use_links={recent_use.get('linked_observation_rows', 0)}"
        ),
    ]

    warnings = report.get("warnings", [])
    if warnings:
        lines.append("warnings:")
        for w in warnings:
            lines.append(f"- {w.get('code')}: {w.get('message')}")

    recs = report.get("recommendations", [])
    if recs:
        lines.append("recommendations:")
        for rec in recs:
            lines.append(f"- {rec.get('type')} (confidence={rec.get('confidence')}, priority={rec.get('priority')}): {rec.get('why')}")
    else:
        lines.append("recommendations: none")

    return "\n".join(lines)


def build_memory_health_review(
    conn: sqlite3.Connection,
    *,
    limit: int = 1000,
    stale_days: int = 60,
    duplicate_min_count: int = 2,
    bloat_summary_chars: int = 240,
    bloat_detail_bytes: int = 4096,
    orphan_min_tokens: int = 2,
    miss_min_count: int = 2,
    lifecycle_limit: int = 200,
    top: int = 10,
    scope: Optional[str] = None,
    importance_drift_profile: Optional[str] = None,
) -> Dict[str, Any]:
    row_limit = max(1, int(limit))
    stale_days = max(1, int(stale_days))
    duplicate_min_count = max(2, int(duplicate_min_count))
    bloat_summary_chars = max(80, int(bloat_summary_chars))
    bloat_detail_bytes = max(256, int(bloat_detail_bytes))
    orphan_min_tokens = max(1, int(orphan_min_tokens))
    miss_min_count = max(2, int(miss_min_count))
    lifecycle_limit = max(1, int(lifecycle_limit))
    top = max(1, int(top))
    scope_norm = _normalize_scope_token(scope)

    prev_query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
    if not prev_query_only:
        conn.execute("PRAGMA query_only = ON")

    try:
        scope_clause = ""
        params_total: List[Any] = []
        params_rows: List[Any] = [row_limit]
        if scope_norm:
            conn.create_function("ocm_scope_norm", 1, _normalize_scope_token)
            scope_clause = (
                " WHERE ocm_scope_norm(json_extract("
                "CASE WHEN json_valid(detail_json) THEN detail_json ELSE '{}' END, '$.scope')) = ?"
            )
            params_total.append(scope_norm)
            params_rows = [scope_norm, row_limit]

        total_rows = int(
            conn.execute(
                f"SELECT COUNT(*) FROM observations{scope_clause}",
                params_total,
            ).fetchone()[0]
        )
        rows = conn.execute(
            f"""
            SELECT id, ts, kind, tool_name, summary, summary_en, detail_json
            FROM observations{scope_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            params_rows,
        ).fetchall()
        recent_use_meta = _recent_use_from_lifecycle(conn, lifecycle_limit=lifecycle_limit)
    finally:
        if not prev_query_only:
            conn.execute("PRAGMA query_only = OFF")

    now = datetime.now(timezone.utc)
    recent_use_index = recent_use_meta.get("by_obs_id", {}) if isinstance(recent_use_meta, dict) else {}
    prepared: List[Dict[str, Any]] = []

    for r in rows:
        summary = _normalize_summary(r["summary_en"] or r["summary"] or "")
        detail_raw = r["detail_json"] or ""
        detail_obj = _parse_detail(detail_raw)
        importance_raw = detail_obj.get("importance")
        importance_parseable = bool(is_parseable_importance(importance_raw)) if importance_raw is not None else False
        importance_score = round(parse_importance_score(importance_raw), 4) if importance_parseable else None
        importance_label = label_from_score(float(importance_score)) if importance_parseable and importance_score is not None else "unknown"
        importance_stored_label = _importance_stored_label(importance_raw)
        if importance_raw is None:
            importance_state = "missing"
        elif not importance_parseable:
            importance_state = "unparseable"
        else:
            importance_state = "parseable"

        tool_name = str(r["tool_name"] or "")
        tool_name_norm = tool_name.strip().lower()
        recall_query = _extract_recall_query(detail_obj) if tool_name_norm == "memory_recall" else None
        recall_result_count = _extract_recall_result_count(detail_obj) if tool_name_norm == "memory_recall" else None
        lifecycle_obj = detail_obj.get("lifecycle") if isinstance(detail_obj.get("lifecycle"), dict) else {}
        lifecycle_archived_at = lifecycle_obj.get("archived_at") if isinstance(lifecycle_obj, dict) else None
        if not isinstance(lifecycle_archived_at, str) or not lifecycle_archived_at.strip():
            lifecycle_archived_at = None
        dt = _parse_iso_utc(r["ts"])
        age_days = None
        if dt is not None:
            age_days = max(0, int((now - dt).total_seconds() // 86400))

        recent_use_slot = recent_use_index.get(int(r["id"]), {})
        item = {
            "id": int(r["id"]),
            "ts": r["ts"],
            "kind": r["kind"],
            "tool_name": r["tool_name"],
            "tool_name_norm": tool_name_norm,
            "summary": summary,
            "summary_preview": _preview(summary),
            "fingerprint": _fingerprint_summary(summary),
            "tokens": _tokenize(summary),
            "token_count": 0,
            "age_days": age_days,
            "detail_bytes": len(detail_raw.encode("utf-8")) if isinstance(detail_raw, str) else 0,
            "summary_chars": len(summary),
            "scope": _normalize_scope_token(detail_obj.get("scope")),
            "importance": importance_label,
            "importance_state": importance_state,
            "importance_score": importance_score,
            "importance_stored_label": importance_stored_label,
            "lifecycle_archived_at": lifecycle_archived_at,
            "recall_query": recall_query,
            "recall_result_count": recall_result_count,
            "recent_use_count": int(recent_use_slot.get("count") or 0),
            "recent_use_last_ts": recent_use_slot.get("last_selected_ts"),
        }
        item["token_count"] = len(item["tokens"])
        prepared.append(item)

    # Staleness
    stale_items: List[Dict[str, Any]] = []
    recent_use_items: List[Dict[str, Any]] = []
    protected_from_stale = 0
    excluded_must_remember = 0
    for it in prepared:
        if it.get("recent_use_count", 0) > 0:
            recent_use_items.append(
                {
                    "id": it["id"],
                    "recent_use_count": it["recent_use_count"],
                    "last_selected_ts": it.get("recent_use_last_ts"),
                    "age_days": it["age_days"],
                    "summary_preview": it["summary_preview"],
                }
            )
        if it["age_days"] is None:
            continue
        if it["age_days"] < stale_days:
            continue
        if it["importance"] == "must_remember":
            excluded_must_remember += 1
            continue
        if it.get("recent_use_count", 0) > 0:
            protected_from_stale += 1
            continue
        stale_items.append(
            {
                "id": it["id"],
                "age_days": it["age_days"],
                "importance": it["importance"],
                "kind": it["kind"],
                "tool_name": it["tool_name"],
                "summary_preview": it["summary_preview"],
            }
        )
    stale_items.sort(key=lambda x: (x["age_days"], x["id"]), reverse=True)
    recent_use_items.sort(key=lambda x: (x["recent_use_count"], x["id"]), reverse=True)

    # Archive-first lifecycle proposals (read-only): stale + low-importance + no recent-use + not already archived
    soft_archive_items: List[Dict[str, Any]] = []
    soft_archive_protected_recent_use = 0
    soft_archive_excluded_must_remember = 0
    soft_archive_excluded_already_archived = 0
    for it in prepared:
        if it["age_days"] is None or it["age_days"] < stale_days:
            continue
        if it["importance"] == "must_remember":
            soft_archive_excluded_must_remember += 1
            continue
        if it.get("lifecycle_archived_at"):
            soft_archive_excluded_already_archived += 1
            continue
        if it["importance"] not in _SOFT_ARCHIVE_LOW_IMPORTANCE_LABELS:
            continue
        if it.get("recent_use_count", 0) > 0:
            soft_archive_protected_recent_use += 1
            continue
        soft_archive_items.append(
            {
                "candidate_id": f"soft-archive-candidate-{it['id']}",
                "id": it["id"],
                "age_days": it["age_days"],
                "importance": it["importance"],
                "kind": it["kind"],
                "tool_name": it["tool_name"],
                "summary_preview": it["summary_preview"],
                "reason_codes": [
                    "stale_age_threshold",
                    "low_importance",
                    "no_recent_use",
                    "archive_first",
                ],
            }
        )
    soft_archive_items.sort(key=lambda x: (x["age_days"], x["id"]), reverse=True)

    # Duplication (fingerprint cluster, scope-isolated)
    fp_map: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for it in prepared:
        fp = it["fingerprint"]
        if not fp or len(fp) < 8:
            continue
        scope_key = it["scope"] or "__global__"
        fp_map.setdefault((scope_key, fp), []).append(it)

    dup_items: List[Dict[str, Any]] = []
    duplicate_rows = 0
    for (scope_key, fp), group in fp_map.items():
        if len(group) < duplicate_min_count:
            continue
        ordered = sorted(group, key=lambda x: x["id"])
        duplicate_rows += len(ordered) - 1
        dup_items.append(
            {
                "scope": None if scope_key == "__global__" else scope_key,
                "fingerprint": fp,
                "count": len(ordered),
                "ids": [g["id"] for g in ordered],
                "canonical_id": ordered[0]["id"],
                "latest_id": ordered[-1]["id"],
                "sample_summary": ordered[0]["summary_preview"],
            }
        )
    dup_items.sort(key=lambda x: (x["count"], x["latest_id"], x.get("scope") or ""), reverse=True)

    # Bloat
    bloat_items: List[Dict[str, Any]] = []
    for it in prepared:
        if it["summary_chars"] < bloat_summary_chars and it["detail_bytes"] < bloat_detail_bytes:
            continue
        bloat_items.append(
            {
                "id": it["id"],
                "summary_chars": it["summary_chars"],
                "detail_bytes": it["detail_bytes"],
                "kind": it["kind"],
                "tool_name": it["tool_name"],
                "summary_preview": it["summary_preview"],
            }
        )
    bloat_items.sort(key=lambda x: (x["detail_bytes"], x["summary_chars"], x["id"]), reverse=True)

    # Weakly connected candidates (token graph degree=0)
    token_to_ids: Dict[str, Set[int]] = {}
    for it in prepared:
        for tok in it["tokens"]:
            token_to_ids.setdefault(tok, set()).add(it["id"])

    max_common_freq = max(2, int(len(prepared) * 0.20))
    weak_items: List[Dict[str, Any]] = []
    for it in prepared:
        if it["token_count"] < orphan_min_tokens:
            continue

        useful_tokens = [tok for tok in it["tokens"] if len(token_to_ids.get(tok, ())) <= max_common_freq]
        if len(useful_tokens) < orphan_min_tokens:
            continue

        neighbors: Set[int] = set()
        for tok in useful_tokens:
            neighbors |= token_to_ids.get(tok, set())
        neighbors.discard(it["id"])

        if neighbors:
            continue

        weak_items.append(
            {
                "id": it["id"],
                "token_count": it["token_count"],
                "degree": 0,
                "kind": it["kind"],
                "tool_name": it["tool_name"],
                "summary_preview": it["summary_preview"],
            }
        )

    weak_items.sort(key=lambda x: (x["token_count"], x["id"]), reverse=True)

    # Repeated memory_recall misses (same normalized query + scope, no results)
    miss_map: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for it in prepared:
        if it["tool_name_norm"] != "memory_recall":
            continue
        if not it["recall_query"]:
            continue
        if it["recall_result_count"] is None or it["recall_result_count"] > 0:
            continue
        scope_key = it["scope"] or "__global__"
        miss_map.setdefault((scope_key, it["recall_query"]), []).append(it)

    repeated_miss_items: List[Dict[str, Any]] = []
    repeated_miss_events = 0
    for (scope_key, query), group in miss_map.items():
        if len(group) < miss_min_count:
            continue
        ordered = sorted(group, key=lambda x: x["id"])
        repeated_miss_events += len(ordered)
        repeated_miss_items.append(
            {
                "scope": None if scope_key == "__global__" else scope_key,
                "query": query,
                "count": len(ordered),
                "ids": [g["id"] for g in ordered],
                "latest_id": ordered[-1]["id"],
                "latest_ts": ordered[-1]["ts"],
            }
        )
    repeated_miss_items.sort(key=lambda x: (x["count"], x["latest_id"], x["query"]), reverse=True)

    # Importance grading drift / operator spot-check signals (proposal-only)
    importance_distribution: Dict[str, int] = {
        "must_remember": 0,
        "nice_to_have": 0,
        "ignore": 0,
        "unknown": 0,
    }
    importance_score_label_mismatch_items: List[Dict[str, Any]] = []
    importance_missing_or_unparseable_items: List[Dict[str, Any]] = []
    importance_high_risk_content_mismatch_items: List[Dict[str, Any]] = []

    for it in prepared:
        normalized_label = str(it.get("importance") or "unknown")
        if normalized_label not in importance_distribution:
            normalized_label = "unknown"
        importance_distribution[normalized_label] += 1

        importance_state = str(it.get("importance_state") or "").strip() or "unknown"
        if importance_state in {"missing", "unparseable"}:
            importance_missing_or_unparseable_items.append(
                {
                    "id": it["id"],
                    "scope": it.get("scope"),
                    "state": importance_state,
                    "kind": it.get("kind"),
                    "tool_name": it.get("tool_name"),
                    "summary_preview": it.get("summary_preview"),
                }
            )

        stored_label = it.get("importance_stored_label")
        if importance_state == "parseable" and stored_label and stored_label != normalized_label:
            importance_score_label_mismatch_items.append(
                {
                    "id": it["id"],
                    "scope": it.get("scope"),
                    "score": it.get("importance_score"),
                    "stored_label": stored_label,
                    "normalized_label": normalized_label,
                    "kind": it.get("kind"),
                    "tool_name": it.get("tool_name"),
                    "summary_preview": it.get("summary_preview"),
                }
            )

        if importance_state == "parseable" and normalized_label == "ignore":
            summary_value = str(it.get("summary") or "")
            keyword_hits = _importance_high_risk_underlabel_hits(summary_value)
            if keyword_hits:
                importance_high_risk_content_mismatch_items.append(
                    {
                        "id": it["id"],
                        "scope": it.get("scope"),
                        "severity": "high",
                        "normalized_label": normalized_label,
                        "recommended_label": "must_remember",
                        "keyword_hits": keyword_hits,
                        "kind": it.get("kind"),
                        "tool_name": it.get("tool_name"),
                        "summary_preview": it.get("summary_preview"),
                    }
                )

    importance_score_label_mismatch_items.sort(key=lambda x: x["id"], reverse=True)
    importance_missing_or_unparseable_items.sort(key=lambda x: x["id"], reverse=True)
    importance_high_risk_content_mismatch_items.sort(key=lambda x: x["id"], reverse=True)

    rows_scanned = len(prepared)
    importance_drift_policy_card = build_importance_drift_policy_card(
        rows_scanned=rows_scanned,
        score_label_mismatch_count=len(importance_score_label_mismatch_items),
        missing_or_unparseable_count=len(importance_missing_or_unparseable_items),
        high_risk_underlabel_count=len(importance_high_risk_content_mismatch_items),
        profile=importance_drift_profile,
    )
    coverage_pct = round((rows_scanned / total_rows) * 100, 1) if total_rows > 0 else 100.0
    warnings: List[Dict[str, Any]] = []
    if total_rows > rows_scanned:
        warnings.append(
            {
                "code": "sample_is_recent_window",
                "message": "Report scans the most recent rows only; staleness/duplication signals may be incomplete outside the current sample window.",
                "sample_order": "id_desc_recent_window",
            }
        )

    report: Dict[str, Any] = {
        "kind": "openclaw-mem.optimize.review.v0",
        "ts": now.isoformat(),
        "version": {
            "openclaw_mem": __version__,
            "schema": "v0",
        },
        "source": {
            "table": "observations",
            "row_limit": row_limit,
            "rows_scanned": rows_scanned,
            "total_rows": total_rows,
            "scope": scope_norm,
            "coverage_pct": coverage_pct,
            "sample_order": "id_desc_recent_window",
        },
        "signals": {
            "staleness": {
                "count": len(stale_items),
                "threshold_days": stale_days,
                "excluded_must_remember": excluded_must_remember,
                "protected_recent_use": protected_from_stale,
                "items": stale_items[:top],
            },
            "soft_archive_candidates": {
                "count": len(soft_archive_items),
                "stale_days_threshold": stale_days,
                "low_importance_labels": sorted(_SOFT_ARCHIVE_LOW_IMPORTANCE_LABELS),
                "excluded_must_remember": soft_archive_excluded_must_remember,
                "excluded_already_archived": soft_archive_excluded_already_archived,
                "protected_recent_use": soft_archive_protected_recent_use,
                "proposal_only": True,
                "items": soft_archive_items[:top],
            },
            "recent_use": {
                "rows_with_recent_use": len(recent_use_items),
                "selection_events": int(recent_use_meta.get("selection_events") or 0),
                "lifecycle_rows_scanned": int(recent_use_meta.get("lifecycle_rows_scanned") or 0),
                "lifecycle_limit": lifecycle_limit,
                "items": recent_use_items[:top],
            },
            "duplication": {
                "groups": len(dup_items),
                "duplicate_rows": duplicate_rows,
                "min_count": duplicate_min_count,
                "fingerprint_algo": "normalize_v1",
                "scope_isolated": True,
                "items": dup_items[:top],
            },
            "bloat": {
                "count": len(bloat_items),
                "summary_chars_threshold": bloat_summary_chars,
                "detail_bytes_threshold": bloat_detail_bytes,
                "items": bloat_items[:top],
            },
            "weakly_connected": {
                "count": len(weak_items),
                "orphan_min_tokens": orphan_min_tokens,
                "rare_token_max_freq": max_common_freq,
                "items": weak_items[:top],
            },
            "repeated_misses": {
                "groups": len(repeated_miss_items),
                "miss_events": repeated_miss_events,
                "min_count": miss_min_count,
                "tool_name": "memory_recall",
                "items": repeated_miss_items[:top],
            },
            "importance_drift": {
                "normalized_label_distribution": importance_distribution,
                "score_label_mismatch_count": len(importance_score_label_mismatch_items),
                "missing_or_unparseable_count": len(importance_missing_or_unparseable_items),
                "high_risk_content_mismatch_count": len(importance_high_risk_content_mismatch_items),
                "score_label_mismatch_items": importance_score_label_mismatch_items[:top],
                "missing_or_unparseable_items": importance_missing_or_unparseable_items[:top],
                "high_risk_content_mismatch_items": importance_high_risk_content_mismatch_items[:top],
                "policy_card": importance_drift_policy_card,
            },
        },
        "policy": {
            "mode": "recommendation-first",
            "writes_performed": 0,
            "memory_mutation": "none",
            "query_only_enforced": True,
        },
        "warnings": warnings,
    }

    report["recommendations"] = _build_recommendations(report)
    return report


def build_evolution_review(
    conn: sqlite3.Connection,
    *,
    limit: int = 1000,
    stale_days: int = 60,
    lifecycle_limit: int = 200,
    top: int = 10,
    scope: Optional[str] = None,
    importance_drift_profile: Optional[str] = None,
) -> Dict[str, Any]:
    review = build_memory_health_review(
        conn,
        limit=limit,
        stale_days=stale_days,
        duplicate_min_count=2,
        bloat_summary_chars=240,
        bloat_detail_bytes=4096,
        orphan_min_tokens=2,
        miss_min_count=2,
        lifecycle_limit=lifecycle_limit,
        top=top,
        scope=scope,
        importance_drift_profile=importance_drift_profile,
    )

    stale = ((review.get("signals") or {}).get("staleness") or {})
    recent_use = ((review.get("signals") or {}).get("recent_use") or {})
    importance_drift = ((review.get("signals") or {}).get("importance_drift") or {})
    importance_drift_policy_card = (
        importance_drift.get("policy_card")
        if isinstance(importance_drift.get("policy_card"), dict)
        else build_importance_drift_policy_card(
            rows_scanned=int(((review.get("source") or {}).get("rows_scanned") or 0)),
            score_label_mismatch_count=int(importance_drift.get("score_label_mismatch_count") or 0),
            missing_or_unparseable_count=int(importance_drift.get("missing_or_unparseable_count") or 0),
            high_risk_underlabel_count=int(importance_drift.get("high_risk_content_mismatch_count") or 0),
            profile=importance_drift_profile,
        )
    )
    recommendations = list(review.get("recommendations") or [])
    items: List[Dict[str, Any]] = []

    threshold_days = int(stale.get("threshold_days") or stale_days)

    def classify_candidate(
        *,
        action: str,
        target: Dict[str, Any],
        patch: Dict[str, Any],
        evidence: Dict[str, Any],
        safe_for_auto_apply: bool,
    ) -> Dict[str, Any]:
        obs_id = int(target.get("observationId") or 0)
        risk_level = "low"
        risk_reasons: List[str] = []

        if obs_id <= 0:
            return {
                "risk_level": "high",
                "risk_reasons": ["missing_observation_id"],
                "auto_apply_eligible": False,
                "safe_for_auto_apply": False,
            }

        if action == "set_stale_candidate":
            lifecycle_patch = patch.get("lifecycle") if isinstance(patch.get("lifecycle"), dict) else {}
            age_days = evidence.get("age_days")
            recent_use_count = int(evidence.get("recent_use_count") or 0)
            threshold = evidence.get("threshold_days")
            if lifecycle_patch.get("stale_candidate") is not True or str(lifecycle_patch.get("stale_reason_code") or "") not in {
                "age_threshold",
                "repeated_miss_pressure",
                "duplicate_cluster",
                "operator_override",
            }:
                return {
                    "risk_level": "high",
                    "risk_reasons": ["invalid_lifecycle_patch"],
                    "auto_apply_eligible": False,
                    "safe_for_auto_apply": False,
                }
            risk_reasons.extend(["bounded_lifecycle_patch", "age_threshold_signal_present"])
            if age_days is None or threshold is None:
                risk_level = "medium"
                risk_reasons.append("staleness_evidence_incomplete")
            elif int(age_days) < int(threshold):
                risk_level = "medium"
                risk_reasons.append("below_staleness_threshold")
            else:
                risk_reasons.append("age_threshold_met")
            if recent_use_count > 0:
                risk_level = "medium"
                risk_reasons.append("recent_use_conflict")
            else:
                risk_reasons.append("no_recent_use_conflict")
        elif action == "adjust_importance_score":
            importance_patch = patch.get("importance") if isinstance(patch.get("importance"), dict) else {}
            try:
                current_score = round(float(evidence.get("current_score")), 4)
                next_score = round(float(importance_patch.get("score")), 4)
                delta = round(float(importance_patch.get("delta")), 4)
            except Exception:
                return {
                    "risk_level": "high",
                    "risk_reasons": ["invalid_importance_patch"],
                    "auto_apply_eligible": False,
                    "safe_for_auto_apply": False,
                }
            next_label = label_from_score(next_score)
            patch_label = str(importance_patch.get("label") or "").strip()
            reason_code = str(importance_patch.get("reason_code") or "").strip()
            age_days = evidence.get("age_days")
            threshold = evidence.get("threshold_days")
            recent_use_count = int(evidence.get("recent_use_count") or 0)
            if patch_label != next_label:
                return {
                    "risk_level": "high",
                    "risk_reasons": ["importance_label_mismatch"],
                    "auto_apply_eligible": False,
                    "safe_for_auto_apply": False,
                }
            if reason_code not in {"stale_pressure", "reuse_signal", "label_alignment"}:
                return {
                    "risk_level": "high",
                    "risk_reasons": ["invalid_importance_reason_code"],
                    "auto_apply_eligible": False,
                    "safe_for_auto_apply": False,
                }
            risk_reasons.extend(["importance_patch_parseable", "score_label_aligned"])
            if round(next_score - current_score, 4) != delta:
                return {
                    "risk_level": "high",
                    "risk_reasons": ["importance_delta_mismatch"],
                    "auto_apply_eligible": False,
                    "safe_for_auto_apply": False,
                }
            if abs(delta) > 0.10:
                risk_level = "medium"
                risk_reasons.append("importance_delta_exceeds_auto_apply_cap")
            else:
                risk_reasons.append("bounded_importance_delta")
            if reason_code == "stale_pressure":
                risk_reasons.append("stale_pressure_signal_present")
                if age_days is None or threshold is None or int(age_days) < int(threshold):
                    risk_level = "medium"
                    risk_reasons.append("staleness_evidence_weak")
                else:
                    risk_reasons.append("age_threshold_met")
                if recent_use_count > 0:
                    risk_level = "medium"
                    risk_reasons.append("recent_use_conflict")
                else:
                    risk_reasons.append("no_recent_use_conflict")
                if current_score >= 0.50:
                    risk_level = "medium"
                    risk_reasons.append("higher_value_memory_requires_review")
            elif reason_code == "reuse_signal":
                if recent_use_count < 2:
                    risk_level = "medium"
                    risk_reasons.append("reuse_signal_not_strong_enough")
                else:
                    risk_reasons.append("reuse_signal_confirmed")
            else:
                if delta != 0.0:
                    risk_level = "medium"
                    risk_reasons.append("label_alignment_should_not_move_score")
                else:
                    risk_reasons.append("label_alignment_only")
        else:
            return {
                "risk_level": "high",
                "risk_reasons": ["unsupported_action_class"],
                "auto_apply_eligible": False,
                "safe_for_auto_apply": False,
            }

        auto_apply_eligible = bool(safe_for_auto_apply and risk_level == "low")
        return {
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "auto_apply_eligible": auto_apply_eligible,
            "safe_for_auto_apply": auto_apply_eligible,
        }
    candidate_obs_ids: Set[int] = set()
    for raw in list(stale.get("items") or [])[:top]:
        if not isinstance(raw, dict):
            continue
        obs_id = int(raw.get("id") or 0)
        if obs_id <= 0:
            continue
        candidate_obs_ids.add(obs_id)
        item = {
                "candidate_id": f"stale-candidate-{obs_id}",
                "action": "set_stale_candidate",
                "confidence": 0.74,
                "reasons": [
                    "age_threshold",
                    "recent_use_not_observed",
                    f"older_than_{threshold_days}d",
                ],
                "target": {
                    "observationId": obs_id,
                    "recordRef": f"obs:{obs_id}",
                    "scope": raw.get("scope"),
                },
                "patch": {
                    "lifecycle": {
                        "stale_candidate": True,
                        "stale_reason_code": "age_threshold",
                    }
                },
                "evidence_refs": [f"obs:{obs_id}"],
                "evidence": {
                    "signal": "staleness",
                    "age_days": raw.get("age_days"),
                    "threshold_days": threshold_days,
                    "recent_use_count": 0,
                    "importance": raw.get("importance"),
                    "summary_preview": raw.get("summary_preview"),
                    "protected_recent_use_rows": int(recent_use.get("rows_with_recent_use") or 0),
                },
        }
        item.update(
            classify_candidate(
                action=item["action"],
                target=item["target"],
                patch=item["patch"],
                evidence=item["evidence"],
                safe_for_auto_apply=True,
            )
        )
        items.append(item)

    importance_rows: Dict[int, Dict[str, Any]] = {}
    if candidate_obs_ids:
        placeholders = ",".join(["?"] * len(candidate_obs_ids))
        for row in conn.execute(
            f"SELECT id, detail_json FROM observations WHERE id IN ({placeholders})",
            list(sorted(candidate_obs_ids)),
        ).fetchall():
            detail_obj = _parse_detail(row["detail_json"] or "")
            importance = detail_obj.get("importance")
            if not is_parseable_importance(importance):
                continue
            score = round(parse_importance_score(importance), 4)
            importance_rows[int(row["id"])] = {
                "score": score,
                "label": label_from_score(score),
                "stored_label": normalize_label(importance.get('label')) if isinstance(importance, dict) else None,
            }

    for obs_id, imp in list(importance_rows.items()):
        stored_label = imp.get('stored_label')
        expected_label = imp.get('label')
        if not stored_label or stored_label == expected_label:
            continue
        matching_raw = next((raw for raw in list(stale.get('items') or [])[:top] if int(raw.get('id') or 0) == obs_id), None)
        items.append(
            {
                "candidate_id": f"importance-label-alignment-{obs_id}",
                "action": "adjust_importance_score",
                "risk_level": "low",
                "risk_reasons": ["score_label_alignment_only", "no_score_change"],
                "auto_apply_eligible": True,
                "safe_for_auto_apply": True,
                "confidence": 0.72,
                "reasons": [
                    "label_alignment",
                    "score_label_mismatch",
                ],
                "target": {
                    "observationId": obs_id,
                    "recordRef": f"obs:{obs_id}",
                    "scope": matching_raw.get("scope") if isinstance(matching_raw, dict) else None,
                },
                "patch": {
                    "importance": {
                        "score": float(imp.get('score') or 0.0),
                        "label": expected_label,
                        "delta": 0.0,
                        "reason_code": "label_alignment",
                    }
                },
                "evidence_refs": [f"obs:{obs_id}"],
                "evidence": {
                    "signal": "importance_consistency",
                    "current_score": float(imp.get('score') or 0.0),
                    "current_label": stored_label,
                    "next_score": float(imp.get('score') or 0.0),
                    "next_label": expected_label,
                    "age_days": matching_raw.get('age_days') if isinstance(matching_raw, dict) else None,
                    "threshold_days": threshold_days,
                    "recent_use_count": 0,
                },
            }
        )

    for raw in list(stale.get("items") or [])[:top]:
        if not isinstance(raw, dict):
            continue
        obs_id = int(raw.get("id") or 0)
        if obs_id <= 0:
            continue
        imp = importance_rows.get(obs_id)
        if not imp:
            continue
        current_score = float(imp.get("score") or 0.0)
        if current_score <= 0.10:
            continue
        next_score = round(max(0.0, current_score - 0.10), 4)
        if next_score == current_score:
            continue
        next_label = label_from_score(next_score)
        item = {
                "candidate_id": f"importance-downshift-{obs_id}",
                "action": "adjust_importance_score",
                "confidence": 0.68,
                "reasons": [
                    "stale_pressure",
                    "bounded_score_delta",
                    f"older_than_{threshold_days}d",
                ],
                "target": {
                    "observationId": obs_id,
                    "recordRef": f"obs:{obs_id}",
                    "scope": raw.get("scope"),
                },
                "patch": {
                    "importance": {
                        "score": next_score,
                        "label": next_label,
                        "delta": round(next_score - current_score, 4),
                        "reason_code": "stale_pressure",
                    }
                },
                "evidence_refs": [f"obs:{obs_id}"],
                "evidence": {
                    "signal": "staleness",
                    "age_days": raw.get("age_days"),
                    "threshold_days": threshold_days,
                    "recent_use_count": 0,
                    "current_score": current_score,
                    "next_score": next_score,
                    "current_label": imp.get("label"),
                    "next_label": next_label,
                    "summary_preview": raw.get("summary_preview"),
                },
        }
        item.update(
            classify_candidate(
                action=item["action"],
                target=item["target"],
                patch=item["patch"],
                evidence=item["evidence"],
                safe_for_auto_apply=True,
            )
        )
        items.append(item)

    deferred_actions = [
        rec for rec in recommendations if str(rec.get("type") or "") != "mark_stale_candidate"
    ]

    return {
        "kind": "openclaw-mem.optimize.evolution-review.v0",
        "ts": review.get("ts"),
        "version": review.get("version"),
        "source": {
            "kind": str(review.get("kind") or ""),
            "scope": ((review.get("source") or {}).get("scope")),
            "row_limit": int(((review.get("source") or {}).get("row_limit") or limit)),
            "rows_scanned": int(((review.get("source") or {}).get("rows_scanned") or 0)),
            "total_rows": int(((review.get("source") or {}).get("total_rows") or 0)),
            "coverage_pct": ((review.get("source") or {}).get("coverage_pct")),
            "sample_order": ((review.get("source") or {}).get("sample_order")),
        },
        "policy": {
            "mode": "recommendation-first",
            "writes_performed": 0,
            "memory_mutation": "none",
            "query_only_enforced": True,
            "governor_required": True,
            "supported_apply_actions": ["set_stale_candidate", "adjust_importance_score"],
            "auto_apply_without_governor": False,
        },
        "counts": {
            "items": len(items),
            "lowRisk": sum(1 for item in items if str(item.get("risk_level") or "") == "low"),
            "mediumRisk": sum(1 for item in items if str(item.get("risk_level") or "") == "medium"),
            "highRisk": sum(1 for item in items if str(item.get("risk_level") or "") == "high"),
            "deferredRecommendations": len(deferred_actions),
            "importanceDriftLabelMismatches": int(importance_drift.get("score_label_mismatch_count") or 0),
            "importanceDriftMissingOrUnparseable": int(importance_drift.get("missing_or_unparseable_count") or 0),
            "importanceDriftHighRiskContent": int(importance_drift.get("high_risk_content_mismatch_count") or 0),
        },
        "importance_drift_policy": importance_drift_policy_card,
        "items": items,
        "deferred": {
            "recommendation_types": [str(rec.get("type") or "") for rec in deferred_actions[:top]],
            "items": deferred_actions[:top],
        },
        "warnings": list(review.get("warnings") or []),
        "upstream_review": review,
    }


def render_evolution_review(report: Dict[str, Any]) -> str:
    counts = report.get("counts") or {}
    importance_drift_policy = report.get("importance_drift_policy") if isinstance(report.get("importance_drift_policy"), dict) else {}
    drift_policy_metrics = importance_drift_policy.get("metrics") if isinstance(importance_drift_policy.get("metrics"), dict) else {}
    drift_policy_profile = (
        ((importance_drift_policy.get("profile") or {}).get("name"))
        if isinstance(importance_drift_policy.get("profile"), dict)
        else None
    ) or str(importance_drift_policy.get("threshold_profile") or "strict")
    lines = [
        "openclaw-mem optimize evolution-review (governed apply candidates)",
        (
            f"candidates={int(counts.get('items') or 0)} "
            f"low_risk={int(counts.get('lowRisk') or 0)} "
            f"deferred={int(counts.get('deferredRecommendations') or 0)} "
            f"importance_drift(label_mismatch={int(counts.get('importanceDriftLabelMismatches') or 0)},"
            f"missing_or_unparseable={int(counts.get('importanceDriftMissingOrUnparseable') or 0)},"
            f"high_risk_content={int(counts.get('importanceDriftHighRiskContent') or 0)})"
        ),
        (
            f"importance_drift_gate={str(importance_drift_policy.get('status') or 'hold')} "
            f"acceptable={bool(importance_drift_policy.get('acceptable_for_promotion_apply', False))} "
            f"rows={int(drift_policy_metrics.get('rows_scanned') or 0)} "
            f"profile={drift_policy_profile}"
        ),
    ]
    for item in list(report.get("items") or [])[:10]:
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        lines.append(
            "- "
            f"{item.get('candidate_id')} action={item.get('action')} risk={item.get('risk_level')} "
            f"obs={target.get('observationId')} age_days={evidence.get('age_days')}"
        )
    return "\n".join(lines)


def render_memory_health_review(report: Dict[str, Any]) -> str:
    src = report.get("source", {})
    sig = report.get("signals", {})

    stale = sig.get("staleness", {})
    soft_archive = sig.get("soft_archive_candidates", {})
    recent_use = sig.get("recent_use", {})
    dup = sig.get("duplication", {})
    bloat = sig.get("bloat", {})
    weak = sig.get("weakly_connected", {})
    misses = sig.get("repeated_misses", {})
    importance_drift = sig.get("importance_drift", {})
    importance_drift_policy = importance_drift.get("policy_card") if isinstance(importance_drift.get("policy_card"), dict) else {}
    drift_policy_metrics = importance_drift_policy.get("metrics") if isinstance(importance_drift_policy.get("metrics"), dict) else {}
    drift_policy_profile = (
        ((importance_drift_policy.get("profile") or {}).get("name"))
        if isinstance(importance_drift_policy.get("profile"), dict)
        else None
    ) or str(importance_drift_policy.get("threshold_profile") or "strict")

    lines = [
        "openclaw-mem optimize review (recommendation-only)",
        (
            "rows scanned: "
            f"{src.get('rows_scanned', 0)}/{src.get('row_limit', 0)} "
            f"(total_rows={src.get('total_rows', 0)}, coverage={src.get('coverage_pct', 0)}%, sample_order={src.get('sample_order', 'unknown')})"
        ),
        (
            "signals: "
            f"stale={stale.get('count', 0)} (protected_recent_use={stale.get('protected_recent_use', 0)}) | "
            f"soft_archive={soft_archive.get('count', 0)} (protected_recent_use={soft_archive.get('protected_recent_use', 0)}) | "
            f"recent_use={recent_use.get('rows_with_recent_use', 0)} rows | "
            f"duplicates={dup.get('groups', 0)} groups ({dup.get('duplicate_rows', 0)} extra rows) | "
            f"bloat={bloat.get('count', 0)} | "
            f"weakly_connected={weak.get('count', 0)} | "
            f"repeated_misses={misses.get('groups', 0)} groups ({misses.get('miss_events', 0)} events) | "
            f"importance_drift=label_mismatch:{importance_drift.get('score_label_mismatch_count', 0)} "
            f"missing_or_unparseable:{importance_drift.get('missing_or_unparseable_count', 0)} "
            f"high_risk_content:{importance_drift.get('high_risk_content_mismatch_count', 0)}"
        ),
        (
            f"importance_drift_gate={str(importance_drift_policy.get('status') or 'hold')} "
            f"acceptable={bool(importance_drift_policy.get('acceptable_for_promotion_apply', False))} "
            f"rows={int(drift_policy_metrics.get('rows_scanned') or 0)} "
            f"profile={drift_policy_profile}"
        ),
    ]

    warnings = report.get("warnings", [])
    if warnings:
        lines.append("warnings:")
        for w in warnings:
            lines.append(f"- {w.get('code')}: {w.get('message')}")

    recs = report.get("recommendations", [])
    if recs:
        lines.append("recommendations:")
        for rec in recs:
            lines.append(
                f"- {rec.get('type')} (confidence={rec.get('confidence')}, priority={rec.get('priority')}): {rec.get('why')}"
            )
    else:
        lines.append("recommendations: none")

    return "\n".join(lines)
