from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

SKILL_PATHS = [
    SKILLS / "memory" / "SKILL.md",
    SKILLS / "governance" / "curate" / "SKILL.md",
    SKILLS / "governance" / "graph" / "SKILL.md",
    SKILLS / "governance" / "sync" / "SKILL.md",
    SKILLS / "governance" / "temporal-facts" / "SKILL.md",
    SKILLS / "labs" / "dream-lite" / "SKILL.md",
    SKILLS / "labs" / "gbrain-sidecar" / "SKILL.md",
    SKILLS / "labs" / "goal-primitive" / "SKILL.md",
    SKILLS / "labs" / "self-improvement" / "SKILL.md",
    SKILLS / "labs" / "self-model" / "SKILL.md",
]


def test_ring_tiered_skill_tree_is_complete_and_compact() -> None:
    assert all(path.is_file() for path in SKILL_PATHS)
    for path in SKILL_PATHS:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), path
        assert "name:" in text and "description:" in text, path
        assert "  ring:" in text and "  version:" in text, path
        assert len(text.splitlines()) <= 60, path


def test_new_skill_tree_has_no_machine_specific_absolute_paths() -> None:
    for path in SKILLS.rglob("SKILL.md"):
        text = path.read_text(encoding="utf-8")
        assert "/root/" not in text, path
        assert "/home/" not in text, path
        assert "C:\\" not in text, path


def test_all_legacy_cards_are_three_line_move_stubs() -> None:
    legacy_cards = list(SKILLS.glob("*.md"))
    assert len(legacy_cards) == 11
    for path in legacy_cards:
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3, path
        assert lines[0] == "# Moved"
        assert lines[1].startswith("Moved to `skills/")
