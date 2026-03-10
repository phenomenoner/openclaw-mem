from __future__ import annotations

import json
import unittest
from pathlib import Path


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


class TestAgentMemorySkillFixtures(unittest.TestCase):
    def test_scenarios_jsonl_is_well_formed(self):
        path = Path(__file__).resolve().parent / "data" / "AGENT_MEMORY_SKILL_SCENARIOS.v0.jsonl"
        self.assertTrue(path.exists(), f"Missing fixture file: {path}")

        allowed = {"recall", "store", "docs_search", "topology_search", "do_nothing"}

        ids = []
        for line_no, row in _iter_jsonl(path):
            self.assertEqual(row.get("version"), "v0", f"Line {line_no}: version must be v0")
            sid = str(row.get("id") or "")
            self.assertTrue(sid, f"Line {line_no}: missing id")
            ids.append(sid)

            prompt = str(row.get("prompt") or "")
            self.assertTrue(prompt, f"{sid}: missing prompt")

            expect = str(row.get("expect") or "")
            self.assertIn(expect, allowed, f"{sid}: expect must be one of {sorted(allowed)}")

            why = str(row.get("why") or "")
            self.assertTrue(why, f"{sid}: missing why")

        self.assertTrue(ids, "Fixture must contain at least 1 scenario")
        self.assertEqual(len(ids), len(set(ids)), "Scenario ids must be unique")

    def test_yaml_and_jsonl_fixture_stay_in_sync_by_id(self):
        """We keep the editable fixture in docs/fixtures (YAML) and a deterministic JSONL mirror for evaluation.

        The project stays dependency-free, so we avoid parsing YAML in tests; instead we assert all ids exist in the YAML file.
        """

        jsonl = Path(__file__).resolve().parent / "data" / "AGENT_MEMORY_SKILL_SCENARIOS.v0.jsonl"
        yaml = Path(__file__).resolve().parents[1] / "docs" / "fixtures" / "agent-memory-skill-scenarios.v0.yaml"

        self.assertTrue(jsonl.exists(), f"Missing JSONL fixture: {jsonl}")
        self.assertTrue(yaml.exists(), f"Missing YAML fixture: {yaml}")

        yaml_text = yaml.read_text(encoding="utf-8")

        missing = []
        for _, row in _iter_jsonl(jsonl):
            sid = str(row.get("id") or "")
            if sid and f"id: {sid}" not in yaml_text:
                missing.append(sid)

        if missing:
            self.fail(f"YAML fixture is missing scenario ids present in JSONL: {missing}")


if __name__ == "__main__":
    unittest.main()
