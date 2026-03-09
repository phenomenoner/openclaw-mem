import json
import sqlite3
import unittest

from openclaw_mem.cli import _extract_writeback_updates, _normalize_episodic_scope
from openclaw_mem.optimization import _normalize_scope_token as _optimize_scope_norm
from openclaw_mem.scope import normalize_scope_token


class TestScopeNormalization(unittest.TestCase):
    def test_shared_scope_normalizer_slugifies_and_trims(self):
        self.assertEqual(normalize_scope_token("  FinLife MVP  "), "finlife-mvp")
        self.assertEqual(normalize_scope_token("proj/a_b.c:dev"), "proj/a_b.c:dev")
        self.assertEqual(normalize_scope_token("中文 Scope"), "scope")
        self.assertIsNone(normalize_scope_token("///"))
        self.assertIsNone(normalize_scope_token(None))

    def test_cli_and_optimization_use_same_scope_normalization(self):
        raw = "  Team/Project Alpha  "
        self.assertEqual(_normalize_episodic_scope(raw), "team/project-alpha")
        self.assertEqual(_optimize_scope_norm(raw), "team/project-alpha")

    def test_scope_normalizer_nfkc_normalizes_full_width_tokens(self):
        raw = "  Ｔｅａｍ／Ｐｒｏｊｅｃｔ　Ａｌｐｈａ  "
        self.assertEqual(normalize_scope_token(raw), "team/project-alpha")
        self.assertEqual(_normalize_episodic_scope(raw), "team/project-alpha")
        self.assertEqual(_optimize_scope_norm(raw), "team/project-alpha")

    def test_cli_scope_validation_rejects_empty_after_normalization(self):
        with self.assertRaises(ValueError):
            _normalize_episodic_scope("...///")

    def _make_writeback_row(self, *, detail_obj, kind="note"):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE obs (kind TEXT, summary TEXT, summary_en TEXT, detail_json TEXT)"
        )
        conn.execute(
            "INSERT INTO obs(kind, summary, summary_en, detail_json) VALUES (?, ?, ?, ?)",
            (kind, "", "", json.dumps(detail_obj, ensure_ascii=False)),
        )
        row = conn.execute("SELECT kind, summary, summary_en, detail_json FROM obs").fetchone()
        self.assertIsNotNone(row)
        conn.close()
        return row

    def test_writeback_scope_uses_shared_normalization(self):
        row = self._make_writeback_row(
            detail_obj={
                "memory_id": "123e4567-e89b-12d3-a456-426614174000",
                "scope": "  ＦｉｎＬｉｆｅ／ＭＶＰ  ",
            }
        )

        packed = _extract_writeback_updates(row)
        self.assertIsNotNone(packed)
        self.assertEqual(packed["updates"].get("scope"), "finlife/mvp")

    def test_writeback_scope_falls_back_to_normalized_kind(self):
        row = self._make_writeback_row(
            detail_obj={"memory_id": "123e4567-e89b-12d3-a456-426614174000"},
            kind="Decision Note",
        )

        packed = _extract_writeback_updates(row)
        self.assertIsNotNone(packed)
        self.assertEqual(packed["updates"].get("scope"), "decision-note")
