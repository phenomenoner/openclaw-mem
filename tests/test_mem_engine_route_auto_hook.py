import json
import shutil
import subprocess
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"
PLUGIN_JSON = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json"
NODE_BEHAVIOR_TEST = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "routeAuto.test.mjs"


def test_route_auto_markers_present_in_ts():
    ts = INDEX_TS.read_text("utf-8")

    assert 'import { runRouteAuto } from "./routeAuto.js";' in ts
    assert "type RouteAutoConfigInput = {" in ts
    assert "routeAuto?: RouteAutoConfigInput;" in ts
    assert "const DEFAULT_ROUTE_AUTO_CONFIG: RouteAutoConfig = {" in ts
    assert 'api.logger.info(`openclaw-mem-engine:routeAuto.receipt ${JSON.stringify(routeAutoResult.receipt)}`);' in ts
    assert 'id: `route-auto:${randomUUID()}`,' in ts


def test_route_auto_schema_contract():
    plugin = json.loads(PLUGIN_JSON.read_text("utf-8"))

    auto_recall = plugin["configSchema"]["properties"]["autoRecall"]["oneOf"][1]["properties"]
    route_auto = auto_recall["routeAuto"]["properties"]

    assert route_auto["enabled"]["default"] is False
    assert route_auto["command"]["default"] == "openclaw-mem"
    assert route_auto["timeoutMs"]["default"] == 1800
    assert route_auto["maxChars"]["default"] == 420
    assert route_auto["maxGraphCandidates"]["default"] == 2
    assert route_auto["maxTranscriptSessions"]["default"] == 2

    ui_hints = plugin["uiHints"]
    assert "autoRecall.routeAuto.enabled" in ui_hints
    assert "autoRecall.routeAuto.timeoutMs" in ui_hints
    assert "autoRecall.routeAuto.maxChars" in ui_hints


def test_route_auto_behavioral_node_tests_pass():
    node = shutil.which("node")
    assert node, "node is required to run mem-engine route-auto behavioral tests"

    proc = subprocess.run(
        [node, "--test", str(NODE_BEHAVIOR_TEST)],
        cwd=NODE_BEHAVIOR_TEST.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, (
        "node route-auto tests failed\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
