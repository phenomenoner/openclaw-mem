from __future__ import annotations

import subprocess
import sys

from openclaw_mem import gbrain_sidecar as legacy_gbrain
from openclaw_mem.cli import build_parser
from openclaw_mem.labs import gbrain_sidecar as labs_gbrain


HIDDEN_COMMANDS = ("continuity", "dream-lite", "gbrain-sidecar")
PRIMARY_COMMANDS = ("recall", "store", "curate", "sync", "graph", "db")


def test_legacy_lab_import_is_the_same_module_for_monkeypatch_compatibility() -> None:
    assert legacy_gbrain is labs_gbrain


def test_default_help_hides_experimental_families_without_removing_commands() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    for command in HIDDEN_COMMANDS:
        assert command not in help_text
    for command in PRIMARY_COMMANDS:
        assert command in help_text
    assert "status" not in help_text
    assert "optimize" not in help_text
    assert "writeback" not in help_text
    assert "--help-all" in help_text
    assert set(HIDDEN_COMMANDS).issubset(parser._actions[-1].choices)
    assert "status" in parser._actions[-1].choices


def test_help_all_reveals_experimental_families() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "openclaw_mem", "--help-all"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert process.returncode == 0
    for command in HIDDEN_COMMANDS:
        assert command in process.stdout
