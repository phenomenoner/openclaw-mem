"""Deterministic, read-only linting for repository skill cards."""

from __future__ import annotations

import argparse
import hashlib
import re
import shlex
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


ABSOLUTE_PATH_RE = re.compile(r"(?:/root/|/home/|[A-Za-z]:[\\/])", re.IGNORECASE)
FRONTMATTER_FIELDS = ("name", "description", "metadata", "ring", "surface", "version", "requires")


def command_schema_from_parser(parser: argparse.ArgumentParser) -> dict[tuple[str, ...], bool]:
    """Return command paths mapped to whether they dispatch to a handler."""

    schema: dict[tuple[str, ...], bool] = {}

    def walk(node: argparse.ArgumentParser, prefix: tuple[str, ...]) -> None:
        for action in node._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for name, child in action.choices.items():
                path = (*prefix, name)
                schema[path] = callable(child._defaults.get("func"))
                walk(child, path)

    walk(parser, ())
    return schema


def _issue(code: str, path: Path, detail: str, line: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "path": path.as_posix(), "detail": detail}
    if line is not None:
        payload["line"] = line
    return payload


def _frontmatter(lines: list[str], path: Path) -> tuple[list[str], int, list[dict[str, Any]]]:
    if not lines or lines[0].strip() != "---":
        return [], 0, [_issue("frontmatter_missing", path, "SKILL.md must start with YAML frontmatter", 1)]
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return [], 0, [_issue("frontmatter_unclosed", path, "frontmatter has no closing delimiter", 1)]

    front = lines[1:end]
    issues: list[dict[str, Any]] = []
    field_lines: dict[str, tuple[int, str]] = {}
    for lineno, raw in enumerate(front, 2):
        match = re.match(r"^\s*([A-Za-z][\w-]*):(?:\s*(.*))?$", raw)
        if match and match.group(1) in FRONTMATTER_FIELDS:
            field_lines[match.group(1)] = (lineno, (match.group(2) or "").strip())
    for field in FRONTMATTER_FIELDS:
        if field not in field_lines:
            issues.append(_issue("frontmatter_field_missing", path, f"required field is missing: {field}", 1))
    if "ring" in field_lines:
        lineno, value = field_lines["ring"]
        if value not in {"0", "1", "2"}:
            issues.append(_issue("ring_invalid", path, "metadata.ring must be one of 0, 1, or 2", lineno))
    return front, end + 1, issues


def _bash_commands(lines: list[str]) -> Iterable[tuple[int, str]]:
    in_bash = False
    pending = ""
    pending_line = 0
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_bash:
                language = stripped[3:].strip().lower()
                in_bash = language in {"bash", "sh", "shell"}
            else:
                if pending:
                    yield pending_line, pending
                    pending = ""
                in_bash = False
            continue
        if not in_bash or not stripped or stripped.startswith("#"):
            continue
        if pending:
            pending += " " + stripped
        else:
            pending = stripped
            pending_line = lineno
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        yield pending_line, pending
        pending = ""


def _command_is_true(command: str, schema: Mapping[tuple[str, ...], bool]) -> bool:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    try:
        start = tokens.index("openclaw-mem") + 1
    except ValueError:
        return True
    words = tokens[start:]
    roots = {path[0] for path in schema if path}
    while words and words[0].startswith("-"):
        words.pop(0)
    if not words or words[0] not in roots:
        return False
    path = (words.pop(0),)
    while words:
        candidate = (*path, words[0])
        if candidate not in schema:
            break
        path = candidate
        words.pop(0)
    return bool(schema.get(path, False))


def _prose_paragraphs(lines: list[str], body_start: int) -> Iterable[tuple[int, str]]:
    paragraph: list[str] = []
    start = body_start + 1
    in_fence = False

    def flush() -> tuple[int, str] | None:
        nonlocal paragraph
        if not paragraph:
            return None
        value = " ".join(part.strip() for part in paragraph)
        paragraph = []
        normalized = re.sub(r"\s+", " ", value).strip().casefold()
        if len(normalized) < 100:
            return None
        return start, normalized

    for lineno, raw in enumerate(lines[body_start:], body_start + 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            item = flush()
            if item:
                yield item
            in_fence = not in_fence
            continue
        excluded = in_fence or not stripped or stripped.startswith(("#", "-", "*", ">", "|"))
        if excluded:
            item = flush()
            if item:
                yield item
            continue
        if not paragraph:
            start = lineno
        paragraph.append(stripped)
    item = flush()
    if item:
        yield item


def lint_skill_tree(
    skill_root: str | Path,
    *,
    command_schema: Mapping[tuple[str, ...], bool],
    max_lines: int = 60,
) -> dict[str, Any]:
    """Lint every SKILL.md below *skill_root* and return a stable receipt."""

    root = Path(skill_root).resolve()
    paths = sorted(root.rglob("SKILL.md"), key=lambda item: item.as_posix()) if root.is_dir() else []
    issues: list[dict[str, Any]] = []
    paragraph_locations: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    commands_checked = 0

    if not root.is_dir():
        issues.append(_issue("skill_root_missing", root, "skill root is not a directory"))

    for path in paths:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        _, body_start, frontmatter_issues = _frontmatter(lines, path)
        issues.extend(frontmatter_issues)
        if len(lines) > max_lines:
            issues.append(_issue("line_limit_exceeded", path, f"{len(lines)} lines exceeds limit {max_lines}"))
        match = ABSOLUTE_PATH_RE.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            issues.append(_issue("absolute_path_prohibited", path, "machine-specific absolute path is prohibited", line))
        for lineno, command in _bash_commands(lines):
            if "openclaw-mem" not in command:
                continue
            commands_checked += 1
            if not _command_is_true(command, command_schema):
                issues.append(_issue("command_unknown", path, f"command does not match the CLI parser: {command}", lineno))
        for lineno, normalized in _prose_paragraphs(lines, body_start):
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            paragraph_locations[digest].append((path, lineno))

    for digest, locations in sorted(paragraph_locations.items()):
        distinct = {path for path, _ in locations}
        if len(distinct) < 2:
            continue
        names = ", ".join(path.as_posix() for path in sorted(distinct, key=lambda item: item.as_posix()))
        for path, line in locations:
            issues.append(_issue("paragraph_duplicate", path, f"paragraph sha256:{digest[:12]} is duplicated across: {names}", line))

    issues.sort(key=lambda item: (item["path"], item.get("line", 0), item["code"]))
    return {
        "kind": "openclaw-mem.skill-lint.v1",
        "ok": not issues,
        "root": root.as_posix(),
        "files_checked": len(paths),
        "commands_checked": commands_checked,
        "error_count": len(issues),
        "issues": issues,
        "writes_performed": False,
    }
