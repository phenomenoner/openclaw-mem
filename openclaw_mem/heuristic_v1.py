from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from openclaw_mem.importance import make_importance


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


@dataclass(frozen=True)
class GradeResult:
    """Result of deterministic heuristic importance grading (heuristic-v1)."""

    score: float
    label: str
    rationale: str
    reasons: Tuple[str, ...]
    penalties: Tuple[str, ...]

    def as_importance(self) -> Dict[str, Any]:
        return make_importance(
            float(self.score),
            method="heuristic-v1",
            rationale=str(self.rationale),
            version=1,
            label=str(self.label),
        )


def _text_from_obs(obs: Dict[str, Any]) -> str:
    tool = (obs.get("tool_name") or obs.get("tool") or "").strip()
    summary = (obs.get("summary") or "").strip()
    if tool and summary:
        return f"{tool}: {summary}"
    return summary or tool


def _has_url(text: str) -> bool:
    return bool(re.search(r"https?://\S+", text or "", flags=re.IGNORECASE))


def _has_uuid(text: str) -> bool:
    return bool(
        re.search(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            text or "",
            flags=re.IGNORECASE,
        )
    )


def _has_config_path(text: str) -> bool:
    # Bias toward the one we actually care about in MVP.
    return bool(re.search(r"\bagents\.[a-z0-9_.]+\b", (text or ""), flags=re.IGNORECASE))


def _has_env_var(text: str) -> bool:
    # Keep this narrow to avoid false positives.
    return "OPENCLAW_" in (text or "")


def _has_cli_command(text: str) -> bool:
    t = (text or "").lower()
    return any(
        s in t
        for s in [
            "uv run",
            "python -m",
            "openclaw ",
            "openclaw-mem",
        ]
    )


def _is_task_like(text: str, kind: str) -> bool:
    t = (text or "").strip()
    tl = t.lower()
    if (kind or "").strip().lower() == "task":
        return True

    # Handle observations formatted as "tool: summary" and bare summaries.
    summary_part = tl.split(":", 1)[-1].strip() if ":" in tl else tl
    if re.match(r"^(todo|task|reminder)(?:[:：\s-]|$)", summary_part):
        return True

    if "要做" in t or "待辦" in t:
        return True
    return False


