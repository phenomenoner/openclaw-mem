import json
from pathlib import Path
import unittest

PLUGIN_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "index.ts"
SECRET_GOLDEN = Path(__file__).resolve().parent / "data" / "SECRET_DETECTOR_GOLDEN.v1.json"


class TestPluginEpisodicSpool(unittest.TestCase):
    def test_plugin_has_episodic_spool_schema_and_feature_flag(self):
        ts = PLUGIN_TS.read_text("utf-8")
        self.assertIn('schema: "openclaw-mem.episodes.spool.v0"', ts)
        self.assertIn("const episodesEnabled = episodesCfg.enabled ?? false;", ts)

    def test_plugin_emits_conversation_tool_and_alert_episode_types(self):
        ts = PLUGIN_TS.read_text("utf-8")
        self.assertIn('type: "conversation.user"', ts)
        self.assertIn('conversation.assistant', ts)
        self.assertIn('type: "tool.call"', ts)
        self.assertIn('type: "tool.result"', ts)
        self.assertIn('type: "ops.alert"', ts)

    def test_plugin_has_scope_tag_derivation_and_sanitized_payload_bounding(self):
        ts = PLUGIN_TS.read_text("utf-8")
        self.assertIn("splitLeadingScopeTag", ts)
        self.assertIn("sanitizeEpisodeValue", ts)
        self.assertIn("conversationPayloadCapBytes", ts)

    def test_plugin_supports_agent_exclusion_without_memory_markdown_writeback(self):
        ts = PLUGIN_TS.read_text("utf-8")
        self.assertIn("excludeAgents", ts)
        self.assertIn("isAgentExcluded", ts)
        self.assertIn('if (isAgentExcluded(ctx.agentId, cfg)) return;', ts)
        self.assertIn('if (isAgentExcluded(event?.agentId ?? event?.agent_id, cfg)) return;', ts)
        self.assertNotIn("MEMORY.md", ts)

    def test_plugin_redaction_patterns_cover_shared_secret_golden_corpus(self):
        ts = PLUGIN_TS.read_text("utf-8")
        corpus = json.loads(SECRET_GOLDEN.read_text("utf-8"))
        self.assertEqual(corpus.get("schema"), "openclaw-mem.secret-detector-golden.v1")

        for case in corpus.get("cases", []):
            if case.get("class") != "high_risk":
                continue
            redaction_anchor = case.get("plugin", {}).get("redactionAnchor")
            if redaction_anchor:
                self.assertIn(redaction_anchor, ts, case.get("id", "unknown"))


if __name__ == "__main__":
    unittest.main()
