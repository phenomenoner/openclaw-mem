"""ContextPack schema (v1).

Defines the stable, shallow JSON contract emitted by `openclaw-mem pack`.

Design goals:
- injection-friendly text plus deterministic JSON anchors
- provenance on every included item
- redaction-safe notes suitable for ops tooling and prompt assembly
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

CONTEXT_PACK_V1_SCHEMA = "openclaw-mem.context-pack.v1"


@dataclass(frozen=True)
class ContextPackV1Meta:
    ts: str
    query: str
    scope: Optional[str]
    budgetTokens: int
    maxItems: int


@dataclass(frozen=True)
class ContextPackV1ItemCitations:
    url: Optional[str] = None
    recordRef: Optional[str] = None


@dataclass(frozen=True)
class ContextPackV1Item:
    recordRef: str
    layer: str
    type: str
    importance: str
    trust: str
    text: str
    citations: ContextPackV1ItemCitations


@dataclass(frozen=True)
class ContextPackV1Notes:
    how_to_use: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContextPackV1:
    schema: str
    meta: ContextPackV1Meta
    bundle_text: str
    items: List[ContextPackV1Item]
    notes: ContextPackV1Notes


def to_dict(pack: ContextPackV1) -> Dict[str, Any]:
    return asdict(pack)
