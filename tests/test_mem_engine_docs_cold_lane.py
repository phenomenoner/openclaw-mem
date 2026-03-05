import json
import unittest
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"
PLUGIN_JSON = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json"
DOCS_COLD_LANE_JS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "docsColdLane.js"


class TestMemEngineDocsColdLane(unittest.TestCase):
    def test_docs_cold_lane_contract_markers_present(self):
        ts = INDEX_TS.read_text("utf-8")

        self.assertIn('name: "memory_docs_ingest"', ts)
        self.assertIn('name: "memory_docs_search"', ts)
        self.assertIn("openclaw-mem-engine:docsColdLane.ingest", ts)
        self.assertIn("openclaw-mem-engine:docsColdLane.search", ts)
        self.assertIn("scopeMappingStrategy", ts)
        self.assertIn("docsColdLane", ts)
        self.assertIn("[docs|operator|", ts)

    def test_docs_cold_lane_schema_defaults(self):
        plugin = json.loads(PLUGIN_JSON.read_text("utf-8"))

        docs_cold_lane = plugin["configSchema"]["properties"]["docsColdLane"]["oneOf"][1]["properties"]

        self.assertIs(docs_cold_lane["enabled"]["default"], False)
        self.assertEqual(docs_cold_lane["sqlitePath"]["default"], "~/.openclaw/memory/openclaw-mem.sqlite")
        self.assertEqual(docs_cold_lane["sourceRoots"]["default"], [])
        self.assertEqual(docs_cold_lane["sourceGlobs"]["default"], ["**/*.md"])
        self.assertEqual(docs_cold_lane["scopeMappingStrategy"]["default"], "repo_prefix")
        self.assertEqual(docs_cold_lane["maxChunkChars"]["default"], 1400)
        self.assertEqual(docs_cold_lane["maxItems"]["default"], 2)

    def test_docs_cold_lane_helper_has_fail_open_guards(self):
        helper = DOCS_COLD_LANE_JS.read_text("utf-8")

        self.assertIn("openclaw-mem_not_found", helper)
        self.assertIn('skipReason: "no_source_roots"', helper)
        self.assertIn('skipReason: "no_matching_markdown"', helper)
        self.assertIn('source_kind: "operator"', helper)
        self.assertIn('trust_tier: "operator"', helper)


if __name__ == "__main__":
    unittest.main()
