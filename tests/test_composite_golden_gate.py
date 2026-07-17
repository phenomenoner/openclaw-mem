from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from openclaw_mem.core.config import built_in_defaults, resolve_config
from tools.composite_golden_gate import LIFECYCLE_FIXTURE, run_gate


RECEIPT = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "golden"
    / "RUN-B-T17-composite-gate.json"
)


def _lifecycle_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in LIFECYCLE_FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_lifecycle_fixture_has_twenty_auditable_competing_record_cases() -> None:
    cases = _lifecycle_cases()

    assert len(cases) == 20
    assert Counter(case["category"] for case in cases) == {
        "superseded": 5,
        "preference": 5,
        "state": 5,
        "archive": 5,
    }
    assert all(len(case["records"]) == 3 for case in cases)
    assert all(
        case["expected_key"] in {record["key"] for record in case["records"]}
        for case in cases
    )
    assert sum(
        record["state"] == "soft-archived"
        for case in cases
        for record in case["records"]
    ) == 5
    assert sum(
        record["used_count"] >= 20
        for case in cases
        for record in case["records"]
    ) == 5


def test_composite_default_gate_matches_committed_receipt_and_passes() -> None:
    actual = run_gate()
    baseline = json.loads(RECEIPT.read_text(encoding="utf-8"))

    assert actual == baseline
    assert actual["fixture"] == {
        "total_cases": 50,
        "language_cases": 30,
        "lifecycle_cases": 20,
        "lifecycle_categories": {
            "archive": 5,
            "preference": 5,
            "state": 5,
            "superseded": 5,
        },
    }
    assert actual["profiles"]["relevance"]["recall_at_5"] == 1.0
    assert actual["profiles"]["composite"]["recall_at_5"] == 1.0
    assert actual["profiles"]["relevance"]["mrr"] == pytest.approx(0.74)
    assert actual["profiles"]["composite"]["mrr"] == pytest.approx(0.99)
    assert actual["delta"]["mrr_relative"] >= 0.05
    assert actual["gate_passed"] is True
    assert actual["decision"] == "flip_to_composite"


def test_gate_decision_is_reflected_in_default_with_relevance_override(monkeypatch) -> None:
    assert built_in_defaults()["scoring"]["profile"] == "composite"

    monkeypatch.setenv("OPENCLAW_MEM_SCORING_PROFILE", "relevance")
    assert resolve_config()["scoring"]["profile"] == "relevance"
