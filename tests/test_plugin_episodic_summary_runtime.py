import shutil
import subprocess
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "index.ts"
NODE_BEHAVIOR_TEST = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "toolResultSummary.test.mjs"


def test_plugin_uses_shared_tool_result_summary_runtime_helper():
    ts = INDEX_TS.read_text("utf-8")
    assert 'import { buildToolResultSummary } from "./toolResultSummary.js";' in ts
    assert "const resultSummary = buildToolResultSummary(toolName, event.message, redactSensitive, episodesSummaryMaxLength);" in ts


def test_plugin_tool_summary_behavioral_node_tests_pass():
    node = shutil.which("node")
    assert node, "node is required to run openclaw-mem plugin behavioral tests"

    proc = subprocess.run(
        [node, "--test", str(NODE_BEHAVIOR_TEST)],
        cwd=NODE_BEHAVIOR_TEST.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, (
        "node plugin behavioral tests failed\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
