import os
import unittest

from openclaw_mem.cli import build_parser


class TestDefaultsEnvOverrides(unittest.TestCase):
    def _with_env(self, **patch):
        """Context helper: temporarily set env vars."""
        class _Env:
            def __enter__(self_inner):
                self_inner.old = {}
                for k, v in patch.items():
                    self_inner.old[k] = os.environ.get(k)
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

            def __exit__(self_inner, exc_type, exc, tb):
                for k, old in self_inner.old.items():
                    if old is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = old

        return _Env()

    def test_embed_defaults_can_be_overridden_by_env(self):
        with self._with_env(
            OPENCLAW_MEM_EMBED_MODEL="embed-x",
            OPENCLAW_MEM_OPENAI_BASE_URL="https://example.invalid/v1",
        ):
            p = build_parser()
            args = p.parse_args(["embed"])
            self.assertEqual(args.model, "embed-x")
            self.assertEqual(args.base_url, "https://example.invalid/v1")

    def test_summarize_defaults_can_be_overridden_by_env(self):
        with self._with_env(
            OPENCLAW_MEM_SUMMARY_MODEL="gpt-test",
            OPENCLAW_MEM_OPENAI_BASE_URL="https://example.invalid/v1",
        ):
            p = build_parser()
            args = p.parse_args(["summarize"])
            self.assertEqual(args.model, "gpt-test")
            self.assertEqual(args.base_url, "https://example.invalid/v1")

    def test_rerank_model_default_can_be_overridden_by_env(self):
        with self._with_env(OPENCLAW_MEM_RERANK_MODEL="rerank-test"):
            p = build_parser()
            args = p.parse_args(["hybrid", "q"])
            self.assertEqual(args.rerank_model, "rerank-test")


if __name__ == "__main__":
    unittest.main()
