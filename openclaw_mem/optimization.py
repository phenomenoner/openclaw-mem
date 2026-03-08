from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from openclaw_mem import __version__
from openclaw_mem.importance import is_parseable_importance, label_from_score, parse_importance_score


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


def _normalize_scope_token(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    token = str(raw).strip().lower()
    if not token:
        return None
    token = re.sub(r"[\s]+", "-", token)
    token = re.sub(r"[^a-z0-9._:/-]+", "-", token)
    token = re.sub(r"-+", "-", token)
    token = re.sub(r"^[-./:_]+", "", token)
    token = re.sub(r"[-./:_]+$", "", token)
    return token or None


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


def _preview(text: str, limit: int = 120) -> str:
    t = text.replace("\n", " ").strip()
    if len(t) <= limit:
        return t
    return t[: max(16, limit - 1)].rstrip() + "…"


def _build_recommendations(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []

    stale = report["signals"]["staleness"]
    if stale["count"] > 0:
        recs.append(
            {
                "type": "mark_stale_candidate",
                "priority": "low",
                "confidence": 0.74,
                "why": f"{stale['count']} rows are older than {stale['threshold_days']} days",
                "evidence": {
                    "count": stale["count"],
                    "sample_ids": [it["id"] for it in stale["items"][:5]],
                },
                "suggested_action": "Review candidates for archive/summary tagging (manual approval).",
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

    return recs


def build_memory_health_review(
    conn: sqlite3.Connection,
    *,
    limit: int = 1000,
    stale_days: int = 60,
    duplicate_min_count: int = 2,
    bloat_summary_chars: int = 240,
    bloat_detail_bytes: int = 4096,
    orphan_min_tokens: int = 2,
    top: int = 10,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    row_limit = max(1, int(limit))
    stale_days = max(1, int(stale_days))
    duplicate_min_count = max(2, int(duplicate_min_count))
    bloat_summary_chars = max(80, int(bloat_summary_chars))
    bloat_detail_bytes = max(256, int(bloat_detail_bytes))
    orphan_min_tokens = max(1, int(orphan_min_tokens))
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
            scope_clause = (
                " WHERE lower(json_extract("
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
    finally:
        if not prev_query_only:
            conn.execute("PRAGMA query_only = OFF")

    now = datetime.now(timezone.utc)
    prepared: List[Dict[str, Any]] = []

    for r in rows:
        summary = _normalize_summary(r["summary_en"] or r["summary"] or "")
        detail_raw = r["detail_json"] or ""
        detail_obj = _parse_detail(detail_raw)
        dt = _parse_iso_utc(r["ts"])
        age_days = None
        if dt is not None:
            age_days = max(0, int((now - dt).total_seconds() // 86400))

        item = {
            "id": int(r["id"]),
            "ts": r["ts"],
            "kind": r["kind"],
            "tool_name": r["tool_name"],
            "summary": summary,
            "summary_preview": _preview(summary),
            "fingerprint": _fingerprint_summary(summary),
            "tokens": _tokenize(summary),
            "token_count": 0,
            "age_days": age_days,
            "detail_bytes": len(detail_raw.encode("utf-8")) if isinstance(detail_raw, str) else 0,
            "summary_chars": len(summary),
            "scope": _normalize_scope_token(detail_obj.get("scope")),
            "importance": _importance_label(detail_obj),
        }
        item["token_count"] = len(item["tokens"])
        prepared.append(item)

    # Staleness
    stale_items: List[Dict[str, Any]] = []
    excluded_must_remember = 0
    for it in prepared:
        if it["age_days"] is None:
            continue
        if it["age_days"] < stale_days:
            continue
        if it["importance"] == "must_remember":
            excluded_must_remember += 1
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

    rows_scanned = len(prepared)
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
                "items": stale_items[:top],
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


def render_memory_health_review(report: Dict[str, Any]) -> str:
    src = report.get("source", {})
    sig = report.get("signals", {})

    stale = sig.get("staleness", {})
    dup = sig.get("duplication", {})
    bloat = sig.get("bloat", {})
    weak = sig.get("weakly_connected", {})

    lines = [
        "openclaw-mem optimize review (recommendation-only)",
        (
            "rows scanned: "
            f"{src.get('rows_scanned', 0)}/{src.get('row_limit', 0)} "
            f"(total_rows={src.get('total_rows', 0)}, coverage={src.get('coverage_pct', 0)}%, sample_order={src.get('sample_order', 'unknown')})"
        ),
        (
            "signals: "
            f"stale={stale.get('count', 0)} | "
            f"duplicates={dup.get('groups', 0)} groups ({dup.get('duplicate_rows', 0)} extra rows) | "
            f"bloat={bloat.get('count', 0)} | "
            f"weakly_connected={weak.get('count', 0)}"
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
