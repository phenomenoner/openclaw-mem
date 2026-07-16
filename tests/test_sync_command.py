from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from openclaw_mem.cli import (
    _connect,
    _run_handler_with_deprecation,
    build_parser,
    cmd_sync,
)


def _run(conn, argv: list[str]) -> dict:
    args = build_parser().parse_args([*argv, "--json"])
    args.json = True
    output = io.StringIO()
    with redirect_stdout(output):
        args.func(conn, args)
    return json.loads(output.getvalue())


@pytest.mark.parametrize("verb", ("status", "run", "init"))
@pytest.mark.parametrize("backend", ("lancedb", "service", "qdrant"))
def test_every_sync_verb_backend_combination_emits_stable_wrapper(
    tmp_path: Path, verb: str, backend: str
) -> None:
    conn = _connect(":memory:")
    argv = ["sync", verb, "--backend", backend]
    if backend == "service":
        argv.extend(["--harness-home", str(tmp_path / "harness")])
    with patch("openclaw_mem.cli.importlib.util.find_spec", return_value=None):
        out = _run(conn, argv)
    assert out["kind"] == f"openclaw-mem.sync.{verb}.v1"
    assert out["verb"] == verb
    assert out["backend"] == backend
    assert isinstance(out["ok"], bool)
    assert isinstance(out["writes_performed"], bool)
    assert "inner" in out
    conn.close()


def test_service_init_and_status_cover_both_readiness_files(tmp_path: Path) -> None:
    conn = _connect(":memory:")
    home = tmp_path / "harness"
    initialized = _run(
        conn,
        ["sync", "init", "--backend", "service", "--harness-home", str(home)],
    )
    assert initialized["ok"] is True
    assert initialized["writes_performed"] is True
    assert [item["source"] for item in initialized["inner"]] == [
        "service-store init",
        "writeback-store init",
    ]
    assert (home / "memory" / "openclaw-mem-service-store.jsonl").exists()
    assert (home / "state" / "memory" / "openclaw-mem-writeback.jsonl").exists()

    status = _run(
        conn,
        ["sync", "status", "--backend", "service", "--harness-home", str(home)],
    )
    assert status["ok"] is True
    assert status["writes_performed"] is False
    assert all(item["receipt"]["store"]["status"] == "present_empty" for item in status["inner"])
    conn.close()


def test_qdrant_status_missing_optional_dependency_is_not_a_traceback(tmp_path: Path) -> None:
    conn = _connect(":memory:")
    db = tmp_path / "memory.sqlite"
    with patch("openclaw_mem.cli.importlib.util.find_spec", return_value=None):
        out = _run(
            conn,
            ["sync", "status", "--backend", "qdrant", "--db", str(db)],
        )
    assert out["ok"] is True
    assert out["inner"]["qdrant"] == "not_installed"
    assert out["inner"]["fallback"] == "sqlite"
    assert out["inner"]["writesPerformed"] is False
    conn.close()


@pytest.mark.parametrize("verb,dry_run", (("status", True), ("run", False)))
def test_lancedb_status_and_run_map_to_existing_writeback_command(
    verb: str, dry_run: bool
) -> None:
    conn = _connect(":memory:")
    args = build_parser().parse_args(
        [
            "sync",
            verb,
            "--backend",
            "lancedb",
            "--lancedb",
            "/tmp/lance",
            "--table",
            "memories",
            "--json",
        ]
    )
    args.json = True
    captured: list[str] = []

    def fake_invoke(_conn, argv):
        captured.extend(argv)
        return {"kind": "fixture.writeback", "ok": True, "writesPerformed": not dry_run}

    output = io.StringIO()
    with patch("openclaw_mem.cli._invoke_cli_json", side_effect=fake_invoke), redirect_stdout(output):
        cmd_sync(conn, args)
    out = json.loads(output.getvalue())
    assert "writeback-lancedb" in captured
    assert ("--dry-run" in captured) is dry_run
    assert out["writes_performed"] is (not dry_run)
    conn.close()


def test_service_store_alias_equals_sync_inner_plus_deprecation(tmp_path: Path) -> None:
    conn = _connect(":memory:")
    home = tmp_path / "harness"
    with patch("openclaw_mem.cli._utcnow_iso", return_value="2026-07-17T00:00:00Z"):
        old_args = build_parser().parse_args(
            ["--harness-home", str(home), "service-store", "status", "--json"]
        )
        old_args.json = True
        old_out = io.StringIO()
        with redirect_stdout(old_out):
            _run_handler_with_deprecation(conn, old_args)
        old = json.loads(old_out.getvalue())
        deprecated = old.pop("deprecated")

        new = _run(
            conn,
            ["sync", "status", "--backend", "service", "--harness-home", str(home)],
        )
    assert deprecated == {
        "use": "sync status --backend service",
        "since": "2.0.0",
        "removal": None,
    }
    assert old == new["inner"][0]["receipt"]
    conn.close()


def test_qdrant_status_alias_equals_sync_inner_plus_deprecation(tmp_path: Path) -> None:
    conn = _connect(":memory:")
    db = tmp_path / "memory.sqlite"
    with patch("openclaw_mem.cli.importlib.util.find_spec", return_value=None):
        old_args = build_parser().parse_args(
            ["--db", str(db), "qdrant", "status", "--json"]
        )
        old_args.db = str(db)
        old_args.json = True
        old_out = io.StringIO()
        with redirect_stdout(old_out):
            _run_handler_with_deprecation(conn, old_args)
        old = json.loads(old_out.getvalue())
        old.pop("deprecated")
        new = _run(
            conn,
            ["sync", "status", "--backend", "qdrant", "--db", str(db)],
        )
    assert old == new["inner"]
    conn.close()
