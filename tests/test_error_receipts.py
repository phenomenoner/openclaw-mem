from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from typing import Any

import pytest

from openclaw_mem.cli import _emit, _emit_error, _with_error_hints


ERROR_SAMPLES = [
    {"error": "empty query"},
    {"error": "missing --file", "kind": "ingest"},
    {"error": "missing --out"},
    {"error": "missing --repo"},
    {"error": "missing --path"},
    {"error": "missing --seed"},
    {"error": "missing --curated"},
    {"error": "missing --harness-home"},
    {"error": "missing --lancedb"},
    {"error": "missing --table"},
    {"error": "invalid mode"},
    {"error": "invalid since/limit"},
    {"error": "invalid receipt JSON"},
    {"error": "receipt JSON must be an object"},
    {"error": "compact text is required"},
    {"error": "unsupported graph command"},
    {"error": "native qdrant recall not active"},
    {"error": "writeback execution failed", "detail": {"returncode": 1}},
    {"ok": False, "error": "runtime unavailable"},
    {"kind": "outer", "inner": {"ok": False, "error": "nested failure"}},
    {"kind": "outer-list", "items": [{"error": "first"}, {"error": "second"}]},
]


def _error_nodes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [node for item in value for node in _error_nodes(item)]
    if not isinstance(value, dict):
        return []
    found = [value] if value.get("error") is not None else []
    for item in value.values():
        found.extend(_error_nodes(item))
    return found


@pytest.mark.parametrize("sample", ERROR_SAMPLES)
def test_every_error_sample_receives_a_hint(sample: dict[str, Any]) -> None:
    output = StringIO()
    with redirect_stdout(output):
        _emit(sample, True)
    emitted = json.loads(output.getvalue())
    nodes = _error_nodes(emitted)
    assert nodes
    assert all(str(node.get("hint") or "").strip() for node in nodes)


def test_existing_specific_hints_are_preserved_recursively() -> None:
    payload = {
        "error": "outer",
        "hint": "outer recovery",
        "inner": {"error": "inner", "hint": "inner recovery"},
    }
    assert _with_error_hints(payload) == payload


@pytest.mark.parametrize("code", [1, 2, 3])
def test_emit_error_uses_documented_nonzero_codes(code: int) -> None:
    output = StringIO()
    with redirect_stdout(output), pytest.raises(SystemExit) as exc_info:
        _emit_error("failure", "run the recovery command", code, as_json=True)
    assert exc_info.value.code == code
    assert json.loads(output.getvalue()) == {
        "ok": False,
        "error": "failure",
        "hint": "run the recovery command",
    }


def test_emit_error_rejects_undocumented_code() -> None:
    with pytest.raises(ValueError, match="unsupported CLI error exit code"):
        _emit_error("failure", "recover", 4, as_json=True)
