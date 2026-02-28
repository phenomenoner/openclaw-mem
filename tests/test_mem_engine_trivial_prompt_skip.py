import re
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"

# Keep these patterns aligned with openclaw-mem-engine/index.ts
HEARTBEAT_RE = re.compile(r"^heartbeat(?:_ok)?$", re.I)
SLASH_CMD_RE = re.compile(r"^/[-\w]+")
GREETING_RE = re.compile(
    r"^(?:hi|hello|hey|yo|morning|evening|good\s+(?:morning|afternoon|evening|night)|哈囉|你好|安安|早安|午安|晚安)$",
    re.I,
)
ACK_RE = re.compile(
    r"^(?:ok(?:ay)?|k+|kk+|got\s*it|roger|sure|thanks?|thx|ty|nudge|收到|好|好的|嗯|嗯嗯|了解|知道了|行|沒問題)$",
    re.I,
)

# Match the same unicode bands used by the TS code.
EMOJI_BANDS_RE = re.compile(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]+", re.UNICODE)
PUNCT_RE = re.compile(r"[!！。\.,，\?？…~～]+")


def should_skip_autorecall(prompt: str, trivial_min_chars: int = 8) -> bool:
    text = (prompt or "").strip()
    if not text:
        return True

    compact = re.sub(r"\s+", " ", text).strip()
    lower = compact.lower()

    if HEARTBEAT_RE.fullmatch(lower):
        return True
    if SLASH_CMD_RE.match(compact):
        return True
    if re.search(r"heartbeat", compact, re.I):
        return True

    # Emoji-only (or whitespace) is always trivial.
    if not EMOJI_BANDS_RE.sub("", compact).strip():
        return True

    cleaned = compact
    cleaned = EMOJI_BANDS_RE.sub(" ", cleaned)
    cleaned = PUNCT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Decorations-only (emoji/punct/whitespace) => trivial.
    if not cleaned:
        return True

    if len(cleaned) <= trivial_min_chars:
        if ACK_RE.fullmatch(cleaned) or GREETING_RE.fullmatch(cleaned):
            return True

    return False


def test_trivial_skip_examples():
    assert should_skip_autorecall("好的👌")
    assert should_skip_autorecall("ok👍")
    assert should_skip_autorecall("收到!!")
    assert should_skip_autorecall("hi～")
    assert should_skip_autorecall("？")
    assert should_skip_autorecall("...")
    assert should_skip_autorecall("/sync_snapshot")
    assert should_skip_autorecall("heartbeat_ok")


def test_non_trivial_examples():
    assert not should_skip_autorecall("好的，幫我看 cron 狀態")
    assert not should_skip_autorecall("ok, let's debug the issue")
    assert not should_skip_autorecall("nudge: please check A-fast")


def test_engine_contract_markers_present_in_ts():
    ts = INDEX_TS.read_text("utf-8")

    # Contract markers for the behavior we rely on.
    assert "if (!cleaned) return true;" in ts
    assert "nudge" in ts  # ACK_PATTERN should include it
