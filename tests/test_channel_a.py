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
