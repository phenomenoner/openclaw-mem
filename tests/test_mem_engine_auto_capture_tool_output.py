from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"


def test_auto_capture_filters_tool_output_per_candidate_not_whole_message():
    ts = INDEX_TS.read_text("utf-8")

    # Regression guard: OpenClaw sessions may include injected autoRecall receipts / code-fenced metadata
    # alongside real user text (e.g. "TODO:"). We must not drop the whole message just because
    # some parts look like tool output.
    assert "looksLikeToolOutput(userText)" not in ts
    assert "looksLikeSecret(userText)" not in ts


def test_auto_capture_strips_injected_auto_recall_artifacts_and_propagates_scope():
    ts = INDEX_TS.read_text("utf-8")

    # Regression guard: injected blocks like <relevant-memories> must not become capture candidates.
    assert "stripAutoInjectedArtifacts" in ts
    assert "<relevant-memories>" in ts

    # Scope tags may be on their own line. Ensure message-level scope can flow to per-line candidates.
    assert "const messageScope = extractScopeFromText(userText)" in ts
