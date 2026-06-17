"""Read-only OpenClaw Mem system status surface."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

SCHEMA_VERSION = "openclaw-mem.system-status.v0"
CORE_SQLITE_TABLES = (
    "observations",
    "docs_chunks",
    "docs_embeddings",
    "docs_chunks_fts",
    "episodic_events",
    "episodic_event_embeddings",
    "episodic_events_fts",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exists(path: str | Path) -> bool:
    return Path(path).expanduser().exists()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _get_path(data: Mapping[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key)
    return current if current is not None else default


def _config_for_plugin(config: Mapping[str, Any], plugin_id: str) -> dict[str, Any]:
    raw = _get_path(config, ("plugins", "entries", plugin_id, "config"), {})
    return dict(raw) if isinstance(raw, Mapping) else {}


def _is_enabled(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _command_readiness(command: str) -> dict[str, Any]:
    resolved = shutil.which(command)
    return {
        "command": command,
        "available": bool(resolved),
        "path": resolved,
    }


def _path_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _sqlite_uri(path: Path) -> str:
    return "file:" + quote(path.resolve().as_posix(), safe="/:") + "?mode=ro"


def _read_sqlite_counts(db_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": _path_size(db_path),
        "tables": {},
        "errors": [],
    }
    if not db_path.exists():
        return payload

    try:
        conn = sqlite3.connect(_sqlite_uri(db_path), uri=True, timeout=1.0)
    except sqlite3.Error as exc:
        payload["errors"].append(f"open_readonly_failed:{exc}")
        return payload

    try:
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
        existing = {str(row[0]) for row in table_rows}
        for table in CORE_SQLITE_TABLES:
            if table not in existing:
                payload["tables"][table] = {"exists": False, "count": None}
                continue
            try:
                count = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                payload["tables"][table] = {"exists": True, "count": count}
            except sqlite3.Error as exc:
                payload["tables"][table] = {"exists": True, "count": None, "error": str(exc)}
    except sqlite3.Error as exc:
        payload["errors"].append(f"count_failed:{exc}")
    finally:
        conn.close()

    return payload


def _build_cli_availability() -> dict[str, Any]:
    return {
        name: _command_readiness(name)
        for name in ("openclaw-mem", "uv", "gbrain")
    }


def _build_symbolic_canvas_status(
    *,
    workspace_root: Path,
    engine_config: Mapping[str, Any],
    cli_availability: Mapping[str, Any],
) -> dict[str, Any]:
    auto = _get_path(engine_config, ("symbolicCanvas", "autoBuild"), {})
    if isinstance(auto, bool):
        auto_cfg: Mapping[str, Any] = {"enabled": auto}
    elif isinstance(auto, Mapping):
        auto_cfg = auto
    else:
        auto_cfg = {}

    command = str(auto_cfg.get("command") or "openclaw-mem").strip() or "openclaw-mem"
    primary_available = bool(shutil.which(command))
    fallback_eligible = command == "openclaw-mem"
    engine_project_root = _engine_project_root(workspace_root)
    fallback_project_ready = (engine_project_root / "pyproject.toml").exists() and (engine_project_root / "openclaw_mem").is_dir()
    uv_available = bool(cli_availability.get("uv", {}).get("available")) if isinstance(cli_availability.get("uv"), Mapping) else False
    fallback_available = bool(fallback_eligible and uv_available and fallback_project_ready)

    return {
        "enabled": _is_enabled(auto_cfg.get("enabled"), False),
        "configured_command": command,
        "primary_available": primary_available,
        "fallback_eligible": fallback_eligible,
        "fallback_available": fallback_available,
        "fallback_command": [
            "uv",
            "run",
            "--project",
            str(engine_project_root),
            "--python",
            "3.13",
            "--frozen",
            "python",
            "-m",
            "openclaw_mem",
        ],
        "readiness": "ready" if primary_available or fallback_available else "missing_command",
    }


def _engine_project_root(workspace_root: Path) -> Path:
    if (workspace_root / "extensions" / "openclaw-mem-engine" / "symbolicCanvasAuto.js").exists():
        return workspace_root
    return Path(__file__).resolve().parent.parent


def _infer_state_root_from_db_path(db_path: Path) -> Path | None:
    parts = db_path.parts
    if len(parts) >= 3 and parts[-2] == "memory" and parts[-1] == "openclaw-mem.sqlite":
        return db_path.parent.parent
    return None


def build_status(
    *,
    workspace_root: str | Path = ".",
    state_root: str | Path | None = None,
    harness_home: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    resolved_db_path = Path(db_path).expanduser().resolve() if db_path else None
    inferred_state = _infer_state_root_from_db_path(resolved_db_path) if resolved_db_path else None
    if state_root:
        state = Path(state_root).expanduser().resolve()
    elif harness_home:
        state = Path(harness_home).expanduser().resolve()
    elif inferred_state:
        state = inferred_state.resolve()
    else:
        state = Path.home() / ".openclaw"
    mem = state / "memory"
    sqlite_db_path = resolved_db_path or (mem / "openclaw-mem.sqlite")
    config_path = state / "openclaw.json"
    config = _load_json(config_path)
    engine_config = _config_for_plugin(config, "openclaw-mem-engine")
    memory_slot = _get_path(config, ("plugins", "slots", "memory"), None)
    cli_availability = _build_cli_availability()
    symbolic_canvas = _build_symbolic_canvas_status(
        workspace_root=root,
        engine_config=engine_config,
        cli_availability=cli_availability,
    )
    auto_recall_enabled = _is_enabled(_get_path(engine_config, ("autoRecall", "enabled"), False), False)
    route_auto_enabled = _is_enabled(_get_path(engine_config, ("autoRecall", "routeAuto", "enabled"), False), False)
    docs_cold_lane_enabled = _is_enabled(_get_path(engine_config, ("docsColdLane", "enabled"), False), False)
    auto_capture_enabled = _is_enabled(_get_path(engine_config, ("autoCapture", "enabled"), False), False)
    gbrain_mirror_enabled = _is_enabled(_get_path(engine_config, ("gbrainMirror", "enabled"), False), False)
    working_set_enabled = _is_enabled(_get_path(engine_config, ("workingSet", "enabled"), False), False)
    route_auto_exists = (root / "extensions" / "openclaw-mem-engine" / "routeAuto.js").exists()
    docs_cold_lane_exists = (root / "extensions" / "openclaw-mem-engine" / "docsColdLane.js").exists()
    symbolic_canvas_exists = (root / "extensions" / "openclaw-mem-engine" / "symbolicCanvasAuto.js").exists()
    gbrain_mirror_exists = (root / "extensions" / "openclaw-mem-engine" / "gbrainMirror.js").exists()
    engine_index_exists = (root / "extensions" / "openclaw-mem-engine" / "index.ts").exists()
    surfaces = [
        {
            "plane": "Store",
            "surface_id": "store.sqlite",
            "state": "stable" if _exists(mem / "openclaw-mem.sqlite") else "shadow",
            "configured": True,
            "writing": auto_capture_enabled,
            "durable_truth_owner": True,
            "path_hint": "memory/openclaw-mem.sqlite",
        },
        {
            "plane": "Store",
            "surface_id": "store.lancedb",
            "state": "stable" if _exists(mem / "lancedb") else "shadow",
            "configured": True,
            "writing": False,
            "index_cache": True,
            "path_hint": "memory/lancedb",
        },
        {
            "plane": "Pack",
            "surface_id": "pack.context-pack",
            "state": "stable" if _exists(root / "openclaw_mem" / "context_pack_v1.py") else "shadow",
            "configured": True,
            "writing": False,
            "path_hint": "openclaw_mem/context_pack_v1.py",
        },
        {
            "plane": "Pack",
            "surface_id": "pack.goal",
            "state": "lab" if _exists(root / "openclaw_mem" / "goal_primitive.py") else "shadow",
            "configured": True,
            "writing": False,
            "path_hint": "openclaw_mem/goal_primitive.py",
        },
        {
            "plane": "Pack",
            "surface_id": "pack.route-auto",
            "state": "stable" if route_auto_enabled and route_auto_exists else ("degraded" if route_auto_enabled else "inert"),
            "configured": route_auto_enabled,
            "inert_reason": None if route_auto_enabled else "routeAuto disabled or not configured",
            "writing": False,
            "path_hint": "extensions/openclaw-mem-engine/routeAuto.js",
        },
        {
            "plane": "Pack",
            "surface_id": "pack.working-set",
            "state": "degraded" if working_set_enabled and not engine_index_exists else ("inert" if working_set_enabled and not auto_recall_enabled else ("lab" if working_set_enabled else "shadow")),
            "configured": working_set_enabled,
            "inert_reason": "autoRecall disabled" if working_set_enabled and not auto_recall_enabled else None,
            "writing": False,
            "path_hint": "extensions/openclaw-mem-engine/index.ts",
        },
        {
            "plane": "Observe",
            "surface_id": "observe.episodes",
            "state": "stable" if _exists(mem / "openclaw-mem-episodes.jsonl") else "shadow",
            "configured": auto_capture_enabled,
            "writing": auto_capture_enabled,
            "path_hint": "memory/openclaw-mem-episodes.jsonl",
        },
        {
            "plane": "Observe",
            "surface_id": "observe.docs-cold-lane",
            "state": "stable" if docs_cold_lane_enabled and docs_cold_lane_exists else ("degraded" if docs_cold_lane_enabled else "inert"),
            "configured": docs_cold_lane_enabled,
            "writing": False,
            "index_cache": True,
            "path_hint": "extensions/openclaw-mem-engine/docsColdLane.js",
        },
        {
            "plane": "Observe",
            "surface_id": "observe.symbolic-canvas",
            "state": "stable" if symbolic_canvas["enabled"] and symbolic_canvas_exists and symbolic_canvas["readiness"] == "ready" else ("inert" if not symbolic_canvas["enabled"] else "degraded"),
            "configured": symbolic_canvas["enabled"],
            "writing": symbolic_canvas["enabled"],
            "write_scope": "observe_receipts_only",
            "path_hint": "memory/symbolic-canvas-auto",
        },
        {
            "plane": "Review",
            "surface_id": "review.steward",
            "state": "stable" if _exists(root / "openclaw_mem" / "steward_review.py") else "shadow",
            "configured": True,
            "writing": False,
            "path_hint": "openclaw_mem/steward_review.py",
        },
        {
            "plane": "Review",
            "surface_id": "review.skill-curator",
            "state": "lab" if _exists(root / "openclaw_mem" / "self_curator.py") else "shadow",
            "configured": True,
            "writing": False,
            "path_hint": "openclaw_mem/self_curator.py",
        },
        {
            "plane": "Curate",
            "surface_id": "curate.dream-lite",
            "state": "lab",
            "configured": True,
            "writing": False,
            "path_hint": "openclaw-mem dream-lite",
        },
        {
            "plane": "Curate",
            "surface_id": "curate.skill-capture",
            "state": "lab" if _exists(root / "openclaw_mem" / "skill_capture.py") else "shadow",
            "configured": True,
            "writing": False,
            "path_hint": "openclaw_mem/skill_capture.py",
        },
        {
            "plane": "Curate",
            "surface_id": "curate.gbrain-mirror",
            "state": "lab" if gbrain_mirror_enabled and gbrain_mirror_exists else ("degraded" if gbrain_mirror_enabled else "inert"),
            "configured": gbrain_mirror_enabled,
            "writing": gbrain_mirror_enabled,
            "write_scope": "experimental_mirror",
            "path_hint": "gbrainMirror",
        },
    ]
    counts: dict[str, int] = {}
    for item in surfaces:
        key = str(item["state"])
        counts[key] = counts.get(key, 0) + 1
    sqlite_counts = _read_sqlite_counts(sqlite_db_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "writes_performed": False,
        "workspace_root": str(root),
        "state_root": str(state),
        "config_path": str(config_path),
        "config_loaded": bool(config),
        "db_path": str(sqlite_db_path),
        "memory_slot": memory_slot,
        "durable_truth_owner": {
            "surface_id": "store.sqlite",
            "path": str(sqlite_db_path),
            "role": "canonical_local_store",
        },
        "planes": ["Store", "Pack", "Observe", "Review", "Curate"],
        "surface_count": len(surfaces),
        "counts_by_state": counts,
        "surfaces": surfaces,
        "cli_availability": cli_availability,
        "symbolic_canvas": symbolic_canvas,
        "coverage": {
            "sqlite": sqlite_counts,
            "lancedb": {
                "path": str(mem / "lancedb"),
                "exists": (mem / "lancedb").exists(),
            },
            "qdrant_edge": {
                "path": str(mem / "qdrant-edge"),
                "exists": (mem / "qdrant-edge").exists(),
                "probed": False,
            },
        },
        "topology_changed": False,
        "checked_at": now_iso(),
    }


def render_status(status: Mapping[str, Any]) -> str:
    counts = status.get("counts_by_state") if isinstance(status.get("counts_by_state"), Mapping) else {}
    symbolic = status.get("symbolic_canvas") if isinstance(status.get("symbolic_canvas"), Mapping) else {}
    return (
        f"mem_system_status surfaces={status.get('surface_count')} "
        f"states={dict(counts)} symbolic_canvas={symbolic.get('readiness', 'unknown')} "
        f"writes_performed=false topology_changed=false"
    )
