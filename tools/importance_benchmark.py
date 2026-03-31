from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from openclaw_mem.heuristic_v1 import grade_observation


LABELS = ("must_remember", "nice_to_have", "ignore", "unknown")


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSON on line {line_no} of {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _summary_preview(text: str, limit: int = 120) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_benchmark(input_path: Path) -> dict[str, Any]:
    totals = Counter()
    expected_counts = Counter()
    predicted_counts = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    mismatches: list[dict[str, Any]] = []
    ignore_spot_check: list[dict[str, Any]] = []

    predicted_must = 0
    predicted_must_correct = 0
    predicted_ignore = 0
    predicted_ignore_correct = 0

    for line_no, tc in _iter_jsonl(input_path):
        tc_id = tc.get("id") or f"line:{line_no}"
        obs = tc.get("obs") or {}
        expect = tc.get("expect") or {}
        expected_label = str(expect.get("label") or "unknown")

        result = grade_observation(obs)
        predicted_label = result.label

        totals["cases"] += 1
        expected_counts[expected_label] += 1
        predicted_counts[predicted_label] += 1
        confusion[expected_label][predicted_label] += 1

        if expected_label == predicted_label:
            totals["label_matches"] += 1
        else:
            mismatches.append(
                {
                    "id": tc_id,
                    "expected_label": expected_label,
                    "predicted_label": predicted_label,
                    "score": round(float(result.score), 4),
                    "summary_preview": _summary_preview(obs.get("summary") or ""),
                    "rationale": result.rationale,
                    "reasons": list(result.reasons),
                    "penalties": list(result.penalties),
                }
            )

        if predicted_label == "must_remember":
            predicted_must += 1
            if expected_label == "must_remember":
                predicted_must_correct += 1

        if predicted_label == "ignore":
            predicted_ignore += 1
            item = {
                "id": tc_id,
                "expected_label": expected_label,
                "predicted_label": predicted_label,
                "score": round(float(result.score), 4),
                "summary_preview": _summary_preview(obs.get("summary") or ""),
                "notes": tc.get("notes") or "",
            }
            ignore_spot_check.append(item)
            if expected_label == "ignore":
                predicted_ignore_correct += 1

    total_cases = totals["cases"]
    label_agreement = round((totals["label_matches"] / total_cases), 4) if total_cases else 0.0
    must_precision = round((predicted_must_correct / predicted_must), 4) if predicted_must else None
    ignore_precision = round((predicted_ignore_correct / predicted_ignore), 4) if predicted_ignore else None

    return {
        "kind": "openclaw-mem.importance-benchmark.v1",
        "benchmark": {
            "name": "importance_grading_mvp_v1",
            "fixture_path": str(input_path),
            "fixture_sha256": _sha256(input_path),
            "total_cases": total_cases,
            "before_operator_labels": {label: int(expected_counts.get(label, 0)) for label in LABELS},
            "after_heuristic_v1": {label: int(predicted_counts.get(label, 0)) for label in LABELS},
            "label_agreement": label_agreement,
            "mismatch_count": len(mismatches),
            "confusion_matrix": {
                label: {inner: int(confusion[label].get(inner, 0)) for inner in LABELS}
                for label in LABELS
            },
        },
        "metrics": {
            "must_remember_precision": must_precision,
            "must_remember_predicted": predicted_must,
            "must_remember_true_positive": predicted_must_correct,
            "ignore_precision": ignore_precision,
            "ignore_predicted": predicted_ignore,
            "ignore_true_positive": predicted_ignore_correct,
        },
        "ignore_spot_check": {
            "count": len(ignore_spot_check),
            "items": ignore_spot_check[:10],
        },
        "mismatches": mismatches[:20],
        "verdict": {
            "ready_for_mvp_closure": len(mismatches) == 0 and must_precision is not None,
            "notes": [
                "This is a small operator-curated regression benchmark, not a broad external quality claim.",
                "Before = operator-labeled fixture; after = current heuristic-v1 predictions.",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the importance-grading benchmark fixture.")
    parser.add_argument("--input", default="benchmarks/importance_grading_set.v1.jsonl", help="Input benchmark JSONL")
    parser.add_argument("--output", default="-", help="Output JSON path, or - for stdout")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input benchmark not found: {input_path}")

    result = build_benchmark(input_path)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"

    if args.output == "-":
        print(text, end="")
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
