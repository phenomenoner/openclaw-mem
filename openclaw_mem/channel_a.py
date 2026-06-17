"""Channel A file-contract producer for ContextPack v1.

This is the offline/fail-open integration path for host agents. It ingests a
JSONL observation feed idempotently and writes per-agent latest ContextPack
files under a caller-provided pack directory.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from openclaw_mem.cli import DEFAULT_DB, _connect, _insert_observation, cmd_pack
from openclaw_mem.context_pack_v1 import CONTEXT_PACK_V1_SCHEMA


PRODUCER_RECEIPT_SCHEMA = "openclaw-mem.channel-a.producer.receipt.v1"
PRIVATE_MARKERS = ("<private>", "</private>", "[NOEXPORT]", "[PRIVATE]", "[NOMEM]")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            rows.append(row)
    return rows


def _already_ingested(conn, observation_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM observations WHERE detail_json LIKE ? LIMIT 1",
        (f'%"observationId": "{observation_id}"%',),
    ).fetchone()
    if row:
        return True
    # json.dumps separators may omit the space after colon.
    row = conn.execute(
        "SELECT 1 FROM observations WHERE detail_json LIKE ? LIMIT 1",
        (f'%"observationId":"{observation_id}"%',),
    ).fetchone()
    return row is not None


def is_private_text(text: str) -> bool:
    upper = str(text or "").upper()
    lower = str(text or "").lower()
    return any(marker.lower() in lower for marker in PRIVATE_MARKERS) or "PRIVATE:" in upper


def ingest_rows(conn, rows: list[dict[str, Any]]) -> dict[str, Any]:
    inserted = 0
    skipped_duplicate = 0
    skipped_invalid = 0
    skipped_private = 0
    ids: list[str] = []
    for row in rows:
        observation_id = str(row.get("observationId") or row.get("id") or "").strip()
        text = str(row.get("text") or "").strip()
        if not observation_id or not text:
            skipped_invalid += 1
            continue
        if is_private_text(text):
            skipped_private += 1
            continue
        if _already_ingested(conn, observation_id):
            skipped_duplicate += 1
            continue
        detail = dict(row)
        detail["observationId"] = observation_id
        rid = _insert_observation(
            conn,
            {
                "ts": row.get("ts"),
                "kind": row.get("kind") or "observation",
                "summary": text,
                "tool_name": "channel-a.ingest",
                "detail": detail,
            },
        )
        inserted += 1
        ids.append(f"obs:{rid}")
    conn.commit()
    return {
        "seen": len(rows),
        "inserted": inserted,
        "skippedDuplicate": skipped_duplicate,
        "skippedInvalid": skipped_invalid,
        "skippedPrivate": skipped_private,
        "recordRefs": ids,
    }


def build_pack(conn, *, query: str, limit: int, budget_tokens: int) -> dict[str, Any]:
    ns = argparse.Namespace(
        query=query,
        query_en=None,
        limit=max(1, int(limit)),
        budget_tokens=max(64, int(budget_tokens)),
        trace=False,
        json=True,
        use_graph="off",
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_pack(conn, ns)
    payload = json.loads(buf.getvalue() or "{}")
    context_pack = payload.get("context_pack")
    if not isinstance(context_pack, dict) or context_pack.get("schema") != CONTEXT_PACK_V1_SCHEMA:
        raise RuntimeError("pack did not emit ContextPack v1")
    return context_pack


def write_latest_pack(*, packs_dir: Path, agent: str, context_pack: dict[str, Any]) -> Path:
    target_dir = packs_dir / agent
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "latest.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(context_pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def run(args: argparse.Namespace) -> dict[str, Any]:
    conn = _connect(str(args.db))
    try:
        rows = _read_jsonl(Path(args.input_jsonl)) if args.input_jsonl else []
        ingest = ingest_rows(conn, rows) if rows else {"seen": 0, "inserted": 0, "skippedDuplicate": 0, "skippedInvalid": 0, "recordRefs": []}
        context_pack = build_pack(conn, query=args.query, limit=args.limit, budget_tokens=args.budget_tokens)
        target = write_latest_pack(packs_dir=Path(args.packs_dir), agent=args.agent, context_pack=context_pack)
        return {
            "schema": PRODUCER_RECEIPT_SCHEMA,
            "ok": True,
            "agent": args.agent,
            "packPath": str(target),
            "contextPackSchema": context_pack.get("schema"),
            "ingest": ingest,
            "pack": {"items": len(context_pack.get("items") or []), "budgetTokens": ((context_pack.get("meta") or {}).get("budgetTokens"))},
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Produce per-agent ContextPack v1 files for channel A")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path")
    parser.add_argument("--input-jsonl", help="Optional observation JSONL to ingest idempotently before packing")
    parser.add_argument("--packs-dir", required=True, help="Output root; writes <packs-dir>/<agent>/latest.json")
    parser.add_argument("--agent", default="main", help="Agent namespace")
    parser.add_argument("--query", required=True, help="Pack query")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--budget-tokens", type=int, default=1200)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args(argv)
    receipt = run(args)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
