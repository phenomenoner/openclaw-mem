import json
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"
PLUGIN_JSON = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json"


def test_autorecall_selection_mode_markers_present_in_ts():
    ts = INDEX_TS.read_text("utf-8")

    # Config + parser surface
    assert "type AutoRecallSelectionMode = \"tier_first_v1\" | \"tier_quota_v1\";" in ts
    assert "autoRecall.quotas config" in ts
    assert "selectionMode:\n          obj.selectionMode === \"tier_first_v1\" || obj.selectionMode === \"tier_quota_v1\"" in ts

    # Selection implementation + receipt explainability
    assert "function selectTierQuotaV1(" in ts
    assert "if (selectionMode === 'tier_first_v1') {" in ts
    assert "if (selected.length >= input.limit) {\n        rejected.push('budget_cap');\n        break;\n      }" in ts
    assert "selectionMode === 'tier_quota_v1'" in ts
    assert "quota: input.quota," in ts
    assert "selection: {\n                mode: autoRecallCfg.selectionMode," in ts


def test_autorecall_selection_mode_schema_contract():
    plugin = json.loads(PLUGIN_JSON.read_text("utf-8"))

    auto_recall = plugin["configSchema"]["properties"]["autoRecall"]["oneOf"][1]["properties"]
    quotas = auto_recall["quotas"]["properties"]

    assert auto_recall["selectionMode"]["default"] == "tier_first_v1"
    assert auto_recall["selectionMode"]["enum"] == ["tier_first_v1", "tier_quota_v1"]

    assert quotas["mustMax"]["default"] == 2
    assert quotas["niceMin"]["default"] == 2
    assert quotas["unknownMax"]["default"] == 1

    ui_hints = plugin["uiHints"]
    assert "autoRecall.selectionMode" in ui_hints
    assert "autoRecall.quotas.mustMax" in ui_hints
    assert "autoRecall.quotas.niceMin" in ui_hints
    assert "autoRecall.quotas.unknownMax" in ui_hints
