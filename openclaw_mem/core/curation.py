"""Governed curation primitives shared by CLI surfaces.

The first primitive intentionally stays narrow: applying an optimize-assist
rollback receipt with compare-and-restore semantics.  Every row is validated
before the transaction starts so a stale receipt can never partially restore a
database.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Mapping


ROLLBACK_KIND = "openclaw-mem.optimize.assist.rollback.v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _failure(*, receipt: str, error: str, hint: str) -> Dict[str, Any]:
    return {
        "kind": "openclaw-mem.curate.memory-rollback.v1",
        "ok": False,
        "writes_performed": False,
        "restored_count": 0,
        "receipt": receipt,
        "error": error,
        "hint": hint,
    }


def rollback_optimize_assist(
    conn: sqlite3.Connection,
    receipt_path: str | Path,
    *,
    actor: str = "operator",
) -> Dict[str, Any]:
    """Restore an optimize assist batch iff every target still matches it.

    Hash checks are deliberately performed for the entire batch before any
    update.  This makes rollback atomic with respect to stale/mutated targets.
    """

    path = Path(receipt_path).expanduser()
    receipt_ref = str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _failure(
            receipt=receipt_ref,
            error=f"unable to read rollback receipt: {exc}",
            hint="pass an existing optimize assist rollback receipt",
        )
    if not isinstance(payload, Mapping) or payload.get("kind") != ROLLBACK_KIND:
        return _failure(
            receipt=receipt_ref,
            error=f"unsupported rollback receipt kind: {payload.get('kind') if isinstance(payload, Mapping) else type(payload).__name__}",
            hint=f"expected {ROLLBACK_KIND}",
        )

    mutations = payload.get("mutations")
    if not isinstance(mutations, list) or not mutations:
        return _failure(
            receipt=receipt_ref,
            error="rollback receipt has no mutations",
            hint="use the rollback_ref emitted by a successful optimize assist-apply run",
        )

    validated = []
    seen = set()
    for index, mutation in enumerate(mutations):
        if not isinstance(mutation, Mapping):
            return _failure(
                receipt=receipt_ref,
                error=f"mutation {index} is not an object",
                hint="use an unmodified optimize assist rollback receipt",
            )
        try:
            observation_id = int(mutation.get("observation_id"))
        except (TypeError, ValueError):
            observation_id = 0
        before_detail = mutation.get("before_detail_json")
        after_sha256 = str(mutation.get("after_sha256") or "").strip()
        before_sha256 = str(mutation.get("before_sha256") or "").strip()
        if observation_id <= 0 or observation_id in seen or not isinstance(before_detail, Mapping):
            return _failure(
                receipt=receipt_ref,
                error=f"mutation {index} has an invalid or duplicate observation target",
                hint="use an unmodified optimize assist rollback receipt",
            )
        seen.add(observation_id)
        if before_sha256 and _json_sha256(before_detail) != before_sha256:
            return _failure(
                receipt=receipt_ref,
                error=f"mutation {index} before-state hash does not match its payload",
                hint="do not edit rollback receipts before applying them",
            )
        row = conn.execute(
            "SELECT detail_json FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
        if row is None:
            return _failure(
                receipt=receipt_ref,
                error=f"observation {observation_id} no longer exists",
                hint="restore the missing row separately or use a matching database snapshot",
            )
        try:
            current_detail = json.loads(row["detail_json"] or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            return _failure(
                receipt=receipt_ref,
                error=f"observation {observation_id} has invalid detail_json: {exc}",
                hint="repair the row before retrying rollback",
            )
        current_sha256 = _json_sha256(current_detail)
        if not after_sha256:
            return _failure(
                receipt=receipt_ref,
                error=f"mutation {index} is missing after_sha256",
                hint="dry-run and incomplete rollback receipts cannot be applied",
            )
        if current_sha256 != after_sha256:
            return _failure(
                receipt=receipt_ref,
                error=f"observation {observation_id} changed after assist-apply",
                hint="review the newer mutation; rollback refuses to overwrite drifted state",
            )
        validated.append(
            {
                "observation_id": observation_id,
                "before_detail": dict(before_detail),
                "from_sha256": current_sha256,
                "to_sha256": _json_sha256(before_detail),
            }
        )

    try:
        with conn:
            for item in validated:
                conn.execute(
                    "UPDATE observations SET detail_json = ? WHERE id = ?",
                    (_canonical_json(item["before_detail"]), item["observation_id"]),
                )
    except sqlite3.Error as exc:
        return _failure(
            receipt=receipt_ref,
            error=f"rollback transaction failed: {exc}",
            hint="database state was not partially restored; resolve the error and retry",
        )

    return {
        "kind": "openclaw-mem.curate.memory-rollback.v1",
        "ok": True,
        "writes_performed": True,
        "restored_count": len(validated),
        "restored_observation_ids": [item["observation_id"] for item in validated],
        "source_run_id": payload.get("run_id"),
        "receipt": receipt_ref,
        "actor": str(actor or "operator"),
        "mutations": [
            {
                "observation_id": item["observation_id"],
                "from_sha256": item["from_sha256"],
                "to_sha256": item["to_sha256"],
            }
            for item in validated
        ],
    }
