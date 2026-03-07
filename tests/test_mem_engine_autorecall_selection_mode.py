import json
import shutil
import subprocess
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"
PLUGIN_JSON = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json"
NODE_BEHAVIOR_TEST = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "tierSelection.test.mjs"


def test_autorecall_selection_mode_markers_present_in_ts():
    ts = INDEX_TS.read_text("utf-8")

    # Config + parser surface
    assert "type AutoRecallSelectionMode = \"tier_first_v1\" | \"tier_quota_v1\";" in ts
    assert "autoRecall.quotas config" in ts
    assert "selectionMode:\n          obj.selectionMode === \"tier_first_v1\" || obj.selectionMode === \"tier_quota_v1\"" in ts

    # Selection implementation now delegates to deterministic helper module.
    assert "from \"./tierSelection.js\"" in ts
    assert "runTierFirstV1({" in ts
    assert "const selectedResult = selectTierQuotaV1({" in ts
    assert "selectionMode === 'tier_quota_v1'" in ts
    assert "quota: selectedResult.quota" in ts
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


def test_autorecall_selection_mode_behavioral_node_tests_pass():
    node = shutil.which("node")
    assert node, "node is required to run mem-engine behavioral tests"

    proc = subprocess.run(
        [node, "--test", str(NODE_BEHAVIOR_TEST)],
        cwd=NODE_BEHAVIOR_TEST.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, (
        "node behavioral tests failed\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
