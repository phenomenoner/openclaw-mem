from __future__ import annotations

import json
from pathlib import Path

import pytest

from openclaw_mem.core.harness_install import (
    HARNESS_NAMES,
    INSTALL_KIND,
    MCP_COMMAND,
    detect,
    install,
    plan,
    verify,
)
from openclaw_mem.harness import END_MARKER, START_MARKER


def _expected_path(root: Path, harness: str) -> Path:
    return {
        "claude-code": root / ".mcp.json",
        "codex": root / "AGENTS.md",
        "openclaw": root / ".openclaw-mem" / "agent-memory-card.md",
        "generic": root / ".openclaw-mem" / "skills" / "openclaw-mem-memory" / "SKILL.md",
    }[harness]


@pytest.mark.parametrize("harness", sorted(HARNESS_NAMES))
def test_each_adapter_dry_run_is_zero_write(tmp_path: Path, harness: str) -> None:
    receipt = install(harness, root=tmp_path, dry_run=True, run_verify=True)

    assert receipt["kind"] == INSTALL_KIND
    assert receipt["phase"] == "plan"
    assert receipt["dry_run"] is True
    assert receipt["writes_performed"] == 0
    assert receipt["plan"]["command"] == MCP_COMMAND
    assert not _expected_path(tmp_path, harness).exists()
    assert "verify" not in receipt


@pytest.mark.parametrize("harness", sorted(HARNESS_NAMES))
def test_each_adapter_apply_verify_and_second_run_noop(
    tmp_path: Path, harness: str
) -> None:
    first = install(harness, root=tmp_path, run_verify=True)
    second = install(harness, root=tmp_path, run_verify=True)

    assert first["ok"] is True
    assert first["writes_performed"] >= 1
    assert first["verify"]["ok"] is True
    assert _expected_path(tmp_path, harness).exists()
    assert second["ok"] is True
    assert second["changed"] is False
    assert second["writes_performed"] == 0
    assert second["backups"] == []


def test_claude_code_merges_json_preserves_unrelated_keys_and_backs_up(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".mcp.json"
    path.write_text(
        json.dumps(
            {
                "unrelated": {"keep": True},
                "mcpServers": {"another": {"command": "another-mcp"}},
            }
        ),
        encoding="utf-8",
    )
    original = path.read_text(encoding="utf-8")

    receipt = install("claude-code", root=tmp_path, run_verify=True)
    value = json.loads(path.read_text(encoding="utf-8"))

    assert value["unrelated"] == {"keep": True}
    assert value["mcpServers"]["another"] == {"command": "another-mcp"}
    assert value["mcpServers"]["openclaw-mem"] == {
        "command": MCP_COMMAND,
        "args": [],
    }
    assert len(receipt["backups"]) == 1
    assert Path(receipt["backups"][0]).read_text(encoding="utf-8") == original


@pytest.mark.parametrize("harness", ["codex", "openclaw"])
def test_managed_card_preserves_human_content_and_backs_up(
    tmp_path: Path, harness: str
) -> None:
    path = _expected_path(tmp_path, harness)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Human rules\n\nKeep this unrelated content.\n", encoding="utf-8")

    receipt = install(harness, root=tmp_path, mode="write", run_verify=True)
    text = path.read_text(encoding="utf-8")

    assert "# Human rules" in text
    assert "Keep this unrelated content." in text
    assert START_MARKER in text and END_MARKER in text
    assert len(receipt["backups"]) == 1


def test_generic_writes_ring_zero_card_and_backs_up_custom_skill(
    tmp_path: Path,
) -> None:
    path = _expected_path(tmp_path, "generic")
    path.parent.mkdir(parents=True)
    path.write_text("old card\n", encoding="utf-8")

    receipt = install("generic", root=tmp_path, run_verify=True)
    text = path.read_text(encoding="utf-8")

    assert "name: openclaw-mem-memory" in text
    assert "openclaw-mem recall" in text
    assert receipt["plan"]["command"] == "openclaw-mem-mcp"
    assert len(receipt["backups"]) == 1


def test_claude_optional_skills_dir_is_installed_and_verified(tmp_path: Path) -> None:
    skills = tmp_path / "custom-skills"
    receipt = install(
        "claude-code",
        root=tmp_path,
        skills_dir=skills,
        run_verify=True,
    )

    assert receipt["ok"] is True
    assert receipt["writes_performed"] == 2
    assert (skills / "openclaw-mem-memory" / "SKILL.md").exists()
    assert {check["name"] for check in receipt["verify"]["checks"]} == {
        "config",
        "skill",
    }


def test_plan_and_detect_never_write(tmp_path: Path) -> None:
    planned = plan("claude-code", root=tmp_path)
    detected = detect(tmp_path)

    assert planned.files[0].changed is True
    assert not (tmp_path / ".mcp.json").exists()
    assert detected["phase"] == "detect"
    assert len(detected["targets"]) == 4
    assert not list(tmp_path.rglob("*"))


def test_verify_missing_install_has_repair_command(tmp_path: Path) -> None:
    receipt = verify("codex", root=tmp_path)
    assert receipt["ok"] is False
    assert receipt["hint"] == "run openclaw-mem install --harness codex"


def test_invalid_claude_json_fails_before_any_write(tmp_path: Path) -> None:
    path = tmp_path / ".mcp.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot merge harness JSON config"):
        install("claude-code", root=tmp_path)
    assert path.read_text(encoding="utf-8") == "{broken"
    assert not list(tmp_path.glob("*.bak.*"))
