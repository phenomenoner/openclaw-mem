from __future__ import annotations

from pathlib import Path

import pytest

from openclaw_mem.cli import build_parser
from openclaw_mem.core.skill_lint import command_schema_from_parser, lint_skill_tree


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = command_schema_from_parser(build_parser())


def _card(body: str = "Use this bounded card for deterministic memory checks.", *, ring: str = "1") -> str:
    return f"""---
name: test-card
description: Use when testing the skill linter.
metadata:
  ring: {ring}
  surface: [cli]
  version: 1.0.0
  requires: []
---

# Test

{body}

```bash
openclaw-mem status --json
```
"""


def _lint(tmp_path: Path, cards: dict[str, str], *, max_lines: int = 60) -> dict:
    for name, text in cards.items():
        path = tmp_path / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
    return lint_skill_tree(tmp_path, command_schema=SCHEMA, max_lines=max_lines)


def test_good_card_passes_with_readonly_receipt(tmp_path: Path) -> None:
    receipt = _lint(tmp_path, {"good": _card()})
    assert receipt["ok"] is True
    assert receipt["files_checked"] == 1
    assert receipt["commands_checked"] == 1
    assert receipt["writes_performed"] is False


@pytest.mark.parametrize(
    ("name", "text", "code", "max_lines"),
    [
        ("frontmatter", "# Missing\n", "frontmatter_missing", 60),
        ("ring", _card(ring="3"), "ring_invalid", 60),
        ("lines", _card() + ("extra\n" * 61), "line_limit_exceeded", 60),
        ("path", _card("Never read C:\\private\\secrets."), "absolute_path_prohibited", 60),
        (
            "command",
            _card().replace("openclaw-mem status --json", "openclaw-mem definitely-not-a-command --json"),
            "command_unknown",
            60,
        ),
    ],
)
def test_bad_card_fails_red(tmp_path: Path, name: str, text: str, code: str, max_lines: int) -> None:
    receipt = _lint(tmp_path, {name: text}, max_lines=max_lines)
    assert receipt["ok"] is False
    assert code in {issue["code"] for issue in receipt["issues"]}


def test_duplicate_long_paragraphs_fail_across_cards(tmp_path: Path) -> None:
    duplicate = (
        "This deliberately repeated prose paragraph is long enough for stable duplicate detection and "
        "must be reported when it appears unchanged in more than one independent skill card."
    )
    receipt = _lint(tmp_path, {"one": _card(duplicate), "two": _card(duplicate)})
    duplicates = [issue for issue in receipt["issues"] if issue["code"] == "paragraph_duplicate"]
    assert len(duplicates) == 2


def test_repository_ring_skill_tree_has_zero_lint_errors() -> None:
    receipt = lint_skill_tree(ROOT / "skills", command_schema=SCHEMA)
    assert receipt["ok"], receipt["issues"]
    assert receipt["files_checked"] == 10
