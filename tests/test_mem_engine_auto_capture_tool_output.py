from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"


def test_auto_capture_filters_tool_output_per_candidate_not_whole_message():
    ts = INDEX_TS.read_text("utf-8")

    # Regression guard: OpenClaw sessions may include injected autoRecall receipts / code-fenced metadata
    # alongside real user text (e.g. "TODO:"). We must not drop the whole message just because
    # some parts look like tool output.
    assert "looksLikeToolOutput(userText)" not in ts
    assert "looksLikeSecret(userText)" not in ts
