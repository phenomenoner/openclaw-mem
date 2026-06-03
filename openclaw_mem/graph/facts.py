from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from openclaw_mem import context_pack_v1


FACT_SCHEMA = "openclaw-mem.graph.fact.v0"
PREDICATE_REGISTRY_SCHEMA = "openclaw-mem.graph.fact.predicate-registry.v0"
FACT_PACK_KIND = "openclaw-mem.graph.fact.pack.v0"
FACT_ROUTE_KIND = "openclaw-mem.graph.fact.route.v0"
EXTRACTION_PROPOSAL_KIND = "openclaw-mem.graph.fact.extraction-proposal.v0"
EXTRACTION_MEASURE_KIND = "openclaw-mem.graph.fact.extraction-measure.v0"

ACTIVE_STATUSES = {"active"}
NON_CURRENT_STATUSES = {"superseded", "invalidated", "retracted"}
SUPPORTED_SOURCE_KINDS = {"receipt", "doc", "memory", "daily_log", "episodic"}
CONFIDENCE_ORDER = {
    "low": 0,
    "source_capped": 1,
    "corroborated": 2,
    "operator_asserted": 3,
}


@dataclass(frozen=True)
class PredicateDef:
    id: str
    cardinality: str
    object_types: Tuple[str, ...]
    aliases: Tuple[str, ...]
    conflict_behavior: str
    source_tier_floor: Optional[str] = None


PREDICATE_REGISTRY: Dict[str, PredicateDef] = {
    "owns": PredicateDef(
        id="owns",
        cardinality="multi",
        object_types=("entity_ref", "literal"),
        aliases=("owner_of",),
        conflict_behavior="append",
    ),
    "uses": PredicateDef(
        id="uses",
        cardinality="multi",
        object_types=("entity_ref", "literal"),
        aliases=("runs_on", "uses_tool"),
        conflict_behavior="append",
    ),
    "depends_on": PredicateDef(
        id="depends_on",
        cardinality="multi",
        object_types=("entity_ref", "literal"),
        aliases=("requires", "depends"),
        conflict_behavior="append",
    ),
    "replaces": PredicateDef(
        id="replaces",
        cardinality="multi",
        object_types=("entity_ref", "literal"),
        aliases=("supersedes",),
        conflict_behavior="append",
    ),
    "status": PredicateDef(
        id="status",
        cardinality="single",
        object_types=("literal",),
        aliases=("state",),
        conflict_behavior="supersede_or_conflict",
    ),
    "configured_as": PredicateDef(
        id="configured_as",
        cardinality="single",
        object_types=("literal", "json"),
        aliases=("config", "configuration"),
        conflict_behavior="supersede_or_conflict",
    ),
    "decision": PredicateDef(
        id="decision",
        cardinality="multi",
        object_types=("literal", "json"),
        aliases=("decides",),
        conflict_behavior="append",
    ),
    "source_of_truth": PredicateDef(
        id="source_of_truth",
        cardinality="single",
        object_types=("literal", "entity_ref"),
        aliases=("truth_owner", "canonical_source"),
        conflict_behavior="supersede_or_conflict",
    ),
    "retired_by": PredicateDef(
        id="retired_by",
        cardinality="single",
        object_types=("entity_ref", "literal"),
        aliases=("deprecated_by",),
        conflict_behavior="supersede_or_conflict",
    ),
}

_PREDICATE_ALIASES: Dict[str, str] = {}
for _pred_id, _pred in PREDICATE_REGISTRY.items():
    _PREDICATE_ALIASES[_pred_id] = _pred_id
    for _alias in _pred.aliases:
        _PREDICATE_ALIASES[_alias] = _pred_id


@dataclass(frozen=True)
class SourceRef:
    kind: str
    ref: str
    locator: Optional[str] = None

    def token(self) -> str:
        base = f"{self.kind}:{self.ref}"
        if self.locator:
            return f"{base}#{self.locator}"
        return base


@dataclass(frozen=True)
class SourceResolution:
    source: SourceRef
    resolved: bool
    reason: str
    digest: Optional[str] = None
    locator: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": asdict(self.source),
            "resolved": self.resolved,
            "reason": self.reason,
            "digest": self.digest,
            "locator": self.locator,
            "meta": dict(self.meta or {}),
        }


@dataclass(frozen=True)
class FactObject:
    type: str
    value: Any


@dataclass(frozen=True)
class AssertionRef:
    kind: str
    ref: str

    def token(self) -> str:
        return f"{self.kind}:{self.ref}"


@dataclass(frozen=True)
class FactRecord:
    id: str
    subject_ref: str
    subject_label: str
    predicate: str
    object: FactObject
    valid_from: str
    valid_to: Optional[str]
    status: str
    confidence_tier: str
    source_refs: Tuple[SourceRef, ...]
    assertion_ref: AssertionRef
    supersedes: Tuple[str, ...]
    superseded_by: Tuple[str, ...]
    created_at: str
    asserted_by: str
    source_snapshots: Tuple[SourceResolution, ...]


