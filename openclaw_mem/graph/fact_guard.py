from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

FACT_PROPOSAL_KIND = "openclaw-mem.graph.fact.proposal.v0"
FACT_GUARD_KIND = "openclaw-mem.graph.fact.guard.v0"
FACT_GUARD_LINT_KIND = "openclaw-mem.graph.fact.guard-lint.v0"
PREDICATES = ["requires_gate", "prohibits", "known_bug", "validated_by", "supersedes", "applies_to"]


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_dt(raw: Any) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text or text == "snapshot":
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_stale(fact: Dict[str, Any], *, stale_after_days: int, now: Optional[datetime] = None) -> bool:
    dt = _parse_dt(fact.get("freshness") or fact.get("valid_from"))
    if dt is None:
        return False
    current = now or datetime.now(timezone.utc)
    return dt < current - timedelta(days=max(0, int(stale_after_days)))


def _load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def propose_fact(*, kind: str, text: str, source_refs: List[str], target: Optional[str] = None) -> Dict[str, Any]:
    source_refs = [str(ref).strip() for ref in source_refs if str(ref).strip()]
    if not source_refs:
        return {
            "kind": FACT_PROPOSAL_KIND,
            "ok": False,
            "status": "policy_denied",
            "rejection_reason": "missing_source_ref",
            "writes_performed": False,
        }
    if kind not in {"correction", "constraint", "regression-risk"}:
        return {
            "kind": FACT_PROPOSAL_KIND,
            "ok": False,
            "status": "policy_denied",
            "rejection_reason": "unsupported_kind",
            "writes_performed": False,
        }
    predicate = "known_bug" if kind in {"correction", "regression-risk"} else "requires_gate"
    digest = hashlib.sha256(json.dumps([kind, text, source_refs, target], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {
        "kind": FACT_PROPOSAL_KIND,
        "ok": True,
        "status": "proposed",
        "proposal": {
            "fact_id": "proposal:" + digest,
            "kind": kind,
            "predicate": predicate,
            "target": target,
            "text": text,
            "source_refs": source_refs,
            "assertion_refs": ["proposal:" + _utcnow()],
            "freshness": "snapshot",
            "receipt_id": "proposal:" + _utcnow(),
        },
        "writes_performed": False,
        "policy": {"mode": "review_only", "canonical_write": False},
    }


def _applies(fact: Dict[str, Any], target: str) -> bool:
    target = target.replace("\\", "/")
    raw = str(fact.get("target") or fact.get("subject_ref") or fact.get("applies_to") or "").replace("\\", "/")
    if not raw:
        return False
    return raw == target or raw in target or target in raw


def _superseded_ids(facts: Iterable[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for fact in facts:
        for ref in list(fact.get("supersedes") or []):
            if str(ref).strip():
                out.add(str(ref).strip())
    return out


def _fact_id(fact: Dict[str, Any]) -> str:
    return str(fact.get("fact_id") or fact.get("id") or fact.get("receipt_id") or "")


def _context_pack(active: List[Dict[str, Any]], risks: List[Dict[str, Any]], gates: List[Dict[str, Any]]) -> Dict[str, Any]:
    lines = ["Graph fact guard advisory block:"]
    for fact in active + risks + gates:
        fid = _fact_id(fact) or "unknown"
        lines.append(f"- [{fid}] {fact.get('predicate') or fact.get('kind')}: {fact.get('text') or fact.get('object') or ''}")
    return {
        "schema": "openclaw-mem.context-pack.fragment.v0",
        "items": [
            {
                "kind": "graph_fact_guard",
                "importance": "advisory",
                "bundle_text": "\n".join(lines),
                "receipt_ids": [str(f.get("receipt_id") or _fact_id(f)) for f in active + risks + gates],
            }
        ],
    }


def guard(*, facts_path: str | Path, target: str, intent: str, stale_after_days: int = 30) -> Dict[str, Any]:
    try:
        facts = _load_jsonl(facts_path)
    except Exception as exc:
        return {
            "kind": FACT_GUARD_KIND,
            "ok": False,
            "status": "error",
            "error": str(exc),
            "target": target,
            "intent": intent,
            "writes_performed": False,
            "context_pack_fragment": {"schema": "openclaw-mem.context-pack.fragment.v0", "items": []},
        }
    superseded = _superseded_ids(facts)
    active: List[Dict[str, Any]] = []
    stale: List[Dict[str, Any]] = []
    superseded_list: List[Dict[str, Any]] = []
    for fact in facts:
        fid = _fact_id(fact)
        if fid in superseded:
            superseded_list.append({**fact, "reason": "superseded"})
            continue
        if _is_stale(fact, stale_after_days=stale_after_days):
            stale.append({**fact, "reason": "stale"})
            continue
        if _applies(fact, target):
            active.append(fact)
    risks = [f for f in active if str(f.get("predicate") or "") == "known_bug" or str(f.get("kind") or "") == "regression-risk"]
    gates = [f for f in active if str(f.get("predicate") or "") == "requires_gate"]
    constraints = [f for f in active if f not in risks and f not in gates]
    return {
        "kind": FACT_GUARD_KIND,
        "ok": True,
        "status": "advisory",
        "target": target,
        "intent": intent,
        "active_constraints": constraints,
        "regression_risks": risks,
        "required_gates": gates,
        "stale": stale,
        "superseded": superseded_list,
        "writes_performed": False,
        "context_pack_fragment": _context_pack(constraints, risks, gates),
    }


def lint_guard_facts(*, facts_path: str | Path, stale_after_days: int = 30) -> Dict[str, Any]:
    try:
        facts = _load_jsonl(facts_path)
    except Exception as exc:
        return {"kind": FACT_GUARD_LINT_KIND, "ok": False, "status": "error", "issues": [{"code": "facts_unreadable", "message": str(exc)}]}
    superseded = _superseded_ids(facts)
    active = [f for f in facts if _fact_id(f) not in superseded and not _is_stale(f, stale_after_days=stale_after_days)]
    issues: List[Dict[str, Any]] = []
    by_target: Dict[str, List[Dict[str, Any]]] = {}
    for fact in active:
        by_target.setdefault(str(fact.get("target") or fact.get("subject_ref") or ""), []).append(fact)
    for target, items in by_target.items():
        prohibitions = [f for f in items if str(f.get("predicate") or "") == "prohibits"]
        validators = [f for f in items if str(f.get("predicate") or "") == "validated_by"]
        if prohibitions and validators:
            issues.append(
                {
                    "code": "conflicting_active_constraints",
                    "target": target,
                    "facts": [_fact_id(f) for f in prohibitions + validators],
                }
            )
    return {
        "kind": FACT_GUARD_LINT_KIND,
        "ok": not issues,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "writes_performed": False,
        "predicate_registry": PREDICATES,
    }
