from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProactivePackDocsTest(unittest.TestCase):
    def test_public_docs_reference_proactive_pack(self):
        targets = [
            ROOT / "README.md",
            ROOT / "docs" / "about.md",
            ROOT / "docs" / "install-modes.md",
            ROOT / "docs" / "proactive-pack.md",
            ROOT / "docs" / "mem-engine.md",
            ROOT / "extensions" / "openclaw-mem-engine" / "README.md",
        ]
        for path in targets:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Proactive Pack", text, path.as_posix())

    def test_plugin_schema_labels_runtime_recall_truthfully(self):
        plugin = json.loads((ROOT / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json").read_text(encoding="utf-8"))
        ui = plugin["uiHints"]
        self.assertIn("Proactive Pack", plugin["description"])
        self.assertEqual(ui["autoRecall.enabled"]["label"], "Proactive Pack (Auto Recall)")
        self.assertIn("pre-reply recall", ui["autoRecall.enabled"]["help"])


if __name__ == "__main__":
    unittest.main()
