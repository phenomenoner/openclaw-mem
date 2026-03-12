from __future__ import annotations

import re
from typing import Any, Dict, Mapping

PROVENANCE_TRUST_SCHEMA_V1_KIND = "openclaw-mem.provenance-trust.v1"

TRUST_TIER_UNKNOWN = "unknown"
TRUST_TIERS = ("trusted", "untrusted", "quarantined")

PROVENANCE_KINDS = ("none", "url", "file_line", "file_anchor", "receipt", "opaque")

_PROVENANCE_LINE_RE = re.compile(r"^(?P<path>[^#]+)#L(?P<start>\d+)(?:-(?:L)?(?P<end>\d+))?$")
_PROVENANCE_ANCHOR_RE = re.compile(r"^(?P<path>[^#]+)#(?P<anchor>[^\s#]+)$")
_PROVENANCE_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_PROVENANCE_RECEIPT_RE = re.compile(r"^(?:receipt:|graph_refresh_receipt:)[^\s]+$")

_TRUST_ALIASES = {
    "quarantine": "quarantined",
}

_PROVENANCE_KIND_ALIASES = {
    "fileline": "file_line",
    "file-line": "file_line",
    "fileanchor": "file_anchor",
    "file-anchor": "file_anchor",
}


def normalize_trust_tier(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None

    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    key = _TRUST_ALIASES.get(key, key)
    if key in TRUST_TIERS:
        return key
    return None


def normalize_provenance_kind(raw: Any) -> str:
    token = str(raw or "").strip().lower().replace("-", "_")
    if not token:
        return "none"
    token = _PROVENANCE_KIND_ALIASES.get(token, token)
    if token in PROVENANCE_KINDS:
        return token
    return "opaque"


def normalize_provenance_kind_counts(raw: Any) -> Dict[str, int]:
    src = raw if isinstance(raw, Mapping) else {}
    out: Dict[str, int] = {}
    for key in sorted(src.keys(), key=lambda x: str(x)):
        try:
            count = int(src.get(key, 0))
        except Exception:
            count = 0
        if count <= 0:
            continue
        kind = normalize_provenance_kind(key)
        out[kind] = int(out.get(kind, 0)) + int(count)
    return {k: int(out[k]) for k in sorted(out.keys())}


def parse_provenance_ref(raw: Any) -> Dict[str, Any]:
    token = str(raw or "").strip()
    out: Dict[str, Any] = {
        "raw": token,
        "kind": "none",
        "is_structured": False,
        "path": None,
        "line_start": None,
        "line_end": None,
        "anchor": None,
        "url": None,
    }
    if not token:
        return out

    if _PROVENANCE_URL_RE.match(token):
        out.update({"kind": "url", "is_structured": True, "url": token})
        return out

    line_match = _PROVENANCE_LINE_RE.match(token)
    if line_match:
        line_start = int(line_match.group("start"))
        line_end_raw = line_match.group("end")
        line_end = int(line_end_raw) if line_end_raw is not None else line_start
        if line_end < line_start:
            line_end = line_start
        out.update(
            {
                "kind": "file_line",
                "is_structured": True,
                "path": line_match.group("path").strip(),
                "line_start": line_start,
                "line_end": line_end,
            }
        )
        return out

    anchor_match = _PROVENANCE_ANCHOR_RE.match(token)
    if anchor_match:
        out.update(
            {
                "kind": "file_anchor",
                "is_structured": True,
                "path": anchor_match.group("path").strip(),
                "anchor": anchor_match.group("anchor").strip(),
            }
        )
        return out

    if _PROVENANCE_RECEIPT_RE.match(token):
        out.update({"kind": "receipt", "is_structured": True})
        return out

    out.update({"kind": "opaque", "is_structured": False})
    return out
