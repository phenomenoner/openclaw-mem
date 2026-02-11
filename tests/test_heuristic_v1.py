from __future__ import annotations

import json
import unittest
from pathlib import Path

from openclaw_mem.heuristic_v1 import grade_observation


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except Exception as e:
                raise AssertionError(f"Invalid JSON on line {i}: {e}")


class TestHeuristicV1(unittest.TestCase):
    def test_heuristic_testcases_jsonl(self):
        path = Path(__file__).resolve().parent / "data" / "HEURISTIC_TESTCASES.jsonl"
        self.assertTrue(path.exists(), f"Missing testcases file: {path}")

        total = 0
        failed = 0
        failures = []

        eps = 1e-9
        for line_no, tc in _iter_jsonl(path):
            total += 1
            tc_id = tc.get("id") or f"line:{line_no}"
            obs = tc.get("obs") or {}
            expect = tc.get("expect") or {}

            r = grade_observation(obs)

            score_min = float(expect.get("score_min", 0.0))
            score_max = float(expect.get("score_max", 1.0))
            exp_label = str(expect.get("label") or "")

            ok = True
            if not (score_min - eps <= r.score <= score_max + eps):
                ok = False
            if exp_label and r.label != exp_label:
                ok = False

            if not ok:
                failed += 1
                failures.append(
                    "\n".join(
                        [
                            f"FAIL {tc_id}",
                            f"  expected: score in [{score_min:.2f}, {score_max:.2f}], label={exp_label}",
                            f"  got:      score={r.score:.2f}, label={r.label}",
                            f"  text:     {(obs.get('tool_name') or '')}: {(obs.get('summary') or '')}",
                            f"  reasons:  {list(r.reasons)}",
                            f"  penalties:{list(r.penalties)}",
                        ]
                    )
                )

        if failures:
            self.fail("\n\n".join(failures) + f"\n\nRESULT: {failed}/{total} failed")


if __name__ == "__main__":
    unittest.main()
