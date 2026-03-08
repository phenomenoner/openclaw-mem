import unittest

from openclaw_mem.cli import _normalize_episodic_scope
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
