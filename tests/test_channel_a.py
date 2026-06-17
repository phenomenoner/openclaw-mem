from __future__ import annotations

import argparse
import json

from openclaw_mem.channel_a import PRODUCER_RECEIPT_SCHEMA, run
from openclaw_mem.context_pack_v1 import CONTEXT_PACK_V1_SCHEMA


def test_channel_a_ingests_idempotently_and_writes_latest_pack(tmp_path):
    db = tmp_path / "mem.sqlite"
    input_jsonl = tmp_path / "events.jsonl"
    input_jsonl.write_text(
        "\n".join(
            [
                json.dumps({"observationId": "obs-a", "kind": "decision", "text": "Channel A emits per-agent ContextPack files."}),
                json.dumps({"observationId": "obs-a", "kind": "decision", "text": "Duplicate retry should not insert."}),
                json.dumps({"observationId": "obs-b", "kind": "decision", "text": "Harness should read packs/main/latest.json."}),
                json.dumps({"observationId": "obs-private", "kind": "decision", "text": "<private> do not ingest this row"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    packs_dir = tmp_path / "packs"
    args = argparse.Namespace(
        db=str(db),
        input_jsonl=str(input_jsonl),
        packs_dir=str(packs_dir),
        agent="main",
        query="ContextPack harness",
        limit=5,
        budget_tokens=400,
    )
    receipt = run(args)
    assert receipt["schema"] == PRODUCER_RECEIPT_SCHEMA
    assert receipt["ingest"]["inserted"] == 2
    assert receipt["ingest"]["skippedDuplicate"] == 1
    assert receipt["ingest"]["skippedPrivate"] == 1
    pack_path = packs_dir / "main" / "latest.json"
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    assert payload["schema"] == CONTEXT_PACK_V1_SCHEMA
    assert len(payload["items"]) >= 1

    receipt2 = run(args)
    assert receipt2["ingest"]["inserted"] == 0
    assert receipt2["ingest"]["skippedDuplicate"] == 3


def test_channel_a_accepts_utf8_bom_jsonl(tmp_path):
    db = tmp_path / "mem.sqlite"
    input_jsonl = tmp_path / "events-bom.jsonl"
    input_jsonl.write_text(
        json.dumps({"observationId": "obs-bom", "kind": "decision", "text": "BOM JSONL should ingest."}) + "\n",
        encoding="utf-8-sig",
    )
    packs_dir = tmp_path / "packs"
    args = argparse.Namespace(
        db=str(db),
        input_jsonl=str(input_jsonl),
        packs_dir=str(packs_dir),
        agent="main",
        query="BOM JSONL",
        limit=5,
        budget_tokens=400,
    )

    receipt = run(args)

    assert receipt["ingest"]["inserted"] == 1
    assert receipt["ingest"]["skippedInvalid"] == 0
    assert (packs_dir / "main" / "latest.json").exists()


def test_channel_a_rejects_summary_only_rows_as_invalid_schema(tmp_path):
    db = tmp_path / "mem.sqlite"
    input_jsonl = tmp_path / "events-invalid.jsonl"
    input_jsonl.write_text(
        json.dumps({"observationId": "obs-summary", "kind": "decision", "summary": "summary is not a Channel A text field"}) + "\n",
        encoding="utf-8",
    )
    packs_dir = tmp_path / "packs"
    args = argparse.Namespace(
        db=str(db),
        input_jsonl=str(input_jsonl),
        packs_dir=str(packs_dir),
        agent="main",
        query="invalid schema",
        limit=5,
        budget_tokens=400,
    )

    receipt = run(args)

    assert receipt["ingest"]["inserted"] == 0
    assert receipt["ingest"]["skippedInvalid"] == 1