def grade_observation(obs: Dict[str, Any]) -> GradeResult:
    """Deterministic heuristic importance grading (heuristic-v1).

    Inputs expected (best-effort):
      - kind, tool_name/tool, summary, detail_json/detail

    Output matches the canonical `detail_json.importance` object.

    Note: This is designed to be stable and testable. For the executable
    reference used by the async playbook, see its `tools/heuristic_v1.py`.
    """

    kind = str(obs.get("kind") or "").strip()
    text = _text_from_obs(obs)
    tl = (text or "").lower()

    # Baseline is intentionally non-zero so a single strong signal can push an item
    # into nice_to_have without requiring multiple matches.
    score = 0.30
    reasons: List[str] = []
    penalties: List[str] = []

    is_task = _is_task_like(text, kind)

    # Precompute signal flags
    has_url = _has_url(text)
    has_uuid = _has_uuid(text)
    has_cfg = _has_config_path(text)
    has_env = _has_env_var(text)
    has_cli = _has_cli_command(text)
    has_ident = has_url or has_uuid or has_cfg or has_env or has_cli

    # J) Secret-like (down-rank)
    if re.search(r"BEGIN (RSA|OPENSSH) PRIVATE KEY", text or "", flags=re.IGNORECASE) or any(
        s in (text or "") for s in ["sk-", "ghp_", "AKIA"]
    ):
        score -= 0.40
        penalties.append("Secret-like content; down-ranked for safety.")

    # A) Constraints / preferences / policies
    if any(
        k in tl
        for k in [
            "prefer",
            "preference",
            "always",
            "never",
            "must",
            "should",
            "do not",
            "don't",
            "required",
            "rule",
            "policy",
            "hard requirement",
        ]
    ) or any(k in text for k in ["偏好", "規則", "一定", "必須", "不要", "禁止", "原則", "硬性", "需求", "不做", "不改"]):
        score += 0.40
        reasons.append("Durable preference/policy that affects future behavior.")

    # B) Decision / architecture choices
    if not is_task:
        decision_kw = any(
            k in tl
            for k in [
                "decide",
                "decision",
                "decided",
                "chose",
                "chosen",
                "we will",
                "we'll",
                "mvp",
                "scope",
                "architecture",
            ]
        ) or any(k in text for k in ["決定", "選擇", "採用", "方案", "架構", "範圍"])

        # Treat durable system/project setup notes as decisions when paired with
        # stable references (repo URLs, cron job ids, etc.).
        setup_kw = any(k in tl for k in ["created", "create", "added", "set up", "setup"]) and (
            ("repo" in tl)
            or ("repository" in tl)
            or ("cron" in tl)
            or ("jobid" in tl)
            or ("github.com" in tl)
        )

        if decision_kw or setup_kw:
            score += 0.30
            reasons.append("Captures a decision that should be consistent over time.")

    # C) Stable identifiers & reproducible references
    if has_ident:
        score += 0.20
        reasons.append("Contains stable identifiers useful for future lookup/automation.")

    # D) Operational runbooks / automation controls
    if any(
        k in tl
        for k in [
            "cron",
            "every ",
            "tz",
            "asia/taipei",
            "how to",
            "how to run",
            "openclaw ",
            "uv run",
            "python -m",
        ]
    ):
        score += 0.20
        reasons.append("Repeatable operational step; useful as a runbook.")

    # E) Errors / incidents
    has_error = any(
        k in tl
        for k in [
            "error",
            "failed",
            "exception",
            "traceback",
            "timeout",
            "rate_limit",
            "unauthorized",
            "forbidden",
        ]
    )
    if has_error:
        score += 0.15
        reasons.append("Operational issue with potential future recurrence.")

        if any(k in tl for k in ["root cause", "fixed by", "workaround", "mitigation", "resolved by"]):
            score += 0.10
            reasons.append("Includes a cause/fix/workaround.")

    # F) Tasks / deadlines
    if is_task:
        score += 0.20
        reasons.append("Action item that remains relevant until done.")

        if re.search(r"\bby\s+\d{4}-\d{2}-\d{2}\b", tl) or any(k in text for k in ["今天", "明天", "之前"]) or any(
            k in tl for k in ["today", "tomorrow", "eod", "before"]
        ):
            score += 0.10
            reasons.append("Has an explicit deadline/time window.")

    # G) Chit-chat / acknowledgements
    if re.search(r"\b(lol|thanks|thx|ok|got it|nice)\b", tl) or any(k in text for k in ["收到", "謝謝", "哈哈"]):
        score -= 0.25
        penalties.append("Acknowledgement/chit-chat; low reuse.")

    # H) Pure progress updates
    progress_kw = any(k in tl for k in ["done", "finished", "pushed", "merged", "wip"])
    if progress_kw and not (has_ident or has_error or is_task):
        score -= 0.20
        penalties.append("Pure progress update; low reuse.")

    # I) Calendar-only items
    meeting_kw = any(k in tl for k in ["meeting", "call"]) or any(k in text for k in ["開會", "約"])
    time_kw = bool(re.search(r"\b\d{1,2}(am|pm)\b", tl)) or bool(re.search(r"\b\d{1,2}:\d{2}\b", tl))
    if meeting_kw and time_kw and not (is_task or has_ident or has_error):
        score -= 0.15
        penalties.append("Calendar-only note without lasting context.")

    score = _clamp01(score)

    # Mirror the rationale style of the playbook reference:
    # 1–3 short sentences (prefer positives; add one down-rank note if any).
    rationale_parts: List[str] = []
    for r in reasons:
        if r not in rationale_parts:
            rationale_parts.append(r)
        if len(rationale_parts) >= 2:
            break

    if penalties and len(rationale_parts) < 3:
        rationale_parts.append(penalties[0])

    rationale = " ".join(rationale_parts).strip() or "Heuristic grade."

    # Keep label logic aligned to openclaw_mem.importance thresholds via make_importance.
    imp = make_importance(score, method="heuristic-v1", rationale=rationale, version=1)
    return GradeResult(
        score=float(imp["score"]),
        label=str(imp["label"]),
        rationale=str(imp["rationale"]),
        reasons=tuple(reasons),
        penalties=tuple(penalties),
    )


def grade_importance(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper: observation dict -> canonical importance dict."""

    return grade_observation(obs).as_importance()
