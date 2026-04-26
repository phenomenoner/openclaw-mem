import re
import shutil
import subprocess
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "index.ts"
TOOL_RESULT_SUMMARY_JS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "toolResultSummary.js"
NODE_BEHAVIOR_TEST = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "toolResultSummary.test.mjs"
NODE_PERSIST_E2E_TEST = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "toolResultPersistE2E.test.mjs"


def test_plugin_uses_public_tool_result_summary_runtime_surface():
    ts = INDEX_TS.read_text("utf-8")

    assert re.search(
        r"import\s*\{\s*buildToolResultSummary\s*\}\s*from\s*[\"']\./toolResultSummary\.js[\"'];",
        ts,
    ), "index.ts must import buildToolResultSummary from ./toolResultSummary.js"
    assert re.search(r"\bbuildToolResultSummary\s*\(", ts), "index.ts must call buildToolResultSummary"
    assert not re.search(r"\bfunction\s+buildToolResultSummary\s*\(", ts), (
        "index.ts must not define local buildToolResultSummary; use ./toolResultSummary.js export"
    )
    assert not re.search(r"\b(?:const|let|var)\s+buildToolResultSummary\s*=", ts), (
        "index.ts must not rebind buildToolResultSummary locally"
    )


def test_tool_result_summary_exports_output_field_keys_symbol():
    src = TOOL_RESULT_SUMMARY_JS.read_text("utf-8")
    direct_export = re.search(r"\bexport\s+const\s+OUTPUT_FIELD_KEYS\b", src)
    named_export = re.search(r"\bexport\s*\{[^}]*\bOUTPUT_FIELD_KEYS\b[^}]*\}", src, flags=re.DOTALL)
    assert direct_export or named_export, "toolResultSummary.js must export OUTPUT_FIELD_KEYS"


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


def test_plugin_tool_result_persist_behavioral_node_tests_pass():
    node = shutil.which("node")
    assert node, "node is required to run openclaw-mem plugin behavioral tests"

    proc = subprocess.run(
        [node, "--experimental-strip-types", "--test", str(NODE_PERSIST_E2E_TEST)],
        cwd=NODE_PERSIST_E2E_TEST.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, (
        "node plugin tool_result_persist e2e tests failed\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
