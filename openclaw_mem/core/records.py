"""Observation record storage primitives."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Protocol

from openclaw_mem.core.db import _sanitize_jsonable_surrogates, _sanitize_str_surrogates

class IngestRunSummary(Protocol):
    total_seen: int
    graded_filled: int
    skipped_existing: int
    skipped_disabled: int
    scorer_errors: int
    def bump_label(self, label: str) -> None: ...

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _normalize_importance_scorer_value(value: str) -> str:
    """Normalize importance autograde scorer values.

    Accepts minor aliases (e.g., heuristic_v1) while keeping a
    single canonical value for storage/receipts.
    """

    v = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if not v:
        return ""

    v = v.replace("_", "-").replace(" ", "")
    if v in {"heuristicv1", "heuristic-v1"}:
        return "heuristic-v1"
    if v in {"heuristicv2", "heuristic-v2"}:
        return "heuristic-v2"
    return v


def _insert_observation(conn: sqlite3.Connection, obs: Dict[str, Any], run_summary: IngestRunSummary | None = None) -> int:
    ts = obs.get("ts") or _utcnow_iso()

    kind = obs.get("kind")
    kind = _sanitize_str_surrogates(str(kind)) if kind is not None else None

    summary = obs.get("summary")
    summary = _sanitize_str_surrogates(str(summary)) if summary is not None else None

    summary_en = obs.get("summary_en") or obs.get("text_en")
    summary_en = _sanitize_str_surrogates(str(summary_en)) if summary_en is not None else None

    lang = obs.get("lang")
    lang = _sanitize_str_surrogates(str(lang)) if lang is not None else None

    tool_name = obs.get("tool_name") or obs.get("tool")
    tool_name = _sanitize_str_surrogates(str(tool_name)) if tool_name is not None else None

    base_detail = obs.get("detail")
    if base_detail is None:
        base_detail = obs.get("detail_json") or {}

    if isinstance(base_detail, str):
        try:
            detail_obj: Dict[str, Any] = json.loads(base_detail)
            if not isinstance(detail_obj, dict):
                detail_obj = {"_raw_detail": base_detail}
        except Exception:
            detail_obj = {"_raw_detail": base_detail}
    elif isinstance(base_detail, dict):
        detail_obj = dict(base_detail)
    else:
        detail_obj = {"_detail": base_detail}

    known_keys = {
        "ts",
        "kind",
        "summary",
        "summary_en",
        "text_en",
        "lang",
        "tool_name",
        "tool",
        "detail",
        "detail_json",
    }
    extras = {k: v for k, v in obs.items() if k not in known_keys}
    if extras:
        detail_obj.update(extras)

    # Sanitize any invalid unicode surrogate codepoints before binding to SQLite.
    detail_obj = _sanitize_jsonable_surrogates(detail_obj)

    if run_summary is not None:
        run_summary.total_seen += 1

    try:
        from openclaw_mem.importance import is_parseable_importance

        had_importance = is_parseable_importance(detail_obj.get("importance"))
    except Exception:
        # Conservative fallback: if the helper import fails for any reason,
        # preserve prior behavior (treat presence of the field as 'existing').
        had_importance = "importance" in detail_obj
    if run_summary is not None and had_importance:
        run_summary.skipped_existing += 1
        try:
            from openclaw_mem.importance import parse_importance_score, label_from_score

            existing = detail_obj.get("importance")
            if isinstance(existing, dict) and isinstance(existing.get("label"), str) and existing.get("label").strip():
                run_summary.bump_label(existing.get("label"))
            else:
                run_summary.bump_label(label_from_score(parse_importance_score(existing)))
        except Exception:
            # Never break ingestion for reporting.
            run_summary.bump_label("unknown")

    # Optional: auto-grade importance behind a feature flag (non-destructive).
    #
    # MVP rules:
    # - default OFF
    # - only populate missing `detail_json.importance`
    # - fail-open on any grading error
    scorer = _normalize_importance_scorer_value(os.environ.get("OPENCLAW_MEM_IMPORTANCE_SCORER") or "")

    if scorer == "heuristic-v1":
        if not had_importance:
            try:
                # Test hook: force a grading failure to prove fail-open behavior.
                if (os.environ.get("OPENCLAW_MEM_IMPORTANCE_TEST_RAISE") or "").strip() == "1":
                    raise RuntimeError("forced importance autograde failure (test)")

                from openclaw_mem.heuristic_v1 import grade_observation

                r = grade_observation(
                    {
                        "ts": ts,
                        "kind": kind,
                        "summary": summary,
                        "summary_en": summary_en,
                        "lang": lang,
                        "tool_name": tool_name,
                        "detail": detail_obj,
                    }
                )
                imp = r.as_importance()
                detail_obj["importance"] = imp

                if run_summary is not None:
                    run_summary.graded_filled += 1
                    run_summary.bump_label(str(imp.get("label") or "unknown"))
            except Exception as e:
                if run_summary is not None:
                    run_summary.scorer_errors += 1
                print(f"Warning: importance autograde failed: {e}", file=sys.stderr)
    else:
        if run_summary is not None and not had_importance:
            run_summary.skipped_disabled += 1

    detail_json = json.dumps(detail_obj, ensure_ascii=False)

    cur = conn.execute(
        "INSERT INTO observations (ts, kind, summary, summary_en, lang, tool_name, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, kind, summary, summary_en, lang, tool_name, detail_json),
    )
    rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO observations_fts (rowid, summary, summary_en, tool_name, detail_json) VALUES (?, ?, ?, ?, ?)",
        (rowid, summary, summary_en, tool_name, detail_json),
    )
    return int(rowid)
