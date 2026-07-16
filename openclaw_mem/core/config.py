"""Small, dependency-free-at-runtime configuration resolver.

Resolution order is deliberately explicit: environment, config.toml, then
built-in defaults.  The writer only fills absent supported keys and never
rewrites an existing value.
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


class ConfigError(ValueError):
    """Raised when the user config cannot be parsed or validated."""


_ENV_KEYS = {
    "db_path": "OPENCLAW_MEM_DB",
    "default_scope": "OPENCLAW_MEM_DEFAULT_SCOPE",
    "vector_backend": "OPENCLAW_MEM_VECTOR_BACKEND",
    "embed_provider": "OPENCLAW_MEM_EMBED_PROVIDER",
    "pack.budget_tokens": "OPENCLAW_MEM_PACK_BUDGET_TOKENS",
    "scoring.profile": "OPENCLAW_MEM_SCORING_PROFILE",
}


def _state_dir() -> Path:
    override = str(
        os.getenv("OPENCLAW_STATE_DIR")
        or os.getenv("CLAWDBOT_STATE_DIR")
        or ""
    ).strip()
    if override:
        return Path(override).expanduser().resolve()
    home_override = str(os.getenv("OPENCLAW_HOME") or "").strip()
    home = Path(home_override).expanduser() if home_override else Path.home()
    return home.resolve() / ".openclaw"


def built_in_defaults() -> Dict[str, Any]:
    return {
        "db_path": str(_state_dir() / "memory" / "openclaw-mem.sqlite"),
        "default_scope": "",
        "vector_backend": "auto",
        "embed_provider": "openai",
        "pack": {"budget_tokens": 1200},
        "scoring": {"profile": "relevance"},
    }


def default_config_path() -> Path:
    override = str(os.getenv("OPENCLAW_MEM_CONFIG") or "").strip()
    return (
        Path(override).expanduser()
        if override
        else Path.home() / ".openclaw-mem" / "config.toml"
    )


def _read(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"config root must be a TOML table: {path}")
    return value


def _nested_get(value: Mapping[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _nested_set(value: Dict[str, Any], dotted: str, item: Any) -> None:
    parts = dotted.split(".")
    current = value
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = item


def _coerce(dotted: str, value: Any, fallback: Any) -> Any:
    if dotted == "pack.budget_tokens":
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed > 0 else fallback
    if value is None:
        return fallback
    text = str(value).strip()
    if dotted == "vector_backend" and text not in {"auto", "python", "numpy", "sqlite-vec"}:
        return fallback
    if dotted == "embed_provider" and text not in {"openai", "local"}:
        return fallback
    return text


def resolve_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Resolve supported settings with env > TOML > built-in priority."""

    target = Path(path).expanduser() if path is not None else default_config_path()
    defaults = built_in_defaults()
    file_value = _read(target)
    resolved = deepcopy(defaults)
    for dotted, env_name in _ENV_KEYS.items():
        fallback = _nested_get(defaults, dotted)
        configured = _nested_get(file_value, dotted)
        if configured is not None:
            _nested_set(resolved, dotted, _coerce(dotted, configured, fallback))
        environment = os.getenv(env_name)
        if environment is not None and str(environment).strip():
            _nested_set(resolved, dotted, _coerce(dotted, environment, fallback))
    resolved["config_path"] = str(target)
    return resolved


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _insert_before_first_table(lines: list[str], additions: list[str]) -> None:
    index = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith("[")),
        len(lines),
    )
    block = additions + ([""] if additions and index < len(lines) else [])
    lines[index:index] = block


def _append_table_keys(lines: list[str], table: str, additions: list[str]) -> None:
    header = f"[{table}]"
    header_index = next(
        (i for i, line in enumerate(lines) if line.strip() == header),
        None,
    )
    if header_index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([header, *additions])
        return
    next_header = next(
        (
            i
            for i in range(header_index + 1, len(lines))
            if lines[i].lstrip().startswith("[")
        ),
        len(lines),
    )
    lines[next_header:next_header] = additions


def ensure_config(
    values: Mapping[str, Any], path: Path | str | None = None
) -> Dict[str, Any]:
    """Atomically create a config or fill only missing supported keys."""

    target = Path(path).expanduser() if path is not None else default_config_path()
    existing = _read(target)
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    added: list[str] = []

    top_additions: list[str] = []
    for key in ("db_path", "default_scope", "vector_backend", "embed_provider"):
        if key not in existing:
            top_additions.append(f"{key} = {_toml_value(values[key])}")
            added.append(key)
    _insert_before_first_table(lines, top_additions)

    for table, key in (("pack", "budget_tokens"), ("scoring", "profile")):
        table_value = existing.get(table)
        if table in existing and not isinstance(table_value, Mapping):
            raise ConfigError(f"config key {table!r} must be a TOML table: {target}")
        if not isinstance(table_value, Mapping) or key not in table_value:
            _append_table_keys(lines, table, [f"{key} = {_toml_value(values[table][key])}"])
            added.append(f"{table}.{key}")

    changed = bool(added)
    if changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(lines).rstrip() + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.replace(target)

    return {
        "path": str(target),
        "changed": changed,
        "added": added,
    }
