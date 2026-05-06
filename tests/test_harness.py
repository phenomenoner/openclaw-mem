from __future__ import annotations

from pathlib import Path

import pytest

from openclaw_mem.harness import START_MARKER, END_MARKER, detect, install_card, verify_install


def test_harness_install_dry_run_does_not_write_token_or_file(tmp_path: Path) -> None:
    receipt = install_card(
        root=tmp_path,
        target="codex",
        mode="write",
        scope="openclaw-mem",
        gateway_url="http://127.0.0.1:18765",
        dry_run=True,
    )
    assert receipt["ok"] is True
    assert receipt["dry_run"] is True
    assert receipt["changed"] is True
    assert receipt["token_written"] is False
    assert not (tmp_path / "AGENTS.md").exists()


def test_harness_install_write_is_idempotent_and_preserves_human_content(tmp_path: Path) -> None:
    path = tmp_path / "CLAUDE.md"
    path.write_text("# Human instructions\n\nKeep this.\n", encoding="utf-8")
    first = install_card(root=tmp_path, target="claude", mode="read", dry_run=False)
    second = install_card(root=tmp_path, target="claude", mode="read", dry_run=False)
    text = path.read_text(encoding="utf-8")
    assert first["action"] == "inserted"
    assert second["action"] == "unchanged"
    assert "Keep this." in text
    assert text.count(START_MARKER) == 1
    assert text.count(END_MARKER) == 1
    assert verify_install(root=tmp_path, target="claude")["ok"] is True


def test_harness_detect_reports_targets(tmp_path: Path) -> None:
    install_card(root=tmp_path, target="generic", mode="read", dry_run=False)
    out = detect(tmp_path)
    installed = {row["target"]: row["installed"] for row in out["targets"]}
    assert installed["generic"] is True
    assert installed["codex"] is False


def test_harness_install_rejects_malformed_managed_block(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(f"human\n{START_MARKER}\npartial\n", encoding="utf-8")
    with pytest.raises(ValueError, match="partial or malformed"):
        install_card(root=tmp_path, target="codex", mode="read", dry_run=False)
    assert path.read_text(encoding="utf-8") == f"human\n{START_MARKER}\npartial\n"


def test_harness_install_rejects_secret_or_nonlocal_gateway_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="userinfo"):
        install_card(root=tmp_path, target="codex", gateway_url="http://user:pw@127.0.0.1:18765", dry_run=True)
    with pytest.raises(ValueError, match="non-local"):
        install_card(root=tmp_path, target="codex", gateway_url="https://memory.example.com", dry_run=True)
    receipt = install_card(root=tmp_path, target="codex", gateway_url="https://memory.example.com", allow_non_local=True, dry_run=True)
    assert receipt["ok"] is True
