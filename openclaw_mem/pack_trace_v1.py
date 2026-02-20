"""Pack trace schema (v1).

This module defines the redaction-safe, versioned `pack --trace` receipt contract.

Notes:
- The trace is intended for debugging *retrieval decisions* (why included/excluded),
  not for content export.
- Do not include raw memory content, secrets, or absolute local paths.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

PACK_TRACE_V1_KIND = "openclaw-mem.pack.trace.v1"


@dataclass(frozen=True)
class PackTraceV1Version:
    openclaw_mem: str
    schema: str = "v1"


@dataclass(frozen=True)
class PackTraceV1Query:
    text: str
    scope: Optional[str] = None
    intent: Optional[str] = None


@dataclass(frozen=True)
class PackTraceV1Budgets:
    budgetTokens: int
    maxItems: int
    maxL2Items: int
    niceCap: int


@dataclass(frozen=True)
class PackTraceV1Retriever:
    kind: str
    # Optional knobs by retriever kind.
    topK: Optional[int] = None
    k: Optional[int] = None


@dataclass(frozen=True)
class PackTraceV1Lane:
    name: str
    source: str
    searched: bool
    retrievers: List[PackTraceV1Retriever] = field(default_factory=list)


@dataclass(frozen=True)
class PackTraceV1DecisionCaps:
    niceCapHit: bool
    l2CapHit: bool


@dataclass(frozen=True)
class PackTraceV1Decision:
    included: bool
    reason: List[str]
    caps: PackTraceV1DecisionCaps


@dataclass(frozen=True)
class PackTraceV1CandidateScores:
    rrf: float
    fts: float
    semantic: float


@dataclass(frozen=True)
class PackTraceV1CandidateCitations:
    url: Optional[str]
    recordRef: str


@dataclass(frozen=True)
class PackTraceV1Candidate:
    id: str
    layer: str
    importance: str
    trust: str
    scores: PackTraceV1CandidateScores
    decision: PackTraceV1Decision
    citations: PackTraceV1CandidateCitations


@dataclass(frozen=True)
class PackTraceV1Output:
    includedCount: int
    excludedCount: int
    l2IncludedCount: int
    citationsCount: int
    refreshedRecordRefs: List[str]


@dataclass(frozen=True)
class PackTraceV1Timing:
    durationMs: int


@dataclass(frozen=True)
class PackTraceV1:
    kind: str
    ts: str
    version: PackTraceV1Version
    query: PackTraceV1Query
    budgets: PackTraceV1Budgets
    lanes: List[PackTraceV1Lane]
    candidates: List[PackTraceV1Candidate]
    output: PackTraceV1Output
    timing: PackTraceV1Timing


def to_dict(trace: PackTraceV1) -> Dict[str, Any]:
    """Serialize the trace to plain JSON-safe types."""
    return asdict(trace)
