from pathlib import Path
import unittest


class TestOpenClawContextInjectionContract(unittest.TestCase):
    def test_context_injection_contract_mentions_runtime_append_not_memory_markdown(self):
        path = Path(__file__).resolve().parents[1] / "docs" / "specs" / "openclaw-context-injection-contract-v0.md"
        text = path.read_text("utf-8")
        self.assertIn("before_prompt_build", text)
        self.assertIn("appendSystemContext", text)
        self.assertIn("Do **not** use `MEMORY.md` as the transport for per-turn context injection.", text)
        self.assertIn("per-agent exclusion", text)


if __name__ == "__main__":
    unittest.main()
