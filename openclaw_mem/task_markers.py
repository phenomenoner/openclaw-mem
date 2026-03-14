from __future__ import annotations

import re
import unicodedata

_MARKERS = ("TODO", "TASK", "REMINDER")
_SEPARATORS = {":", "：", ";", "；", "-", ".", "。", "－", "–", "—", "−"}
_BULLET_PREFIXES = {"-", "*", "+", "•", "▪", "‣", "∙", "·", "●", "○", "◦", "・", "–", "—", "−"}
_CHECKBOX_MARKERS = {" ", "x", "X", "✓", "✔", "☐", "☑", "☒", "✅"}
_ORDERED_PREFIX_SEP = {".", ")", "-", "－", "–", "—", "−"}
_CLOSE_BY_OPEN = {
    "[": "]",
    "(": ")",
    "【": "】",
    "〔": "〕",
    "{": "}",
    "「": "」",
    "『": "』",
    "《": "》",
    "〈": "〉",
    "«": "»",
    "〖": "〗",
    "〘": "〙",
    "‹": "›",
    "<": ">",
}


def _has_valid_suffix(text: str, idx: int, *, allow_compact: bool = False) -> bool:
    if len(text) == idx:
        return True
    nxt = text[idx]
    if nxt in _SEPARATORS or nxt.isspace():
        return True
    return allow_compact


def _matches_marker_prefix(text: str) -> bool:
    up = text.upper()
    for marker in _MARKERS:
        if not up.startswith(marker):
            continue
        if _has_valid_suffix(text, len(marker)):
            return True

    if not text:
        return False

    close = _CLOSE_BY_OPEN.get(text[0])
    if close is None:
        return False

    rest_up = text[1:].upper()
    for marker in _MARKERS:
        if not rest_up.startswith(marker):
            continue

        close_idx = 1 + len(marker)
        if close_idx >= len(text) or text[close_idx] != close:
            continue

        if _has_valid_suffix(text, close_idx + 1, allow_compact=True):
            return True

    return False


def _is_roman_token(token: str) -> bool:
    if not token:
        return False

    return re.fullmatch(
        r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})",
        token.upper(),
    ) is not None


def _looks_like_checkbox_prefix(value: str) -> bool:
    return len(value) >= 3 and value[0] == "[" and value[2] == "]" and value[1] in _CHECKBOX_MARKERS


def _looks_like_ordered_prefix(value: str) -> bool:
    if len(value) >= 4 and value[0] == "(":
        j = 1
        while j < len(value) and value[j].isdigit():
            j += 1
        if j > 1 and j < len(value) and value[j] == ")" and j + 1 < len(value):
            return True

        k = 1
        while k < len(value) and ("a" <= value[k] <= "z" or "A" <= value[k] <= "Z"):
            k += 1
        if k > 1 and k < len(value) and value[k] == ")" and k + 1 < len(value):
            token = value[1:k]
            if len(token) == 1 or _is_roman_token(token):
                return True

    i = 0
    while i < len(value) and value[i].isdigit():
        i += 1
    if i > 0 and i < len(value) and value[i] in _ORDERED_PREFIX_SEP and i + 1 < len(value):
        return True

    j = 0
    while j < len(value) and ("a" <= value[j] <= "z" or "A" <= value[j] <= "Z"):
        j += 1
    if j > 0 and j < len(value) and value[j] in _ORDERED_PREFIX_SEP and j + 1 < len(value):
        token = value[:j]
        if len(token) == 1 or _is_roman_token(token):
            return True

    return False


def _can_strip_compact(remainder: str) -> bool:
    if not remainder:
        return False
    if _matches_marker_prefix(remainder):
        return True
    if remainder[0] == ">" or remainder[0] in _BULLET_PREFIXES:
        return True
    if _looks_like_checkbox_prefix(remainder):
        return True
    if _looks_like_ordered_prefix(remainder):
        return True
    return False


def _strip_ordered_prefix(value: str) -> str:
    if len(value) >= 4 and value[0] == "(":
        j = 1
        while j < len(value) and value[j].isdigit():
            j += 1
        if j > 1 and j < len(value) and value[j] == ")" and j + 1 < len(value):
            next_part = value[j + 1 :]
            if next_part and next_part[0].isspace():
                return next_part.lstrip()
            if _can_strip_compact(next_part):
                return next_part

        k = 1
        while k < len(value) and ("a" <= value[k] <= "z" or "A" <= value[k] <= "Z"):
            k += 1
        if k > 1 and k < len(value) and value[k] == ")" and k + 1 < len(value):
            token = value[1:k]
            if len(token) == 1 or _is_roman_token(token):
                next_part = value[k + 1 :]
                if next_part and next_part[0].isspace():
                    return next_part.lstrip()
                if _can_strip_compact(next_part):
                    return next_part

    i = 0
    while i < len(value) and value[i].isdigit():
        i += 1
    if i > 0 and i < len(value) and value[i] in _ORDERED_PREFIX_SEP and i + 1 < len(value):
        next_part = value[i + 1 :]
        if next_part and next_part[0].isspace():
            return next_part.lstrip()
        if _can_strip_compact(next_part):
            return next_part

    j = 0
    while j < len(value) and ("a" <= value[j] <= "z" or "A" <= value[j] <= "Z"):
        j += 1
    if j > 0 and j < len(value) and value[j] in _ORDERED_PREFIX_SEP and j + 1 < len(value):
        token = value[:j]
        if len(token) == 1 or _is_roman_token(token):
            next_part = value[j + 1 :]
            if next_part and next_part[0].isspace():
                return next_part.lstrip()
            if _can_strip_compact(next_part):
                return next_part

    return value


def strip_markdown_task_prefix(text: str) -> str:
    """Strip optional markdown/list wrappers before a task marker candidate."""

    t = unicodedata.normalize("NFKC", (text or "")).lstrip()
    changed = True
    while changed:
        changed = False

        block_depth = 0
        while block_depth < len(t) and t[block_depth] == ">":
            block_depth += 1

        if block_depth > 0 and block_depth < len(t):
            remainder = t[block_depth:]
            if remainder and remainder[0].isspace():
                t = remainder.lstrip()
                changed = True
            elif _can_strip_compact(remainder):
                t = remainder
                changed = True

        if len(t) >= 2 and t[0] in _BULLET_PREFIXES:
            remainder = t[1:]
            if remainder[0].isspace():
                t = remainder.lstrip()
                changed = True
            elif _can_strip_compact(remainder):
                t = remainder
                changed = True

        if _looks_like_checkbox_prefix(t) and len(t) >= 4:
            remainder = t[3:]
            if remainder and remainder[0].isspace():
                t = remainder.lstrip()
                changed = True
            elif _can_strip_compact(remainder):
                t = remainder
                changed = True

        stripped_ordered = _strip_ordered_prefix(t)
        if stripped_ordered != t:
            t = stripped_ordered
            changed = True

    return t


def summary_has_task_marker(summary: str) -> bool:
    """Return True when text begins with an accepted TODO/TASK/REMINDER marker."""

    s = unicodedata.normalize("NFKC", (summary or "")).lstrip()
    if not s:
        return False

    candidates = [s]
    stripped = strip_markdown_task_prefix(s)
    if stripped and stripped != s:
        candidates.append(stripped)

    for cand in candidates:
        if _matches_marker_prefix(cand):
            return True

    return False
