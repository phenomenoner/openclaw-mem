from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from openclaw_mem.context_pack_v1 import CONTEXT_PACK_V1_SCHEMA


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "docs" / "fixtures" / "context-pack-v1-compat"


REQUIRED_TOP_LEVEL = {"schema", "meta", "bundle_text", "items", "notes"}
REQUIRED_META = {"ts", "query", "scope", "budgetTokens", "maxItems"}
REQUIRED_ITEM = {"recordRef", "layer", "type", "importance", "trust", "text", "citations"}


def _load_json(name: str) -> dict[str, Any]:
    path = FIXTURE_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _estimate_tokens(text: str) -> int:
    # Compatibility guard only: keep this intentionally simple and deterministic.
    return max(1, (len(text or "") + 3) // 4)


def _validate_minimal_context_pack(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL - set(payload))
    if missing:
        errors.append(f"missing top-level fields: {missing}")
        return errors

    if payload.get("schema") != CONTEXT_PACK_V1_SCHEMA:
        errors.append(f"unexpected schema: {payload.get('schema')!r}")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        errors.append("meta must be an object")
    else:
        meta_missing = sorted(REQUIRED_META - set(meta))
        if meta_missing:
            errors.append(f"missing meta fields: {meta_missing}")
        if not isinstance(meta.get("budgetTokens"), int) or int(meta.get("budgetTokens") or 0) <= 0:
            errors.append("meta.budgetTokens must be a positive integer")
        if not isinstance(meta.get("maxItems"), int) or int(meta.get("maxItems") or 0) <= 0:
            errors.append("meta.maxItems must be a positive integer")

    if not isinstance(payload.get("bundle_text"), str) or not payload.get("bundle_text"):
        errors.append("bundle_text must be a non-empty string")

    items = payload.get("items")
    if not isinstance(items, list):
        errors.append("items must be an array")
    else:
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"items[{index}] must be an object")
                continue
            item_missing = sorted(REQUIRED_ITEM - set(item))
            if item_missing:
                errors.append(f"items[{index}] missing fields: {item_missing}")
            citations = item.get("citations")
            if not isinstance(citations, dict) or not citations.get("recordRef"):
                errors.append(f"items[{index}].citations.recordRef is required")

    notes = payload.get("notes")
    if not isinstance(notes, dict) or not isinstance(notes.get("how_to_use"), list):
        errors.append("notes.how_to_use must be an array")

    return errors


class TestContextPackV1CompatFixtures(unittest.TestCase):
    def test_fixture_directory_exists(self):
        self.assertTrue(FIXTURE_DIR.exists(), f"Missing fixture directory: {FIXTURE_DIR}")

    def test_legal_pack_uses_canonical_schema_and_required_fields(self):
        payload = _load_json("legal-pack.json")
        self.assertEqual(_validate_minimal_context_pack(payload), [])
        self.assertEqual(payload["schema"], CONTEXT_PACK_V1_SCHEMA)
        self.assertEqual(payload["items"][0]["recordRef"], payload["items"][0]["citations"]["recordRef"])

    def test_missing_field_pack_is_invalid(self):
        payload = _load_json("missing-field-pack.json")
        errors = _validate_minimal_context_pack(payload)
        self.assertTrue(any("bundle_text" in error for error in errors), errors)

    def test_oversized_pack_is_structurally_valid_but_budget_invalid(self):
        payload = _load_json("oversized-pack.json")
        self.assertEqual(_validate_minimal_context_pack(payload), [])
        budget = int(payload["meta"]["budgetTokens"])
        estimated = _estimate_tokens(payload["bundle_text"])
        self.assertGreater(estimated, budget)

    def test_ingest_idempotency_fixture_declares_duplicate_behavior(self):
        path = FIXTURE_DIR / "ingest-idempotency.jsonl"
        seen: set[str] = set()
        inserts_by_id: dict[str, list[bool]] = {}
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                self.assertEqual(row.get("schema"), "openclaw-mem.ingest-observation-fixture.v1")
                obs_id = str(row.get("observationId") or "")
                self.assertTrue(obs_id, f"line {line_no}: missing observationId")
                expect_insert = bool(row.get("expectEffectiveInsert"))
                self.assertEqual(expect_insert, obs_id not in seen, f"line {line_no}: idempotency expectation mismatch")
                seen.add(obs_id)
                inserts_by_id.setdefault(obs_id, []).append(expect_insert)

        self.assertIn("obs-idem-001", inserts_by_id)
        self.assertEqual(inserts_by_id["obs-idem-001"], [True, False])


if __name__ == "__main__":
    unittest.main()
