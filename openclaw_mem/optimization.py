from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from openclaw_mem import __version__
from openclaw_mem.importance import is_parseable_importance, label_from_score, parse_importance_score
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


_EPISODIC_RETENTION_DAYS: Dict[str, Optional[int]] = {
    "conversation.user": 60,
    "conversation.assistant": 90,
    "tool.call": 30,
    "tool.result": 30,
    "ops.alert": 90,
    "ops.decision": None,
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
                "why": f"{links['pairs']} cross-session lexical link candidates were found",
                "evidence": {
                    "pairs": links["pairs"],
                    "sample_shared_tokens": [it.get("shared_tokens", [])[:3] for it in links.get("items", [])[:3]],
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
    top: int = 10,
) -> Dict[str, Any]:
    row_limit = max(1, int(limit))
    summary_min_group_size = max(2, int(summary_min_group_size))
    summary_min_shared_tokens = max(1, int(summary_min_shared_tokens))
    archive_lookahead_days = max(1, int(archive_lookahead_days))
    archive_min_signal_reasons = max(1, int(archive_min_signal_reasons))
    link_min_shared_tokens = max(1, int(link_min_shared_tokens))
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

    archive_items: List[Dict[str, Any]] = []
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

    link_items: List[Dict[str, Any]] = []
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
                if len(shared) < link_min_shared_tokens:
                    continue
                union_size = max(1, len(left["tokens"] | right["tokens"]))
                score = round(len(shared) / union_size, 3)
                link_items.append(
                    {
                        "scope": scope_key,
                        "shared_tokens": shared[:5],
                        "shared_token_count": len(shared),
                        "score": score,
                        "left": _event_ref(left),
                        "right": _event_ref(right),
                    }
                )
                seen_pairs.add(pair_key)
    link_items.sort(key=lambda x: (x["shared_token_count"], x["score"], x["right"]["id"]), reverse=True)

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
            "rare_token_max_freq": max_common_freq,
        },
        "candidates": {
            "summary": {"groups": len(summary_items), "items": summary_items[:top]},
            "archive": {"count": len(archive_items), "items": archive_items[:top]},
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
            f"archive={archive.get('count', 0)} | "
            f"links={links.get('pairs', 0)} pairs"
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
    top: int = 10,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    row_limit = max(1, int(limit))
    stale_days = max(1, int(stale_days))
    duplicate_min_count = max(2, int(duplicate_min_count))
    bloat_summary_chars = max(80, int(bloat_summary_chars))
    bloat_detail_bytes = max(256, int(bloat_detail_bytes))
    orphan_min_tokens = max(1, int(orphan_min_tokens))
    miss_min_count = max(2, int(miss_min_count))
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
    finally:
        if not prev_query_only:
            conn.execute("PRAGMA query_only = OFF")

    now = datetime.now(timezone.utc)
    prepared: List[Dict[str, Any]] = []

    for r in rows:
        summary = _normalize_summary(r["summary_en"] or r["summary"] or "")
        detail_raw = r["detail_json"] or ""
        detail_obj = _parse_detail(detail_raw)
        tool_name = str(r["tool_name"] or "")
        tool_name_norm = tool_name.strip().lower()
        recall_query = _extract_recall_query(detail_obj) if tool_name_norm == "memory_recall" else None
        recall_result_count = _extract_recall_result_count(detail_obj) if tool_name_norm == "memory_recall" else None
        dt = _parse_iso_utc(r["ts"])
        age_days = None
        if dt is not None:
            age_days = max(0, int((now - dt).total_seconds() // 86400))

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
            "importance": _importance_label(detail_obj),
            "recall_query": recall_query,
            "recall_result_count": recall_result_count,
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
            "repeated_misses": {
                "groups": len(repeated_miss_items),
                "miss_events": repeated_miss_events,
                "min_count": miss_min_count,
                "tool_name": "memory_recall",
                "items": repeated_miss_items[:top],
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
    misses = sig.get("repeated_misses", {})

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
            f"weakly_connected={weak.get('count', 0)} | "
            f"repeated_misses={misses.get('groups', 0)} groups ({misses.get('miss_events', 0)} events)"
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
