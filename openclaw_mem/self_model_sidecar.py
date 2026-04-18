from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STATE_DIR = os.path.expanduser(os.environ.get("OPENCLAW_STATE_DIR", "~/.openclaw"))
DEFAULT_SELF_MODEL_RUN_DIR = os.path.join(STATE_DIR, "memory", "openclaw-mem", "self-model-sidecar")

SELF_SNAPSHOT_SCHEMA = "openclaw-mem.self-model.snapshot.v0"
ATTACHMENT_MAP_SCHEMA = "openclaw-mem.self-model.attachment-map.v0"
THREAT_FEED_SCHEMA = "openclaw-mem.self-model.threat-feed.v0"
DIFF_SCHEMA = "openclaw-mem.self-model.diff.v0"
RELEASE_RECEIPT_SCHEMA = "openclaw-mem.self-model.release-receipt.v0"
COMPARE_MIGRATION_SCHEMA = "openclaw-mem.self-model.compare-migration.v0"
CONTROL_SCHEMA = "openclaw-mem.self-model.control.v0"
AUTORUN_SCHEMA = "openclaw-mem.self-model.autorun.v0"
ADJUDICATION_SCHEMA = "openclaw-mem.self-model.adjudication.v0"
PUBLIC_SUMMARY_SCHEMA = "openclaw-mem.self-model.public-summary.v0"
DERIVATION_VERSION = "self_model_sidecar_v0"
ADJUDICATION_POLICY_VERSION = "self_model_sidecar_adjudication_v1"

KEYWORD_GROUPS: Dict[str, Dict[str, Sequence[str]]] = {
    "role": {
        "operator": ("operator", "marshal", "field marshal", "governor"),
        "engineer": ("engineer", "developer", "coder", "builder"),
        "strategist": ("strategist", "planner", "strategy"),
        "reviewer": ("review", "code review", "auditor"),
        "assistant": ("assistant", "teammate", "copilot"),
    },
    "goal": {
        "ship_mvp": ("ship", "mvp", "deliver", "launch"),
        "stabilize": ("stabilize", "stability", "rollback", "reliable"),
        "verify": ("verify", "receipts", "proof", "test"),
        "optimize": ("optimize", "improve", "tighten", "refactor"),
        "protect_scope": ("bounded", "scope", "guardrail", "non-goal"),
    },
    "refusal": {
        "avoid_anthropomorphism": ("anthropomorphism", "consciousness", "soul", "selfhood theater"),
        "avoid_truth_owner_drift": ("truth owner", "split-brain", "second owner", "overwrite"),
        "avoid_blind_autonomy": ("blind autonomy", "blind push", "unbounded", "reckless"),
        "avoid_direct_core_writes": ("no writes", "do not write", "read-only", "side-car only"),
    },
    "style": {
        "direct": ("direct", "plain", "crisp"),
        "warm": ("warm", "supportive", "teammate"),
        "concise": ("concise", "brief", "minimal fluff"),
        "evidence_first": ("receipts", "evidence", "verifier", "truth"),
        "chinese_native": ("中文", "chinese", "chinese-native"),
    },
    "stance": {
        "sidecar_only": ("side-car", "sidecar", "additive"),
        "continuity_matters": ("continuity", "drift", "identity mirror", "self-model"),
        "release_is_governed": ("release", "rebind", "retire", "weaken"),
        "nuwa_is_prior_only": ("nuwa", "prior", "weighted hint", "persona prior"),
        "topology_unchanged": ("topology unchanged", "topology: unchanged", "topology intent"),
    },
}

