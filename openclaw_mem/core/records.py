"""Observation record storage primitives."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Protocol

from openclaw_mem.core.db import _sanitize_jsonable_surrogates, _sanitize_str_surrogates

_IMPORTANCE_LABEL_KEYS = ("critical", "high", "medium", "low", "trivial")


@dataclass
class IngestRunSummary:
    """Aggregate ingest/harvest stats for importance autograde receipts."""

    total_seen: int = 0
    graded_filled: int = 0
    skipped_existing: int = 0
    skipped_disabled: int = 0
    scorer_errors: int = 0
    label_counts: Dict[str, int] = field(default_factory=dict)

    def bump_label(self, label: str) -> None:
        raw = label or ""
        try:
            from openclaw_mem.importance import normalize_label

            normalized = normalize_label(raw)
        except Exception:
            normalized = None
        key = normalized or unicodedata.normalize("NFKC", raw).strip().lower() or "unknown"
        self.label_counts[key] = int(self.label_counts.get(key, 0)) + 1

    def normalized_label_counts(self) -> Dict[str, int]:
        out = {key: int(self.label_counts.get(key, 0)) for key in _IMPORTANCE_LABEL_KEYS}
        for key in sorted(self.label_counts):
            if key not in out:
                out[key] = int(self.label_counts[key])
        return out

class IngestRunSummaryLike(Protocol):
    total_seen: int
    graded_filled: int
    skipped_existing: int
    skipped_disabled: int
    scorer_errors: int
    def bump_label(self, label: str) -> None: ...


class HarvestError(RuntimeError):
    """Harvest failure carrying the CLI-compatible error receipt."""

    def __init__(self, receipt: Dict[str, Any]):
        super().__init__(str(receipt.get("error") or "harvest failed"))
        self.receipt = receipt

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


def apply_importance_scorer_override(value: str | None) -> None:
    """Apply the CLI-compatible process-local importance scorer override."""

    if value is None:
        return
    normalized = _normalize_importance_scorer_value(value)
    if not normalized:
        return
    if normalized in {"off", "none", "disable", "disabled", "0"}:
        os.environ.pop("OPENCLAW_MEM_IMPORTANCE_SCORER", None)
    else:
        os.environ["OPENCLAW_MEM_IMPORTANCE_SCORER"] = normalized


def ingest_observations(
    conn: sqlite3.Connection,
    observations: Iterable[Dict[str, Any]],
    *,
    importance_scorer: str | None = None,
) -> Dict[str, Any]:
    """Insert an observation stream and return its deterministic receipt."""

    apply_importance_scorer_override(importance_scorer)
    summary = IngestRunSummary()
    inserted = [_insert_observation(conn, obs, summary) for obs in observations]
    conn.commit()
    return {
        "inserted": len(inserted),
        "ids": inserted[:50],
        "total_seen": summary.total_seen,
        "graded_filled": summary.graded_filled,
        "skipped_existing": summary.skipped_existing,
        "skipped_disabled": summary.skipped_disabled,
        "scorer_errors": summary.scorer_errors,
        "label_counts": summary.normalized_label_counts(),
    }


def _atomic_append_file(path: Path, content: str) -> None:
    """Append through a same-directory temporary file and atomic replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        prefix=".tmp_",
        suffix=path.suffix or ".txt",
    ) as tmp:
        tmp.write(existing + content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def store_memory(
    conn: sqlite3.Connection,
    *,
    text: str,
    category: str,
    importance: float,
    text_en: str | None = None,
    lang: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str,
    memory_dir: Path | None = None,
    embedding_client_factory: Callable[..., Any] | None = None,
) -> tuple[Dict[str, Any], List[str]]:
    """Store one memory and return a receipt plus non-fatal warnings.

    This core function never prints or exits. The CLI owns presentation and
    exit status while this function owns SQLite/vector/Markdown behavior.
    """

    normalized_text = text.strip()
    if not normalized_text:
        return {"error": "empty text"}, []
    normalized_text_en = (text_en or "").strip() or None
    normalized_lang = (lang or "").strip() or None

    from openclaw_mem.importance import make_importance

    importance_obj = make_importance(
        float(importance),
        method="manual-via-cli",
        rationale="Provided via openclaw-mem store --importance.",
        version=1,
    )
    rowid = _insert_observation(
        conn,
        {
            "kind": category,
            "summary": normalized_text,
            "summary_en": normalized_text_en,
            "lang": normalized_lang,
            "tool_name": "memory_store",
            "detail": {"importance": importance_obj},
        },
    )

    warnings: List[str] = []
    if api_key:
        try:
            from openclaw_mem.vector import l2_norm, pack_f32

            if embedding_client_factory is None:
                raise RuntimeError("embedding client factory is required when api_key is set")
            client = embedding_client_factory(api_key=api_key, base_url=base_url)
            created_at = _utcnow_iso()
            vec = client.embed([normalized_text], model=model)[0]
            conn.execute(
                """INSERT OR REPLACE INTO observation_embeddings
                   (observation_id, model, dim, vector, norm, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (rowid, model, len(vec), pack_f32(vec), l2_norm(vec), created_at),
            )
            if normalized_text_en:
                vec_en = client.embed([normalized_text_en], model=model)[0]
                conn.execute(
                    """INSERT OR REPLACE INTO observation_embeddings_en
                       (observation_id, model, dim, vector, norm, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (rowid, model, len(vec_en), pack_f32(vec_en), l2_norm(vec_en), created_at),
                )
        except Exception as exc:
            warnings.append(f"Failed to embed memory: {exc}")
    else:
        warnings.append("No API key, skipping embedding")
    conn.commit()

    markdown_path: str | None = None
    markdown_write_status = "skipped:no_file_write"
    if memory_dir is not None:
        md_file = memory_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
        md_entry = (
            f"- [{category.upper()}] {normalized_text} "
            f"(importance: {importance_obj['score']:.2f}, {importance_obj['label']})\n"
        )
        try:
            _atomic_append_file(md_file, md_entry)
            markdown_path = str(md_file)
            markdown_write_status = "written"
        except Exception as exc:
            markdown_write_status = f"failed:{exc}"

    return {
        "ok": True,
        "id": rowid,
        "file": markdown_path,
        "markdownPath": markdown_path,
        "markdownWriteStatus": markdown_write_status,
        "embedded": bool(api_key),
    }, warnings


def _iter_jsonl(fp: Iterable[str]) -> Iterable[Dict[str, Any]]:
    for line in fp:
        stripped = line.strip()
        if stripped:
            yield json.loads(stripped)


def harvest_observations(
    conn: sqlite3.Connection,
    *,
    source: Path,
    version: str,
    importance_scorer: str | None = None,
    archive_dir: Path | None = None,
    update_index: bool = True,
    index_path: Path | None = None,
    index_limit: int = 5000,
    build_index: Callable[[sqlite3.Connection, Path, int], Any] | None = None,
    embed: bool = False,
    api_key: str | None = None,
    api_key_provider: Callable[[], str | None] | None = None,
    base_url: str | None = None,
    model: str = "text-embedding-3-small",
    embed_limit: int = 1000,
    embedding_client_factory: Callable[..., Any] | None = None,
    warn_embedding_model_mismatch: Callable[..., Any] | None = None,
) -> tuple[Dict[str, Any], List[str]]:
    """Recover, ingest, optionally index/embed, and archive a harvest batch.

    The function owns all state transitions but never prints or exits. Expected
    operational failures are raised as :class:`HarvestError` receipts.
    """

    from openclaw_mem.vector import l2_norm, pack_f32

    apply_importance_scorer_override(importance_scorer)
    summary = IngestRunSummary()
    warnings: List[str] = []
    processing_files = sorted(source.parent.glob(f"{source.name}.*.processing"))
    recovered = bool(processing_files)
    rotated = False

    if source.exists() and source.stat().st_size > 0:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        processing = source.with_suffix(f".jsonl.{stamp}.processing")
        try:
            source.rename(processing)
        except OSError as exc:
            raise HarvestError({"error": f"Failed to rotate log: {exc}"}) from exc
        processing_files.append(processing)
        processing_files.sort()
        rotated = True

    if not processing_files:
        return {
            "kind": "openclaw-mem.harvest.v0",
            "ts": _utcnow_iso(),
            "version": {"openclaw_mem": version, "schema": "v0"},
            "ok": True,
            "processed_files": 0,
            "ingested": 0,
            "reason": "source empty/missing",
            "total_seen": summary.total_seen,
            "graded_filled": summary.graded_filled,
            "skipped_existing": summary.skipped_existing,
            "skipped_disabled": summary.skipped_disabled,
            "scorer_errors": summary.scorer_errors,
            "label_counts": summary.normalized_label_counts(),
        }, warnings

    inserted_ids: List[int] = []
    for processing in processing_files:
        try:
            with processing.open("r", encoding="utf-8") as fp:
                for observation in _iter_jsonl(fp):
                    inserted_ids.append(_insert_observation(conn, observation, summary))
            conn.commit()
        except Exception as exc:
            raise HarvestError({"error": f"Ingest failed: {exc}", "file": str(processing)}) from exc

    if update_index and build_index is not None and index_path is not None:
        try:
            build_index(conn, index_path, int(index_limit))
        except Exception as exc:
            warnings.append(f"failed to update index: {exc}")

    embedded = 0
    embed_error: str | None = None
    if embed:
        if api_key is None and api_key_provider is not None:
            api_key = api_key_provider()
        if not api_key:
            embed_error = "missing_api_key"
        else:
            try:
                if embedding_client_factory is None:
                    raise RuntimeError("embedding client factory is required when api_key is set")
                client = embedding_client_factory(api_key=api_key, base_url=base_url)
                table = "observation_embeddings"
                if warn_embedding_model_mismatch is not None:
                    warn_embedding_model_mismatch(
                        conn,
                        table=table,
                        requested_model=model,
                        label="original",
                    )
                rows = conn.execute(
                    """SELECT id, tool_name, summary AS text_value
                       FROM observations
                       WHERE id NOT IN (
                           SELECT observation_id FROM observation_embeddings WHERE model = ?
                       )
                       AND trim(coalesce(summary, '')) <> ''
                       ORDER BY id
                       LIMIT ?""",
                    (model, max(1, int(embed_limit))),
                ).fetchall()
                todo = [dict(row) for row in rows]
                created_at = _utcnow_iso()
                for offset in range(0, len(todo), 64):
                    chunk = todo[offset : offset + 64]
                    texts = [
                        f"{(row.get('tool_name') or '').strip()}: {(row.get('text_value') or '').strip()}".strip(": ")
                        for row in chunk
                    ]
                    vectors = client.embed(texts, model=model)
                    for row, vector in zip(chunk, vectors):
                        conn.execute(
                            """INSERT OR REPLACE INTO observation_embeddings
                               (observation_id, model, dim, vector, norm, created_at)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (
                                int(row["id"]),
                                model,
                                len(vector),
                                pack_f32(vector),
                                l2_norm(vector),
                                created_at,
                            ),
                        )
                        embedded += 1
                    conn.commit()
            except Exception as exc:
                embed_error = str(exc)

    try:
        if archive_dir is not None:
            archive_dir.mkdir(parents=True, exist_ok=True)
            for processing in processing_files:
                processing.rename(archive_dir / processing.name)
        else:
            for processing in processing_files:
                processing.unlink()
    except Exception as exc:
        raise HarvestError({"error": f"Failed to archive/delete processing files: {exc}"}) from exc

    receipt: Dict[str, Any] = {
        "kind": "openclaw-mem.harvest.v0",
        "ts": _utcnow_iso(),
        "version": {"openclaw_mem": version, "schema": "v0"},
        "ok": True,
        "ingested": len(inserted_ids),
        "processed_files": len(processing_files),
        "files": [path.name for path in processing_files[:20]],
        "recovered": recovered,
        "rotated": rotated,
        "source": str(source),
        "archive": str(archive_dir) if archive_dir is not None else "deleted",
        "total_seen": summary.total_seen,
        "graded_filled": summary.graded_filled,
        "skipped_existing": summary.skipped_existing,
        "skipped_disabled": summary.skipped_disabled,
        "scorer_errors": summary.scorer_errors,
        "label_counts": summary.normalized_label_counts(),
        "embedded": embedded,
    }
    if embed_error:
        receipt["embed_error"] = embed_error
    return receipt, warnings


def _insert_observation(conn: sqlite3.Connection, obs: Dict[str, Any], run_summary: IngestRunSummaryLike | None = None) -> int:
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
