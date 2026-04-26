import re
import shutil
import subprocess
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "index.ts"
TOOL_RESULT_SUMMARY_JS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "toolResultSummary.js"
NODE_BEHAVIOR_TEST = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "toolResultSummary.test.mjs"
NODE_PERSIST_E2E_TEST = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem" / "toolResultPersistE2E.test.mjs"


def _extract_tool_result_persist_hook_body(source: str) -> str:
    start = re.search(
        r"api\.on\(\s*[\"']tool_result_persist[\"']\s*,\s*\(event,\s*ctx\)\s*=>\s*\{",
        source,
    )
    assert start, "index.ts must register a tool_result_persist hook"

    i = start.end()
    depth = 1
    while i < len(source) and depth > 0:
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1

    assert depth == 0, "index.ts tool_result_persist hook body must have balanced braces"
    return source[start.end() : i - 1]


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


def test_tool_result_persist_hook_uses_shared_summary_helper_without_local_output_key_fallbacks():
    ts = INDEX_TS.read_text("utf-8")
    hook_body = _extract_tool_result_persist_hook_body(ts)
    assert re.search(
        r"\bconst\s+resultSummary\s*=\s*buildToolResultSummary\s*\(\s*toolName\s*,\s*event\.message\b",
        hook_body,
    ), "tool_result_persist hook must derive resultSummary from buildToolResultSummary"
    assert re.search(
        r"type:\s*[\"']tool\.result[\"'][\s\S]*?summary:\s*resultSummary",
        hook_body,
    ), "tool_result_persist tool.result episode summary must use resultSummary"
    assert "OUTPUT_FIELD_KEYS" not in hook_body, (
        "tool_result_persist hook must not embed output field-key fallback wiring; keep it in toolResultSummary.js"
    )
    assert not re.search(
        r"['\"](?:stdout|stderr|raw_stdout|raw_stderr|tool_output|command_output)['\"]",
        hook_body,
    ), (
        "tool_result_persist hook must not locally define output field-key fallback lists"
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
