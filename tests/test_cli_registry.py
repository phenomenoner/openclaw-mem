from __future__ import annotations

from pathlib import Path

from openclaw_mem.cli import build_parser


def test_cli_is_package_with_non_overlapping_command_ownership() -> None:
    import openclaw_mem.cli as cli

    cli_path = Path(cli.__file__).resolve()
    assert cli_path.name == "__init__.py"
    assert cli_path.parent.name == "cli"
    registry = build_parser().openclaw_command_registry
    assert registry["search"] == "core_cmds"
    assert registry["graph"] == "graph_cmds"
    assert registry["engine"] == "engine_cmds"
    assert registry["dream-lite"] == "labs_cmds"
    assert registry["optimize"] == "ops_cmds"
    assert len(registry) == len(set(registry))
