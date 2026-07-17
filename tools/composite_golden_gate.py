#!/usr/bin/env python3
"""Evaluate relevance vs composite scoring on the complete golden recall set."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openclaw_mem.core.db import _connect
from openclaw_mem.core.records import _insert_observation
from openclaw_mem.core.search import lexical_search_with_receipt


REPO_ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "golden_queries_zh.jsonl"
LIFECYCLE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "golden_lifecycle_queries.jsonl"
REQUIRED_RELATIVE_IMPROVEMENT = 0.05


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _timestamp(now: datetime, age_days: float) -> str:
    value = now - timedelta(days=max(0.0, float(age_days)))
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_fixture_db(now: datetime):
    conn = _connect(":memory:")
    expected: dict[str, int] = {}
    cases: list[dict[str, Any]] = []

    for case in _read_jsonl(LANGUAGE_FIXTURE):
        case_id = str(case["key"])
        expected[case_id] = _insert_observation(
            conn,
            {
                # The language fixture measures lexical recovery, so arbitrary
                # row order must not introduce a recency preference.
                "ts": _timestamp(now, 30),
                "kind": "golden",
                "summary": case["summary"],
                "tool_name": case_id,
                "detail": {"golden_key": case_id},
            },
        )
        cases.append(
            {
                "case_id": case_id,
                "category": f"language:{case['category']}",
                "query": case["query"],
            }
        )

    for case in _read_jsonl(LIFECYCLE_FIXTURE):
        case_id = str(case["case_id"])
        expected_key = str(case["expected_key"])
        records = list(case.get("records") or [])
        # The JSONL is old-to-current for reviewability.  Insert in reverse to
        # model a history backfill where superseded rows arrive after the
        # already-correct current record; raw relevance then cannot use rowid
        # recency as a proxy for lifecycle truth.
        for record in reversed(records):
            key = str(record["key"])
            detail = {
                "golden_key": key,
                "answer": record.get("answer"),
                "importance": {"label": str(record.get("importance") or "unknown")},
                "lifecycle": {
                    "state": str(record.get("state") or "active"),
                    "used_count": max(0, int(record.get("used_count") or 0)),
                },
            }
            searchable = str(case["query"])
            if key != expected_key:
                # Superseded memories often contain repeated topic wording and
                # therefore outrank the concise current answer on BM25 alone.
                searchable = f"{searchable} {searchable}"
            row_id = _insert_observation(
                conn,
                {
                    "ts": _timestamp(now, float(record.get("age_days") or 0.0)),
                    "kind": str(case.get("kind") or "note"),
                    "summary": searchable,
                    "tool_name": key,
                    "detail": detail,
                },
            )
            if key == expected_key:
                expected[case_id] = row_id
        if case_id not in expected:
            raise ValueError(f"missing expected record {expected_key!r} for {case_id}")
        cases.append(
            {
                "case_id": case_id,
                "category": f"lifecycle:{case['category']}",
                "query": case["query"],
            }
        )

    conn.commit()
    return conn, cases, expected


def _evaluate_profile(
    conn,
    cases: list[dict[str, Any]],
    expected: dict[str, int],
    profile: str,
) -> dict[str, Any]:
    reciprocal_rank = 0.0
    hits = 0
    failures: list[dict[str, Any]] = []
    ranks_by_category: dict[str, list[int | None]] = {}
    for case in cases:
        receipt = lexical_search_with_receipt(
            conn,
            str(case["query"]),
            limit=5,
            scoring_profile=profile,
        )
        ids = [int(item["id"]) for item in receipt["results"]]
        target = expected[str(case["case_id"])]
        rank = ids.index(target) + 1 if target in ids else None
        ranks_by_category.setdefault(str(case["category"]), []).append(rank)
        if rank is None:
            failures.append(
                {
                    "case_id": case["case_id"],
                    "query": case["query"],
                    "result_ids": ids,
                }
            )
            continue
        hits += 1
        reciprocal_rank += 1.0 / rank

    count = len(cases)
    return {
        "profile": profile,
        "cases": count,
        "recall_at_5": hits / count if count else 0.0,
        "mrr": reciprocal_rank / count if count else 0.0,
        "misses": len(failures),
        "failures": failures,
        "mean_rank_by_category": {
            category: (
                sum(rank for rank in ranks if rank is not None) / len(ranks)
                if ranks and all(rank is not None for rank in ranks)
                else None
            )
            for category, ranks in sorted(ranks_by_category.items())
        },
    }


def _relative_delta(candidate: float, baseline: float) -> float:
    if baseline == 0.0:
        return 0.0 if candidate == 0.0 else 1.0
    return (candidate - baseline) / baseline


def run_gate() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    conn, cases, expected = _build_fixture_db(now)
    try:
        relevance = _evaluate_profile(conn, cases, expected, "relevance")
        composite = _evaluate_profile(conn, cases, expected, "composite")
    finally:
        conn.close()

    recall_delta = composite["recall_at_5"] - relevance["recall_at_5"]
    mrr_delta = composite["mrr"] - relevance["mrr"]
    recall_relative = _relative_delta(composite["recall_at_5"], relevance["recall_at_5"])
    mrr_relative = _relative_delta(composite["mrr"], relevance["mrr"])
    non_regressing = (
        composite["recall_at_5"] >= relevance["recall_at_5"]
        and composite["mrr"] >= relevance["mrr"]
    )
    material_improvement = max(recall_relative, mrr_relative) >= REQUIRED_RELATIVE_IMPROVEMENT
    passed = bool(non_regressing and material_improvement)
    lifecycle_categories = Counter(
        str(case["category"]).split(":", 1)[1]
        for case in cases
        if str(case["category"]).startswith("lifecycle:")
    )
    return {
        "kind": "openclaw-mem.golden.composite-default-gate.v1",
        "fixture": {
            "total_cases": len(cases),
            "language_cases": sum(
                str(case["category"]).startswith("language:") for case in cases
            ),
            "lifecycle_cases": sum(
                str(case["category"]).startswith("lifecycle:") for case in cases
            ),
            "lifecycle_categories": dict(sorted(lifecycle_categories.items())),
        },
        "profiles": {"relevance": relevance, "composite": composite},
        "delta": {
            "recall_at_5_absolute": recall_delta,
            "recall_at_5_relative": recall_relative,
            "mrr_absolute": mrr_delta,
            "mrr_relative": mrr_relative,
        },
        "criteria": {
            "both_metrics_non_regressing": True,
            "one_metric_relative_improvement_at_least": REQUIRED_RELATIVE_IMPROVEMENT,
        },
        "gate_passed": passed,
        "decision": "flip_to_composite" if passed else "keep_relevance",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the JSON receipt to this path")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON")
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="Return exit 1 when the default-flip gate does not pass",
    )
    args = parser.parse_args(argv)
    receipt = run_gate()
    rendered = json.dumps(
        receipt,
        ensure_ascii=False,
        indent=None if args.json else 2,
        sort_keys=True,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if args.require_pass and not receipt["gate_passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
