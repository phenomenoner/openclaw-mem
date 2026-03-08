import json
from pathlib import Path

INDEX_TS = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "index.ts"
PLUGIN_JSON = Path(__file__).resolve().parents[1] / "extensions" / "openclaw-mem-engine" / "openclaw.plugin.json"


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

    auto_capture = plugin["configSchema"]["properties"]["autoCapture"]["oneOf"][1]["properties"]

    # Default behavior is unchanged until explicitly enabled.
    assert auto_capture["captureTodo"]["default"] is False

    # Auto-capture bounds/defaults must match index.ts runtime normalization.
    assert auto_capture["maxItemsPerTurn"]["default"] == 2
    assert auto_capture["maxItemsPerTurn"]["minimum"] == 1
    assert auto_capture["maxItemsPerTurn"]["maximum"] == 3

    # Step 3 TODO guardrails defaults + bounds.
    assert auto_capture["maxTodoPerTurn"]["default"] == 1
    assert auto_capture["maxTodoPerTurn"]["minimum"] == 0
    assert auto_capture["maxTodoPerTurn"]["maximum"] == 3

    assert auto_capture["todoDedupeWindowHours"]["default"] == 24
    assert auto_capture["todoDedupeWindowHours"]["minimum"] == 1
    assert auto_capture["todoDedupeWindowHours"]["maximum"] == 168

    assert auto_capture["todoStaleTtlDays"]["default"] == 7
    assert auto_capture["todoStaleTtlDays"]["minimum"] == 1
    assert auto_capture["todoStaleTtlDays"]["maximum"] == 90

    ui_hints = plugin["uiHints"]
    assert "autoCapture.maxTodoPerTurn" in ui_hints
    assert "autoCapture.todoDedupeWindowHours" in ui_hints
    assert "autoCapture.todoStaleTtlDays" in ui_hints
