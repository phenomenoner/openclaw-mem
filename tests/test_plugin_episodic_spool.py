from pathlib import Path

PLUGIN_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "index.ts"


def test_plugin_has_episodic_spool_schema_and_feature_flag():
    ts = PLUGIN_TS.read_text("utf-8")
    assert 'schema: "openclaw-mem.episodes.spool.v0"' in ts
    assert "const episodesEnabled = episodesCfg.enabled ?? false;" in ts


def test_plugin_emits_conversation_tool_and_alert_episode_types():
    ts = PLUGIN_TS.read_text("utf-8")
    assert 'type: "conversation.user"' in ts
    assert 'conversation.assistant' in ts
    assert 'type: "tool.call"' in ts
    assert 'type: "tool.result"' in ts
    assert 'type: "ops.alert"' in ts


def test_plugin_has_scope_tag_derivation_and_sanitized_payload_bounding():
    ts = PLUGIN_TS.read_text("utf-8")
    assert "splitLeadingScopeTag" in ts
    assert "sanitizeEpisodeValue" in ts
    assert "conversationPayloadCapBytes" in ts
