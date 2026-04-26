import re
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


def test_auto_capture_secret_filters_and_receipt_surface_stay_bounded():
    ts = INDEX_TS.read_text("utf-8")

    # Guardrail expansion: include common high-risk token families.
    assert "sk-proj-" in ts
    assert "github_pat_" in ts
    assert "aws[_-]?secret[_-]?access[_-]?key" in ts
    assert "Authorization:\\s*Bearer" in ts

    # Candidate-level secret skip remains explicit and count-based.
    assert "if (looksLikeSecret(candidate))" in ts
    assert "filteredOut.secrets_like += 1" in ts

    receipt_fn = re.search(
        r"function buildAutoCaptureLifecycleReceipt\([\s\S]*?\n}\n\nfunction renderAutoRecallReceiptComment",
        ts,
    )
    assert receipt_fn, "missing buildAutoCaptureLifecycleReceipt function"
    block = receipt_fn.group(0)

    # Receipt stays bounded (aggregate counters, no raw candidate text fields).
    assert "schema: \"openclaw-mem-engine.autoCapture.receipt.v1\"" in block
    assert "candidateExtractionCount" in block
    assert "secrets_like" in block
    assert "storedCount" in block
    assert "text:" not in block
