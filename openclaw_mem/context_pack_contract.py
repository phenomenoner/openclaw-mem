"""ContextPack v1 compatibility helpers.

This module is intentionally small and side-effect free so hosts can validate
or adapt pack payloads without importing CLI code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from openclaw_mem.context_pack_v1 import CONTEXT_PACK_V1_SCHEMA


REQUIRED_TOP_LEVEL = frozenset({"schema", "meta", "bundle_text", "items", "notes"})
REQUIRED_META = frozenset({"ts", "query", "scope", "budgetTokens", "maxItems"})
REQUIRED_ITEM = frozenset({"recordRef", "layer", "type", "importance", "trust", "text", "citations"})
AGENT_HARNESS_CONTEXT_PACK_SCHEMA = "agent-harness.context-pack.v1"


class ContextPackContractError(ValueError):
    """Raised when a ContextPack payload violates the compatibility contract."""


@dataclass(frozen=True)
class ContextPackValidationResult:
    ok: bool
    schema: str | None
    errors: list[str]


def validate_context_pack_v1(payload: Mapping[str, Any]) -> ContextPackValidationResult:
    errors: list[str] = []
    schema = payload.get("schema")
    missing = sorted(REQUIRED_TOP_LEVEL - set(payload))
    if missing:
        errors.append(f"missing top-level fields: {missing}")

    if schema != CONTEXT_PACK_V1_SCHEMA:
        errors.append(f"unsupported ContextPack schema: {schema!r}")

    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        errors.append("meta must be an object")
    else:
        meta_missing = sorted(REQUIRED_META - set(meta))
        if meta_missing:
            errors.append(f"missing meta fields: {meta_missing}")
        if not isinstance(meta.get("budgetTokens"), int) or int(meta.get("budgetTokens") or 0) <= 0:
            errors.append("meta.budgetTokens must be a positive integer")
        if not isinstance(meta.get("maxItems"), int) or int(meta.get("maxItems") or 0) <= 0:
            errors.append("meta.maxItems must be a positive integer")

    if not isinstance(payload.get("bundle_text"), str):
        errors.append("bundle_text must be a string")

    items = payload.get("items")
    if not isinstance(items, list):
        errors.append("items must be an array")
    else:
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                errors.append(f"items[{index}] must be an object")
                continue
            item_missing = sorted(REQUIRED_ITEM - set(item))
            if item_missing:
                errors.append(f"items[{index}] missing fields: {item_missing}")
            if not str(item.get("recordRef") or ""):
                errors.append(f"items[{index}].recordRef is required")
            if not isinstance(item.get("text"), str):
                errors.append(f"items[{index}].text must be a string")
            citations = item.get("citations")
            if not isinstance(citations, Mapping):
                errors.append(f"items[{index}].citations must be an object")
            elif not str(citations.get("recordRef") or ""):
                errors.append(f"items[{index}].citations.recordRef is required")

    notes = payload.get("notes")
    if not isinstance(notes, Mapping) or not isinstance(notes.get("how_to_use"), list):
        errors.append("notes.how_to_use must be an array")

    return ContextPackValidationResult(ok=not errors, schema=str(schema) if schema is not None else None, errors=errors)


def require_context_pack_v1(payload: Mapping[str, Any]) -> None:
    result = validate_context_pack_v1(payload)
    if not result.ok:
        raise ContextPackContractError("; ".join(result.errors))


def to_agent_harness_context_pack_v1(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable Agent Harness adapter view for an OpenClaw-mem v1 pack."""

    require_context_pack_v1(payload)
    meta = payload.get("meta") if isinstance(payload.get("meta"), Mapping) else {}
    items = []
    for item in list(payload.get("items") or []):
        citations = item.get("citations") if isinstance(item.get("citations"), Mapping) else {}
        citation_id = str(citations.get("recordRef") or item.get("recordRef") or "")
        items.append(
            {
                "citationId": citation_id,
                "source": "openclaw-mem",
                "chunk": {
                    "id": citation_id,
                    "text": str(item.get("text") or ""),
                    "sourceUri": citations.get("url"),
                },
                "recordRef": str(item.get("recordRef") or citation_id),
                "trust": str(item.get("trust") or "unknown"),
            }
        )
    return {
        "schema": AGENT_HARNESS_CONTEXT_PACK_SCHEMA,
        "sourceSchema": CONTEXT_PACK_V1_SCHEMA,
        "packId": f"openclaw-mem:{meta.get('ts')}:{meta.get('query')}",
        "query": str(meta.get("query") or ""),
        "budgetTokens": int(meta.get("budgetTokens") or 0),
        "items": items,
        "bundleText": str(payload.get("bundle_text") or ""),
    }
