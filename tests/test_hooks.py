from __future__ import annotations

import argparse
import io
import json
from unittest.mock import patch

from openclaw_mem.hooks import post_tool_use, session_start


def test_session_start_returns_latest_pack_content(tmp_path):
    pack = tmp_path / "packs" / "main" / "latest.json"
    pack.parent.mkdir(parents=True)
    pack.write_text('{"schema":"openclaw-mem.context-pack.v1"}\n', encoding="utf-8")
    out = session_start(argparse.Namespace(packs_dir=str(tmp_path / "packs"), agent="main", pack_path=None))
    assert out["ok"] is True
    assert out["packFound"] is True
    assert "context-pack" in out["content"]


def test_post_tool_use_appends_jsonl_fail_open_shape(tmp_path):
    out_jsonl = tmp_path / "events.jsonl"
    payload = {"toolUseId": "tool-1", "result": "tool result summary"}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        receipt = post_tool_use(argparse.Namespace(out_jsonl=str(out_jsonl), agent="main", max_chars=2000))
    assert receipt["ok"] is True
    row = json.loads(out_jsonl.read_text(encoding="utf-8").strip())
    assert row["observationId"] == "tool-1"
    assert row["text"] == "tool result summary"