OPPOSING_IDS = {
    frozenset(("refusal:avoid_direct_core_writes", "goal:ship_mvp")): "speed_vs_write_safety",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_run_dir() -> str:
    return os.path.expanduser(os.environ.get("OPENCLAW_MEM_SELF_MODEL_DIR", DEFAULT_SELF_MODEL_RUN_DIR))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_payload(obj: Any) -> str:
    return hashlib.sha256(_json_dumps(obj).encode("utf-8")).hexdigest()


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _control_path(run_dir: Optional[str]) -> Path:
    return _mkdir(Path(run_dir or default_run_dir())) / "control.json"


def _control_history_dir(run_dir: Optional[str]) -> Path:
    return _mkdir(Path(run_dir or default_run_dir()) / "control-history")


def _state_residue_summary(run_dir: Optional[str]) -> Dict[str, Any]:
    root = Path(run_dir or default_run_dir())
    snapshots_dir = root / "snapshots"
    releases_dir = root / "releases"
    autorun_dir = root / "autorun"
    latest_path = snapshots_dir / "latest.json"
    return {
        "run_dir": str(root),
        "latest_pointer_present": latest_path.exists(),
        "snapshot_count": len(list(snapshots_dir.glob("*.json"))) if snapshots_dir.exists() else 0,
        "release_receipt_count": len(list(releases_dir.glob("*.json"))) if releases_dir.exists() else 0,
        "autorun_receipt_count": len(list(autorun_dir.glob("*.json"))) if autorun_dir.exists() else 0,
    }


def _write_control_receipt(run_dir: Optional[str], payload: Dict[str, Any]) -> str:
    action = str(payload.get("action") or "status")
    stamp = str(payload.get("updated_at") or _utcnow_iso())
    fname = f"{stamp.replace(':', '').replace('+', '_').replace('-', '')}__{int(time.time() * 1000)}__{_slug(action)}.json"
    path = _control_history_dir(run_dir) / fname
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


@contextmanager
def _db_readonly_guard(conn: sqlite3.Connection):
    current = int(conn.execute("PRAGMA query_only").fetchone()[0])
    conn.execute("PRAGMA query_only = 1")
    try:
        yield
    finally:
        conn.execute(f"PRAGMA query_only = {current}")


def db_readonly_guard(conn: sqlite3.Connection):
    return _db_readonly_guard(conn)


def load_control_config(run_dir: Optional[str]) -> Dict[str, Any]:
    path = _control_path(run_dir)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    return {
        "schema": CONTROL_SCHEMA,
        "enabled": False,
        "cadence_seconds": 0,
        "persist_on_run": True,
        "updated_at": None,
    }


def save_control_config(run_dir: Optional[str], *, enabled: bool, cadence_seconds: int, persist_on_run: bool) -> Dict[str, Any]:
    root = Path(run_dir or default_run_dir())
    latest_path = root / "snapshots" / "latest.json"
    cleared_latest = False
    cleared_snapshot_id = None
    previous = load_control_config(run_dir)
    if not enabled and latest_path.exists():
        try:
            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
            cleared_snapshot_id = latest_payload.get("snapshot_id")
        except Exception:
            cleared_snapshot_id = None
        latest_path.unlink()
        cleared_latest = True
    payload = {
        "schema": CONTROL_SCHEMA,
        "enabled": bool(enabled),
        "cadence_seconds": int(cadence_seconds),
        "persist_on_run": bool(persist_on_run),
        "action": "enable" if enabled else "disable",
        "cleared_latest_pointer": cleared_latest,
        "cleared_snapshot_id": cleared_snapshot_id,
        "previous_enabled": bool(previous.get("enabled")),
        "updated_at": _utcnow_iso(),
    }
    path = _control_path(run_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["path"] = str(path)
    payload["residue"] = _state_residue_summary(run_dir)
    payload["receipt_path"] = _write_control_receipt(run_dir, payload)
    return payload


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"value": data}


def _load_jsonl(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    out: List[Dict[str, Any]] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        obj = json.loads(raw)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _flatten_json_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        return " ".join(part for part in (_flatten_json_text(x) for x in obj) if part)
    if isinstance(obj, dict):
        parts: List[str] = []
        for key, value in obj.items():
            if key.endswith("_id"):
                continue
            text = _flatten_json_text(value)
            if text:
                parts.append(f"{key} {text}")
        return " ".join(parts)
    return ""


def _safe_json(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"value": data}
        except Exception:
            return {"raw": raw}
    return {"value": raw}


def _iter_db_evidence(conn: sqlite3.Connection, scope: Optional[str], session_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    obs_limit = max(1, limit)
    rows = conn.execute(
        "SELECT id, ts, kind, summary, tool_name, detail_json FROM observations ORDER BY id DESC LIMIT ?",
        (obs_limit,),
    ).fetchall()
    for row in rows:
        detail = _safe_json(row["detail_json"])
        detail_scope = str(detail.get("scope") or "").strip() or None
        detail_session = str(detail.get("session_id") or "").strip() or None
        if scope and detail_scope != scope:
            continue
        if session_id and detail_session != session_id:
            continue
        text = " ".join(
            part
            for part in [str(row["summary"] or ""), str(row["tool_name"] or ""), _flatten_json_text(detail)]
            if part
        ).strip()
        if not text:
            continue
        evidence.append(
            {
                "source_class": "observation",
                "source_id": f"obs:{row['id']}",
                "ts": row["ts"],
                "scope": detail_scope,
                "session_id": detail_session,
                "text": text,
            }
        )
    event_rows = conn.execute(
        "SELECT id, ts_ms, scope, session_id, type, summary, payload_json FROM episodic_events ORDER BY ts_ms DESC, id DESC LIMIT ?",
        (obs_limit,),
    ).fetchall()
    for row in event_rows:
        event_scope = str(row["scope"] or "").strip() or None
        event_session = str(row["session_id"] or "").strip() or None
        if scope and event_scope != scope:
            continue
        if session_id and event_session != session_id:
            continue
        payload = _safe_json(row["payload_json"])
        text = " ".join(
            part
            for part in [str(row["summary"] or ""), str(row["type"] or ""), _flatten_json_text(payload)]
            if part
        ).strip()
        if not text:
            continue
        evidence.append(
            {
                "source_class": "episode",
                "source_id": f"event:{row['id']}",
                "ts": row["ts_ms"],
                "scope": event_scope,
                "session_id": event_session,
                "text": text,
            }
        )
    evidence.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return evidence[: limit * 2]


def _iter_file_evidence(observations_file: Optional[str], episodes_file: Optional[str], scope: Optional[str], session_id: Optional[str]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for idx, row in enumerate(_load_jsonl(observations_file), start=1):
        detail = _safe_json(row.get("detail") or row.get("detail_json"))
        detail_scope = str(detail.get("scope") or row.get("scope") or "").strip() or None
        detail_session = str(detail.get("session_id") or row.get("session_id") or "").strip() or None
        if scope and detail_scope != scope:
            continue
        if session_id and detail_session != session_id:
            continue
        text = " ".join(
            part
            for part in [str(row.get("summary") or ""), str(row.get("tool_name") or ""), _flatten_json_text(detail)]
            if part
        ).strip()
        if text:
            evidence.append({
                "source_class": "observation_file",
                "source_id": f"obs-file:{idx}",
                "ts": row.get("ts") or row.get("created_at") or "",
                "scope": detail_scope,
                "session_id": detail_session,
                "text": text,
            })
    for idx, row in enumerate(_load_jsonl(episodes_file), start=1):
        event_scope = str(row.get("scope") or "").strip() or None
        event_session = str(row.get("session_id") or "").strip() or None
        if scope and event_scope != scope:
            continue
        if session_id and event_session != session_id:
            continue
        payload = _safe_json(row.get("payload") or row.get("payload_json"))
        text = " ".join(
            part
            for part in [str(row.get("summary") or ""), str(row.get("type") or ""), _flatten_json_text(payload)]
            if part
        ).strip()
        if text:
            evidence.append({
                "source_class": "episode_file",
                "source_id": f"episode-file:{idx}",
                "ts": row.get("ts") or row.get("ts_ms") or "",
                "scope": event_scope,
                "session_id": event_session,
                "text": text,
            })
    evidence.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return evidence


def _normalize_priors(persona: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    priors: Dict[str, Dict[str, float]] = defaultdict(dict)
    for category in ("roles", "goals", "refusals", "style_commitments", "stances"):
        raw = persona.get(category) or {}
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    priors[category][_slug(item)] = 1.0
                elif isinstance(item, dict):
                    priors[category][_slug(str(item.get("id") or item.get("label") or "item"))] = float(item.get("weight") or 1.0)
        elif isinstance(raw, dict):
            for key, value in raw.items():
                priors[category][_slug(str(key))] = float(value if isinstance(value, (int, float)) else 1.0)
    return priors


def _active_release_map(run_dir: str, *, scope: Optional[str], session_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    releases_dir = Path(run_dir) / "releases"
    latest: Dict[str, Dict[str, Any]] = {}
    if not releases_dir.exists():
        return latest
    for path in sorted(releases_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        stance_id = str(payload.get("stance_id") or "").strip()
        if not stance_id:
            continue
        receipt_scope = str(payload.get("scope") or "").strip() or None
        receipt_session = str(payload.get("session_id") or "").strip() or None
        if receipt_scope is not None and receipt_scope != scope:
            continue
        if receipt_session is not None and receipt_session != session_id:
            continue
        latest[stance_id] = payload
    return latest


def _collect_candidates(evidence: List[Dict[str, Any]], persona_priors: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}

    def ensure_item(category: str, raw_id: str, label: str) -> Dict[str, Any]:
        full_id = f"{category}:{raw_id}"
        item = by_id.get(full_id)
        if item is None:
            prior_bucket = {
                "role": "roles",
                "goal": "goals",
                "refusal": "refusals",
                "style": "style_commitments",
                "stance": "stances",
            }[category]
            item = {
                "id": full_id,
                "category": category,
                "label": label,
                "evidence_ids": [],
                "source_classes": Counter(),
                "evidence_hits": 0,
                "prior_weight": float(persona_priors.get(prior_bucket, {}).get(raw_id, 0.0)),
                "contradiction_hits": 0,
                "matched_keywords": set(),
            }
            by_id[full_id] = item
        return item

    for ev in evidence:
        text = str(ev.get("text") or "")
        normalized = text.lower()
        for category, groups in KEYWORD_GROUPS.items():
            for raw_id, keywords in groups.items():
                hits = [kw for kw in keywords if kw in normalized]
                if not hits:
                    continue
                item = ensure_item(category, raw_id, raw_id.replace("_", " "))
                item["evidence_hits"] += len(hits)
                item["evidence_ids"].append(ev["source_id"])
                item["source_classes"][ev["source_class"]] += 1
                item["matched_keywords"].update(hits)

    for bucket_name, category in (("roles", "role"), ("goals", "goal"), ("refusals", "refusal"), ("style_commitments", "style"), ("stances", "stance")):
        for raw_id, weight in persona_priors.get(bucket_name, {}).items():
            item = ensure_item(category, raw_id, raw_id.replace("_", " "))
            item["prior_weight"] = max(item["prior_weight"], float(weight))

    items = list(by_id.values())
    active_ids = {item["id"] for item in items if item["evidence_hits"] or item["prior_weight"]}
    for pair, _reason in OPPOSING_IDS.items():
        if pair.issubset(active_ids):
            for stance_id in pair:
                if stance_id in by_id:
                    by_id[stance_id]["contradiction_hits"] += 1

    out: List[Dict[str, Any]] = []
    for item in items:
        evidence_ids = sorted(set(item["evidence_ids"]))
        source_classes = sorted(item["source_classes"].keys())
        evidence_count = len(evidence_ids)
        source_class_bonus = min(0.15, 0.05 * len(source_classes))
        score = min(
            1.0,
            0.15 + (0.18 * evidence_count) + (0.2 * float(item["prior_weight"])) + (0.08 * item["contradiction_hits"]) + source_class_bonus,
        )
        out.append(
            {
                "id": item["id"],
                "category": item["category"],
                "label": item["label"],
                "attachment_score": round(score, 3),
                "evidence_count": evidence_count,
                "evidence_ids": evidence_ids[:8],
                "source_classes": source_classes,
                "prior_weight": round(float(item["prior_weight"]), 3),
                "contradiction_hits": int(item["contradiction_hits"]),
                "matched_keywords": sorted(item["matched_keywords"]),
            }
        )
    out.sort(key=lambda item: (-item["attachment_score"], item["id"]))
    return out


def _apply_releases(attachments: List[Dict[str, Any]], release_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in attachments:
        release = release_map.get(item["id"])
        patched = dict(item)
        if not release:
            patched["release_state"] = "active"
            patched["latest_release_receipt_id"] = None
            out.append(patched)
            continue
        mode = str(release.get("mode") or "weaken").strip() or "weaken"
        if mode == "retire":
            continue
        factor = float(release.get("factor") or 0.5)
        patched["attachment_score"] = round(max(0.0, min(1.0, item["attachment_score"] * factor)), 3)
        patched["release_state"] = "weakening"
        patched["latest_release_receipt_id"] = release.get("receipt_id")
        patched["release"] = {
            "mode": mode,
            "factor": factor,
            "reason": release.get("reason"),
            "receipt_id": release.get("receipt_id"),
            "released_at": release.get("released_at"),
        }
        out.append(patched)
    out.sort(key=lambda item: (-item["attachment_score"], item["id"]))
    return out


def _build_narrative(attachments: List[Dict[str, Any]]) -> str:
    def top(category: str) -> List[str]:
        return [item["label"] for item in attachments if item["category"] == category][:2]

    roles = top("role")
    goals = top("goal")
    styles = top("style")
    stances = top("stance")
    chunks: List[str] = []
    if roles:
        chunks.append("Acts like " + ", ".join(roles))
    if goals:
        chunks.append("pulling toward " + ", ".join(goals))
    if styles:
        chunks.append("while sounding " + ", ".join(styles))
    if stances:
        chunks.append("with durable stance on " + ", ".join(stances))
    if not chunks:
        return "Insufficient evidence to assemble a stable self-model yet."
    text = "; ".join(chunks)
    return text[0].upper() + text[1:] + "."


def _score_band(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _fragility_label(evidence_count: int, prior_weight: float, contradiction_hits: int) -> str:
    if evidence_count <= 1 and prior_weight > 0.0:
        return "fragile"
    if contradiction_hits > 0:
        return "contested"
    if evidence_count >= 3:
        return "supported"
    return "watch"


def _adjudicate_attachment(item: Dict[str, Any]) -> Dict[str, Any]:
    score = round(float(item.get("attachment_score") or 0.0), 3)
    evidence_count = int(item.get("evidence_count") or 0)
    prior_weight = round(float(item.get("prior_weight") or 0.0), 3)
    contradiction_hits = int(item.get("contradiction_hits") or 0)
    contradiction_pressure = round(float(item.get("contradiction_pressure") or 0.0), 3)
    release_state = str(item.get("release_state") or "active")
    reasons: List[str] = []

    if release_state == "retired":
        state = "retired"
        reasons.append("release_retired")
    elif evidence_count <= 0 and prior_weight <= 0.0:
        state = "rejected"
        reasons.append("no_support")
    elif contradiction_pressure >= 0.7 or (contradiction_hits > 0 and evidence_count <= 1):
        state = "contested"
        reasons.append("contradiction_pressure")
    elif prior_weight > 0.0 and evidence_count == 0:
        state = "tentative"
        reasons.append("prior_only")
    elif release_state == "weakening" and evidence_count < 4:
        state = "fragile"
        reasons.append("released_claim_requires_revalidation")
    elif evidence_count <= 1 and (prior_weight > 0.0 or score < 0.55):
        state = "fragile"
        reasons.append("thin_evidence")
    elif contradiction_pressure > 0.0:
        state = "fragile"
        reasons.append("contradicted_but_not_contested")
    elif score >= 0.75 and evidence_count >= 3:
        state = "accepted"
        reasons.append("strong_multi_source_support")
    elif score >= 0.4 and evidence_count >= 1:
        state = "tentative"
        reasons.append("bounded_support")
    else:
        state = "fragile"
        reasons.append("low_support")

    public_visible = state == "accepted" or (state == "tentative" and "prior_only" not in reasons)

    return {
        "state": state,
        "reasons": reasons,
        "operator_visible": True,
        "public_visible": public_visible,
        "hedge": "derived continuity signal" if state in {"accepted", "tentative"} else "insufficient evidence",
        "policy_version": ADJUDICATION_POLICY_VERSION,
        "determinism_boundary": {
            "fields": [
                "attachment_score",
                "evidence_count",
                "prior_weight",
                "contradiction_hits",
                "contradiction_pressure",
                "release_state",
            ],
            "rule_only": True,
        },
    }


def _with_attachment_provenance(attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for item in attachments:
        score = round(float(item.get("attachment_score") or 0.0), 3)
        evidence_count = int(item.get("evidence_count") or 0)
        prior_weight = round(float(item.get("prior_weight") or 0.0), 3)
        contradiction_hits = int(item.get("contradiction_hits") or 0)
        contradiction_pressure = round(min(1.0, contradiction_hits * 0.35), 3)
        confidence = round(min(0.99, max(0.05, (score * 0.7) + min(0.25, evidence_count * 0.06))), 3)
        fragility = _fragility_label(evidence_count, prior_weight, contradiction_hits)
        patched = dict(item)
        patched["attachment_score"] = score
        patched["confidence"] = confidence
        patched["band"] = _score_band(score)
        patched["contradiction_pressure"] = contradiction_pressure
        patched["fragility"] = fragility
        adjudication = _adjudicate_attachment(patched)
        patched["adjudication_state"] = adjudication["state"]
        patched["adjudication_reasons"] = list(adjudication["reasons"])
        patched["publication"] = {
            "operator_visible": bool(adjudication["operator_visible"]),
            "public_visible": bool(adjudication["public_visible"]),
            "hedge": adjudication["hedge"],
        }
        patched["provenance"] = {
            "derived": True,
            "authoritative": False,
            "derivation_version": DERIVATION_VERSION,
            "source_event_count": evidence_count,
            "source_classes": list(item.get("source_classes") or []),
            "evidence_ids": list(item.get("evidence_ids") or []),
            "prior_weight": prior_weight,
            "adjudication_policy": adjudication["policy_version"],
            "determinism_boundary": adjudication["determinism_boundary"],
        }
        enriched.append(patched)
    return enriched


def build_snapshot(
    conn: sqlite3.Connection,
    *,
    scope: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 50,
    persona_file: Optional[str] = None,
    observations_file: Optional[str] = None,
    episodes_file: Optional[str] = None,
    run_dir: Optional[str] = None,
) -> Dict[str, Any]:
    with _db_readonly_guard(conn):
        persona = _load_json(persona_file)
        persona_priors = _normalize_priors(persona)
        evidence = _iter_db_evidence(conn, scope=scope, session_id=session_id, limit=limit)
        evidence.extend(_iter_file_evidence(observations_file, episodes_file, scope=scope, session_id=session_id))
        evidence.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
        evidence = evidence[: max(limit * 2, 1)]
        release_map = _active_release_map(run_dir or default_run_dir(), scope=scope, session_id=session_id)
        attachments = _with_attachment_provenance(_apply_releases(_collect_candidates(evidence, persona_priors), release_map))
        top = attachments[:8]
        source_digest = _digest_payload(
            {
                "scope": scope,
                "session_id": session_id,
                "evidence": [{"source_id": e["source_id"], "ts": e.get("ts"), "text": e.get("text")} for e in evidence],
                "persona": persona,
                "releases": release_map,
            }
        )
        snapshot_id = f"sms:v0:{source_digest[:16]}"
        snapshot = {
            "schema": SELF_SNAPSHOT_SCHEMA,
            "snapshot_id": snapshot_id,
            "generated_at": _utcnow_iso(),
            "scope": scope,
            "session_id": session_id,
            "narrative": _build_narrative(top),
            "roles": [item["id"] for item in attachments if item["category"] == "role"][:5],
            "goals": [item["id"] for item in attachments if item["category"] == "goal"][:5],
            "refusals": [item["id"] for item in attachments if item["category"] == "refusal"][:5],
            "style_commitments": [item["id"] for item in attachments if item["category"] == "style"][:5],
            "attachments": attachments,
            "evidence_summary": {
                "total_evidence": len(evidence),
                "source_classes": sorted({e["source_class"] for e in evidence}),
                "sample_evidence_ids": [e["source_id"] for e in evidence[:8]],
                "active_release_count": len(release_map),
                "derived": True,
                "non_authoritative": True,
                "operator_surface": "continuity",
                "adjudication_policy": ADJUDICATION_POLICY_VERSION,
            },
            "provenance": {
                "derived": True,
                "authoritative": False,
                "derivation_version": DERIVATION_VERSION,
                "source_digest": source_digest,
                "source_classes": sorted({e["source_class"] for e in evidence}),
                "record_count": len(evidence),
                "persona_prior_count": sum(len(bucket) for bucket in persona_priors.values()),
                "release_receipt_count": len(release_map),
                "query_only_enforced": True,
                "adjudication_policy": ADJUDICATION_POLICY_VERSION,
            },
            "source_digest": source_digest,
        }
        return snapshot


def build_adjudication_report(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    attachments = list(snapshot.get("attachments") or [])
    by_state: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in attachments:
        by_state[str(item.get("adjudication_state") or "tentative")].append(item)
    ordered_states = ["accepted", "tentative", "fragile", "contested", "retired", "rejected"]
    return {
        "schema": ADJUDICATION_SCHEMA,
        "snapshot_id": snapshot.get("snapshot_id"),
        "generated_at": _utcnow_iso(),
        "policy_version": ADJUDICATION_POLICY_VERSION,
        "counts": {state: len(by_state.get(state, [])) for state in ordered_states},
        "claims_by_state": {state: by_state.get(state, []) for state in ordered_states if by_state.get(state)},
        "operator_summary": {
            "top_accepted": [item.get("id") for item in by_state.get("accepted", [])[:5]],
            "top_fragile": [item.get("id") for item in by_state.get("fragile", [])[:5]],
            "top_contested": [item.get("id") for item in by_state.get("contested", [])[:5]],
        },
        "provenance": {
            "derived": True,
            "authoritative": False,
            "derivation_version": DERIVATION_VERSION,
            "adjudication_policy": ADJUDICATION_POLICY_VERSION,
            "snapshot_source_digest": snapshot.get("source_digest"),
        },
    }


def build_public_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    attachments = list(snapshot.get("attachments") or [])
    public_claims = [item for item in attachments if bool(((item.get("publication") or {}).get("public_visible")))]
    warnings: List[str] = []
    if any(str(item.get("adjudication_state") or "") == "fragile" for item in attachments):
        warnings.append("Some continuity signals remain fragile and are intentionally withheld from the public-safe summary.")
    if any(str(item.get("adjudication_state") or "") == "contested" for item in attachments):
        warnings.append("Some continuity signals are contested by contradictory evidence.")
    if not public_claims:
        summary = "Insufficient evidence to publish a stable derived continuity summary."
    else:
        ordered = sorted(public_claims, key=lambda item: (-float(item.get("attachment_score") or 0.0), str(item.get("id") or "")))
        labels = [str(item.get("label") or item.get("id") or "claim") for item in ordered[:4]]
        summary = "Derived continuity signal currently points toward " + ", ".join(labels) + "."
    return {
        "schema": PUBLIC_SUMMARY_SCHEMA,
        "snapshot_id": snapshot.get("snapshot_id"),
        "generated_at": _utcnow_iso(),
        "summary": summary,
        "claims": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "category": item.get("category"),
                "adjudication_state": item.get("adjudication_state"),
                "hedge": ((item.get("publication") or {}).get("hedge")),
            }
            for item in public_claims[:8]
        ],
        "warnings": warnings,
        "provenance": {
            "derived": True,
            "authoritative": False,
            "derivation_version": DERIVATION_VERSION,
            "adjudication_policy": ADJUDICATION_POLICY_VERSION,
            "snapshot_source_digest": snapshot.get("source_digest"),
            "public_safe": True,
        },
    }


def build_attachment_map(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    attachments = list(snapshot.get("attachments") or [])
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in attachments:
        grouped[str(item.get("category") or "unknown")].append(item)
    return {
        "schema": ATTACHMENT_MAP_SCHEMA,
        "snapshot_id": snapshot.get("snapshot_id"),
        "generated_at": _utcnow_iso(),
        "narrative": snapshot.get("narrative"),
        "counts": {key: len(value) for key, value in sorted(grouped.items())},
        "adjudication_counts": dict(sorted(Counter(str(item.get("adjudication_state") or "tentative") for item in attachments).items())),
        "attachments": attachments,
        "top_attachments": attachments[:5],
        "provenance": {
            "derived": True,
            "authoritative": False,
            "derivation_version": DERIVATION_VERSION,
            "snapshot_source_digest": snapshot.get("source_digest"),
        },
    }


def build_threat_feed(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    attachments = list(snapshot.get("attachments") or [])
    attachment_ids = {str(item.get("id")) for item in attachments}
    threats: List[Dict[str, Any]] = []
    for pair, reason in OPPOSING_IDS.items():
        if pair.issubset(attachment_ids):
            threats.append(
                {
                    "kind": "identity_tension",
                    "severity": "medium",
                    "reason": reason,
                    "attachment_ids": sorted(pair),
                    "source_signals": [
                        {"id": item.get("id"), "confidence": item.get("confidence"), "fragility": item.get("fragility"), "adjudication_state": item.get("adjudication_state")}
                        for item in attachments
                        if item.get("id") in pair
                    ],
                }
            )
    if attachments:
        top = attachments[0]
        if float(top.get("prior_weight") or 0.0) > 0.8 and int(top.get("evidence_count") or 0) == 0:
            threats.append(
                {
                    "kind": "prior_dominance",
                    "severity": "medium",
                    "reason": "persona prior outweighs memory evidence",
                    "attachment_ids": [top.get("id")],
                    "source_signals": [
                        {
                            "id": top.get("id"),
                            "prior_weight": top.get("prior_weight"),
                            "evidence_count": top.get("evidence_count"),
                            "fragility": top.get("fragility"),
                            "adjudication_state": top.get("adjudication_state"),
                        }
                    ],
                }
            )
    if not attachments:
        threats.append(
            {
                "kind": "insufficient_evidence",
                "severity": "high",
                "reason": "no stable self-model could be assembled",
                "attachment_ids": [],
                "source_signals": [],
            }
        )
    return {
        "schema": THREAT_FEED_SCHEMA,
        "snapshot_id": snapshot.get("snapshot_id"),
        "generated_at": _utcnow_iso(),
        "threats": threats,
        "threat_count": len(threats),
        "provenance": {
            "derived": True,
            "authoritative": False,
            "derivation_version": DERIVATION_VERSION,
            "snapshot_source_digest": snapshot.get("source_digest"),
        },
    }


def compare_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_map = {str(item.get("id")): item for item in list(before.get("attachments") or [])}
    after_map = {str(item.get("id")): item for item in list(after.get("attachments") or [])}
    before_ids = set(before_map)
    after_ids = set(after_map)
    changed: List[Dict[str, Any]] = []
    risk_flags: List[str] = []
    for stance_id in sorted(before_ids & after_ids):
        b = float(before_map[stance_id].get("attachment_score") or 0.0)
        a = float(after_map[stance_id].get("attachment_score") or 0.0)
        before_state = before_map[stance_id].get("adjudication_state")
        after_state = after_map[stance_id].get("adjudication_state")
        state_changed = before_state is not None and after_state is not None and before_state != after_state
        if round(a - b, 3) != 0 or state_changed:
            delta = round(a - b, 3)
            changed.append({
                "id": stance_id,
                "before_score": round(b, 3),
                "after_score": round(a, 3),
                "delta": delta,
                "before_confidence": before_map[stance_id].get("confidence"),
                "after_confidence": after_map[stance_id].get("confidence"),
                "fragility": after_map[stance_id].get("fragility") or before_map[stance_id].get("fragility"),
                "before_state": before_map[stance_id].get("adjudication_state"),
                "after_state": after_map[stance_id].get("adjudication_state"),
            })
            if abs(delta) >= 0.35:
                risk_flags.append(f"large_delta:{stance_id}")
            if (after_map[stance_id].get("fragility") or before_map[stance_id].get("fragility")) == "fragile":
                risk_flags.append(f"fragile_claim:{stance_id}")
            if state_changed:
                risk_flags.append(f"state_transition:{stance_id}:{before_state}->{after_state}")
    if before.get("source_digest") == after.get("source_digest") and not changed and before_ids == after_ids:
        drift_class = "no_op"
    elif any(flag.startswith("large_delta:") for flag in risk_flags):
        drift_class = "suspicious"
    else:
        drift_class = "organic"
    return {
        "schema": DIFF_SCHEMA,
        "generated_at": _utcnow_iso(),
        "from_snapshot_id": before.get("snapshot_id"),
        "to_snapshot_id": after.get("snapshot_id"),
        "drift_class": drift_class,
        "added": [after_map[x] for x in sorted(after_ids - before_ids)],
        "removed": [before_map[x] for x in sorted(before_ids - after_ids)],
        "changed": changed,
        "risk_flags": sorted(set(risk_flags)),
        "summary": {
            "added": len(after_ids - before_ids),
            "removed": len(before_ids - after_ids),
            "changed": len(changed),
        },
        "provenance": {
            "derived": True,
            "authoritative": False,
            "derivation_version": DERIVATION_VERSION,
            "arbiter_policy": "openclaw-mem-memory-of-record-wins",
            "from_source_digest": before.get("source_digest"),
            "to_source_digest": after.get("source_digest"),
        },
    }


def persist_snapshot(snapshot: Dict[str, Any], run_dir: Optional[str] = None, *, update_latest: bool = True) -> Dict[str, str]:
    root = Path(run_dir or default_run_dir())
    snapshots_dir = _mkdir(root / "snapshots")
    snapshot_path = snapshots_dir / f"{snapshot['snapshot_id']}.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = {"snapshot_path": str(snapshot_path)}
    if update_latest:
        latest_path = snapshots_dir / "latest.json"
        latest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths["latest_path"] = str(latest_path)
    return paths


def load_snapshot(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_latest_snapshot(run_dir: Optional[str]) -> Optional[Dict[str, Any]]:
    latest_path = Path(run_dir or default_run_dir()) / "snapshots" / "latest.json"
    if not latest_path.exists():
        return None
    return load_snapshot(str(latest_path))


def write_release_receipt(
    *,
    run_dir: Optional[str],
    stance_id: str,
    reason: str,
    mode: str,
    factor: float,
    operator: Optional[str],
    scope: Optional[str],
    session_id: Optional[str],
) -> Dict[str, Any]:
    released_at = _utcnow_iso()
    receipt = {
        "schema": RELEASE_RECEIPT_SCHEMA,
        "receipt_id": f"release:v0:{hashlib.sha256((stance_id + released_at + reason).encode('utf-8')).hexdigest()[:16]}",
        "released_at": released_at,
        "stance_id": stance_id,
        "reason": reason,
        "mode": mode,
        "factor": round(factor, 3),
        "operator": operator,
        "scope": scope,
        "session_id": session_id,
        "provenance": {
            "derived": False,
            "authoritative": True,
            "derivation_version": "release_receipt_v0",
        },
    }
    releases_dir = _mkdir(Path(run_dir or default_run_dir()) / "releases")
    fname = f"{released_at.replace(':', '').replace('+', '_').replace('-', '')}__{_slug(stance_id)}.json"
    path = releases_dir / fname
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["path"] = str(path)
    return receipt


def compare_migration(
    conn: sqlite3.Connection,
    *,
    scope: Optional[str],
    session_id: Optional[str],
    limit: int,
    baseline_persona_file: Optional[str],
    candidate_persona_file: Optional[str],
    observations_file: Optional[str],
    episodes_file: Optional[str],
    run_dir: Optional[str],
) -> Dict[str, Any]:
    with _db_readonly_guard(conn):
        before = build_snapshot(
            conn,
            scope=scope,
            session_id=session_id,
            limit=limit,
            persona_file=baseline_persona_file,
            observations_file=observations_file,
            episodes_file=episodes_file,
            run_dir=run_dir,
        )
        after = build_snapshot(
            conn,
            scope=scope,
            session_id=session_id,
            limit=limit,
            persona_file=candidate_persona_file,
            observations_file=observations_file,
            episodes_file=episodes_file,
            run_dir=run_dir,
        )
    diff = compare_snapshots(before, after)
    return {
        "schema": COMPARE_MIGRATION_SCHEMA,
        "generated_at": _utcnow_iso(),
        "baseline": before,
        "candidate": after,
        "diff": diff,
        "provenance": {
            "derived": True,
            "authoritative": False,
            "derivation_version": DERIVATION_VERSION,
            "query_only_enforced": True,
        },
    }


def run_autonomous_cycle(
    conn: sqlite3.Connection,
    *,
    scope: Optional[str],
    session_id: Optional[str],
    limit: int,
    persona_file: Optional[str],
    observations_file: Optional[str],
    episodes_file: Optional[str],
    run_dir: Optional[str],
    cycles: int,
    interval_seconds: float,
    dry_run: bool,
) -> Dict[str, Any]:
    control = load_control_config(run_dir)
    if not dry_run and not bool(control.get("enabled")):
        return {
            "schema": AUTORUN_SCHEMA,
            "generated_at": _utcnow_iso(),
            "ok": False,
            "reason": "continuity side-car is disabled",
            "control": control,
            "runs": [],
        }

    receipts_dir = _mkdir(Path(run_dir or default_run_dir()) / "autorun")
    runs: List[Dict[str, Any]] = []
    previous = load_latest_snapshot(run_dir)
    with _db_readonly_guard(conn):
        for index in range(max(1, int(cycles))):
            snapshot = build_snapshot(
                conn,
                scope=scope,
                session_id=session_id,
                limit=limit,
                persona_file=persona_file,
                observations_file=observations_file,
                episodes_file=episodes_file,
                run_dir=run_dir,
            )
            diff = compare_snapshots(previous, snapshot) if previous else None
            receipt = {
                "schema": AUTORUN_SCHEMA,
                "generated_at": _utcnow_iso(),
                "run_index": index + 1,
                "dry_run": bool(dry_run),
                "snapshot_id": snapshot["snapshot_id"],
                "persisted": False,
                "diff_summary": diff["summary"] if diff else None,
                "provenance": {
                    "derived": True,
                    "authoritative": False,
                    "derivation_version": DERIVATION_VERSION,
                    "query_only_enforced": True,
                },
            }
            if not dry_run and bool(control.get("persist_on_run", True)):
                persisted = persist_snapshot(snapshot, run_dir, update_latest=True)
                receipt["persisted"] = True
                receipt["snapshot_path"] = persisted["snapshot_path"]
                if "latest_path" in persisted:
                    receipt["latest_path"] = persisted["latest_path"]
            receipt_path = receipts_dir / f"run-{int(time.time() * 1000)}-{index + 1}.json"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            receipt["receipt_path"] = str(receipt_path)
            runs.append(receipt)
            previous = snapshot
            if index + 1 < max(1, int(cycles)) and interval_seconds > 0:
                time.sleep(interval_seconds)
    return {
        "schema": AUTORUN_SCHEMA,
        "generated_at": _utcnow_iso(),
        "ok": True,
        "dry_run": bool(dry_run),
        "control": control,
        "runs": runs,
        "residue": _state_residue_summary(run_dir),
    }
