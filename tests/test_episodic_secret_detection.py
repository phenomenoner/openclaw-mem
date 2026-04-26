import json
from pathlib import Path

from openclaw_mem.cli import _episodic_guard_text_fragments, _looks_like_secret

_FIXTURE_PATH = Path(__file__).resolve().parent / "data" / "SECRET_DETECTOR_GOLDEN.v1.json"


def _load_golden_cases() -> dict:
    payload = json.loads(_FIXTURE_PATH.read_text("utf-8"))
    assert payload.get("schema") == "openclaw-mem.secret-detector-golden.v1"
    return payload


def test_secret_detector_matches_shared_golden_corpus():
    corpus = _load_golden_cases()

    for case in corpus["cases"]:
        expect_secret_like = bool(case.get("episodic", {}).get("expectSecretLike"))
        assert _looks_like_secret(case["sample"]) is expect_secret_like, case["id"]


def test_guard_error_message_does_not_echo_high_risk_values_from_golden_corpus():
    corpus = _load_golden_cases()
    expected_fragment = corpus.get("receipt_expectations", {}).get("episodicGuard", {}).get("expectErrorContains", "")

    high_risk_cases = [c for c in corpus["cases"] if c.get("class") == "high_risk"]
    for case in high_risk_cases:
        payload = json.dumps({"auth": case["sample"]}, ensure_ascii=False)

        try:
            _episodic_guard_text_fragments("safe summary", payload, None, allow_tool_output=False)
        except ValueError as exc:
            msg = str(exc)
            if expected_fragment:
                assert expected_fragment in msg
            for needle in case.get("episodic", {}).get("leakNeedles", []):
                assert needle not in msg
        else:
            raise AssertionError(f"expected ValueError for secret-like payload: {case['id']}")
