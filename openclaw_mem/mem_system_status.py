"""Read-only OpenClaw Mem system status surface."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "openclaw-mem.system-status.v0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exists(path: str | Path) -> bool:
    return Path(path).expanduser().exists()


def build_status(*, workspace_root: str | Path = ".", state_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    state = Path(state_root).expanduser().resolve() if state_root else Path.home() / ".openclaw"
    mem = state / "memory"
    surfaces = [
        {
            "plane": "Store",
            "surface_id": "store.sqlite",
            "state": "stable" if _exists(mem / "openclaw-mem.sqlite") else "shadow",
            "path_hint": "memory/openclaw-mem.sqlite",
        },
        {
            "plane": "Store",
            "surface_id": "store.lancedb",
            "state": "stable" if _exists(mem / "lancedb") else "shadow",
            "path_hint": "memory/lancedb",
        },
        {
            "plane": "Pack",
            "surface_id": "pack.context-pack",
            "state": "stable" if _exists(root / "openclaw_mem" / "context_pack_v1.py") else "shadow",
            "path_hint": "openclaw_mem/context_pack_v1.py",
        },
        {
            "plane": "Pack",
            "surface_id": "pack.goal",
            "state": "lab" if _exists(root / "openclaw_mem" / "goal_primitive.py") else "shadow",
            "path_hint": "openclaw_mem/goal_primitive.py",
        },
        {
            "plane": "Observe",
            "surface_id": "observe.episodes",
            "state": "stable" if _exists(mem / "openclaw-mem-episodes.jsonl") else "shadow",
            "path_hint": "memory/openclaw-mem-episodes.jsonl",
        },
        {
            "plane": "Review",
            "surface_id": "review.steward",
            "state": "stable" if _exists(root / "openclaw_mem" / "steward_review.py") else "shadow",
            "path_hint": "openclaw_mem/steward_review.py",
        },
        {
            "plane": "Review",
            "surface_id": "review.skill-curator",
            "state": "lab" if _exists(root / "openclaw_mem" / "self_curator.py") else "shadow",
            "path_hint": "openclaw_mem/self_curator.py",
        },
        {
            "plane": "Curate",
            "surface_id": "curate.dream-lite",
            "state": "lab",
            "path_hint": "openclaw-mem dream-lite",
        },
        {
            "plane": "Curate",
            "surface_id": "curate.skill-capture",
            "state": "lab" if _exists(root / "openclaw_mem" / "skill_capture.py") else "shadow",
            "path_hint": "openclaw_mem/skill_capture.py",
        },
    ]
    counts: dict[str, int] = {}
    for item in surfaces:
        key = str(item["state"])
        counts[key] = counts.get(key, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "writes_performed": False,
        "workspace_root": str(root),
        "state_root": str(state),
        "planes": ["Store", "Pack", "Observe", "Review", "Curate"],
        "surface_count": len(surfaces),
        "counts_by_state": counts,
        "surfaces": surfaces,
        "topology_changed": False,
        "checked_at": now_iso(),
    }


def render_status(status: Mapping[str, Any]) -> str:
    counts = status.get("counts_by_state") if isinstance(status.get("counts_by_state"), Mapping) else {}
    return (
        f"mem_system_status surfaces={status.get('surface_count')} "
        f"states={dict(counts)} writes_performed=false topology_changed=false"
    )
