from pathlib import Path
import unittest

PLUGIN_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "index.ts"


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


if __name__ == "__main__":
    unittest.main()
