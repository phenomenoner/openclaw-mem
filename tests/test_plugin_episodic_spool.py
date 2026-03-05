from pathlib import Path

PLUGIN_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "index.ts"


def test_plugin_has_episodic_spool_schema_and_feature_flag():
    ts = PLUGIN_TS.read_text("utf-8")
    assert 'schema: "openclaw-mem.episodes.spool.v0"' in ts
    assert "const episodesEnabled = episodesCfg.enabled ?? false;" in ts


def test_plugin_emits_tool_and_alert_episode_types():
    ts = PLUGIN_TS.read_text("utf-8")
    assert 'type: "tool.call"' in ts
    assert 'type: "tool.result"' in ts
    assert 'type: "ops.alert"' in ts
    assert "withBoundedJson" in ts
