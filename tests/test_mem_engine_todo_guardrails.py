import json
import re
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"
PLUGIN_JSON = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json"


def _eval_numeric_expr(expr: str) -> int:
    compact = expr.strip()
    if not re.fullmatch(r"[0-9+\-*/ ().]+", compact):
        raise AssertionError(f"unsupported numeric expression: {expr}")
    value = eval(compact, {"__builtins__": {}}, {})  # noqa: S307 - restricted grammar above
    if not isinstance(value, (int, float)):
        raise AssertionError(f"expression did not evaluate to a number: {expr}")
    if int(value) != value:
        raise AssertionError(f"expression must resolve to an integer: {expr}")
    return int(value)


def _extract_ts_const_int(ts: str, name: str) -> int:
    match = re.search(rf"const\s+{re.escape(name)}\s*=\s*([^;]+);", ts)
    assert match, f"missing TS const: {name}"
    return _eval_numeric_expr(match.group(1))


def _extract_ts_object_scalar(obj_body: str, key: str):
    match = re.search(rf"{re.escape(key)}\s*:\s*([^,\n]+),", obj_body)
    assert match, f"missing object key in DEFAULT_AUTO_CAPTURE_CONFIG: {key}"
    token = match.group(1).strip()
    if token == "true":
        return True
    if token == "false":
        return False
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    raise AssertionError(f"unsupported scalar token for {key}: {token}")


def _extract_default_auto_capture(ts: str) -> dict:
    match = re.search(
        r"const\s+DEFAULT_AUTO_CAPTURE_CONFIG:\s*AutoCaptureConfig\s*=\s*\{(?P<body>.*?)\n\};",
        ts,
        flags=re.S,
    )
    assert match, "missing DEFAULT_AUTO_CAPTURE_CONFIG"
    body = match.group("body")
    keys = (
        "maxItemsPerTurn",
        "maxCharsPerItem",
        "captureTodo",
        "maxTodoPerTurn",
        "todoDedupeWindowHours",
        "todoStaleTtlDays",
    )
    return {key: _extract_ts_object_scalar(body, key) for key in keys}


def test_todo_guardrail_contract_markers_and_schema_defaults():
    ts = INDEX_TS.read_text("utf-8")
    plugin = json.loads(PLUGIN_JSON.read_text("utf-8"))

    # Contract markers in TS implementation.
    assert "openclaw-mem-engine:todoGuardrail" in ts
    assert "listRecentTodosByScope" in ts
    assert "listRecentTodosByScope_failed" in ts
    assert "isTodoWithinDedupeWindow" in ts
    assert "isTodoStale(" in ts
    assert "SUBSTRING_NEAR_DUPLICATE_MIN_CHARS = 30" in ts
    assert '"maxTodoPerTurn"' in ts
    assert '"todoDedupeWindowHours"' in ts
    assert '"todoStaleTtlDays"' in ts

    auto_capture_defaults = _extract_default_auto_capture(ts)
    max_items_per_turn = _extract_ts_const_int(ts, "AUTO_CAPTURE_MAX_ITEMS_PER_TURN")
    max_chars_per_item = _extract_ts_const_int(ts, "AUTO_CAPTURE_MAX_CHARS_PER_ITEM")
    max_todo_per_turn = _extract_ts_const_int(ts, "AUTO_CAPTURE_MAX_TODO_PER_TURN")
    max_todo_dedupe_window_hours = _extract_ts_const_int(ts, "AUTO_CAPTURE_MAX_TODO_DEDUPE_WINDOW_HOURS")
    max_todo_stale_ttl_days = _extract_ts_const_int(ts, "AUTO_CAPTURE_MAX_TODO_STALE_TTL_DAYS")

    auto_capture = plugin["configSchema"]["properties"]["autoCapture"]["oneOf"][1]["properties"]

    # Default behavior is unchanged until explicitly enabled.
    assert auto_capture["captureTodo"]["default"] == auto_capture_defaults["captureTodo"]

    # Auto-capture bounds/defaults must match index.ts runtime normalization.
    assert auto_capture["maxItemsPerTurn"]["default"] == auto_capture_defaults["maxItemsPerTurn"]
    assert auto_capture["maxItemsPerTurn"]["minimum"] == 1
    assert auto_capture["maxItemsPerTurn"]["maximum"] == max_items_per_turn

    assert auto_capture["maxCharsPerItem"]["default"] == auto_capture_defaults["maxCharsPerItem"]
    assert auto_capture["maxCharsPerItem"]["minimum"] == 60
    assert auto_capture["maxCharsPerItem"]["maximum"] == max_chars_per_item

    # Step 3 TODO guardrails defaults + bounds.
    assert auto_capture["maxTodoPerTurn"]["default"] == auto_capture_defaults["maxTodoPerTurn"]
    assert auto_capture["maxTodoPerTurn"]["minimum"] == 0
    assert auto_capture["maxTodoPerTurn"]["maximum"] == max_todo_per_turn

    assert (
        auto_capture["todoDedupeWindowHours"]["default"]
        == auto_capture_defaults["todoDedupeWindowHours"]
    )
    assert auto_capture["todoDedupeWindowHours"]["minimum"] == 1
    assert auto_capture["todoDedupeWindowHours"]["maximum"] == max_todo_dedupe_window_hours

    assert auto_capture["todoStaleTtlDays"]["default"] == auto_capture_defaults["todoStaleTtlDays"]
    assert auto_capture["todoStaleTtlDays"]["minimum"] == 1
    assert auto_capture["todoStaleTtlDays"]["maximum"] == max_todo_stale_ttl_days

    ui_hints = plugin["uiHints"]
    assert "autoCapture.maxTodoPerTurn" in ui_hints
    assert "autoCapture.todoDedupeWindowHours" in ui_hints
    assert "autoCapture.todoStaleTtlDays" in ui_hints