class FactValidationError(ValueError):
    def __init__(self, message: str, *, issues: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.issues = list(issues or [])


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def predicate_registry_payload() -> Dict[str, Any]:
    return {
        "schema": PREDICATE_REGISTRY_SCHEMA,
        "predicates": {
            key: {
                "cardinality": value.cardinality,
                "object_types": list(value.object_types),
                "aliases": list(value.aliases),
                "conflict_behavior": value.conflict_behavior,
                "source_tier_floor": value.source_tier_floor,
            }
            for key, value in sorted(PREDICATE_REGISTRY.items())
        },
    }


def ensure_fact_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_facts (
          id TEXT PRIMARY KEY,
          schema TEXT NOT NULL,
          subject_ref TEXT NOT NULL,
          subject_label TEXT NOT NULL,
          predicate TEXT NOT NULL,
          object_type TEXT NOT NULL,
          object_json TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT,
          status TEXT NOT NULL,
          confidence_tier TEXT NOT NULL,
          source_refs_json TEXT NOT NULL,
          assertion_ref_json TEXT NOT NULL,
          supersedes_json TEXT NOT NULL,
          superseded_by_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          asserted_by TEXT NOT NULL,
          source_snapshots_json TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_facts_subject ON graph_facts(subject_ref, predicate)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_facts_status ON graph_facts(status)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_fact_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO graph_fact_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("schema", FACT_SCHEMA),
    )


def normalize_subject_ref(raw: str) -> str:
    token = str(raw or "").strip()
    if not token:
        raise FactValidationError("subject ref is required")
    if ":" not in token:
        token = "entity:" + _slug(token)
    return token


def normalize_predicate(raw: str) -> str:
    token = _slug(str(raw or "").strip().replace("-", "_"))
    if not token:
        raise FactValidationError("predicate is required")
    canonical = _PREDICATE_ALIASES.get(token)
    if not canonical:
        raise FactValidationError(
            f"unknown predicate: {raw}",
            issues=[{"code": "unknown_predicate", "predicate": raw, "severity": "error"}],
        )
    return canonical


def parse_iso8601(raw: Any, *, field_name: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise FactValidationError(f"{field_name} is required")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = text + "T00:00:00Z"
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise FactValidationError(f"{field_name} must be ISO-8601") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def parse_optional_iso8601(raw: Any, *, field_name: str) -> Optional[str]:
    if raw is None or str(raw).strip() == "":
        return None
    return parse_iso8601(raw, field_name=field_name)


def parse_source_ref(raw: Any) -> SourceRef:
    if isinstance(raw, dict):
        kind = str(raw.get("kind") or "").strip().lower()
        ref = str(raw.get("ref") or "").strip()
        locator = raw.get("locator")
        locator_s = str(locator).strip() if locator is not None and str(locator).strip() else None
        if not kind and ref.startswith("obs:"):
            kind = "receipt"
        if not kind or not ref:
            raise FactValidationError("source ref requires kind and ref")
        return SourceRef(kind=kind, ref=ref, locator=locator_s)

    token = str(raw or "").strip()
    if not token:
        raise FactValidationError("source ref is required")
    if token.startswith("obs:"):
        return SourceRef(kind="receipt", ref=token)
    if ":" not in token:
        raise FactValidationError(f"source ref must be kind:ref: {token}")
    kind, rest = token.split(":", 1)
    kind = kind.strip().lower()
    rest = rest.strip()
    locator = None
    if "#" in rest:
        rest, locator = rest.split("#", 1)
        locator = locator.strip() or None
    if not kind or not rest:
        raise FactValidationError(f"source ref must be kind:ref: {token}")
    return SourceRef(kind=kind, ref=rest, locator=locator)


def parse_assertion_ref(raw: Any) -> AssertionRef:
    if isinstance(raw, dict):
        kind = str(raw.get("kind") or "receipt").strip().lower()
        ref = str(raw.get("ref") or "").strip()
        if not ref:
            raise FactValidationError("assertion ref is required")
        return AssertionRef(kind=kind or "receipt", ref=ref)
    token = str(raw or "").strip()
    if not token:
        raise FactValidationError("assertion ref is required")
    if ":" not in token:
        return AssertionRef(kind="receipt", ref=token)
    kind, ref = token.split(":", 1)
    return AssertionRef(kind=kind.strip().lower() or "receipt", ref=ref.strip())


def normalize_fact_object(predicate: str, object_type: str, raw_value: Any) -> FactObject:
    object_type = str(object_type or "").strip().lower()
    pred = PREDICATE_REGISTRY.get(predicate)
    if pred is None:
        raise FactValidationError(f"unknown predicate: {predicate}")
    if object_type not in pred.object_types:
        raise FactValidationError(
            f"object type {object_type!r} is not allowed for predicate {predicate}",
            issues=[
                {
                    "code": "object_type_mismatch",
                    "predicate": predicate,
                    "object_type": object_type,
                    "allowed": list(pred.object_types),
                    "severity": "error",
                }
            ],
        )
    if object_type == "json":
        if isinstance(raw_value, str):
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise FactValidationError("json object value must parse as JSON") from exc
        else:
            value = raw_value
    else:
        value = str(raw_value or "").strip()
        if not value:
            raise FactValidationError("object value is required")
        if object_type == "entity_ref" and ":" not in value:
            value = "entity:" + _slug(value)
    return FactObject(type=object_type, value=value)


def resolve_source_ref(
    conn: Optional[sqlite3.Connection],
    source: SourceRef,
    *,
    source_root: Optional[str | Path] = None,
) -> SourceResolution:
    if source.kind not in SUPPORTED_SOURCE_KINDS:
        return SourceResolution(source=source, resolved=False, reason="unsupported_kind")

    if source.kind == "receipt" and source.ref.startswith("obs:"):
        if conn is None:
            return SourceResolution(source=source, resolved=False, reason="sqlite_unavailable")
        try:
            obs_id = int(source.ref.split(":", 1)[1])
        except ValueError:
            return SourceResolution(source=source, resolved=False, reason="bad_observation_ref")
        try:
            row = conn.execute(
                "SELECT id, ts, kind, tool_name, summary, detail_json FROM observations WHERE id = ?",
                (obs_id,),
            ).fetchone()
        except sqlite3.Error:
            return SourceResolution(source=source, resolved=False, reason="observations_table_unavailable")
        if row is None:
            return SourceResolution(source=source, resolved=False, reason="observation_missing")
        digest_payload = {
            "id": int(row["id"]),
            "ts": row["ts"],
            "kind": row["kind"],
            "tool_name": row["tool_name"],
            "summary": row["summary"],
            "detail_json": row["detail_json"],
        }
        return SourceResolution(
            source=source,
            resolved=True,
            reason="ok",
            digest=_sha256_json(digest_payload),
            locator=source.locator,
            meta={"resolver": "sqlite.observations"},
        )

    path = _resolve_source_path(source.ref, source_root=source_root)
    if not path.exists():
        return SourceResolution(source=source, resolved=False, reason="file_missing", locator=source.locator)
    if not path.is_file():
        return SourceResolution(source=source, resolved=False, reason="not_a_file", locator=source.locator)
    return SourceResolution(
        source=source,
        resolved=True,
        reason="ok",
        digest=_sha256_file(path),
        locator=source.locator,
        meta={"resolver": "file", "size": path.stat().st_size},
    )


def resolve_sources(
    conn: Optional[sqlite3.Connection],
    sources: Sequence[SourceRef],
    *,
    source_root: Optional[str | Path] = None,
) -> Tuple[SourceResolution, ...]:
    return tuple(resolve_source_ref(conn, source, source_root=source_root) for source in sources)


def source_confidence_cap(resolutions: Sequence[SourceResolution]) -> str:
    resolved_by_token = {item.source.token(): item for item in resolutions if item.resolved}
    resolved = list(resolved_by_token.values())
    if not resolved:
        return "low"
    kinds = {item.source.kind for item in resolved}
    if "receipt" in kinds:
        return "operator_asserted"
    if len(resolved_by_token) >= 2:
        return "corroborated"
    return "source_capped"


def build_fact_record(
    *,
    conn: Optional[sqlite3.Connection],
    subject_ref: str,
    subject_label: Optional[str],
    predicate: str,
    object_type: str,
    object_value: Any,
    valid_from: Any,
    valid_to: Any = None,
    status: str = "active",
    confidence_tier: str = "source_capped",
    source_refs: Sequence[Any],
    assertion_ref: Any,
    supersedes: Optional[Sequence[str]] = None,
    superseded_by: Optional[Sequence[str]] = None,
    created_at: Optional[str] = None,
    asserted_by: str = "operator",
    source_root: Optional[str | Path] = None,
    require_resolved_sources: bool = True,
) -> FactRecord:
    subject = normalize_subject_ref(subject_ref)
    pred = normalize_predicate(predicate)
    obj = normalize_fact_object(pred, object_type, object_value)
    vf = parse_iso8601(valid_from, field_name="valid_from")
    vt = parse_optional_iso8601(valid_to, field_name="valid_to")
    if vt is not None and _dt(vf) > _dt(vt):
        raise FactValidationError(
            "valid_from must be <= valid_to",
            issues=[{"code": "interval_invalid", "severity": "error"}],
        )
    status = str(status or "active").strip().lower()
    if status not in ACTIVE_STATUSES | NON_CURRENT_STATUSES | {"stale"}:
        raise FactValidationError(f"unsupported fact status: {status}")
    confidence = str(confidence_tier or "").strip().lower()
    if confidence not in CONFIDENCE_ORDER:
        raise FactValidationError(f"unsupported confidence tier: {confidence_tier}")
    parsed_sources = _dedupe_source_refs(parse_source_ref(item) for item in source_refs)
    if not parsed_sources:
        raise FactValidationError(
            "at least one source ref is required",
            issues=[{"code": "missing_source_refs", "severity": "error"}],
        )
    assertion = parse_assertion_ref(assertion_ref)
    source_snapshots = resolve_sources(conn, parsed_sources, source_root=source_root)
    dangling = [item.to_dict() for item in source_snapshots if not item.resolved]
    if dangling and require_resolved_sources:
        raise FactValidationError(
            "source refs must resolve",
            issues=[
                {
                    "code": "dangling_source_ref",
                    "severity": "error",
                    "source_resolutions": dangling,
                }
            ],
        )
    cap = source_confidence_cap(source_snapshots)
    if CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER[cap]:
        raise FactValidationError(
            "confidence tier exceeds source cap",
            issues=[
                {
                    "code": "confidence_exceeds_source_cap",
                    "severity": "error",
                    "confidence_tier": confidence,
                    "source_cap": cap,
                }
            ],
        )
    created = parse_iso8601(created_at, field_name="created_at") if created_at else utcnow_iso()
    supersedes_tuple = tuple(sorted({str(x).strip() for x in list(supersedes or []) if str(x).strip()}))
    superseded_by_tuple = tuple(sorted({str(x).strip() for x in list(superseded_by or []) if str(x).strip()}))
    fact_id = stable_fact_id(
        subject_ref=subject,
        predicate=pred,
        object=obj,
        valid_from=vf,
        valid_to=vt,
        source_refs=parsed_sources,
        assertion_ref=assertion,
    )
    return FactRecord(
        id=fact_id,
        subject_ref=subject,
        subject_label=(str(subject_label or "").strip() or subject),
        predicate=pred,
        object=obj,
        valid_from=vf,
        valid_to=vt,
        status=status,
        confidence_tier=confidence,
        source_refs=parsed_sources,
        assertion_ref=assertion,
        supersedes=supersedes_tuple,
        superseded_by=superseded_by_tuple,
        created_at=created,
        asserted_by=str(asserted_by or "operator").strip() or "operator",
        source_snapshots=source_snapshots,
    )


def stable_fact_id(
    *,
    subject_ref: str,
    predicate: str,
    object: FactObject,
    valid_from: str,
    valid_to: Optional[str],
    source_refs: Sequence[SourceRef],
    assertion_ref: AssertionRef,
) -> str:
    payload = {
        "schema": FACT_SCHEMA,
        "subject_ref": subject_ref,
        "predicate": predicate,
        "object": _canonical_jsonable(asdict(object)),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source_refs": sorted(source.token() for source in source_refs),
        "assertion_ref": assertion_ref.token(),
    }
    return "fact_" + _sha256_json(payload)[:20]


def store_fact(conn: sqlite3.Connection, fact: FactRecord) -> None:
    ensure_fact_schema(conn)
    conn.execute(
        """
        INSERT INTO graph_facts(
          id, schema, subject_ref, subject_label, predicate, object_type, object_json,
          valid_from, valid_to, status, confidence_tier, source_refs_json,
          assertion_ref_json, supersedes_json, superseded_by_json, created_at,
          asserted_by, source_snapshots_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          subject_label=excluded.subject_label,
          status=excluded.status,
          confidence_tier=excluded.confidence_tier,
          valid_to=excluded.valid_to,
          supersedes_json=excluded.supersedes_json,
          superseded_by_json=excluded.superseded_by_json,
          source_snapshots_json=excluded.source_snapshots_json
        """,
        _fact_row_values(fact),
    )


def assert_fact(
    conn: sqlite3.Connection,
    *,
    subject_ref: str,
    subject_label: Optional[str],
    predicate: str,
    object_type: str,
    object_value: Any,
    valid_from: Any,
    valid_to: Any = None,
    confidence_tier: str = "source_capped",
    source_refs: Sequence[Any],
    assertion_ref: Any,
    supersedes: Optional[Sequence[str]] = None,
    asserted_by: str = "operator",
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    ensure_fact_schema(conn)
    fact = build_fact_record(
        conn=conn,
        subject_ref=subject_ref,
        subject_label=subject_label,
        predicate=predicate,
        object_type=object_type,
        object_value=object_value,
        valid_from=valid_from,
        valid_to=valid_to,
        status="active",
        confidence_tier=confidence_tier,
        source_refs=source_refs,
        assertion_ref=assertion_ref,
        supersedes=supersedes,
        asserted_by=asserted_by,
        source_root=source_root,
        require_resolved_sources=True,
    )
    missing_supersedes = [item for item in fact.supersedes if get_fact(conn, item) is None]
    if missing_supersedes:
        raise FactValidationError(
            "superseded facts must exist",
            issues=[{"code": "unresolved_supersedes", "severity": "error", "fact_ids": missing_supersedes}],
        )
    _assert_no_single_value_conflict(conn, fact, source_root=source_root)
    store_fact(conn, fact)
    for old_id in fact.supersedes:
        _mark_superseded(conn, old_id, by_fact_id=fact.id, valid_to=fact.valid_from)
    conn.commit()
    return {
        "kind": "openclaw-mem.graph.fact.assert.v0",
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "writes_performed": True,
        "fact": fact_to_dict(fact),
        "source_resolutions": [item.to_dict() for item in fact.source_snapshots],
    }


def invalidate_fact(
    conn: sqlite3.Connection,
    *,
    fact_id: str,
    invalidated_at: Optional[str],
    assertion_ref: Any,
    source_refs: Sequence[Any],
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    ensure_fact_schema(conn)
    fact = get_fact(conn, fact_id)
    if fact is None:
        raise FactValidationError("fact not found", issues=[{"code": "fact_not_found", "severity": "error", "fact_id": fact_id}])
    parsed_sources = tuple(parse_source_ref(item) for item in source_refs)
    snapshots = resolve_sources(conn, parsed_sources, source_root=source_root)
    dangling = [item.to_dict() for item in snapshots if not item.resolved]
    if dangling:
        raise FactValidationError(
            "source refs must resolve",
            issues=[{"code": "dangling_source_ref", "severity": "error", "source_resolutions": dangling}],
        )
    vt = parse_iso8601(invalidated_at or utcnow_iso(), field_name="invalidated_at")
    updated = FactRecord(
        id=fact.id,
        subject_ref=fact.subject_ref,
        subject_label=fact.subject_label,
        predicate=fact.predicate,
        object=fact.object,
        valid_from=fact.valid_from,
        valid_to=vt,
        status="invalidated",
        confidence_tier=fact.confidence_tier,
        source_refs=fact.source_refs,
        assertion_ref=parse_assertion_ref(assertion_ref),
        supersedes=fact.supersedes,
        superseded_by=fact.superseded_by,
        created_at=fact.created_at,
        asserted_by=fact.asserted_by,
        source_snapshots=fact.source_snapshots,
    )
    store_fact(conn, updated)
    conn.commit()
    return {
        "kind": "openclaw-mem.graph.fact.invalidate.v0",
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "writes_performed": True,
        "fact": fact_to_dict(updated),
        "invalidation": {
            "assertion_ref": asdict(parse_assertion_ref(assertion_ref)),
            "source_resolutions": [item.to_dict() for item in snapshots],
        },
    }


def get_fact(conn: sqlite3.Connection, fact_id: str) -> Optional[FactRecord]:
    ensure_fact_schema(conn)
    row = conn.execute("SELECT * FROM graph_facts WHERE id = ?", (fact_id,)).fetchone()
    return _fact_from_row(row) if row is not None else None


def load_facts(
    conn: sqlite3.Connection,
    *,
    subject_ref: Optional[str] = None,
    predicate: Optional[str] = None,
) -> List[FactRecord]:
    ensure_fact_schema(conn)
    where: List[str] = []
    params: List[Any] = []
    if subject_ref:
        where.append("subject_ref = ?")
        params.append(normalize_subject_ref(subject_ref))
    if predicate:
        where.append("predicate = ?")
        params.append(normalize_predicate(predicate))
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = conn.execute(
        f"SELECT * FROM graph_facts {where_sql} ORDER BY subject_ref, predicate, valid_from, created_at, id",
        params,
    ).fetchall()
    return [_fact_from_row(row) for row in rows]


def current_facts(
    conn: sqlite3.Connection,
    *,
    subject_ref: str,
    as_of: Optional[str] = None,
    include_stale: bool = False,
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    as_of_iso = parse_iso8601(as_of or utcnow_iso(), field_name="as_of")
    facts = load_facts(conn, subject_ref=subject_ref)
    included: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for fact in facts:
        status = effective_fact_status(conn, fact, source_root=source_root)
        if not _is_interval_current(fact, as_of_iso):
            excluded.append({"fact_id": fact.id, "reason": "outside_interval", "status": status})
            continue
        if status in NON_CURRENT_STATUSES:
            excluded.append({"fact_id": fact.id, "reason": "non_current_status", "status": status})
            continue
        if status == "stale" and not include_stale:
            excluded.append({"fact_id": fact.id, "reason": "stale_excluded", "status": status})
            continue
        included.append(fact_to_dict(fact, effective_status=status))
    return {
        "kind": "openclaw-mem.graph.fact.current.v0",
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "subject": normalize_subject_ref(subject_ref),
        "as_of": as_of_iso,
        "include_stale": include_stale,
        "count": len(included),
        "facts": included,
        "excluded": excluded,
    }


def timeline(
    conn: sqlite3.Connection,
    *,
    subject_ref: str,
    predicate: Optional[str] = None,
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    facts = load_facts(conn, subject_ref=subject_ref, predicate=predicate)
    return {
        "kind": "openclaw-mem.graph.fact.timeline.v0",
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "subject": normalize_subject_ref(subject_ref),
        "predicate": normalize_predicate(predicate) if predicate else None,
        "count": len(facts),
        "events": [
            fact_to_dict(fact, effective_status=effective_fact_status(conn, fact, source_root=source_root))
            for fact in facts
        ],
    }


def lint_facts(
    conn: sqlite3.Connection,
    *,
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    facts = load_facts(conn)
    issues: List[Dict[str, Any]] = []
    stale_facts: List[str] = []

    for fact in facts:
        if fact.predicate not in PREDICATE_REGISTRY:
            issues.append(_issue("unknown_predicate", fact.id, severity="error", predicate=fact.predicate))
            continue
        if not fact.source_refs:
            issues.append(_issue("missing_source_refs", fact.id, severity="error"))
        if fact.valid_to is not None and _dt(fact.valid_from) > _dt(fact.valid_to):
            issues.append(_issue("interval_invalid", fact.id, severity="error"))
        resolutions = resolve_sources(conn, fact.source_refs, source_root=source_root)
        dangling = [item.to_dict() for item in resolutions if not item.resolved]
        if dangling:
            issues.append(_issue("dangling_source_ref", fact.id, severity="error", source_resolutions=dangling))
        cap = source_confidence_cap(resolutions)
        if CONFIDENCE_ORDER.get(fact.confidence_tier, 999) > CONFIDENCE_ORDER[cap]:
            issues.append(
                _issue(
                    "confidence_exceeds_source_cap",
                    fact.id,
                    severity="error",
                    confidence_tier=fact.confidence_tier,
                    source_cap=cap,
                )
            )
        stale = source_stale(fact, resolutions=resolutions)
        if stale:
            stale_facts.append(fact.id)
            issues.append(_issue("stale_source", fact.id, severity="warning"))
        for old_id in fact.supersedes:
            if get_fact(conn, old_id) is None:
                issues.append(_issue("unresolved_supersedes", fact.id, severity="error", target_fact_id=old_id))

    active_by_key: Dict[Tuple[str, str], List[FactRecord]] = {}
    for fact in facts:
        pred = PREDICATE_REGISTRY.get(fact.predicate)
        if pred is None or pred.cardinality != "single":
            continue
        status = effective_fact_status(conn, fact, source_root=source_root)
        if status != "active":
            continue
        active_by_key.setdefault((fact.subject_ref, fact.predicate), []).append(fact)
    for (subject, predicate), items in sorted(active_by_key.items()):
        for left_idx, left in enumerate(items):
            for right in items[left_idx + 1 :]:
                if _intervals_overlap(left.valid_from, left.valid_to, right.valid_from, right.valid_to):
                    if right.id in left.superseded_by or left.id in right.supersedes:
                        continue
                    issues.append(
                        _issue(
                            "single_value_interval_conflict",
                            left.id,
                            severity="error",
                            subject=subject,
                            predicate=predicate,
                            other_fact_id=right.id,
                        )
                    )

    errors = [item for item in issues if item.get("severity") == "error"]
    warnings = [item for item in issues if item.get("severity") == "warning"]
    return {
        "kind": "openclaw-mem.graph.fact.lint.v0",
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "ok": not errors,
        "counts": {
            "facts": len(facts),
            "errors": len(errors),
            "warnings": len(warnings),
            "staleFacts": len(set(stale_facts)),
        },
        "issues": issues,
    }


def stale_facts(
    conn: sqlite3.Connection,
    *,
    apply: bool = False,
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    facts = load_facts(conn)
    stale: List[Dict[str, Any]] = []
    for fact in facts:
        resolutions = resolve_sources(conn, fact.source_refs, source_root=source_root)
        if source_stale(fact, resolutions=resolutions):
            stale.append({"fact_id": fact.id, "subject": fact.subject_ref, "predicate": fact.predicate})
            if apply and fact.status == "active":
                updated = _replace_fact_status(fact, "stale")
                store_fact(conn, updated)
    if apply:
        conn.commit()
    return {
        "kind": "openclaw-mem.graph.fact.stale.v0",
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "writes_performed": bool(apply and stale),
        "count": len(stale),
        "facts": stale,
    }


def fact_pack(
    conn: sqlite3.Connection,
    *,
    subject_ref: str,
    budget_tokens: int = 1200,
    max_items: int = 20,
    include_stale: bool = False,
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    budget_tokens = max(1, int(budget_tokens))
    max_items = max(1, int(max_items))
    current = current_facts(
        conn,
        subject_ref=subject_ref,
        include_stale=include_stale,
        source_root=source_root,
    )
    fact_items = list(current.get("facts") or [])
    fact_items.sort(
        key=lambda item: (
            -CONFIDENCE_ORDER.get(str(item.get("confidence_tier") or "low"), 0),
            str(item.get("valid_from") or ""),
            str(item.get("id") or ""),
        )
    )

    lines = ["[TEMPORAL_FACTS v0]", f"Subject: {normalize_subject_ref(subject_ref)}", ""]
    included_items: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = list(current.get("excluded") or [])
    for item in fact_items:
        if len(included_items) >= max_items:
            excluded.append({"fact_id": item.get("id"), "reason": "max_items"})
            continue
        text = _fact_pack_text(item)
        projected = "\n".join(lines + [f"{len(included_items) + 1}) {text}"])
        if _estimate_tokens(projected) > budget_tokens and included_items:
            excluded.append({"fact_id": item.get("id"), "reason": "budget_exceeded"})
            continue
        lines.append(f"{len(included_items) + 1}) {text}")
        included_items.append(item)

    bundle_text = "\n".join(lines).strip() + "\n"
    context_items = [
        context_pack_v1.ContextPackV1Item(
            recordRef=str(item.get("id")),
            layer="L2",
            type="temporal_fact",
            importance="high",
            trust=str(item.get("confidence_tier") or "low"),
            text=_fact_pack_text(item),
            citations=context_pack_v1.ContextPackV1ItemCitations(
                recordRef=(item.get("assertion_ref") or {}).get("ref")
            ),
        )
        for item in included_items
    ]
    pack = context_pack_v1.ContextPackV1(
        schema=context_pack_v1.CONTEXT_PACK_V1_SCHEMA,
        meta=context_pack_v1.ContextPackV1Meta(
            ts=utcnow_iso(),
            query=f"temporal facts current truth for {normalize_subject_ref(subject_ref)}",
            scope=normalize_subject_ref(subject_ref),
            budgetTokens=budget_tokens,
            maxItems=max_items,
        ),
        bundle_text=bundle_text,
        items=context_items,
        notes=context_pack_v1.ContextPackV1Notes(
            how_to_use=["Use as cited current-truth context; do not treat stale/excluded facts as current truth."]
        ),
    )
    context_pack = context_pack_v1.to_dict(pack)
    for pack_item, fact_item in zip(context_pack.get("items", []), included_items):
        pack_item["assertionRef"] = dict(fact_item.get("assertion_ref") or {})
        pack_item["evidenceSourceRefs"] = list(fact_item.get("source_refs") or [])

    return {
        "kind": FACT_PACK_KIND,
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "context_pack": context_pack,
        "items": included_items,
        "trace": {
            "subject": normalize_subject_ref(subject_ref),
            "include_stale": include_stale,
            "budgetTokens": budget_tokens,
            "maxItems": max_items,
            "includedFactIds": [item["id"] for item in included_items],
            "excluded": excluded,
            "allIncludedHaveSources": all(bool(item.get("source_refs")) for item in included_items),
        },
        "bundle_text": bundle_text,
    }


def route_fact_query(
    conn: sqlite3.Connection,
    *,
    query: str,
    subject_ref: Optional[str] = None,
    budget_tokens: int = 1200,
    max_items: int = 20,
    source_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    query_text = str(query or "").strip()
    subject = normalize_subject_ref(subject_ref) if subject_ref else _extract_subject_from_query(query_text)
    if not subject:
        return {
            "kind": FACT_ROUTE_KIND,
            "schema": FACT_SCHEMA,
            "ts": utcnow_iso(),
            "query": query_text,
            "fact_view_used": False,
            "reason": "no_subject_detected",
            "fallback": "existing graph/search pack route",
        }
    current = current_facts(conn, subject_ref=subject, source_root=source_root)
    if not current.get("facts"):
        return {
            "kind": FACT_ROUTE_KIND,
            "schema": FACT_SCHEMA,
            "ts": utcnow_iso(),
            "query": query_text,
            "subject": subject,
            "fact_view_used": False,
            "reason": "unknown_subject_or_no_current_facts",
            "fallback": "existing graph/search pack route",
        }
    return {
        "kind": FACT_ROUTE_KIND,
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "query": query_text,
        "subject": subject,
        "fact_view_used": True,
        "pack": fact_pack(
            conn,
            subject_ref=subject,
            budget_tokens=budget_tokens,
            max_items=max_items,
            source_root=source_root,
        ),
        "receipt": {
            "fact_view_used": True,
            "visible_context_pack_receipt": True,
        },
    }


def propose_extractions(
    *,
    text: str,
    source_refs: Sequence[Any],
    max_proposals: int = 20,
) -> Dict[str, Any]:
    parsed_sources = [parse_source_ref(item) for item in source_refs]
    if not parsed_sources:
        raise FactValidationError(
            "source refs are required for extraction proposals",
            issues=[{"code": "missing_source_refs", "severity": "error"}],
        )
    proposals: List[Dict[str, Any]] = []
    for line in str(text or "").splitlines():
        match = re.search(
            r"\b(entity:[A-Za-z0-9_.:/-]+)\s+"
            r"(owns|uses|depends_on|replaces|status|configured_as|decision|source_of_truth|retired_by)\s+"
            r"(.+?)\s*$",
            line.strip(),
        )
        if not match:
            continue
        subject, predicate, value = match.groups()
        predicate = normalize_predicate(predicate)
        object_type = "entity_ref" if value.startswith("entity:") else "literal"
        if object_type not in PREDICATE_REGISTRY[predicate].object_types:
            object_type = PREDICATE_REGISTRY[predicate].object_types[0]
        value = value.strip().rstrip(".")
        proposals.append(
            {
                "schema": FACT_SCHEMA,
                "subject": {"ref": normalize_subject_ref(subject), "label": subject.split(":", 1)[1]},
                "predicate": predicate,
                "object": {"type": object_type, "value": value},
                "valid_from": None,
                "valid_to": None,
                "status": "proposed",
                "confidence_tier": "source_capped",
                "source_refs": [asdict(item) for item in parsed_sources],
                "writes_performed": False,
            }
        )
        if len(proposals) >= max(1, int(max_proposals)):
            break
    return {
        "kind": EXTRACTION_PROPOSAL_KIND,
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "writes_performed": False,
        "proposal_count": len(proposals),
        "proposals": proposals,
        "review_required": True,
    }


def measure_extraction_precision(
    *,
    corpus_rows: Sequence[Dict[str, Any]],
    golden_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    golden = {
        _triple_key(row.get("subject"), row.get("predicate"), row.get("object"))
        for row in golden_rows
        if row.get("subject") and row.get("predicate") and row.get("object") is not None
    }
    proposed: set[Tuple[str, str, str]] = set()
    for row in corpus_rows:
        payload = propose_extractions(
            text=str(row.get("text") or ""),
            source_refs=list(row.get("source_refs") or []),
            max_proposals=int(row.get("max_proposals") or 20),
        )
        for item in payload.get("proposals") or []:
            proposed.add(_triple_key(item["subject"]["ref"], item["predicate"], item["object"]["value"]))
    true_positive = len(proposed & golden)
    false_positive = len(proposed - golden)
    false_negative = len(golden - proposed)
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
    return {
        "kind": EXTRACTION_MEASURE_KIND,
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "writes_performed": False,
        "counts": {
            "golden": len(golden),
            "proposed": len(proposed),
            "truePositive": true_positive,
            "falsePositive": false_positive,
            "falseNegative": false_negative,
        },
        "precision": precision,
        "recall": recall,
        "apply_allowed": False,
    }


def rebuild_from_records(
    conn: sqlite3.Connection,
    records: Sequence[Dict[str, Any]],
    *,
    clear: bool = True,
    source_root: Optional[str | Path] = None,
    require_resolved_sources: bool = True,
) -> Dict[str, Any]:
    ensure_fact_schema(conn)
    if clear:
        conn.execute("DELETE FROM graph_facts")
    fact_ids: List[str] = []
    for record in records:
        subject = record.get("subject") if isinstance(record.get("subject"), dict) else {}
        obj = record.get("object") if isinstance(record.get("object"), dict) else {}
        assertion_ref = record.get("assertion_ref") or {"kind": "receipt", "ref": f"rebuild:{len(fact_ids) + 1}"}
        fact = build_fact_record(
            conn=conn,
            subject_ref=subject.get("ref") or record.get("subject_ref"),
            subject_label=subject.get("label") or record.get("subject_label"),
            predicate=record.get("predicate"),
            object_type=obj.get("type") or record.get("object_type"),
            object_value=obj.get("value") if "value" in obj else record.get("object_value"),
            valid_from=record.get("valid_from"),
            valid_to=record.get("valid_to"),
            status=record.get("status") or "active",
            confidence_tier=record.get("confidence_tier") or "source_capped",
            source_refs=record.get("source_refs") or [],
            assertion_ref=assertion_ref,
            supersedes=record.get("supersedes") or [],
            superseded_by=record.get("superseded_by") or [],
            created_at=record.get("created_at") or "2026-06-03T00:00:00Z",
            asserted_by=record.get("asserted_by") or "operator",
            source_root=source_root,
            require_resolved_sources=require_resolved_sources,
        )
        store_fact(conn, fact)
        fact_ids.append(fact.id)
    conn.commit()
    return {
        "kind": "openclaw-mem.graph.fact.rebuild.v0",
        "schema": FACT_SCHEMA,
        "ts": utcnow_iso(),
        "writes_performed": bool(records),
        "count": len(fact_ids),
        "fact_ids": fact_ids,
    }


def fact_to_dict(fact: FactRecord, *, effective_status: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema": FACT_SCHEMA,
        "id": fact.id,
        "subject": {"ref": fact.subject_ref, "label": fact.subject_label},
        "predicate": fact.predicate,
        "object": {"type": fact.object.type, "value": fact.object.value},
        "valid_from": fact.valid_from,
        "valid_to": fact.valid_to,
        "status": effective_status or fact.status,
        "stored_status": fact.status,
        "confidence_tier": fact.confidence_tier,
        "source_refs": [asdict(item) for item in fact.source_refs],
        "assertion_ref": asdict(fact.assertion_ref),
        "supersedes": list(fact.supersedes),
        "superseded_by": list(fact.superseded_by),
        "created_at": fact.created_at,
        "asserted_by": fact.asserted_by,
    }


def effective_fact_status(
    conn: sqlite3.Connection,
    fact: FactRecord,
    *,
    source_root: Optional[str | Path] = None,
) -> str:
    if fact.status in NON_CURRENT_STATUSES or fact.status == "stale":
        return fact.status
    resolutions = resolve_sources(conn, fact.source_refs, source_root=source_root)
    if source_stale(fact, resolutions=resolutions):
        return "stale"
    return fact.status


def source_stale(fact: FactRecord, *, resolutions: Sequence[SourceResolution]) -> bool:
    previous = {item.source.token(): item.digest for item in fact.source_snapshots if item.resolved}
    for item in resolutions:
        if not item.resolved:
            continue
        token = item.source.token()
        if token in previous and previous[token] != item.digest:
            return True
    return False


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fp:
        for line in fp:
            text = line.strip()
            if not text:
                continue
            obj = json.loads(text)
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _fact_row_values(fact: FactRecord) -> Tuple[Any, ...]:
    return (
        fact.id,
        FACT_SCHEMA,
        fact.subject_ref,
        fact.subject_label,
        fact.predicate,
        fact.object.type,
        json.dumps(fact.object.value, ensure_ascii=False, sort_keys=True),
        fact.valid_from,
        fact.valid_to,
        fact.status,
        fact.confidence_tier,
        json.dumps([asdict(item) for item in fact.source_refs], ensure_ascii=False, sort_keys=True),
        json.dumps(asdict(fact.assertion_ref), ensure_ascii=False, sort_keys=True),
        json.dumps(list(fact.supersedes), ensure_ascii=False, sort_keys=True),
        json.dumps(list(fact.superseded_by), ensure_ascii=False, sort_keys=True),
        fact.created_at,
        fact.asserted_by,
        json.dumps([item.to_dict() for item in fact.source_snapshots], ensure_ascii=False, sort_keys=True),
    )


def _dedupe_source_refs(sources: Iterable[SourceRef]) -> Tuple[SourceRef, ...]:
    out: List[SourceRef] = []
    seen: set[str] = set()
    for source in sources:
        token = source.token()
        if token in seen:
            continue
        seen.add(token)
        out.append(source)
    return tuple(out)


def _fact_from_row(row: sqlite3.Row) -> FactRecord:
    source_refs = tuple(parse_source_ref(item) for item in _json_load(row["source_refs_json"], []))
    assertion_raw = _json_load(row["assertion_ref_json"], {})
    snapshots_raw = _json_load(row["source_snapshots_json"], [])
    snapshots: List[SourceResolution] = []
    for item in snapshots_raw:
        source = parse_source_ref((item or {}).get("source") or {})
        snapshots.append(
            SourceResolution(
                source=source,
                resolved=bool((item or {}).get("resolved")),
                reason=str((item or {}).get("reason") or ""),
                digest=(item or {}).get("digest"),
                locator=(item or {}).get("locator"),
                meta=dict((item or {}).get("meta") or {}),
            )
        )
    return FactRecord(
        id=str(row["id"]),
        subject_ref=str(row["subject_ref"]),
        subject_label=str(row["subject_label"]),
        predicate=str(row["predicate"]),
        object=FactObject(type=str(row["object_type"]), value=_json_load(row["object_json"], None)),
        valid_from=str(row["valid_from"]),
        valid_to=row["valid_to"],
        status=str(row["status"]),
        confidence_tier=str(row["confidence_tier"]),
        source_refs=source_refs,
        assertion_ref=parse_assertion_ref(assertion_raw),
        supersedes=tuple(_json_load(row["supersedes_json"], [])),
        superseded_by=tuple(_json_load(row["superseded_by_json"], [])),
        created_at=str(row["created_at"]),
        asserted_by=str(row["asserted_by"]),
        source_snapshots=tuple(snapshots),
    )


def _mark_superseded(conn: sqlite3.Connection, fact_id: str, *, by_fact_id: str, valid_to: str) -> None:
    fact = get_fact(conn, fact_id)
    if fact is None:
        return
    updated_by = tuple(sorted(set(fact.superseded_by + (by_fact_id,))))
    updated = FactRecord(
        id=fact.id,
        subject_ref=fact.subject_ref,
        subject_label=fact.subject_label,
        predicate=fact.predicate,
        object=fact.object,
        valid_from=fact.valid_from,
        valid_to=fact.valid_to or valid_to,
        status="superseded",
        confidence_tier=fact.confidence_tier,
        source_refs=fact.source_refs,
        assertion_ref=fact.assertion_ref,
        supersedes=fact.supersedes,
        superseded_by=updated_by,
        created_at=fact.created_at,
        asserted_by=fact.asserted_by,
        source_snapshots=fact.source_snapshots,
    )
    store_fact(conn, updated)


def _assert_no_single_value_conflict(
    conn: sqlite3.Connection,
    fact: FactRecord,
    *,
    source_root: Optional[str | Path] = None,
) -> None:
    pred = PREDICATE_REGISTRY.get(fact.predicate)
    if pred is None or pred.cardinality != "single" or fact.status != "active":
        return
    for existing in load_facts(conn, subject_ref=fact.subject_ref, predicate=fact.predicate):
        if existing.id == fact.id:
            continue
        if existing.id in fact.supersedes:
            continue
        if effective_fact_status(conn, existing, source_root=source_root) != "active":
            continue
        if _intervals_overlap(existing.valid_from, existing.valid_to, fact.valid_from, fact.valid_to):
            raise FactValidationError(
                "single-valued predicate has overlapping active fact; use --supersedes or invalidate first",
                issues=[
                    {
                        "code": "single_value_interval_conflict",
                        "severity": "error",
                        "fact_id": fact.id,
                        "other_fact_id": existing.id,
                        "subject": fact.subject_ref,
                        "predicate": fact.predicate,
                    }
                ],
            )


def _replace_fact_status(fact: FactRecord, status: str) -> FactRecord:
    return FactRecord(
        id=fact.id,
        subject_ref=fact.subject_ref,
        subject_label=fact.subject_label,
        predicate=fact.predicate,
        object=fact.object,
        valid_from=fact.valid_from,
        valid_to=fact.valid_to,
        status=status,
        confidence_tier=fact.confidence_tier,
        source_refs=fact.source_refs,
        assertion_ref=fact.assertion_ref,
        supersedes=fact.supersedes,
        superseded_by=fact.superseded_by,
        created_at=fact.created_at,
        asserted_by=fact.asserted_by,
        source_snapshots=fact.source_snapshots,
    )


def _fact_pack_text(item: Dict[str, Any]) -> str:
    subject = (item.get("subject") or {}).get("ref") or ""
    obj = item.get("object") or {}
    source_refs = ", ".join(_source_token_from_dict(src) for src in item.get("source_refs") or [])
    return (
        f"{subject} {item.get('predicate')} = {obj.get('value')} "
        f"(status={item.get('status')}, confidence={item.get('confidence_tier')}, "
        f"valid_from={item.get('valid_from')}, sources={source_refs})"
    )


def _source_token_from_dict(item: Dict[str, Any]) -> str:
    return SourceRef(kind=str(item.get("kind")), ref=str(item.get("ref")), locator=item.get("locator")).token()


def _extract_subject_from_query(query: str) -> Optional[str]:
    match = re.search(r"\bentity:[A-Za-z0-9_.:/-]+", query or "")
    if match:
        return normalize_subject_ref(match.group(0))
    return None


def _estimate_tokens(text: str) -> int:
    return max(1, int((len(text or "") + 3) / 4))


def _issue(code: str, fact_id: str, *, severity: str, **extra: Any) -> Dict[str, Any]:
    out = {"code": code, "fact_id": fact_id, "severity": severity}
    out.update(extra)
    return out


def _is_interval_current(fact: FactRecord, as_of: str) -> bool:
    point = _dt(as_of)
    if _dt(fact.valid_from) > point:
        return False
    if fact.valid_to is not None and _dt(fact.valid_to) <= point:
        return False
    return True


def _intervals_overlap(a_from: str, a_to: Optional[str], b_from: str, b_to: Optional[str]) -> bool:
    a_start = _dt(a_from)
    b_start = _dt(b_from)
    a_end = _dt(a_to) if a_to else None
    b_end = _dt(b_to) if b_to else None
    if a_end is not None and a_end <= b_start:
        return False
    if b_end is not None and b_end <= a_start:
        return False
    return True


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc)


def _resolve_source_path(ref: str, *, source_root: Optional[str | Path]) -> Path:
    path = Path(str(ref)).expanduser()
    if path.is_absolute():
        return path
    root = Path(source_root).expanduser() if source_root else Path.cwd()
    return root / path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_json(payload: Any) -> str:
    data = json.dumps(_canonical_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _canonical_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _canonical_jsonable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_jsonable(item) for item in value]
    return value


def _json_load(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(str(raw))
    except Exception:
        return default


def _slug(text: str) -> str:
    token = str(text or "").strip().lower()
    token = re.sub(r"[^a-z0-9_.:/-]+", "-", token)
    token = token.strip("-")
    return token or "unknown"


def _triple_key(subject: Any, predicate: Any, object_value: Any) -> Tuple[str, str, str]:
    return (
        normalize_subject_ref(str(subject)),
        normalize_predicate(str(predicate)),
        str(object_value or "").strip(),
    )
